"""
Read public web pages and feeds for research. **Not a data feed.**

This module sits outside ``core/quant/`` on purpose. Nothing in the signal path
imports it, and it must stay that way: it exists so a person can read what is
being said about an instrument before acting, not so a model can vote on it.

Why it cannot become a model input, stated plainly because the temptation is
obvious:

    Every voting model implements ``score(f) -> pd.Series``, computed
    vectorised over the whole frame so that one call yields both the live
    signal and the complete historical path. That path is what the backtester
    replays, what the confidence engine calibrates against, and what earns a
    t-statistic.

    A web read returns what a page says *now*. There is no way to ask it what
    Reddit or a news site said on each of the previous 1,499 bars. A model fed
    this way could fill the last element of the series and nothing else — so it
    could never be backtested, never be calibrated, and never clear the
    significance bar in ``backtest.py``.

    Marking ``DataNeed.NEWS`` satisfied on this basis would flip ten sentiment
    models to "voting" while leaving them structurally unverifiable, which is
    the exact failure the ``DataNeed`` enum was introduced to stop.

If point-in-time social data is ever wanted properly, the honest route is to
record these readings forward into a dated archive and wait for history to
accumulate — not to backfill from a live endpoint, whose results are ranked by
today's engagement and silently omit whatever has since been deleted.

Routing comes from Panniantong/Agent-Reach, which is a capability router and
health checker rather than a fetch library: it reports which channels work on
this machine and which backend each would use. Channels are filtered to
``tier == 0`` — Agent-Reach's own marker for zero-configuration sources. Tier 1
and above (Reddit, Twitter, Xueqiu, XiaoHongShu) work only through a personal
logged-in session or exported cookies, and driving those from an automated
process means acting on someone's account against the platform's terms. That
line is enforced here in code, not left to a docstring.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

# Agent-Reach's own tier marker for "works with no configuration". Anything
# above this needs a personal session; see the module docstring.
MAX_TIER = 0

JINA_READER = "https://r.jina.ai/"
DEFAULT_TIMEOUT = 30
MAX_CHARS = 20_000


@dataclass
class Channel:
    name: str
    status: str            # ok | warn | off
    tier: int
    backend: str = ""
    message: str = ""

    @property
    def usable(self) -> bool:
        return self.status == "ok" and self.tier <= MAX_TIER


@dataclass
class Reading:
    """One fetched document. ``ok`` False carries the reason."""
    ok: bool = False
    url: str = ""
    title: str = ""
    text: str = ""
    source: str = ""
    error: str = ""
    items: list = field(default_factory=list)   # RSS entries, when a feed

    def to_dict(self) -> dict:
        return {"ok": self.ok, "url": self.url, "title": self.title,
                "text": self.text[:MAX_CHARS], "source": self.source,
                "error": self.error, "items": self.items[:50]}


def available() -> tuple[bool, str]:
    try:
        import agent_reach  # noqa: F401
    except ImportError:
        return False, ("agent-reach is not installed. Install the real project "
                       "from source — note the PyPI package of that name is a "
                       "different, unrelated project:\n"
                       "  pip install git+https://github.com/Panniantong/Agent-Reach")
    return True, ""


def channels(include_gated: bool = False) -> list[Channel]:
    """
    Which channels this machine can use.

    By default only zero-configuration ones. ``include_gated`` lists the rest
    so their status can be *seen* — it does not make them usable here.
    """
    ok, _ = available()
    if not ok:
        return []
    from agent_reach.core import AgentReach

    out = []
    for name, info in AgentReach().doctor().items():
        if not isinstance(info, dict):
            continue
        ch = Channel(name=name, status=str(info.get("status", "?")),
                     tier=int(info.get("tier", 99)),
                     backend=str(info.get("active_backend") or ""),
                     message=str(info.get("message") or "").strip())
        if include_gated or ch.tier <= MAX_TIER:
            out.append(ch)
    return sorted(out, key=lambda c: (c.tier, c.name))


def _channel(name: str) -> Optional[Channel]:
    return next((c for c in channels(include_gated=True) if c.name == name), None)


def _guard(name: str) -> Optional[str]:
    """Refuse a gated channel in words that say why, not just that."""
    ch = _channel(name)
    if ch is None:
        return f"no channel named {name!r}"
    if ch.tier > MAX_TIER:
        return (f"{name} is tier {ch.tier}: it works only through a personal "
                f"logged-in session or exported cookies. This module is "
                f"restricted to zero-configuration sources, so it will not "
                f"drive your account.")
    if ch.status != "ok":
        return f"{name} is not ready on this machine: {ch.message[:200]}"
    return None


def read_url(url: str, timeout: int = DEFAULT_TIMEOUT) -> Reading:
    """
    Read a public page as text, through the ``web`` channel's Jina Reader.

    Agent-Reach names the backend; the fetch happens here, which is how it is
    designed to be used — it routes and health-checks, it does not retrieve.
    """
    why = _guard("web")
    if why:
        return Reading(url=url, error=why)
    if not url.lower().startswith(("http://", "https://")):
        return Reading(url=url, error="only http(s) URLs are read")

    target = JINA_READER + url
    req = urllib.request.Request(target, headers={
        "User-Agent": "quant-desk-research", "Accept": "text/plain"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return Reading(url=url, error=f"HTTP {exc.code} reading the page")
    except (urllib.error.URLError, TimeoutError) as exc:
        return Reading(url=url, error=f"could not reach the reader: {exc}")

    title = ""
    for line in body.splitlines()[:8]:
        if line.lower().startswith("title:"):
            title = line.split(":", 1)[1].strip()
            break
    return Reading(ok=True, url=url, title=title, text=body[:MAX_CHARS],
                   source="web via Jina Reader")


def read_feed(url: str, limit: int = 20, timeout: int = DEFAULT_TIMEOUT) -> Reading:
    """Read an RSS/Atom feed through the ``rss`` channel's feedparser backend."""
    why = _guard("rss")
    if why:
        return Reading(url=url, error=why)
    try:
        import feedparser
    except ImportError:
        return Reading(url=url, error="feedparser is not installed")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "quant-desk-research"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except Exception as exc:
        return Reading(url=url, error=f"could not fetch the feed: {exc}")

    parsed = feedparser.parse(raw)
    items = [{"title": (e.get("title") or "").strip(),
              "link": e.get("link") or "",
              "published": str(e.get("published") or e.get("updated") or ""),
              "summary": (e.get("summary") or "")[:600].strip()}
             for e in parsed.entries[:limit]]
    if not items:
        return Reading(url=url, error="the feed parsed but contained no entries")
    return Reading(ok=True, url=url,
                   title=str((parsed.feed or {}).get("title") or ""),
                   text="\n".join(f"- {i['title']}" for i in items),
                   source="rss via feedparser", items=items)


def summarise_channels() -> str:
    """A short human report of what can and cannot be read here, and why."""
    ok, why = available()
    if not ok:
        return why
    rows = channels(include_gated=True)
    free = [c for c in rows if c.tier <= MAX_TIER]
    gated = [c for c in rows if c.tier > MAX_TIER]
    lines = [f"Zero-configuration channels ({sum(c.usable for c in free)} usable "
             f"of {len(free)}):"]
    for c in free:
        mark = "ok " if c.usable else c.status.ljust(3)
        lines.append(f"  [{mark}] {c.name:12s} {c.backend or '-'}")
    lines.append("")
    lines.append(f"Gated behind a personal session, not used here ({len(gated)}):")
    lines.append("  " + ", ".join(c.name for c in gated))
    lines.append("")
    lines.append("This is research only. Nothing here feeds a model, sets a "
                 "signal, or sizes a position — a live page has no history, so "
                 "anything built on it could never be backtested.")
    return "\n".join(lines)
