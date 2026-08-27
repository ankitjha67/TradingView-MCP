"""
Admission tests for anything joining the strategy library.

The library began as 200 claimed models, most of them template clones that
degraded to a moving-average crossover when their real input was missing. These
checks exist so that cannot recur — especially for candidates drafted from a
paper, which are fluent, plausible and entirely unverified.

The causality check is the one nothing in this codebase had. It caught two real
look-aheads in the shipped library: both GARCH models anchored their recursion
on np.nanvar over the whole sample, so appending a bar revised 825 of 835
earlier readings.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingview_mcp.core.quant.base import BaseStrategy, DataNeed, Horizon
from tradingview_mcp.core.quant.candidate import (
    admit, check_causal, check_contract, check_non_degenerate,
)
from tradingview_mcp.core.quant.features import build_features


@pytest.fixture(scope="module")
def frame():
    rng = np.random.default_rng(31)
    n = 800
    idx = pd.date_range("2022-01-01", periods=n, freq="D", tz="UTC")
    close = pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.015, n)), index=idx)
    return build_features(pd.DataFrame({
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close * 1.01, "low": close * 0.99, "close": close,
        "volume": pd.Series(rng.integers(1_000, 9_000, n).astype(float), index=idx),
    }, index=idx), "1d", "TEST")


class _Good(BaseStrategy):
    name = "Good"; category = "T"; family = "t"; research = "-"
    description = "-"; horizon = Horizon.SWING; min_bars = 60

    def score(self, f):
        return (f.close.pct_change(20) * 5).clip(-1, 1).fillna(0.0)


class _LooksAhead(BaseStrategy):
    """Normalises over the whole sample — the classic silent look-ahead."""
    name = "LooksAhead"; category = "T"; family = "t"; research = "-"
    description = "-"; horizon = Horizon.SWING; min_bars = 60

    def score(self, f):
        r = f.close.pct_change().fillna(0.0)
        return (r / (r.std() or 1.0) / 10).clip(-1, 1)


class _Centred(BaseStrategy):
    """
    A wide centred window reads well into the future.

    Kept wide on purpose: a narrow centred window diverges only within a few
    bars of the truncation join, which the edge guard excludes. The probe is a
    strong filter for global leakage, not a proof against every local form.
    """
    name = "Centred"; category = "T"; family = "t"; research = "-"
    description = "-"; horizon = Horizon.SWING; min_bars = 20

    def score(self, f):
        m = f.close.rolling(151, center=True, min_periods=5).mean()
        return ((f.close / m - 1) * 10).clip(-1, 1).fillna(0.0)


class _AlwaysLong(BaseStrategy):
    name = "AlwaysLong"; category = "T"; family = "t"; research = "-"
    description = "-"; horizon = Horizon.SWING; min_bars = 60

    def score(self, f):
        return pd.Series(0.8, index=f.close.index)


class _OutOfRange(BaseStrategy):
    name = "OutOfRange"; category = "T"; family = "t"; research = "-"
    description = "-"; horizon = Horizon.SWING; min_bars = 60

    def score(self, f):
        return pd.Series(4.2, index=f.close.index)


def test_a_sound_model_is_admitted(frame):
    """
    Soundness is judged in isolation, so the comparison pool is empty here.
    Against the real library this same model is correctly rejected — a 20-bar
    momentum rule is a duplicate of several things already present, which is
    what test_a_duplicate_is_rejected covers.
    """
    assert admit(_Good(), frame, against=[]).admitted


def test_a_duplicate_is_rejected(frame):
    """
    The check the other five cannot make. A duplicate is causal, in-contract,
    non-degenerate and well behaved — it is simply the same signal already
    present, and admitting it doubles that family's weight.
    """
    from tradingview_mcp.core.quant.candidate import check_novel

    class _Twin(_Good):
        name = "Twin"

    r = check_novel(_Twin(), frame, against=[_Good()])
    assert not r.passed and r.fatal
    assert "same signal" in r.detail


def test_a_distinctive_model_passes_novelty(frame):
    from tradingview_mcp.core.quant.candidate import check_novel

    class _Other(_Good):
        name = "Other"
        def score(self, f):
            return (f.rsi(14) / 100 - 0.5).clip(-1, 1).fillna(0.0) * 2

    assert check_novel(_Other(), frame, against=[_Good()]).passed


def test_full_sample_normalisation_is_caught(frame):
    r = check_causal(_LooksAhead(), frame)
    assert not r.passed and r.fatal
    assert "would not have had" in r.detail


def test_a_centred_window_is_caught(frame):
    assert not check_causal(_Centred(), frame).passed


def test_a_causal_model_passes(frame):
    assert check_causal(_Good(), frame).passed


def test_a_constant_non_zero_score_is_rejected(frame):
    """Voting the same way whatever the data is the template-clone failure."""
    r = check_non_degenerate(_AlwaysLong(), frame)
    assert not r.passed and r.fatal
    assert "whatever the data" in r.detail


def test_a_flat_zero_is_an_abstention_not_a_failure(frame):
    class _Silent(_Good):
        name = "Silent"
        def score(self, f):
            return pd.Series(0.0, index=f.close.index)
    r = check_non_degenerate(_Silent(), frame)
    assert r.passed, "abstaining is honest; it is counted available but not voting"


def test_a_binary_signal_is_not_degenerate(frame):
    """Parabolic SAR is long or short and nothing between."""
    class _Binary(_Good):
        name = "Binary"
        def score(self, f):
            return pd.Series(np.where(f.close > f.close.shift(1), 0.8, -0.8),
                             index=f.close.index)
    assert check_non_degenerate(_Binary(), frame).passed


def test_a_score_outside_the_band_is_rejected(frame):
    r = check_contract(_OutOfRange(), frame)
    assert not r.passed
    assert "4.2" in r.detail or "outside" in r.detail


def test_the_shipped_library_is_causal(frame):
    """
    A regression guard on the whole library. Both GARCH models failed this
    before their long-run variance was made expanding.
    """
    from tradingview_mcp.core.quant.registry import get_registry

    offenders = []
    for m in get_registry().all():
        if not m.availability(frame)[0]:
            continue
        r = check_causal(m, frame)
        if not r.passed and r.fatal:
            offenders.append(f"{m.name}: {r.detail[:70]}")
    assert not offenders, "look-ahead in the library:\n" + "\n".join(offenders)
