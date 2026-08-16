"""
Consensus engine.

The central question: given N model opinions, what is the aggregate view?

The naive answer — count BUYs, count SELLs, take the bigger number — is wrong in
a way that matters. It treats 30 variants of a moving-average crossover as 30
independent opinions when they are one opinion repeated 30 times. Under that
scheme, whichever style happens to be most numerous in the library wins every
vote, and adding models makes the bias worse rather than better.

This engine corrects for that with three mechanisms:

1. **Family weighting.** Models sharing a ``family`` split one family's worth of
   vote between them, so a crowded family cannot dominate by headcount.
2. **Category balancing.** Family weights are then normalised within each
   category, so the library's shape does not determine the answer.
3. **Proxy discounting.** Models approximating their published method from
   substituted data are explicitly down-weighted.

Unavailable models contribute nothing and are reported separately, so a reading
of "42 of 264 models" is never presented as "264 models agree".
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional, Sequence

import numpy as np
import pandas as pd

from .base import NEUTRAL_BAND, BaseStrategy, DataNeed, Regime, Signal
from .features import FeatureSet, build_features
from .registry import StrategyRegistry, get_registry

# A proxy contributes this fraction of a full vote.
PROXY_WEIGHT = 0.4
# Conviction below this is treated as no opinion for vote-counting purposes.
VOTE_BAND = NEUTRAL_BAND


@dataclass
class CategoryView:
    category: str
    score: float
    buy: int
    sell: int
    neutral: int
    available: int
    total: int

    def to_dict(self) -> dict:
        return {"category": self.category, "score": round(self.score, 4),
                "buy": self.buy, "sell": self.sell, "neutral": self.neutral,
                "available": self.available, "total": self.total}


@dataclass
class ConsensusResult:
    """Aggregate view plus everything needed to audit how it was reached."""
    symbol: str
    interval: str
    as_of: datetime
    direction: str                  # BUY | SELL | NEUTRAL
    score: float                    # -1..+1 weighted consensus
    confidence: float               # 0..1 — agreement-adjusted conviction
    agreement: float                # 0..1 — share of weight on the winning side
    price: float

    models_total: int
    models_available: int
    models_voting: int
    buy_votes: int
    sell_votes: int
    neutral_votes: int

    categories: list[CategoryView] = field(default_factory=list)
    top_long: list[Signal] = field(default_factory=list)
    top_short: list[Signal] = field(default_factory=list)
    unavailable_reasons: dict[str, int] = field(default_factory=dict)
    regime: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "interval": self.interval,
            "as_of": self.as_of.isoformat(), "direction": self.direction,
            "score": round(self.score, 4), "confidence": round(self.confidence, 4),
            "agreement": round(self.agreement, 4), "price": self.price,
            "models": {"total": self.models_total, "available": self.models_available,
                       "voting": self.models_voting, "buy": self.buy_votes,
                       "sell": self.sell_votes, "neutral": self.neutral_votes},
            "categories": [c.to_dict() for c in self.categories],
            "top_long": [s.to_dict() for s in self.top_long],
            "top_short": [s.to_dict() for s in self.top_short],
            "unavailable_reasons": self.unavailable_reasons,
            "regime": self.regime, "warnings": self.warnings,
        }

    def summary_line(self) -> str:
        return (f"{self.direction} on {self.symbol} ({self.interval}) — "
                f"score {self.score:+.2f}, confidence {self.confidence:.0%}, "
                f"{self.models_voting} of {self.models_available} available models voting "
                f"({self.buy_votes} long / {self.sell_votes} short)")


def _regime_fit(strategy: BaseStrategy, f: FeatureSet) -> float:
    """
    How well the current regime suits this model. 1.0 = designed for it,
    0.5 = neutral/any, lower = designed for the opposite conditions.
    """
    regimes = {r.value for r in strategy.regimes}
    if "any" in regimes or not regimes:
        return 1.0
    try:
        trend = float(f.trend_strength.iloc[-1])
        vol = float(f.vol_regime.iloc[-1])
    except Exception:
        return 1.0
    if not (math.isfinite(trend) and math.isfinite(vol)):
        return 1.0

    fit = []
    if "trending" in regimes:
        fit.append(0.4 + 1.2 * trend)
    if "ranging" in regimes:
        fit.append(0.4 + 1.2 * (1 - trend))
    if "high_vol" in regimes:
        fit.append(0.4 + 1.2 * vol)
    if "low_vol" in regimes:
        fit.append(0.4 + 1.2 * (1 - vol))
    return float(np.clip(np.mean(fit), 0.15, 1.5)) if fit else 1.0


def _build_weights(signals: list[tuple[BaseStrategy, Signal]], f: FeatureSet) -> dict[str, float]:
    """
    Weight each voting model.

    Weight = (1 / family size) × regime fit × proxy discount, then normalised so
    every category contributes equally regardless of how many models it holds.
    """
    by_family: dict[str, list[str]] = defaultdict(list)
    for strat, _ in signals:
        by_family[strat.family].append(strat.name)

    raw: dict[str, float] = {}
    for strat, _ in signals:
        family_size = len(by_family[strat.family])
        w = 1.0 / family_size                      # a family gets one vote, shared
        w *= _regime_fit(strat, f)                 # suited models count for more
        if strat.is_proxy:
            w *= PROXY_WEIGHT                      # approximations count for less
        raw[strat.name] = w

    # Normalise within category so library composition does not drive the answer.
    by_cat: dict[str, float] = defaultdict(float)
    cat_of: dict[str, str] = {}
    for strat, _ in signals:
        by_cat[strat.category] += raw[strat.name]
        cat_of[strat.name] = strat.category

    n_cats = len(by_cat) or 1
    return {
        name: (w / by_cat[cat_of[name]] / n_cats) if by_cat[cat_of[name]] > 0 else 0.0
        for name, w in raw.items()
    }


def evaluate_all(
    data,
    interval: str = "1d",
    symbol: str = "",
    registry: Optional[StrategyRegistry] = None,
    strategies: Optional[Sequence[BaseStrategy]] = None,
    available_feeds: Iterable[str] = (),
    meta: Optional[dict] = None,
) -> tuple[FeatureSet, list[tuple[BaseStrategy, Signal]]]:
    """Run every model once over a shared FeatureSet and return all signals."""
    if isinstance(data, FeatureSet):
        f = data
    else:
        f = build_features(data, interval, symbol)
    f.meta.update(meta or {})
    f.meta["available_feeds"] = tuple(available_feeds)

    reg = registry or get_registry()
    models = list(strategies) if strategies is not None else reg.all()
    return f, [(m, m.analyze(f)) for m in models]


def compute_consensus(
    data,
    interval: str = "1d",
    symbol: str = "",
    registry: Optional[StrategyRegistry] = None,
    strategies: Optional[Sequence[BaseStrategy]] = None,
    available_feeds: Iterable[str] = (),
    meta: Optional[dict] = None,
    top_n: int = 8,
) -> ConsensusResult:
    """Aggregate every model's opinion into one auditable view."""
    f, all_signals = evaluate_all(data, interval, symbol, registry, strategies,
                                  available_feeds, meta)

    available = [(s, sig) for s, sig in all_signals if sig.available]
    voting = [(s, sig) for s, sig in available if abs(sig.score) >= VOTE_BAND]

    reasons: dict[str, int] = defaultdict(int)
    for _, sig in all_signals:
        if not sig.available:
            # Collapse to a reason class so the report is readable.
            r = sig.reason_unavailable
            key = ("insufficient history" if "bars" in r else
                   "missing data feed" if "feed" in r else
                   "model error" if "error" in r else
                   "no defined reading" if "undefined" in r else r or "unknown")
            reasons[key] += 1

    price = float(f.close.iloc[-1]) if f.n else float("nan")
    as_of = f.df.index[-1].to_pydatetime() if isinstance(f.df.index, pd.DatetimeIndex) \
        else datetime.now(timezone.utc)

    warnings: list[str] = []
    if not voting:
        warnings.append("No model produced an actionable reading on this bar.")
        return ConsensusResult(
            symbol=symbol or f.symbol, interval=interval, as_of=as_of,
            direction="NEUTRAL", score=0.0, confidence=0.0, agreement=0.0, price=price,
            models_total=len(all_signals), models_available=len(available),
            models_voting=0, buy_votes=0, sell_votes=0,
            neutral_votes=len(available), unavailable_reasons=dict(reasons),
            regime=_regime_snapshot(f), warnings=warnings)

    weights = _build_weights(voting, f)
    total_w = sum(weights.values()) or 1.0
    score = sum(sig.score * weights[s.name] for s, sig in voting) / total_w

    long_w = sum(weights[s.name] for s, sig in voting if sig.score > 0)
    short_w = sum(weights[s.name] for s, sig in voting if sig.score < 0)
    winning_w = max(long_w, short_w)
    agreement = winning_w / total_w if total_w > 0 else 0.0

    direction = "BUY" if score >= VOTE_BAND else "SELL" if score <= -VOTE_BAND else "NEUTRAL"

    # Confidence blends conviction, agreement and breadth. A strong score from
    # three models is not the same as a strong score from eighty.
    breadth = min(1.0, len(voting) / 40.0)
    confidence = float(np.clip(abs(score) * 0.45 + agreement * 0.35 + breadth * 0.20, 0, 1))
    if direction == "NEUTRAL":
        confidence *= 0.5

    if agreement < 0.6:
        warnings.append(f"Models are split — only {agreement:.0%} of weight on the leading side.")
    if len(available) < len(all_signals) * 0.5:
        warnings.append(f"Only {len(available)} of {len(all_signals)} models could run on this data.")

    # Category rollup.
    cat_rows: list[CategoryView] = []
    cat_all: dict[str, list] = defaultdict(list)
    for s, sig in all_signals:
        cat_all[s.category].append((s, sig))
    for cat, rows in sorted(cat_all.items()):
        avail = [sg for _, sg in rows if sg.available]
        votes = [sg for sg in avail if abs(sg.score) >= VOTE_BAND]
        cat_score = float(np.mean([sg.score for sg in votes])) if votes else 0.0
        cat_rows.append(CategoryView(
            category=cat, score=cat_score,
            buy=sum(1 for sg in votes if sg.score > 0),
            sell=sum(1 for sg in votes if sg.score < 0),
            neutral=len(avail) - len(votes),
            available=len(avail), total=len(rows)))

    ranked = sorted(voting, key=lambda x: x[1].score, reverse=True)
    top_long = [sig for _, sig in ranked if sig.score > 0][:top_n]
    top_short = [sig for _, sig in reversed(ranked) if sig.score < 0][:top_n]

    return ConsensusResult(
        symbol=symbol or f.symbol, interval=interval, as_of=as_of,
        direction=direction, score=float(score), confidence=confidence,
        agreement=float(agreement), price=price,
        models_total=len(all_signals), models_available=len(available),
        models_voting=len(voting),
        buy_votes=sum(1 for _, sg in voting if sg.score > 0),
        sell_votes=sum(1 for _, sg in voting if sg.score < 0),
        neutral_votes=len(available) - len(voting),
        categories=cat_rows, top_long=top_long, top_short=top_short,
        unavailable_reasons=dict(reasons), regime=_regime_snapshot(f), warnings=warnings)


