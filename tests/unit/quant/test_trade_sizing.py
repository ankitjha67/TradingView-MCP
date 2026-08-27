"""
Trade P&L must respect the size the position was actually held at.

Positions are scaled by conviction by default, so a model carrying 0.3 units
earns 0.3x the price move. _extract_trades used to book every trade at full
size — it took only sign(position) — while the equity curve scaled properly.
The two then described different simulations, and the performance report's
headline could come out with the opposite sign to the ranking's return.

Observed on SOL-USD daily: Realized Volatility Cone reported net profit of
-53.64% for a strategy whose equity curve had grown +93.12%.

Exact reconciliation is not expected and is not asserted: a strategy flat for
79% of bars pays transition costs in the equity curve that belong to no trade
span, so the trade list covers only part of the path.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradingview_mcp.core.quant.backtest import run_backtest
from tradingview_mcp.core.quant.features import build_features
from tradingview_mcp.core.quant.performance import analyse
from tradingview_mcp.core.quant.registry import get_registry


@pytest.fixture(scope="module")
def frame():
    rng = np.random.default_rng(23)
    n = 900
    idx = pd.date_range("2023-01-01", periods=n, freq="D", tz="UTC")
    close = pd.Series(100 * np.cumprod(1 + rng.normal(0.0008, 0.03, n)), index=idx)
    return build_features(pd.DataFrame({
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close * 1.02, "low": close * 0.98, "close": close,
        "volume": pd.Series(rng.integers(1_000, 9_000, n).astype(float), index=idx),
    }, index=idx), "1d", "TEST")


def _traded(frame, limit=45):
    for strat in get_registry().all()[:limit]:
        bt = run_backtest(strat, frame, allow_short=True)
        if not bt.error and bt.total_trades >= 5 and len(bt.trades):
            yield strat, bt


def test_trades_are_not_booked_at_full_size(frame):
    """
    The regression, stated directly.

    The old code priced every trade as (exit/entry - 1) * sign(position),
    discarding the size. For a model whose average conviction is well under 1,
    that inflates every trade. Comparing the recorded returns against what
    full-size booking would have produced is enough to catch a reversion,
    without re-deriving the simulation's internals.
    """
    checked = 0
    for strat, bt in _traded(frame):
        pos = bt.position.to_numpy()
        idx = bt.position.index
        sizes, ratios = [], []
        for t in bt.trades:
            lo, hi = idx.get_loc(t.entry_time), idx.get_loc(t.exit_time)
            if hi <= lo:
                continue
            avg_size = float(np.abs(pos[lo:hi]).mean())
            full = abs(t.exit_price / t.entry_price - 1.0)
            if avg_size > 0.85 or full < 1e-4:
                continue          # near full size: the two agree by definition
            sizes.append(avg_size)
            ratios.append(abs(t.gross_return) / full)
        if len(ratios) < 5:
            continue
        # gross_return is the price move carried at the size actually held, so
        # the ratio tracks average conviction rather than sitting at 1.0.
        assert np.median(ratios) < 0.95, (
            f"{strat.name}: trades look full-size (median ratio "
            f"{np.median(ratios):.2f}) while average conviction is "
            f"{np.mean(sizes):.2f}")
        checked += 1
        if checked >= 3:
            break
    if not checked:
        pytest.skip("no partially-sized strategy in this sample")


def test_report_net_profit_agrees_in_sign_with_the_equity_curve(frame):
    """The failure a reader would actually notice: opposite signs."""
    checked = 0
    for strat, bt in _traded(frame):
        if abs(bt.total_return_pct) < 5:
            continue          # near zero, sign is not meaningful
        rep = analyse(bt, frame.df, bars_per_year=365, position=bt.position)
        net = rep.all_trades.net_profit_pct
        if abs(net) < 5:
            continue
        assert np.sign(net) == np.sign(bt.total_return_pct), (
            f"{strat.name}: report says {net:+.2f}%, equity says "
            f"{bt.total_return_pct:+.2f}%")
        checked += 1
        if checked >= 5:
            break
    assert checked, "no strategy produced a large enough result to compare"


def test_trade_returns_are_derived_from_the_simulated_series(frame):
    """A full-size booking would blow past the equity curve's total."""
    for strat, bt in _traded(frame):
        compounded = float(np.prod([1 + t.net_return for t in bt.trades]) - 1) * 100
        # Generous, because flat bars carry costs outside every trade span.
        assert abs(compounded) < abs(bt.total_return_pct) * 6 + 100, (
            f"{strat.name}: trades compound to {compounded:+.1f}% against an "
            f"equity return of {bt.total_return_pct:+.1f}%")
