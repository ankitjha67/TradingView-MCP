"""
An instrument is sized in the currency its exchange quotes, not in dollars.

resolve_instrument used to decide currency as:

    quote = "INR" if spec.exchange in ("NSE", "BSE") else "USD"

so every venue outside India was assumed to quote dollars. A London price
became dollars, a Tokyo price became dollars, and the notional was out by
whatever the cross rate happened to be.

London is worse than a plain cross-rate error: the LSE quotes equities in
pence. LSEG at 8,913 means GBP 89.13. Read as GBP the notional is a hundred
times too large, and read as USD it is wrong twice over.
"""
from __future__ import annotations

import pytest

from tradingview_mcp.core.quant.sizing import (
    CapitalConfig, build_position, resolve_instrument,
)


@pytest.mark.parametrize("symbol,currency", [
    ("NSE:ICICIBANK", "INR"), ("BSE:RELIANCE", "INR"),
    ("NASDAQ:AAPL", "USD"), ("NYSE:JPM", "USD"),
    ("LSE:LSEG", "GBp"),                       # pence, not pounds
    ("TSE:7203", "JPY"), ("HKEX:0700", "HKD"),
    ("ASX:BHP", "AUD"), ("TSX:SHOP", "CAD"),
    ("XETR:SAP", "EUR"), ("SIX:NESN", "CHF"),
])
def test_exchange_determines_the_quote_currency(symbol, currency):
    assert resolve_instrument(symbol).quote_currency == currency


def test_an_unknown_venue_still_defaults_to_usd():
    """The old behaviour is correct as a fallback, just not as a rule."""
    assert resolve_instrument("SOMEWHERE:XYZ").quote_currency == "USD"


def test_london_is_priced_in_pence_not_pounds():
    """
    The specific hundredfold error. LSEG at 8,913 GBp is about INR 9,982 a
    share, so a INR 12,500 exposure budget buys one. Read as GBP it would be
    INR 998,000 a share and nothing would ever be sizeable.
    """
    cap = CapitalConfig(capital=50_000.0, currency="INR", risk_pct=1.0,
                        max_position_pct=25.0)
    pos = build_position("LSE:LSEG", "BUY", 8913.59, 8472.41, 9800.0, cap, 1.0)
    d = pos if isinstance(pos, dict) else pos.__dict__
    assert d["quantity"] >= 1, "a single LSEG share must fit in INR 12,500"
    per_share = d["notional_account_ccy"] / d["quantity"]
    assert 8_000 < per_share < 12_000, (
        f"one share priced at INR {per_share:,.0f} — pence/pounds confusion")


def test_a_yen_instrument_sizes_sensibly():
    cap = CapitalConfig(capital=50_000.0, currency="INR", risk_pct=1.0,
                        max_position_pct=25.0)
    pos = build_position("TSE:7203", "BUY", 2850.0, 2750.0, 3100.0, cap, 1.0)
    d = pos if isinstance(pos, dict) else pos.__dict__
    assert d["quantity"] >= 1
    per_share = d["notional_account_ccy"] / d["quantity"]
    assert 1_000 < per_share < 2_500, f"INR {per_share:,.0f} a share is not JPY 2,850"


def test_refusing_to_size_explains_the_binding_constraint():
    """A silent zero reads as a bug; the reason must name what is blocking."""
    cap = CapitalConfig(capital=50_000.0, currency="INR", risk_pct=1.0,
                        max_position_pct=25.0)
    pos = build_position("NASDAQ:AAPL", "BUY", 313.45, 298.0, 340.0, cap, 1.0)
    d = pos if isinstance(pos, dict) else pos.__dict__
    assert d["quantity"] == 0 and not d["tradeable"]
    assert d["reasons"], "a refusal must say why"
    assert any("risk" in r.lower() or "capital" in r.lower() for r in d["reasons"])


def test_matching_currency_needs_no_conversion():
    cap = CapitalConfig(capital=50_000.0, currency="INR")
    assert cap.rate_to_account("INR") == 1.0


@pytest.mark.parametrize("code", ["USD", "EUR", "GBP", "GBp", "JPY", "HKD"])
def test_every_quoted_currency_has_a_rate(code):
    """A missing rate silently falls back to 1.0 — a 100x sizing error."""
    cap = CapitalConfig(capital=50_000.0, currency="INR")
    assert cap.fx_rates.get(code), f"{code} has no rate; sizing would assume parity"


def test_pence_is_a_hundredth_of_the_pound_rate():
    cap = CapitalConfig(capital=50_000.0, currency="INR")
    assert cap.fx_rates["GBp"] == pytest.approx(cap.fx_rates["GBP"] / 100, rel=1e-6)