def _regime_snapshot(f: FeatureSet) -> dict:
    """Current market state, in the terms the models are gated on."""
    def _last(series, default=float("nan")):
        try:
            v = float(series.iloc[-1])
            return v if math.isfinite(v) else default
        except Exception:
            return default

    trend = _last(f.trend_strength)
    vol_pct = _last(f.vol_regime)
    adx, _, _ = f.adx(14)
    return {
        "trend_strength": trend,
        "vol_percentile": vol_pct,
        "adx": _last(adx),
        "realized_vol_pct": _last(f.realized_vol(20)) * 100,
        "atr": _last(f.atr(14)),
        "natr_pct": _last(f.natr(14)) * 100,
        "hurst": _last(f.hurst(100)),
        "efficiency_ratio": _last(f.efficiency_ratio(20)),
        "drawdown_pct": _last(f.drawdown()) * 100,
        "label": _regime_label(trend, vol_pct),
    }


def _regime_label(trend: float, vol: float) -> str:
    if not (math.isfinite(trend) and math.isfinite(vol)):
        return "indeterminate"
    t = "trending" if trend > 0.5 else "range-bound"
    v = "high volatility" if vol > 0.7 else "low volatility" if vol < 0.3 else "normal volatility"
    return f"{t}, {v}"


# ── risk levels ───────────────────────────────────────────────────────────────

