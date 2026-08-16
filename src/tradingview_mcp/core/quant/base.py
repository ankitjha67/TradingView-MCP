"""
Strategy contract.

Every model in the library implements one method::

    def score(self, f: FeatureSet) -> pd.Series   # continuous, -1.0 .. +1.0

The score is computed **vectorised over the whole frame**, not bar-by-bar. One
call yields both the live signal (last element) and the complete historical
signal path used by the backtester. That single change is what makes 200+ models
evaluable in seconds instead of minutes.

Sign convention: positive = long conviction, negative = short conviction,
0 = no opinion. Magnitude is conviction, not position size — sizing is the risk
layer's job (see ``core/quant/sizing.py``).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd

from .features import FeatureSet, build_features


class DataNeed(str, Enum):
    """
    What a model actually needs to be *honest*.

    This exists because the library previously claimed 200 working models while
    many of them silently degraded to a moving-average crossover when their real
    input was unavailable. A model that needs an options chain and does not have
    one is marked unavailable and excluded from the live consensus — it does not
    get to vote with a proxy and be counted as an independent opinion.
    """
    OHLC = "ohlc"                    # always available
    VOLUME = "volume"                # absent on many index/forex feeds
    CROSS_SECTION = "cross_section"  # needs a universe of symbols
    BENCHMARK = "benchmark"          # needs an index/market series
    FUNDAMENTALS = "fundamentals"
    OPTIONS_CHAIN = "options_chain"
    ORDER_BOOK = "order_book"        # L2 depth — not available from bar data
    ONCHAIN = "onchain"
    NEWS = "news"


class Regime(str, Enum):
    ANY = "any"
    TRENDING = "trending"
    RANGING = "ranging"
    HIGH_VOL = "high_vol"
    LOW_VOL = "low_vol"


class Horizon(str, Enum):
    INTRADAY = "intraday"
    SWING = "swing"
    POSITION = "position"


@dataclass(frozen=True)
class Signal:
    """A single model's opinion at a point in time, with its reasoning."""
    strategy: str
    category: str
    direction: str          # BUY | SELL | NEUTRAL
    score: float            # -1..+1 raw conviction
    strength: float         # 0..1 = |score|
    rationale: str
    diagnostics: dict = field(default_factory=dict)
    available: bool = True
    reason_unavailable: str = ""

    @property
    def is_actionable(self) -> bool:
        return self.available and self.direction != "NEUTRAL"

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy, "category": self.category,
            "direction": self.direction, "score": round(self.score, 4),
            "strength": round(self.strength, 4), "rationale": self.rationale,
            "diagnostics": {k: (round(v, 6) if isinstance(v, float) else v)
                            for k, v in self.diagnostics.items()},
            "available": self.available, "reason_unavailable": self.reason_unavailable,
        }


NEUTRAL_BAND = 0.15  # |score| below this is treated as no opinion


