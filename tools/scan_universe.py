"""
Scan a universe of liquid instruments and rank whatever survives every gate.

    python tools/scan_universe.py --capital 50000 --risk 1.0

Checking a handful of tickers and reporting "nothing found" is a weak answer:
most instruments are neutral most of the time, so a narrow scan mostly measures
which tickers you happened to pick. This sweeps a broad liquid universe so that
"nothing passed" is a finding rather than an artefact of the sample.

Every candidate runs the full pipeline — 311 models, consensus, confidence with
all vetoes, and position sizing — and only setups that are both signalled and
executable at the given capital are reported.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from tradingview_mcp.core.quant.confidence import (  # noqa: E402
    calibrate, consensus_series, score_trade,
)
from tradingview_mcp.core.quant.consensus import (  # noqa: E402
    compute_consensus, compute_risk_levels, evaluate_all,
)
from tradingview_mcp.core.quant.features import build_features  # noqa: E402
from tradingview_mcp.core.quant.market_data import fetch_ohlcv  # noqa: E402
from tradingview_mcp.core.quant.registry import get_registry  # noqa: E402
from tradingview_mcp.core.quant.sizing import CapitalConfig, build_position  # noqa: E402

# Liquid, borrowable, and cheap enough to clear venue minimums at small capital.
UNIVERSE = [
    # Major crypto — deep books, perp markets for shorts
    ("BTCUSDT", "BINANCE"), ("ETHUSDT", "BINANCE"), ("SOLUSDT", "BINANCE"),
    ("XRPUSDT", "BINANCE"), ("BNBUSDT", "BINANCE"), ("ADAUSDT", "BINANCE"),
    ("AVAXUSDT", "BINANCE"), ("LINKUSDT", "BINANCE"), ("DOTUSDT", "BINANCE"),
    ("MATICUSDT", "BINANCE"), ("LTCUSDT", "BINANCE"), ("ATOMUSDT", "BINANCE"),
    ("NEARUSDT", "BINANCE"), ("APTUSDT", "BINANCE"), ("ARBUSDT", "BINANCE"),
    # US large caps
    ("AAPL", ""), ("MSFT", ""), ("NVDA", ""), ("GOOGL", ""), ("AMZN", ""),
    ("META", ""), ("TSLA", ""), ("AMD", ""), ("NFLX", ""), ("JPM", ""),
    ("XOM", ""), ("WMT", ""), ("KO", ""), ("DIS", ""), ("INTC", ""),
    # Liquid ETFs — cheapest way to get index exposure in a small account
    ("SPY", ""), ("QQQ", ""), ("IWM", ""), ("GLD", ""), ("SLV", ""),
    ("TLT", ""), ("XLF", ""), ("XLE", ""), ("EEM", ""), ("ARKK", ""),
    # Indian large caps
    ("RELIANCE", "NSE"), ("TCS", "NSE"), ("HDFCBANK", "NSE"), ("INFY", "NSE"),
    ("ICICIBANK", "NSE"), ("SBIN", "NSE"), ("ITC", "NSE"), ("TATAMOTORS", "NSE"),
    # Indices and macro
    ("NIFTY", "NSE"), ("SPX", "SP"), ("DXY", "TVC"), ("GOLD", "TVC"),
]

INTERVALS = ["1d", "4h"]


def evaluate(sym: str, exch: str, interval: str, cfg: CapitalConfig,
             models, do_calibrate: bool = True) -> dict | None:
    """Run the full pipeline on one instrument/interval."""
    label = f"{exch}:{sym}" if exch else sym
    try:
        md = fetch_ohlcv(sym, interval, exch)
        if md.bars < 250:
            return {"label": label, "interval": interval, "status": "skip",
                    "reason": f"only {md.bars} bars"}
        f = build_features(md.df.tail(1200), interval, sym)

        _, sigs = evaluate_all(f, interval, sym)
        con = compute_consensus(f, interval, sym)
        rk = compute_risk_levels(f, con.direction)
        voting = [(a, b) for a, b in sigs if b.available and abs(b.score) >= 0.15]

        path = consensus_series(f, models)
        calib = calibrate(f, models, horizon=10) if do_calibrate else {}

        target_pct = (abs(rk.take_profit - rk.entry) / rk.entry * 100) if rk.entry else float("nan")
        stop_dist = abs(rk.entry - rk.stop_loss)
        notional = ((cfg.capital * cfg.risk_pct / 100.0) / stop_dist * rk.entry) if stop_dist > 0 else 0.0

        conf = score_trade(con, f, voting, risk_reward=rk.risk_reward, score_path=path,
                           target_move_pct=target_pct, asset_class=md.symbol.asset_class,
                           calibration=calib, notional_quote=notional)
        pos = build_position(label, conf.direction, rk.entry, rk.stop_loss,
                             rk.take_profit, cfg, conf.size_multiplier)

        return {
            "label": label, "interval": interval, "asset_class": md.symbol.asset_class,
            "status": "ok", "direction": conf.direction, "grade": conf.grade,
            "confidence": conf.score, "verdict": conf.verdict,
            "consensus": con.score, "agreement": con.agreement,
            "families": next((c.raw.get("agreeing_families", 0) for c in conf.components
                              if c.name == "Family diversity"), 0),
            "tradeable": pos.tradeable, "position": pos, "confidence_report": conf,
            "levels": rk, "price": con.price,
            "veto": conf.vetoes[0] if conf.vetoes else "",
            "blocker": pos.reasons[0] if (not pos.tradeable and pos.reasons) else "",
            "calibrated": calib.get("stronger_signal_paid_more"),
        }
    except Exception as exc:
        return {"label": label, "interval": interval, "status": "error",
                "reason": f"{type(exc).__name__}: {exc}"[:90]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=50_000)
    ap.add_argument("--currency", default="INR")
    ap.add_argument("--risk", type=float, default=1.0)
    ap.add_argument("--max-exposure", type=float, default=25.0)
    ap.add_argument("--intervals", default=",".join(INTERVALS))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--no-calibrate", action="store_true")
    a = ap.parse_args()

    cfg = CapitalConfig(capital=a.capital, currency=a.currency, risk_pct=a.risk,
                        max_position_pct=a.max_exposure)
    models = get_registry().all()
    intervals = [s.strip() for s in a.intervals.split(",") if s.strip()]
    jobs = [(s, e, iv) for s, e in UNIVERSE for iv in intervals]

    print(f"Universe scan — {len(UNIVERSE)} instruments × {len(intervals)} intervals "
          f"= {len(jobs)} candidates")
    print(f"Capital {a.currency} {cfg.capital:,.0f} · risk {cfg.risk_pct}% "
          f"(= {a.currency} {cfg.capital * cfg.risk_pct / 100:,.0f}) · "
          f"exposure cap {cfg.max_position_pct:.0f}%")
    print(f"{len(models)} models per candidate\n")

    t0 = time.time()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures = {pool.submit(evaluate, s, e, iv, cfg, models, not a.no_calibrate): (s, e, iv)
                   for s, e, iv in jobs}
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            r = fut.result()
            done += 1
            if r:
                results.append(r)
            if done % 20 == 0:
                print(f"  … {done}/{len(jobs)} ({time.time() - t0:.0f}s)", flush=True)

    ok = [r for r in results if r["status"] == "ok"]
    actionable = [r for r in ok if r["tradeable"]]
    signalled = [r for r in ok if r["verdict"] != "STAND ASIDE"]
    errors = [r for r in results if r["status"] == "error"]

    elapsed = time.time() - t0
    print(f"\nScanned {len(ok)} candidates in {elapsed:.0f}s "
          f"({len(errors)} data failures)\n")

    print("=" * 108)
    print(f"ACTIONABLE — signalled, survived every veto, and executable at "
          f"{a.currency} {cfg.capital:,.0f}")
    print("=" * 108)
    if not actionable:
        print("  none")
    else:
        actionable.sort(key=lambda r: -r["confidence"])
        print(f"  {'instrument':>18} {'iv':>4} {'dir':>5} {'gr':>3} {'conf':>5} {'fam':>4} "
              f"{'agree':>6}  position")
        for r in actionable:
            p = r["position"]
            print(f"  {r['label']:>18} {r['interval']:>4} {r['direction']:>5} {r['grade']:>3} "
                  f"{r['confidence']:5.0f} {r['families']:4d} {r['agreement']:5.0%}  "
                  f"{p.quantity:.6g} {p.units_label}, "
                  f"deploy {a.currency} {p.capital_required:,.0f}, "
                  f"risk {a.currency} {p.risk_amount:,.0f}, "
                  f"reward {a.currency} {p.reward_amount:,.0f}")

    blocked = [r for r in signalled if not r["tradeable"]]
    if blocked:
        print(f"\n{'-' * 108}")
        print("SIGNALLED but not executable at this capital")
        print(f"{'-' * 108}")
        blocked.sort(key=lambda r: -r["confidence"])
        for r in blocked[:12]:
            print(f"  {r['label']:>18} {r['interval']:>4} {r['direction']:>5} "
                  f"{r['grade']:>3} {r['confidence']:5.0f}  {r['blocker'][:70]}")

    print(f"\n{'-' * 108}")
    print("WHY THE REST WERE REJECTED")
    print(f"{'-' * 108}")
    reasons: dict[str, int] = {}
    for r in ok:
        if r["verdict"] == "STAND ASIDE":
            key = (r["veto"].split("—")[0].split(":")[0].strip()[:60] or "unspecified")
            reasons[key] = reasons.get(key, 0) + 1
    for reason, n in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  {n:4d}  {reason}")

    print(f"\n  Totals: {len(ok)} scanned · {len(signalled)} signalled · "
          f"{len(actionable)} actionable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
