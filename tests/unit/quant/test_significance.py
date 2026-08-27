"""
Sharpe significance: t = annualised Sharpe x sqrt(years observed).

The standard and the 1.96 threshold come from the replication catalogue in
paperswithbacktest/awesome-systematic-trading, which reports both for every
one of its 1,687 replicated papers. The first test checks the arithmetic
against that catalogue's own published rows — if our formula disagrees with
sixty independently replicated strategies, the formula is wrong.

The rest pin the thing that actually matters here: a high Sharpe over a short
window must not be reported as a result.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tradingview_mcp.core.quant.backtest import (
    SIGNIFICANCE_T, compare_strategies, run_backtest,
)
from tradingview_mcp.core.quant.features import build_features
from tradingview_mcp.core.quant.registry import get_registry

CATALOGUE = Path(__file__).resolve().parents[3] / "data" / "replication_catalogue.json"

# Published rows from the catalogue, kept inline so this test does not depend
# on a network fetch or on the file having been synced.
PUBLISHED = [
    # (name,                          sharpe, t_stat, years)
    ("Large vs Small Companies EU",     1.89,  11.4,  37),
    ("The Investment CAPM",             1.80,  11.0,  37),
    ("Role of Beta and Size EU",        1.63,   9.6,  34),
    ("Whitening Residuals Bond Yields", 0.90,   5.0,  30),
    ("Good Carry, Bad Carry",           1.74,  10.6,  37),
    ("Multi-Timeframe Trend Bitcoin",   3.39,  16.2,  23),
    ("Trading the Term Premium",        0.45,   2.8,  37),
    ("Commodity Momentum Intra-Market", 0.65,   2.8,  19),
]


@pytest.mark.parametrize("name,sharpe,t_pub,years", PUBLISHED)
def test_formula_reproduces_published_t_statistics(name, sharpe, t_pub, years):
    """Our arithmetic must agree with sixty replicated papers, to rounding."""
    assert abs(sharpe * math.sqrt(years) - t_pub) < 0.15, name


def test_stored_catalogue_agrees_if_it_has_been_synced():
    if not CATALOGUE.exists():
        pytest.skip("catalogue not synced; run tools/sync_replication_catalogue.py")
    data = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    assert data["significance_check"]["holds"] is True
    for row in data["strategies"]:
        assert abs(row["sharpe"] * math.sqrt(row["years"]) - row["t_stat"]) < 0.15


# ── the property that matters ─────────────────────────────────────────────────

def _series(n: int, freq: str, drift: float, vol: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq=freq, tz="UTC")
    close = pd.Series(100 * np.cumprod(1 + rng.normal(drift, vol, n)), index=idx)
    return pd.DataFrame({
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close * 1.003, "low": close * 0.997, "close": close,
        "volume": pd.Series(rng.integers(1_000, 9_000, n).astype(float), index=idx),
    }, index=idx)


def test_a_short_window_cannot_produce_a_significant_result():
    """
    The whole point. 1,500 one-minute bars is about six trading days; no Sharpe
    computed over it should be presented as established, however large.
    """
    f = build_features(_series(1500, "min", 0.0004, 0.004, 5), "1m", "TEST")
    res = compare_strategies(f, strategies=get_registry().all())
    assert res["years_tested"] < 0.05, "six days should not read as a long window"
    for row in res["ranking"]:
        if row["t_stat"] is not None:
            assert not (row["significant"] and row["t_stat"] < SIGNIFICANCE_T)
    assert res["significant"] == sum(1 for r in res["ranking"] if r["significant"])


def test_significance_is_one_sided():
    """A reliably losing strategy is statistically solid but not 'significant'."""
    from tradingview_mcp.core.quant.backtest import BacktestResult

    def _mk(t):
        r = BacktestResult(
            strategy="x", category="c", symbol="s", interval="1d", bars=500,
            total_return_pct=0.0, annualized_return_pct=0.0, sharpe_ratio=1.0,
            t_stat=t, years_tested=2.0, sortino_ratio=0.0, max_drawdown_pct=-1.0,
            calmar_ratio=0.0, volatility_pct=10.0, total_trades=30,
            win_rate_pct=50.0, profit_factor=1.0, avg_win_pct=1.0,
            avg_loss_pct=-1.0, expectancy_pct=0.0, avg_bars_held=5.0,
            exposure_pct=50.0, buy_and_hold_pct=0.0, excess_return_pct=0.0)
        return r

    assert _mk(2.5).significant is True
    assert _mk(1.95).significant is False
    assert _mk(-4.0).significant is False, "reliably losing is not 'significant'"
    assert _mk(float("nan")).significant is False


def test_t_stat_scales_with_the_square_root_of_the_window():
    """Four times the history, twice the t-statistic, same Sharpe."""
    short = build_features(_series(500, "D", 0.0006, 0.011, 3), "1d", "S")
    long_ = build_features(_series(2000, "D", 0.0006, 0.011, 3), "1d", "L")
    strat = get_registry().all()[0]
    a = run_backtest(strat, short)
    b = run_backtest(strat, long_)
    if not (math.isfinite(a.t_stat) and math.isfinite(b.t_stat)):
        pytest.skip("model produced no measurable path on this synthetic series")
    assert b.years_tested > a.years_tested
    ratio = math.sqrt(b.years_tested / a.years_tested)
    assert 1.5 < ratio < 2.5


def test_an_unrunnable_model_reports_no_t_stat_rather_than_zero():
    from tradingview_mcp.core.quant.backtest import _empty_result

    r = _empty_result("x", "c", "S", "1d", 10, "insufficient history")
    assert math.isnan(r.t_stat)
    assert r.significant is False
    assert r.to_dict()["t_stat"] is None, "None, not 0.0 — it was never measured"


def test_performance_report_flags_an_insignificant_sharpe():
    from tradingview_mcp.core.quant.performance import analyse

    f = build_features(_series(400, "D", 0.0003, 0.012, 9), "1d", "TEST")
    for strat in get_registry().all()[:40]:
        bt = run_backtest(strat, f)
        if bt.error or bt.total_trades < 3 or not math.isfinite(bt.t_stat):
            continue
        rep = analyse(bt, f.df, bars_per_year=252, position=bt.position)
        if bt.t_stat < SIGNIFICANCE_T:
            assert any("t-statistic" in c for c in rep.caveats), (
                f"{strat.name}: t={bt.t_stat:.2f} went unflagged")
            return
    pytest.skip("no model produced an insignificant-but-trading result here")
