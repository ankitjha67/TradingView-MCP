"""
Full TradingView-style performance report for one strategy, or a ranked sweep.

    # one strategy, full Performance Summary
    python tools/strategy_report.py --symbol AAPL --interval 1d \
        --strategy "Donchian Channel Breakout"

    # rank every model, then report the winner in full
    python tools/strategy_report.py --symbol AAPL --interval 1d --top

    # follow whatever chart is open
    python tools/strategy_report.py --strategy "Turtle Trading System 1"

Produces the All / Long / Short breakdown, MAE/MFE, drawdown and run-up with
durations, streaks, the risk-ratio block, and a monthly returns grid.
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

from tradingview_mcp.core.quant.backtest import compare_strategies, run_backtest  # noqa: E402
from tradingview_mcp.core.quant.features import build_features  # noqa: E402
from tradingview_mcp.core.quant.features import BARS_PER_YEAR  # noqa: E402
from tradingview_mcp.core.quant.market_data import fetch_ohlcv  # noqa: E402
from tradingview_mcp.core.quant.monitor import read_chart_from_browser  # noqa: E402
from tradingview_mcp.core.quant.performance import analyse, render_markdown  # noqa: E402
from tradingview_mcp.core.quant.registry import get_registry  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="", help="default: the chart you have open")
    ap.add_argument("--interval", default="")
    ap.add_argument("--exchange", default="")
    ap.add_argument("--strategy", default="", help="exact model name")
    ap.add_argument("--top", action="store_true",
                    help="rank all models by Sharpe and report the best one in full")
    ap.add_argument("--sort-by", default="sharpe_ratio")
    ap.add_argument("--bars", type=int, default=2500)
    ap.add_argument("--capital", type=float, default=100_000.0)
    ap.add_argument("--commission", type=float, default=0.05)
    ap.add_argument("--slippage", type=float, default=0.05)
    ap.add_argument("--long-only", action="store_true")
    ap.add_argument("--out", default="", help="also write the report to this file")
    a = ap.parse_args()

    symbol, interval, exchange = a.symbol, a.interval, a.exchange
    if not symbol:
        chart = read_chart_from_browser()
        if not chart or not chart.is_valid():
            print("No chart detected and no --symbol given.", file=sys.stderr)
            return 1
        symbol, interval, exchange = chart.symbol, chart.interval, chart.exchange
        print(f"Following your chart: {exchange}:{symbol} @ {interval}\n")
    interval = interval or "1d"

    md = fetch_ohlcv(symbol, interval, exchange)
    f = build_features(md.df.tail(a.bars), interval, symbol)
    bpy = BARS_PER_YEAR.get(interval, 252)
    reg = get_registry()

    name = a.strategy
    if a.top or not name:
        print(f"Ranking all models on {symbol} {interval} ({f.n} bars)…")
        res = compare_strategies(f, commission_pct=a.commission, slippage_pct=a.slippage,
                                 allow_short=not a.long_only, sort_by=a.sort_by)
        rank = res["ranking"]
        if not rank:
            print("No model produced enough trades to rank.", file=sys.stderr)
            return 1
        print(f"\n{'#':>3} {'strategy':44s} {'ret%':>8} {'sharpe':>7} {'maxDD%':>8} {'trades':>7}")
        for row in rank[:10]:
            print(f"{row['rank']:>3} {row['strategy'][:44]:44s} {row['total_return_pct']:>8.2f} "
                  f"{row['sharpe_ratio']:>7.2f} {row['max_drawdown_pct']:>8.2f} "
                  f"{row['total_trades']:>7}")
        print(f"\n{len(rank)} ranked of {res['models_tested']} tested · "
              f"buy & hold {res['buy_and_hold_pct']:+.2f}% · "
              f"{res['beat_buy_and_hold']} beat it\n")
        name = rank[0]["strategy"]
        print(f"Full report for the top-ranked model: {name}\n")

    strat = reg.get(name)
    if strat is None:
        print(f"No model named {name!r}. Try --top, or check STRATEGY_CATALOG.md.",
              file=sys.stderr)
        return 1

    bt = run_backtest(strat, f, commission_pct=a.commission, slippage_pct=a.slippage,
                      allow_short=not a.long_only)
    if bt.error:
        print(f"{name}: {bt.error}", file=sys.stderr)
        return 1

    rep = analyse(bt, f.df, bars_per_year=bpy, initial_capital=a.capital,
                  commission_pct=a.commission, slippage_pct=a.slippage,
                  position=bt.position)
    text = render_markdown(rep)
    print(text)

    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"\nwritten to {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
