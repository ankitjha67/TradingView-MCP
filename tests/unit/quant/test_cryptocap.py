"""
Nothing on the CRYPTOCAP pseudo-exchange is tradeable.

It is TradingView's index provider for crypto market capitalisation and
dominance: TOTAL, BTC.D (dominance %), SOLANA.C (market cap). Every series is
computed. The classifier used to match a list of eight known names, so any
series outside that list fell through to the crypto branch and was mapped to a
pair by string-munging — CRYPTOCAP:SOLANA.C resolved to SOLAUSDT, a different
token, which the engine would then price, backtest and size a position on.
"""
from __future__ import annotations

import pytest

from tradingview_mcp.core.quant.market_data import parse_symbol


@pytest.mark.parametrize("symbol", [
    "CRYPTOCAP:TOTAL", "CRYPTOCAP:TOTAL2", "CRYPTOCAP:TOTAL3",
    "CRYPTOCAP:BTC.D", "CRYPTOCAP:USDT.D", "CRYPTOCAP:ETH.D",
    "CRYPTOCAP:STABLE.C", "CRYPTOCAP:SOLANA.C", "CRYPTOCAP:DOGE.C",
    "CRYPTOCAP:OTHERS", "CRYPTOCAP:SOMETHING.NEW",
])
def test_every_cryptocap_series_is_an_aggregate(symbol):
    spec = parse_symbol(symbol)
    assert spec.asset_class == "aggregate", symbol


@pytest.mark.parametrize("symbol", [
    "CRYPTOCAP:SOLANA.C", "CRYPTOCAP:DOGE.C", "CRYPTOCAP:ETH.D",
    "CRYPTOCAP:SOMETHING.NEW",
])
def test_an_aggregate_never_resolves_to_a_tradeable_pair(symbol):
    """The specific failure: a market-cap series priced as a spot pair."""
    spec = parse_symbol(symbol)
    assert not spec.yahoo, f"{symbol} mapped to yahoo {spec.yahoo!r}"
    assert not spec.binance, f"{symbol} mapped to binance {spec.binance!r}"


def test_solana_market_cap_is_not_confused_with_a_sola_token():
    """CRYPTOCAP:SOLANA.C once became SOLAUSDT — a different asset."""
    spec = parse_symbol("CRYPTOCAP:SOLANA.C")
    assert spec.asset_class == "aggregate"
    assert spec.binance != "SOLAUSDT"
    assert spec.yahoo != "SOLA-USD"


@pytest.mark.parametrize("symbol,binance", [
    ("BINANCE:SOLUSDT", "SOLUSDT"),
    ("BINANCE:BTCUSDT", "BTCUSDT"),
])
def test_real_pairs_still_resolve(symbol, binance):
    """The fix must not swallow genuine tradeable crypto."""
    spec = parse_symbol(symbol)
    assert spec.asset_class == "crypto"
    assert spec.binance == binance
