"""
Run or inspect a TradingAgents debate from the command line.

    python tools/agent_desk.py --symbol AAPL              # today, cached if present
    python tools/agent_desk.py                            # follow the open chart
    python tools/agent_desk.py --symbol AAPL --refresh    # force a fresh debate
    python tools/agent_desk.py --symbol AAPL --reports    # print each desk's working
    python tools/agent_desk.py --list                     # what is already cached

A debate is several minutes of model calls, so results are cached per
(ticker, trading date) and reused by the dashboard and the monitor for the
rest of that day. Nothing here votes: the verdict's only effect on a trade is
a caution when it contradicts the models, which halves position size. See
src/tradingview_mcp/core/quant/agents.py for why that asymmetry is deliberate.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from tradingview_mcp.core.quant.agents import (  # noqa: E402
    CACHE_DIR, availability, desk_params_from_llm_config, load_cached, run_desk,
)
from tradingview_mcp.core.quant.monitor import read_chart_from_browser  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="", help="default: the chart you have open")
    ap.add_argument("--date", default="", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--refresh", action="store_true", help="ignore the cache")
    ap.add_argument("--reports", action="store_true", help="print every section")
    ap.add_argument("--rounds", type=int, default=1, help="debate rounds (default 1)")
    ap.add_argument("--list", action="store_true", help="list cached verdicts")
    a = ap.parse_args()

    if a.list:
        if not CACHE_DIR.exists():
            print("nothing cached yet.")
            return 0
        rows = sorted(CACHE_DIR.glob("*.json"))
        print(f"{len(rows)} cached verdict(s) in {CACHE_DIR}:")
        for p in rows:
            v = load_cached(*p.stem.rsplit("_", 1))
            if v:
                print(f"  {p.stem:28s} {v.direction:7s} conf {v.confidence:.0%} "
                      f"· {len(v.reports)} sections")
        return 0

    ok, why = availability()
    if not ok:
        print(why, file=sys.stderr)
        return 1

    symbol = a.symbol
    if not symbol:
        chart = read_chart_from_browser()
        if not chart or not chart.is_valid():
            print("No chart detected and no --symbol given.", file=sys.stderr)
            return 1
        symbol = chart.symbol
        print(f"Following your chart: {symbol}\n")

    day = a.date or date.today().isoformat()
    cached = load_cached(symbol, day)
    if cached and not a.refresh:
        print(f"Using the cached verdict for {symbol} on {day} "
              f"(--refresh to debate again).\n")
    else:
        print(f"Debating {symbol} for {day}. This takes several minutes.\n")

    v = run_desk(symbol, day=day, refresh=a.refresh, debate_rounds=a.rounds,
                 **desk_params_from_llm_config())

    if not v.available:
        print(f"The desk did not run: {v.reason_unavailable}", file=sys.stderr)
        if v.error:
            print(v.error[:800], file=sys.stderr)
        return 1

    print("=" * 72)
    print(f"{v.ticker} · {v.as_of} · {'cached' if v.cached else f'{v.elapsed_s:.0f}s'}")
    print(f"VERDICT   {v.direction}   desk confidence {v.confidence:.0%}")
    if v.size_fraction:
        print(f"          (it suggests {v.size_fraction:.0%} of book — advisory only; "
              f"this engine sizes from its own calibrated model)")
    for label, val in (("target", v.target), ("stop", v.stop)):
        if val is not None:
            print(f"          {label}: {val}")
    if v.horizon_days:
        print(f"          horizon: {v.horizon_days} days")
    if v.rationale:
        print(f"\nRATIONALE\n{v.rationale}")
    if v.warning:
        print(f"\nWARNING\n{v.warning}")

    print(f"\n{len(v.reports)} report section(s): {', '.join(sorted(v.reports))}")
    if a.reports:
        for name, text in v.reports.items():
            print(f"\n{'-' * 72}\n{name}\n{'-' * 72}\n{text}")

    print("\nThis is a second opinion. It cannot set direction or size a position; "
          "if it contradicts the models it halves the trade, nothing more.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
