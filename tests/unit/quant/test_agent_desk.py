"""
The agent desk is a second opinion, not a vote. These tests pin that boundary.

Nothing here starts a debate — a real one is minutes of LLM calls. The subject
under test is the contract: what the desk is allowed to change, what it must
never change, and that a desk which cannot run says so instead of guessing.
"""
from __future__ import annotations

import json

import pytest

from tradingview_mcp.core.quant.agents import (
    AgentVerdict, concordance_caution, load_cached, parse_direction,
)


# ── direction parsing ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("FINAL TRANSACTION PROPOSAL: **BUY**", "BUY"),
    ("FINAL TRANSACTION PROPOSAL: **SELL**", "SELL"),
    ("FINAL TRANSACTION PROPOSAL: **HOLD**", "NEUTRAL"),
    ("", "NEUTRAL"),
    ("   \n  ", "NEUTRAL"),
])
def test_parse_direction_reads_the_explicit_proposal(text, expected):
    assert parse_direction(text) == expected


def test_parse_direction_ignores_argument_bulk_before_the_verdict():
    """
    The agents argue both sides at length. Counting keywords over the whole
    transcript would measure how much the bear talked, not what was decided.
    """
    transcript = (
        "The bear case: sell, sell, bearish, reduce, underweight, short.\n" * 40
        + "FINAL TRANSACTION PROPOSAL: **BUY**"
    )
    assert parse_direction(transcript) == "BUY"


def test_parse_direction_is_neutral_when_the_closing_lines_argue_both_ways():
    assert parse_direction("we could buy here or sell here, unclear") == "NEUTRAL"


# ── the authority boundary ────────────────────────────────────────────────────

def test_disagreement_produces_a_caution():
    v = AgentVerdict(available=True, direction="SELL")
    note = concordance_caution(v, "BUY")
    assert note is not None
    assert "SELL" in note and "BUY" in note


@pytest.mark.parametrize("verdict,quant", [
    (AgentVerdict(available=True, direction="BUY"), "BUY"),      # agrees
    (AgentVerdict(available=True, direction="NEUTRAL"), "BUY"),  # no call
    (AgentVerdict(available=False), "BUY"),                      # never ran
    (AgentVerdict(available=True, direction="SELL"), "NEUTRAL"),  # models flat
])
def test_no_caution_without_a_genuine_contradiction(verdict, quant):
    assert concordance_caution(verdict, quant) is None


def test_agrees_with_returns_none_when_either_side_has_no_opinion():
    assert AgentVerdict(available=False).agrees_with("BUY") is None
    assert AgentVerdict(available=True, direction="NEUTRAL").agrees_with("BUY") is None
    assert AgentVerdict(available=True, direction="BUY").agrees_with("NEUTRAL") is None
    assert AgentVerdict(available=True, direction="BUY").agrees_with("BUY") is True
    assert AgentVerdict(available=True, direction="SELL").agrees_with("BUY") is False


def test_the_desk_cannot_veto_or_set_direction(monkeypatch):
    """
    The engine's rule is that an LLM explains and never originates. The desk's
    only channel into a trade is a caution, which halves size. If a future edit
    ever gives it veto power this test is the thing that should fail.
    """
    import inspect

    from tradingview_mcp.core.quant import confidence as C

    src = inspect.getsource(C.score_trade)
    agent_block = src.split("agent_verdict is not None")[1]
    agent_block = agent_block.split("return ConfidenceReport")[0]
    assert "vetoes.append" not in agent_block
    assert "vetoes.extend" not in agent_block
    assert "direction =" not in agent_block


def test_score_and_direction_survive_a_disagreeing_desk():
    """A contradicting desk may shrink the trade; it may not move the call."""
    import numpy as np
    import pandas as pd

    from tradingview_mcp.core.quant.confidence import score_trade
    from tradingview_mcp.core.quant.consensus import (
        compute_consensus, compute_risk_levels, evaluate_all)
    from tradingview_mcp.core.quant.features import build_features
    from tradingview_mcp.core.quant.registry import get_registry

    rng = np.random.default_rng(11)
    n = 400
    # Build the series *on* the datetime index. Constructing it on a RangeIndex
    # and passing index=... to DataFrame makes pandas realign on a non-
    # overlapping index, which silently yields an empty frame.
    idx = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    close = pd.Series(100 * np.cumprod(1 + rng.normal(0.0012, 0.01, n)), index=idx)
    df = pd.DataFrame({
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close * 1.004, "low": close * 0.996, "close": close,
        "volume": pd.Series(rng.integers(5_000, 20_000, n).astype(float), index=idx),
    }, index=idx)

    f = build_features(df, "1d", "TEST")
    models = get_registry().all()
    _, sigs = evaluate_all(f, "1d", "TEST", strategies=models)
    con = compute_consensus(f, "1d", "TEST", strategies=models, signals=sigs)
    risk = compute_risk_levels(f, con.direction)
    voting = [(s, g) for s, g in sigs if g.available and abs(g.score) >= 0.15]

    base = score_trade(con, f, voting, risk_reward=risk.risk_reward)
    opposite = {"BUY": "SELL", "SELL": "BUY"}.get(con.direction, "SELL")
    against = score_trade(con, f, voting, risk_reward=risk.risk_reward,
                          agent_verdict=AgentVerdict(available=True,
                                                     direction=opposite))

    assert against.direction == base.direction
    assert against.score == base.score
    assert against.size_multiplier <= base.size_multiplier


# ── honest unavailability ─────────────────────────────────────────────────────

def test_an_unavailable_desk_reports_neutral_and_says_why():
    v = AgentVerdict(available=False, reason_unavailable="not installed")
    assert v.direction == "NEUTRAL"
    assert v.reason_unavailable
    assert concordance_caution(v, "BUY") is None


def test_a_corrupt_cache_entry_is_a_miss_not_a_crash(tmp_path, monkeypatch):
    from tradingview_mcp.core.quant import agents as A

    monkeypatch.setattr(A, "CACHE_DIR", tmp_path)
    (tmp_path / "AAPL_2026-01-02.json").write_text("{not json", encoding="utf-8")
    assert load_cached("AAPL", "2026-01-02") is None


def test_cache_round_trip_marks_the_result_as_cached(tmp_path, monkeypatch):
    from tradingview_mcp.core.quant import agents as A

    monkeypatch.setattr(A, "CACHE_DIR", tmp_path)
    original = AgentVerdict(available=True, ticker="AAPL", as_of="2026-01-02",
                            direction="SELL", confidence=0.8,
                            rationale="because", reports={"news_report": "x"})
    (tmp_path / "AAPL_2026-01-02.json").write_text(
        json.dumps(original.to_dict()), encoding="utf-8")

    got = load_cached("AAPL", "2026-01-02")
    assert got is not None
    assert got.cached is True
    assert got.direction == "SELL"
    assert got.confidence == pytest.approx(0.8)
    assert got.reports["news_report"] == "x"


def test_cache_key_survives_an_exchange_qualified_symbol(tmp_path, monkeypatch):
    """`NSE:ICICIBANK` must not escape the cache directory."""
    from tradingview_mcp.core.quant import agents as A

    monkeypatch.setattr(A, "CACHE_DIR", tmp_path)
    p = A._cache_path("NSE:ICICIBANK", "2026-01-02")
    assert p.parent == tmp_path
    assert ":" not in p.name
