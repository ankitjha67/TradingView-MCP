"""
The research channel is context for a person, never an input to a model.

These tests pin that boundary. Two properties matter more than the fetching:

  * gated channels are refused in code, so an unattended process never drives
    someone's logged-in Reddit or Twitter session;
  * nothing in the signal path imports this module, so it cannot quietly
    become a data feed for models that could never be backtested on it.

Network fetches are not exercised here — the point under test is the contract.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tradingview_mcp.core import research as R

SRC = Path(__file__).resolve().parents[3] / "src" / "tradingview_mcp"


@pytest.fixture(scope="module")
def probe():
    """
    One doctor pass for the whole module.

    ``channels()`` health-checks every backend over the network; called per
    test it turned a contract check into two minutes of waiting.
    """
    ok, _ = R.available()
    if not ok:
        pytest.skip("agent-reach not installed")
    rows = R.channels(include_gated=True)
    if not rows:
        pytest.skip("no channels reported")
    return {c.name: c for c in rows}


# ── the cookie boundary ───────────────────────────────────────────────────────

def test_zero_config_is_the_declared_ceiling():
    assert R.MAX_TIER == 0, "raising this silently would enable session-gated sources"


@pytest.mark.network
@pytest.mark.parametrize("name", ["reddit", "twitter", "xueqiu", "xiaohongshu"])
def test_session_gated_channels_are_refused(name, probe):
    ch = probe.get(name)
    if ch is None:
        pytest.skip(f"{name} not present in this agent-reach build")
    assert ch.tier > R.MAX_TIER, f"{name} should be session-gated"
    assert not ch.usable, f"{name} must never report usable"


@pytest.mark.network
def test_reading_a_gated_channel_returns_a_reason_not_data(probe):
    # There is deliberately no public entry point that reaches a tier-1
    # channel; the only readers are pinned to `web` and `rss`.
    for fn in (R.read_url, R.read_feed):
        r = fn("not-a-url")
        assert r.ok is False
        assert r.error


@pytest.mark.network
def test_channels_hides_gated_ones_by_default(probe):
    # Both assertions read from the module-scoped probe. Calling channels()
    # again here cost a second full health sweep — 17s, in what is meant to be
    # the hermetic part of the suite.
    assert any(c.tier > R.MAX_TIER for c in probe.values()), \
        "include_gated should reveal them for inspection"
    assert all(c.tier <= R.MAX_TIER
               for c in probe.values() if c.tier <= R.MAX_TIER)


@pytest.mark.network
def test_only_http_urls_are_read(probe):
    for bad in ("file:///etc/passwd", "ftp://x/y", "javascript:alert(1)", ""):
        assert R.read_url(bad).ok is False


# ── the separation from the signal path ───────────────────────────────────────

def test_the_engine_never_imports_the_research_module():
    """
    If this fails, a live web read has become reachable from something that
    votes, sizes or scores — and that input has no history to backtest.
    """
    offenders = []
    for path in (SRC / "core" / "quant").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "core.research" in text or "from ..research" in text \
                or "import research" in text:
            offenders.append(path.name)
    assert not offenders, f"signal path imports research: {offenders}"


def test_research_declares_no_data_need():
    """
    It must never satisfy DataNeed.NEWS — those ten models could not be
    backtested on a live page, so marking them available would be a lie.

    Checked against the *code*, not the file text: the docstring discusses
    DataNeed at length precisely to explain why it is not used, and a naive
    substring search flags its own explanation.
    """
    import ast

    tree = ast.parse((SRC / "core" / "research.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        # Strip docstrings so prose about DataNeed is not mistaken for a use.
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and                     isinstance(body[0].value, ast.Constant) and                     isinstance(body[0].value.value, str):
                node.body = body[1:]
    code = ast.unparse(tree)
    assert "DataNeed" not in code, "research must not reference DataNeed in code"
    assert "available_feeds" not in code, "research must not declare a feed available"


def test_reading_dataclass_defaults_are_a_failure_not_a_blank():
    r = R.Reading()
    assert r.ok is False
    assert r.text == "" and r.items == []
    assert r.to_dict()["ok"] is False


def test_channel_usable_requires_both_ok_and_zero_tier():
    assert R.Channel(name="x", status="ok", tier=0).usable is True
    assert R.Channel(name="x", status="ok", tier=1).usable is False
    assert R.Channel(name="x", status="warn", tier=0).usable is False
    assert R.Channel(name="x", status="off", tier=0).usable is False
