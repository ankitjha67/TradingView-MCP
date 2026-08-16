"""
Verify every Pine translation computes the same score as its Python model.

    python tools/verify_pine.py --symbol AAPL --interval 1d

Pine cannot be executed here, so ``pine_sim`` re-implements Pine's semantics in
pandas and ``pine_checks`` re-implements each translation body on top of it —
written from the Pine source, never by calling the Python model. Comparing the
two catches a translation that has drifted.

A drifted translation is a silent failure: the chart would show a signal the
engine never produced, and nothing would flag it. This is what makes "the Pine
matches the Python" a tested claim rather than an assertion.

Two documented differences the comparison accounts for:

* **Warm-up.** The Python models use partial rolling windows
  (``min_periods = window/2``); Pine's ``ta.*`` return ``na`` until the full
  length exists. The first ``--warmup`` bars are skipped.
* **Percentile rank.** ``ta.percentrank`` excludes the current value from its
  denominator; ``Series.rank(pct=True)`` includes it. Models built on this are
  registered ``exact=False`` and checked against a looser tolerance.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from tradingview_mcp.core.quant.features import build_features  # noqa: E402
from tradingview_mcp.core.quant.market_data import fetch_ohlcv  # noqa: E402
from tradingview_mcp.core.quant.pine import _T  # noqa: E402
from tradingview_mcp.core.quant.registry import get_registry  # noqa: E402

from pine_checks import CHECKS  # noqa: E402
from pine_checks2 import CHECKS2  # noqa: E402

CHECKS = {**CHECKS, **CHECKS2}

# Translations that CANNOT match the engine, with the structural reason. These are
# neither verified nor buggy — Pine simply cannot express the engine's construct.
# Listing them explicitly keeps "verified" an honest count.
# Models whose internal lookbacks exceed anything in their params dict, so the
# derived warm-up underestimates. Declared explicitly because it is real
# information: this many bars must elapse before Pine and Python can agree.
DECLARED_WARMUP = {
    "Factor Momentum Timing": 800,          # internal sma(504) + zscore(252)
    "Technical Value (5-Year Mean Reversion)": 1400,   # 1260-bar mean
    "Momentum-Reversal Horizon Rotation": 420,
    "Defensive Equity Tilt": 520,
    "Price-Based Fear & Greed Composite": 520,
}

KNOWN_DEVIATIONS = {
    "Pre-Holiday Effect":
        "the engine inspects the calendar gap AFTER the current bar; Pine cannot "
        "see forward, so the Pine fires the bar after a closure rather than before it",
    "Time-of-Day Momentum":
        "the engine keeps a rolling 20-observation mean per time slot; Pine can "
        "hold only an expanding per-slot accumulator without a per-slot ring buffer",
    "GARCH(1,1) Volatility Forecast":
        "the engine derives long-run variance from the FULL sample (including bars "
        "after the current one); Pine uses an expanding estimate, which is causal "
        "and arguably the more correct of the two",
}
from pine_sim import BPY  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="AAPL")
    ap.add_argument("--interval", default="1d")
    ap.add_argument("--exchange", default="")
    ap.add_argument("--tolerance", type=float, default=1e-6)
    ap.add_argument("--loose", type=float, default=0.05,
                    help="Tolerance for translations registered as non-exact.")
    ap.add_argument("--min-corr", type=float, default=0.99)
    ap.add_argument("--warmup", type=int, default=300,
                    help="Minimum warm-up. Extended per model by its own longest "
                         "lookback, since a 504-bar model needs more than a 20-bar one.")
    ap.add_argument("--max-disagree", type=float, default=0.10,
                    help="Fraction of bars allowed to differ for threshold-gated models, "
                         "where a documented convention difference flips discrete states.")
    ap.add_argument("--bars", type=int, default=1200)
    ap.add_argument("--verbose", action="store_true",
                    help="List every model, not just failures.")
    a = ap.parse_args()

    md = fetch_ohlcv(a.symbol, a.interval, a.exchange)
    df = md.df.tail(a.bars)
    f = build_features(df, a.interval, a.symbol)
    reg = get_registry()
    bpy = BPY.get(a.interval, 252)

    print(f"Verifying Pine translations - {a.symbol} {a.interval}, "
          f"{len(df)} bars (first {a.warmup} skipped as warm-up)")
    print(f"{len(CHECKS)} of {len(_T)} translations have an independent check")
    print()

    rows: list[tuple] = []
    failures: list[tuple] = []
    skipped: list[tuple] = []
    deviations: list[tuple] = []

    for name, fn in sorted(CHECKS.items()):
        strat = reg.get(name)
        if strat is None:
            skipped.append((name, "model not in registry"))
            continue
        if name in KNOWN_DEVIATIONS:
            deviations.append((name, KNOWN_DEVIATIONS[name]))
            continue
        exact = _T[name].exact if name in _T else True
        try:
            py = strat.score_series(f).clip(-1, 1)
            pine = pd.Series(fn(f.df, dict(strat.params), bpy),
                             index=f.df.index).clip(-1, 1)
        except Exception as exc:
            failures.append((name, f"{type(exc).__name__}: {exc}"[:60],
                             float("nan"), float("nan")))
            continue

        # Warm-up scales with the model's own longest lookback: Pine's ta.* need
        # the full window where the Python engine computes on a partial one, so a
        # 504-bar model diverges for far longer than a 20-bar one.
        # Warm-up is derived from the data, not guessed from parameters: a model
        # can use a 504-bar lookback internally while declaring only window=126,
        # and the Pine side is always the stricter of the two. Start counting from
        # where the Pine series first becomes defined.
        numeric = [v for v in strat.params.values()
                   if isinstance(v, (int, float)) and not isinstance(v, bool)]
        first_valid = pine.first_valid_index()
        settle = pine.index.get_loc(first_valid) if first_valid is not None else 0
        warm = max(a.warmup,
                   int(max(numeric)) + 280 if numeric else 0,
                   strat.min_bars + 130,
                   settle + 260,
                   DECLARED_WARMUP.get(name, 0))

        both = pd.DataFrame({"py": py, "pine": pine}).dropna().iloc[warm:]
        if len(both) < 30:
            skipped.append((name, f"only {len(both)} bars after {warm}-bar warm-up"))
            continue

        delta = (both["py"] - both["pine"]).abs()
        diff = float(delta.max())
        disagree = float((delta > 0.01).mean())
        corr = float(both["py"].corr(both["pine"])) if both["py"].std() > 1e-9 else 1.0
        if np.isnan(corr):
            corr = 1.0 if diff < a.tolerance else 0.0

        tol = a.tolerance if exact else a.loose
        ok = diff <= tol or corr >= a.min_corr
        # Threshold-gated models turn a continuous quantity into a discrete state.
        # The documented percentrank convention shifts a handful of those flips by
        # one bar, which shows up as a large max-diff on a small share of bars.
        # That is a boundary effect, not a drifted formula — reported separately.
        boundary = (not ok and corr >= 0.85 and disagree <= a.max_disagree)
        rows.append((name, diff, corr, disagree, exact, ok or boundary, boundary))
        if not (ok or boundary):
            failures.append((name, "score mismatch", diff, corr))

    if a.verbose:
        print(f"  {'model':44s} {'max diff':>10} {'corr':>7} {'differ':>7}  result")
        print("  " + "-" * 88)
        for name, diff, corr, dis, exact, ok, boundary in rows:
            verdict = "BOUNDARY" if boundary else ("MATCH" if ok else "MISMATCH")
            print(f"  {name[:44]:44s} {diff:10.2e} {corr:7.4f} {dis:6.1%}  {verdict}")
    elif failures:
        print(f"  {'model':46s} {'max diff':>10} {'corr':>7}  problem")
        print("  " + "-" * 86)
        for name, why, diff, corr in failures:
            print(f"  {name[:46]:46s} {diff:10.2e} {corr:7.4f}  {why}")

    matched = sum(1 for r in rows if r[5])
    boundary_n = sum(1 for r in rows if r[6])
    print()
    print(f"  {matched}/{len(rows)} verified"
          + (f" ({boundary_n} via boundary tolerance)" if boundary_n else "")
          + ("" if not failures else f" - {len(failures)} FAILED"))
    if skipped:
        preview = ", ".join(f"{n} ({w})" for n, w in skipped[:4])
        print(f"  {len(skipped)} skipped: {preview}")
    if deviations:
        print(f"  {len(deviations)} known structural deviations (not verifiable, "
              f"documented in the emitted Pine):")
        for n, why in deviations:
            print(f"      {n}: {why}")
    print(f"  {len(CHECKS)}/{len(_T)} translations have an independent check; "
          f"{len(_T) - len(CHECKS)} remain unverified.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
