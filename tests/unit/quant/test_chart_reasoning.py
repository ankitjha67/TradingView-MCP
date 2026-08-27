"""
The engine must not analyse bars that are not the charted instrument.

Symbol resolution is a chain of guesses and a wrong one is silent: the models
run, the consensus forms, a position gets sized, and every number is ordinary
— just about a different asset. CRYPTOCAP:SOLANA.C resolving to SOLAUSDT is
the case that prompted this.

The price TradingView renders is an independent measurement, so these tests
pin that comparison. No network or DevTools access: the chart context and the
fetched data are both constructed.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from tradingview_mcp.core.quant.chart_reasoning import (
    PRICE_ABSURD_PCT, PRICE_TOLERANCE_PCT, ChartContext, verify,
)


@dataclass
class FakeSpec:
    raw: str = "CRYPTO:SOLUSD"
    ticker: str = "SOLUSD"
    asset_class: str = "crypto"
    yahoo: str = "SOL-USD"
    binance: str = "SOLUSDT"
    exchange: str = "CRYPTO"


class FakeMD:
    def __init__(self, last: float, bars: int = 500):
        idx = pd.date_range("2024-01-01", periods=bars, freq="D", tz="UTC")
        close = pd.Series(np.linspace(last * 0.8, last, bars), index=idx)
        self.df = pd.DataFrame({"open": close, "high": close, "low": close,
                                "close": close, "volume": 1.0}, index=idx)


def _chart(price: float, symbol: str = "SOLUSD") -> ChartContext:
    return ChartContext(symbol=symbol, price=price, ok=True)


def test_matching_price_passes_every_check():
    v = verify(FakeSpec(), FakeMD(104.18), _chart(104.17))
    assert v.safe
    assert not v.failures


def test_a_wildly_different_price_is_fatal():
    """BTC bars under a SOL chart — the silent wrong-instrument failure."""
    v = verify(FakeSpec(), FakeMD(79_447.71), _chart(104.17))
    assert not v.safe
    bad = [c for c in v.failures if c.name == "price cross-check"]
    assert bad and bad[0].fatal
    assert "not the same instrument" in bad[0].detail


def test_a_moderate_gap_warns_without_blocking():
    """A stale feed or a different venue is worth flagging, not refusing."""
    v = verify(FakeSpec(), FakeMD(104.17 * 1.12), _chart(104.17))
    assert v.safe, "a 12% gap should not be fatal"
    assert any(c.name == "price cross-check" for c in v.failures)


@pytest.mark.parametrize("drift", [0.0, 0.01, 0.03, 0.049])
def test_small_drift_is_accepted(drift):
    """The chart ticks ahead of the last closed bar; that is normal."""
    v = verify(FakeSpec(), FakeMD(104.0 * (1 + drift)), _chart(104.0))
    assert v.safe
    assert not [c for c in v.failures if c.name == "price cross-check"]


def test_an_aggregate_is_refused_before_anything_else():
    spec = FakeSpec(raw="CRYPTOCAP:SOLANA.C", ticker="SOLANA.C",
                    asset_class="aggregate", yahoo="", binance="")
    v = verify(spec, FakeMD(104.0), _chart(104.0))
    assert not v.safe
    assert v.checks[0].name == "tradeable" and v.checks[0].fatal
    assert len(v.checks) == 1, "should stop rather than keep checking"


def test_an_unresolvable_symbol_is_refused():
    spec = FakeSpec(raw="NONSENSE:XYZ", ticker="XYZ", yahoo="", binance="")
    v = verify(spec, FakeMD(104.0), _chart(104.0))
    assert not v.safe
    assert any(c.name == "resolution" and c.fatal for c in v.failures)


def test_too_little_history_is_fatal():
    v = verify(FakeSpec(), FakeMD(104.17, bars=10), _chart(104.17))
    assert not v.safe
    assert any(c.name == "history" and c.fatal for c in v.failures)


def test_an_unreadable_chart_does_not_block_analysis():
    """
    No chart is not the same as a wrong chart. Running with --symbol, or with
    no browser at all, must stay possible — the resolution is then unverified,
    which is honest, rather than assumed wrong.
    """
    v = verify(FakeSpec(), FakeMD(104.17),
               ChartContext(ok=False, error="no DevTools endpoint"))
    assert v.safe
    check = next(c for c in v.checks if c.name == "price cross-check")
    assert check.passed and "unverified" in check.detail


def test_thresholds_are_ordered_sensibly():
    assert 0 < PRICE_TOLERANCE_PCT < PRICE_ABSURD_PCT