class BaseStrategy:
    """
    Base class for every quantitative model.

    Subclasses set the metadata attributes and implement ``score``. Metadata is
    not decoration: ``needs`` drives availability gating, ``family`` drives
    correlation-aware consensus weighting, and ``research`` is the provenance
    that makes a claim like "used by quant funds" checkable rather than asserted.
    """

    # ── identity ──────────────────────────────────────────────────────────────
    name: str = "BaseStrategy"
    category: str = "General"
    family: str = "generic"        # models sharing a family are near-duplicates
    description: str = ""
    research: str = ""             # citation: author(s), year, title

    # ── requirements & suitability ────────────────────────────────────────────
    needs: Sequence[DataNeed] = (DataNeed.OHLC,)
    min_bars: int = 60
    regimes: Sequence[Regime] = (Regime.ANY,)
    horizon: Horizon = Horizon.SWING
    params: dict = {}

    # ── proxy honesty ─────────────────────────────────────────────────────────
    # True when the implementation approximates the published method using only
    # single-series bar data (e.g. modelling order-flow imbalance from bar
    # volume). Proxies are labelled everywhere they surface and are down-weighted
    # in consensus. They are NOT presented as the original method.
    is_proxy: bool = False
    proxy_note: str = ""

    def __init__(self, **overrides):
        if overrides:
            self.params = {**self.params, **overrides}

    # ── the one method subclasses implement ───────────────────────────────────
    def score(self, f: FeatureSet) -> pd.Series:
        raise NotImplementedError(f"{self.name} does not implement score()")

    # ── availability ──────────────────────────────────────────────────────────
    def availability(self, f: FeatureSet) -> tuple[bool, str]:
        """Can this model run honestly on the data we actually have?"""
        if f.n < self.min_bars:
            return False, f"needs {self.min_bars} bars, have {f.n}"
        if DataNeed.VOLUME in self.needs and not f.has_volume:
            return False, "feed has no usable volume"
        unmet = [n.value for n in self.needs
                 if n in (DataNeed.CROSS_SECTION, DataNeed.FUNDAMENTALS,
                          DataNeed.OPTIONS_CHAIN, DataNeed.ORDER_BOOK,
                          DataNeed.ONCHAIN, DataNeed.NEWS, DataNeed.BENCHMARK)
                 and n.value not in f.meta.get("available_feeds", ())]
        if unmet:
            return False, f"missing feed(s): {', '.join(unmet)}"
        return True, ""

    # ── derived outputs ───────────────────────────────────────────────────────
    def score_series(self, f: FeatureSet) -> pd.Series:
        """Sanitised score path: finite, clipped to [-1, 1], NaN where undefined."""
        s = self.score(f)
        if not isinstance(s, pd.Series):
            s = pd.Series(s, index=f.close.index)
        return s.replace([np.inf, -np.inf], np.nan).clip(-1.0, 1.0).reindex(f.close.index)

    def direction_series(self, f: FeatureSet, band: float = NEUTRAL_BAND) -> pd.Series:
        s = self.score_series(f)
        return pd.Series(
            np.where(s >= band, "BUY", np.where(s <= -band, "SELL", "NEUTRAL")),
            index=s.index,
        ).where(s.notna(), "NEUTRAL")

    def analyze(self, data, interval: str = "1d", symbol: str = "") -> Signal:
        """Full-depth read on the most recent bar."""
        f = data if isinstance(data, FeatureSet) else build_features(data, interval, symbol)

        ok, why = self.availability(f)
        if not ok:
            return Signal(self.name, self.category, "NEUTRAL", 0.0, 0.0,
                          f"Not evaluated: {why}.", {}, False, why)
        try:
            s = self.score_series(f)
        except Exception as exc:  # a broken model must not take down the scan
            return Signal(self.name, self.category, "NEUTRAL", 0.0, 0.0,
                          f"Model error: {exc}", {}, False, f"error: {exc}")

        last = s.iloc[-1] if len(s) else np.nan
        if not np.isfinite(last):
            return Signal(self.name, self.category, "NEUTRAL", 0.0, 0.0,
                          "Insufficient warm-up for a defined reading.", {}, False,
                          "score undefined on latest bar")

        val = float(last)
        direction = "BUY" if val >= NEUTRAL_BAND else "SELL" if val <= -NEUTRAL_BAND else "NEUTRAL"
        diag = self.diagnostics(f)
        return Signal(self.name, self.category, direction, val, abs(val),
                      self.explain(f, val, diag), diag)

    # ── overridable depth hooks ───────────────────────────────────────────────
    def diagnostics(self, f: FeatureSet) -> dict:
        """Named intermediate values that justify the score. Override for depth."""
        return {}

    def explain(self, f: FeatureSet, value: float, diag: dict) -> str:
        """Plain-language reason for the current reading. Override for depth."""
        stance = "long" if value >= NEUTRAL_BAND else "short" if value <= -NEUTRAL_BAND else "flat"
        bits = ", ".join(f"{k}={v:.4g}" if isinstance(v, (int, float)) else f"{k}={v}"
                         for k, v in list(diag.items())[:4])
        base = f"{self.name}: {stance} at conviction {abs(value):.2f}"
        return f"{base} ({bits})." if bits else f"{base}."

    # ── backward compatibility ────────────────────────────────────────────────
    def evaluate(self, df) -> str:
        """Legacy contract kept so older callers keep working."""
        try:
            return self.analyze(df).direction
        except Exception:
            return "NEUTRAL"

    # ── introspection ─────────────────────────────────────────────────────────
    @classmethod
    def spec(cls) -> dict:
        return {
            "name": cls.name, "category": cls.category, "family": cls.family,
            "description": cls.description, "research": cls.research,
            "needs": [n.value for n in cls.needs], "min_bars": cls.min_bars,
            "regimes": [r.value for r in cls.regimes], "horizon": cls.horizon.value,
            "params": dict(cls.params), "is_proxy": cls.is_proxy,
            "proxy_note": cls.proxy_note,
        }

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name!r} [{self.category}]>"


# ── helpers shared by strategy implementations ────────────────────────────────

def squash(x, scale: float = 1.0) -> pd.Series:
    """
    Map an unbounded statistic to (-1, 1) with tanh.

    Preferred over hard thresholds: it keeps conviction proportional to evidence,
    so a 4-sigma dislocation outranks a 2-sigma one instead of both emitting an
    identical "BUY". ``scale`` is the value that maps to ~0.76.
    """
    if isinstance(x, pd.Series):
        return np.tanh(x.astype(float) / scale)
    return float(np.tanh(float(x) / scale))


def band_score(x: pd.Series, lo: float, hi: float) -> pd.Series:
    """Linearly map [lo, hi] onto [-1, +1], clipped outside."""
    return (2 * (x - lo) / (hi - lo) - 1).clip(-1, 1)


def crossover(a: pd.Series, b: pd.Series) -> pd.Series:
    """+1 where a crosses above b, -1 where it crosses below, else 0."""
    diff = np.sign(a - b)
    return diff.diff().fillna(0).clip(-1, 1) * (diff.abs() > 0)


def persist(sig: pd.Series, bars: int) -> pd.Series:
    """Hold a sparse event signal for ``bars`` bars so it is tradeable."""
    return sig.replace(0, np.nan).ffill(limit=max(1, bars)).fillna(0)