@dataclass
class RiskLevels:
    """ATR-derived entry, stop and target — the levels a desk would actually use."""
    entry: float
    stop_loss: float
    take_profit: float
    atr: float
    risk_per_unit: float
    reward_per_unit: float
    risk_reward: float
    direction: str

    def to_dict(self) -> dict:
        return {k: (round(v, 6) if isinstance(v, float) else v)
                for k, v in self.__dict__.items()}


def compute_risk_levels(f: FeatureSet, direction: str, sl_atr: float = 1.5,
                        tp_atr: float = 3.0) -> RiskLevels:
    """
    Volatility-scaled stop and target.

    ATR rather than a fixed percentage: a 2% stop is loose on a calm index and
    inside the noise on a volatile altcoin. If ATR is unavailable, falls back to
    1% of price rather than returning a nonsensical zero-width stop.
    """
    price = float(f.close.iloc[-1])
    atr = float(f.atr(14).iloc[-1])
    if not math.isfinite(atr) or atr <= 0:
        atr = price * 0.01

    if direction == "SELL":
        sl, tp = price + sl_atr * atr, price - tp_atr * atr
    else:
        sl, tp = price - sl_atr * atr, price + tp_atr * atr

    risk = abs(price - sl)
    reward = abs(tp - price)
    return RiskLevels(
        entry=price, stop_loss=sl, take_profit=tp, atr=atr,
        risk_per_unit=risk, reward_per_unit=reward,
        risk_reward=reward / risk if risk > 0 else float("nan"),
        direction=direction if direction != "NEUTRAL" else "BUY (hypothetical)",
    )
