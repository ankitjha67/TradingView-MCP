"""
Emit Pine Script v6 for every model currently signalling BUY (or SELL).

    python tools/emit_pine.py --symbol AAPL --interval 1d
    python tools/emit_pine.py                     # follows your TradingView chart

Writes one .pine file per signalling model into ``pine_out/``, plus a combined
consensus indicator. Paste any of them into TradingView's Pine Editor and add to
the chart.

Models with no faithful Pine translation are listed with the reason rather than
approximated — a plot that disagrees with the engine is worse than no plot,
because there is no way to tell which one is wrong.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from tradingview_mcp.core.quant.consensus import evaluate_all  # noqa: E402
from tradingview_mcp.core.quant.features import build_features  # noqa: E402
from tradingview_mcp.core.quant.market_data import fetch_ohlcv  # noqa: E402
from tradingview_mcp.core.quant.monitor import read_chart_from_browser  # noqa: E402
from tradingview_mcp.core.quant.pine import (  # noqa: E402
    coverage, emit, emit_consensus, is_translatable, untranslatable_reason,
)


def slug(name: str) -> str:
    keep = [c if (c.isalnum() or c in " -_") else "" for c in name]
    return "".join(keep).strip().replace(" ", "_").replace("__", "_")[:70]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="", help="default: whatever chart you have open")
    ap.add_argument("--interval", default="")
    ap.add_argument("--exchange", default="")
    ap.add_argument("--direction", default="BUY", choices=["BUY", "SELL", "BOTH"])
    ap.add_argument("--band", type=float, default=0.15)
    ap.add_argument("--out", default="pine_out")
    a = ap.parse_args()

    symbol, interval, exchange = a.symbol, a.interval, a.exchange
    if not symbol:
        chart = read_chart_from_browser()
        if not chart or not chart.is_valid():
            print("No TradingView chart detected and no --symbol given.", file=sys.stderr)
            return 1
        symbol, interval, exchange = chart.symbol, chart.interval, chart.exchange
        print(f"Following your chart: {exchange}:{symbol} @ {interval}")
    interval = interval or "1d"

    md = fetch_ohlcv(symbol, interval, exchange)
    f = build_features(md.df.tail(1500), interval, symbol)
    print(f"{md.bars} bars from {md.provider} · last bar {md.last_bar_time}\n")

    _, signals = evaluate_all(f, interval, symbol)

    wanted = {"BUY", "SELL"} if a.direction == "BOTH" else {a.direction}
    firing = [(s, sig) for s, sig in signals
              if sig.available and sig.direction in wanted]
    firing.sort(key=lambda x: -abs(x[1].score))

    translatable = [(s, sig) for s, sig in firing if is_translatable(s)]
    blocked = [(s, sig) for s, sig in firing if not is_translatable(s)]

    out_dir = ROOT / a.out
    out_dir.mkdir(exist_ok=True)
    for old in out_dir.glob("*.pine"):
        old.unlink()

    cov = coverage()
    print(f"{len(firing)} models signalling {a.direction} · "
          f"{len(translatable)} have a Pine translation "
          f"({cov['translations']} translations exist in total)\n")

    print("=" * 92)
    print(f"PINE EMITTED — {a.direction} signals you can plot on your chart")
    print("=" * 92)
    if not translatable:
        print("  none")
    for s, sig in translatable:
        src = emit(s, interval, a.band)
        path = out_dir / f"{slug(s.name)}.pine"
        path.write_text(src, encoding="utf-8")
        flag = " [PROXY]" if s.is_proxy else ""
        print(f"  {sig.score:+.2f}  {s.name}{flag}")
        print(f"         → {path.relative_to(ROOT)}")

    if translatable:
        combined = emit_consensus([s for s, _ in translatable], interval, a.band,
                                  title=f"Quant Desk — {symbol} {interval} consensus")
        cpath = out_dir / "_CONSENSUS.pine"
        cpath.write_text(combined, encoding="utf-8")
        print(f"\n  Combined indicator ({len(translatable)} models, family-weighted)")
        print(f"         → {cpath.relative_to(ROOT)}")

    if blocked:
        print(f"\n{'-' * 92}")
        print(f"NOT EMITTED — {len(blocked)} signalling models have no faithful Pine translation")
        print(f"{'-' * 92}")
        seen: dict[str, int] = {}
        for s, _ in blocked:
            seen[untranslatable_reason(s)] = seen.get(untranslatable_reason(s), 0) + 1
        for reason, n in sorted(seen.items(), key=lambda x: -x[1]):
            print(f"  {n:4d}  {reason}")
        print("\n  These are not approximated. A Pine plot that disagrees with the engine")
        print("  would be indistinguishable from one that agrees, so none is emitted.")

    print(f"\nPaste any .pine file into TradingView → Pine Editor → Add to chart.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
