"""
Read public pages and news feeds about an instrument. Research only.

    python tools/research.py --doctor            # what this machine can read
    python tools/research.py                     # news for the chart you have open
    python tools/research.py --symbol ICICIBANK  # news for a named ticker
    python tools/research.py --url https://...   # read one public page
    python tools/research.py --feed https://...  # read one RSS/Atom feed

Nothing here touches the signal path. It does not mark any DataNeed satisfied,
does not vote, does not size, and is never called by the monitor. A live page
has no history, so a model built on one could not be backtested, calibrated, or
cleared by the significance test in backtest.py — see core/research.py for the
argument in full.

Restricted to zero-configuration sources. Reddit, Twitter, Xueqiu and the rest
need a personal logged-in session, and an unattended process driving those is
acting on your account against the platform's terms. The restriction is
enforced in code by channel tier, not by convention.
"""
from __future__ import annotations

import argparse
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from tradingview_mcp.core import research as R  # noqa: E402

# Google News RSS is a public feed with no key and no session — it fits the
# zero-configuration rule, and its query syntax takes a bare ticker.
NEWS_RSS = ("https://news.google.com/rss/search"
            "?q={q}&hl=en-IN&gl=IN&ceid=IN:en")


def news_for(symbol: str, limit: int) -> R.Reading:
    ticker = symbol.split(":")[-1].strip()
    q = urllib.parse.quote_plus(f"{ticker} stock")
    return R.read_feed(NEWS_RSS.format(q=q), limit=limit)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doctor", action="store_true", help="what can be read here")
    ap.add_argument("--symbol", default="", help="default: the chart you have open")
    ap.add_argument("--url", default="", help="read one public page")
    ap.add_argument("--feed", default="", help="read one RSS/Atom feed")
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--full", action="store_true", help="print the whole page text")
    a = ap.parse_args()

    ok, why = R.available()
    if not ok:
        print(why, file=sys.stderr)
        return 1

    if a.doctor:
        print(R.summarise_channels())
        return 0

    if a.url:
        r = R.read_url(a.url)
    elif a.feed:
        r = R.read_feed(a.feed, limit=a.limit)
    else:
        symbol = a.symbol
        if not symbol:
            from tradingview_mcp.core.quant.monitor import read_chart_from_browser
            chart = read_chart_from_browser()
            if not chart or not chart.is_valid():
                print("No chart detected and no --symbol given.", file=sys.stderr)
                return 1
            symbol = chart.symbol
            print(f"Following your chart: {symbol}\n")
        r = news_for(symbol, a.limit)

    if not r.ok:
        print(f"Could not read it: {r.error}", file=sys.stderr)
        return 1

    print("=" * 72)
    if r.title:
        print(r.title)
    print(f"{r.source} · {r.url[:90]}")
    print("=" * 72)

    if r.items:
        for i, item in enumerate(r.items, 1):
            print(f"\n{i:>2}. {item['title']}")
            if item["published"]:
                print(f"    {item['published']}")
            if item["link"]:
                print(f"    {item['link'][:100]}")
            if a.full and item["summary"]:
                print(f"    {item['summary'][:400]}")
    else:
        print(r.text if a.full else r.text[:2500])
        if not a.full and len(r.text) > 2500:
            print(f"\n… {len(r.text) - 2500:,} more characters (--full for all)")

    print("\nResearch context only — this is not a signal, and nothing here "
          "reaches the models, the confidence engine or the sizer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
