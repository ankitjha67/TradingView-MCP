"""
The two catalogue replications the novelty gate first rejected.

Both were renames on the first attempt — a Kelly fraction that reduced to a
mean-variance ratio (0.96 against the Sharpe tilt) and a 500-bar return fade
(0.97 against De Bondt-Thaler). These tests pin the mechanism that makes each
rewrite a different model, so a later "simplification" cannot fold them back.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from tradingview_mcp.core.quant.features import build_features
from tradingview_mcp.core.quant.library.mean_reversion import LongTermReversal
from tradingview_mcp.core.quant.library.replications import (
    KellyMultiOutcomeFraction, LongRunCommodityReversal)


def _features(close: np.ndarray):
    idx = pd.date_range("2015-01-01", periods=len(close), freq="D", tz="UTC")
    c = pd.Series(close, index=idx)
    return build_features(pd.DataFrame({
        "open": c.shift(1).fillna(c.iloc[0]), "high": c * 1.005,
        "low": c * 0.995, "close": c,
        "volume": pd.Series(5000.0, index=idx)}, index=idx), "1d", "TEST")


def test_the_worst_outcome_bounds_the_kelly_fraction():
    """
    Multi-outcome Kelly is bounded by ruin: with one -25% bar in the window no
    fraction above 4x survives, however good the mean and variance look. A
    mean-variance reading has no such bound — that is the difference between
    this model and the Sharpe tilt it was first mistaken for.
    """
    rng = np.random.default_rng(7)
    r = rng.normal(0.003, 0.01, 400)
    calm = _features(100 * np.cumprod(1 + r))
    crashed_r = r.copy()
    crashed_r[350] = -0.25
    crashed = _features(100 * np.cumprod(1 + crashed_r))

    m = KellyMultiOutcomeFraction()
    f_calm = m.diagnostics(calm)["kelly_fraction"]
    f_crash = m.diagnostics(crashed)["kelly_fraction"]
    assert f_calm >= 5.0, f_calm
    assert 0.0 < f_crash < 1 / 0.25, f_crash
    assert m.score(crashed).iloc[-1] < m.score(calm).iloc[-1]


def test_kelly_does_not_bet_when_no_fraction_grows_wealth():
    rng = np.random.default_rng(3)
    r = rng.normal(0.0, 0.02, 400)
    r -= r.mean()  # zero drift: log growth is negative at every non-zero fraction
    f = _features(100 * np.cumprod(1 + r))
    s = KellyMultiOutcomeFraction().score(f)
    assert abs(float(s.iloc[-1])) <= 0.2


def _excursion_then_turn() -> np.ndarray:
    """Flat base, a 300-bar doubling, then a 450-bar retreat that closes part of it."""
    rng = np.random.default_rng(11)
    base = 100 * np.cumprod(1 + rng.normal(0, 0.002, 750))
    rise = base[-1] * np.exp(np.linspace(0, np.log(2), 300))
    fall = rise[-1] * np.exp(np.linspace(0, np.log(0.7), 450))
    return np.concatenate([base, rise, fall])


def test_the_reversal_waits_for_the_turn():
    """
    At the top of the rise the price is far above its multi-year mean, but the
    past year is still extending the move: nothing to fade yet, so the score is
    zero. Once the past year is moving back toward the anchor, it fades.
    """
    f = _features(_excursion_then_turn())
    s = LongRunCommodityReversal().score(f)
    top = s.iloc[1000:1050]
    assert top.notna().all() and (top == 0).all(), top.describe()
    assert float(s.iloc[1300]) < -0.1, s.iloc[1300]


def test_the_reversal_is_not_the_de_bondt_thaler_fade():
    """Same top of the rise: the 3-5 year overreaction fade is already short."""
    f = _features(_excursion_then_turn())
    ours = LongRunCommodityReversal().score(f)
    theirs = LongTermReversal().score(f)
    assert float(theirs.iloc[1049]) < -0.5
    assert float(ours.iloc[1049]) == 0.0
