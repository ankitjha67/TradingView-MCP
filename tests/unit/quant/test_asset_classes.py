"""
The pipeline must work for every asset class, not the one currently on screen.

Two failure shapes are covered here.

*Resolution.* Continuous futures (GC1!, ES1!) had no handling at all: the "!"
was removed by the character filter, leaving "GC1", which is a valid ticker
nowhere. SymbolSpec has always documented "futures" as an asset class and
nothing ever produced one.

*Rendering.* The chart price is parsed back for the cross-check, and each
asset class renders differently — thousands separators, currency prefixes,
five-decimal forex, unicode minus, and K/M/B abbreviations. A parser that only
understands plain decimals mis-reads most of them, and reading "2.45M" as 2.45
would make the check refuse a working instrument rather than catch a broken
one.
"""
from __future__ import annotations

import pytest

from tradingview_mcp.core.quant.chart_reasoning import _to_float
from tradingview_mcp.core.quant.market_data import parse_symbol


# ── resolution across classes ─────────────────────────────────────────────────

@pytest.mark.parametrize("symbol,asset_class", [
    ("NSE:ICICIBANK", "equity"), ("NASDAQ:AAPL", "equity"),
    ("LSE:VOD", "equity"), ("TSE:7203", "equity"),
    ("BINANCE:BTCUSDT", "crypto"), ("CRYPTO:SOLUSD", "crypto"),
    ("FX:EURUSD", "forex"), ("OANDA:GBPJPY", "forex"),
    ("TVC:SPX", "index"), ("TVC:DXY", "index"), ("TVC:US10Y", "index"),
    ("COMEX:GC1!", "futures"), ("CME:ES1!", "futures"),
    ("CRYPTOCAP:BTC.D", "aggregate"), ("CRYPTOCAP:SOLANA.C", "aggregate"),
])
def test_asset_class_is_identified(symbol, asset_class):
    assert parse_symbol(symbol).asset_class == asset_class


@pytest.mark.parametrize("symbol,yahoo", [
    ("COMEX:GC1!", "GC=F"), ("CME:ES1!", "ES=F"), ("NYMEX:CL1!", "CL=F"),
    ("CBOT:ZN1!", "ZN=F"), ("CME:6E1!", "6E=F"), ("COMEX:SI1!", "SI=F"),
])
def test_front_month_futures_map_to_a_real_series(symbol, yahoo):
    spec = parse_symbol(symbol)
    assert spec.yahoo == yahoo
    assert "!" not in spec.yahoo


@pytest.mark.parametrize("symbol", ["COMEX:GC2!", "CME:ES3!", "NYMEX:CL4!"])
def test_back_months_are_not_substituted_with_the_front_month(symbol):
    """
    Yahoo serves only the front month. Quietly returning it for GC2! would be
    a different series wearing the requested name — the same silent
    wrong-instrument failure the reasoning layer exists to stop.
    """
    spec = parse_symbol(symbol)
    assert spec.asset_class == "futures"
    assert not spec.yahoo, f"{symbol} must not resolve to the front month"


def test_an_unknown_futures_root_is_still_classed_futures():
    spec = parse_symbol("CME:XYZ1!")
    assert spec.asset_class == "futures"
    assert not spec.yahoo


def test_equities_are_not_mistaken_for_futures():
    """A trailing digit is common in tickers; only "!" marks a contract."""
    for symbol in ("TSE:7203", "NASDAQ:AAPL", "NSE:M&M"):
        assert parse_symbol(symbol).asset_class != "futures"


# ── price rendering across classes ────────────────────────────────────────────

@pytest.mark.parametrize("rendered,expected", [
    ("104.17", 104.17),                     # crypto
    ("1,443.00", 1443.0),                   # equity, grouped
    ("\u20b91,443.00", 1443.0),             # equity, currency prefix
    ("$79,447.71", 79447.71),               # crypto, dollar prefix
    ("1.08505", 1.08505),                   # forex, five decimals
    ("0.00001234", 1.234e-05),              # micro-priced token
    ("5,912.75", 5912.75),                  # index level
    ("104.17 USD", 104.17),                 # trailing currency code
    ("4.664", 4.664),                       # a rate, in percent
    ("-0.0025", -0.0025),                   # ascii minus
    ("\u2212104.17", -104.17),              # unicode minus, what TV renders
    ("1.2K", 1_200.0),                      # abbreviated
    ("2.45M", 2_450_000.0),
    ("50.4B", 5.04e10),
])
def test_every_rendering_parses(rendered, expected):
    got = _to_float(rendered)
    assert got is not None, rendered
    assert abs(got - expected) < max(1e-9, abs(expected) * 1e-9), rendered


@pytest.mark.parametrize("rendered", ["", "N/A", "\u2014", "-", "."])
def test_non_numbers_return_none_rather_than_zero(rendered):
    """Zero would compare as a wild mismatch and refuse a working chart."""
    assert _to_float(rendered) is None


def test_a_magnitude_suffix_is_not_confused_with_a_currency_code():
    """"104.17 USD" ends in D; it must not be read as a magnitude."""
    assert _to_float("104.17 USD") == pytest.approx(104.17)
    assert _to_float("1,443.00 INR") == pytest.approx(1443.0)
