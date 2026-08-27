"""
Draft candidate strategies from published papers and put them through the gate.

    python tools/draft_models.py --list          # what would be drafted
    python tools/draft_models.py --all           # draft every buildable gap
    python tools/draft_models.py --n 5           # draft the top 5
    python tools/draft_models.py --show <name>   # print a drafted model

Each candidate is read from its source page, expressed against the FeatureSet
API by the configured LLM, then run through ``candidate.admit`` — contract,
causality, non-degeneracy, honest DataNeed and evidence. Drafts that fail are
kept with their verdict rather than deleted, because the failures are the
useful part: they show what a fluent model gets wrong.

What this does not do is claim a passing draft is correct. The gate proves a
model is not cheating — it does not read the paper and confirm the rule was
understood. A draft that clears it is a candidate for review, and is written
to ``drafts/`` rather than into the library, where a human decision belongs.

The prompt is constrained hard on purpose. The model is given the exact
FeatureSet surface and told that anything outside it does not exist, because
the failure mode of a language model asked for a trading rule is to invent a
plausible data source — an earnings field, a peer universe, an options chain —
and produce code that reads beautifully and cannot run.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

DRAFTS = ROOT / "drafts"

API = """
ATTRIBUTES (pandas Series unless noted, never called):
  f.close f.open f.high f.low f.volume f.typical f.ret f.logret
  f.true_range f.hl_range f.obv f.trend_strength f.vol_regime
  f.n (int) f.bars_per_year (int) f.has_volume (bool) f.interval (str)

METHODS (all return a Series aligned to f.close.index):
  f.sma(p) f.ema(p) f.hull(p) f.kama(p,fast,slow) f.std(p)
  f.rsi(p=14) f.cci(p=20) f.mfi(p=14) f.stoch_k(p=14) f.williams_r(p=14)
  f.atr(p=14) f.natr(p=14) f.adx(p=14) f.drawdown()
  f.realized_vol(p=20) f.parkinson_vol(p=20) f.garman_klass_vol(p=20)
  f.rogers_satchell_vol(p=20) f.yang_zhang_vol(p=20)
  f.skew(p=60) f.kurtosis(p=60) f.hurst(p=100) f.half_life(p=100)
  f.efficiency_ratio(p=10) f.variance_ratio(q=5,p=100)
  f.volume_z(p=20) f.vwap(p=20)

TUPLE-RETURNING:
  upper, mid, lower, width, pctb = f.bollinger(p=20, k=2.0)
  upper, mid, lower = f.keltner(p=20, atr_p=14, k=2.0)
  upper, lower, mid = f.donchian(p=20)
  macd_line, signal_line, hist = f.macd(12, 26, 9)

HELPERS already imported for you:
  squash(series, scale)   -> tanh-style compression into [-1, +1]
  zscore(series, window)  -> rolling z-score
  persist(series, bars)   -> hold a signal for N bars
  band_score(series, lo, hi)
  np, pd
"""

SYSTEM = """You write one trading model for an existing Python engine.

HARD RULES — a violation makes the model unusable:

1. Use ONLY the FeatureSet API given to you. Nothing else exists. There is no
   earnings data, no peer universe, no options chain, no order book, no
   fundamentals, no external series. If the paper needs those, say so instead
   of approximating them.

2. Every calculation must be CAUSAL. The value at bar i may use only bars <= i.
   Never use .mean(), .std(), .var(), .quantile() or .rank() over the whole
   series — use .rolling(window) or .expanding(). Never use center=True. Never
   broadcast .iloc[-1] backwards. A model that fails this is silently
   worthless: it backtests beautifully and cannot be traded.

3. Return a pandas Series on f.close.index, values in [-1, +1]. Positive means
   long conviction, negative short, 0 no opinion. Magnitude is conviction, not
   position size.

4. No imports, no file or network access, no randomness, no fitting loops.

Reply with ONLY a Python class, no prose and no code fence. Exactly this shape:

class SomeName(BaseStrategy):
    name = "Human Readable Name"
    category = "<one of the given categories>"
    family = "lowercase_family_tag"
    research = "Author (year), 'Title'"
    description = "One sentence on what it measures."
    horizon = Horizon.SWING
    min_bars = 150
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        ...
        return squash(something, 1.0)
"""

CATEGORIES = ("Trend & Momentum", "Mean Reversion", "Volatility", "Regime & Risk",
              "Seasonality & Calendar", "Statistical Arbitrage", "Microstructure",
              "Macro & Allocation", "Commodity & Carry", "Rates & Credit",
              "Factor & Smart Beta", "Machine Learning")

HEADER = '''"""
Machine-drafted candidates, not yet part of the library.

Each class here was drafted from a published paper by the configured LLM and
then run through core/quant/candidate.py. Passing that gate means the model
is not cheating — it is causal, it honours the score contract, it is not
degenerate and it declares what it reads. It does NOT mean the rule matches
the paper. Nobody has checked that but the model that wrote it.

Nothing in this file is registered. Moving one into core/quant/library/ is a
human decision that should follow reading the source.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from tradingview_mcp.core.quant.base import (
    BaseStrategy, DataNeed, Horizon, Regime, band_score, persist, squash)
from tradingview_mcp.core.quant.features import FeatureSet, zscore


'''


def buildable_gaps(limit: int) -> list:
    from find_model_gaps import load_catalogue, library_models, match, shape

    models = library_models()
    out = []
    for entry in load_catalogue():
        if shape(entry["name"]) != "single-instrument":
            continue
        found, _ = match(entry, models)
        if found is None:
            out.append(entry)
    out.sort(key=lambda e: -e["t_stat"])
    return out[:limit] if limit else out


def read_source(entry: dict) -> str:
    from tradingview_mcp.core.research import read_url

    doc = read_url(entry["url"])
    if not doc.ok:
        return ""
    text = doc.text
    # The pages carry a lot of site furniture; the rule is in the middle.
    cut = text.find("## Code")
    return (text[:cut] if cut > 400 else text)[:6000]


def draft_one(entry: dict, source: str) -> str:
    from tradingview_mcp.core.quant.llm import chat, load_config

    prompt = (
        f"PAPER: {entry['name']}\n"
        f"ASSET CLASS: {entry['asset_class']}\n"
        f"PUBLISHED: Sharpe {entry['sharpe']}, t-stat {entry['t_stat']}, "
        f"{entry['years']:.0f} years\n\n"
        f"SOURCE PAGE:\n{source or '(page unreadable — work from the title)'}\n\n"
        f"AVAILABLE API:\n{API}\n\n"
        f"category must be one of: {', '.join(CATEGORIES)}\n\n"
        f"Write the model.")
    cfg = load_config()
    cfg.max_tokens = 2200
    return chat(SYSTEM, prompt, cfg)


def extract_class(text: str) -> str:
    """Pull the class out of whatever the model wrapped it in."""
    if not text:
        return ""
    body = text
    fence = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    if fence:
        body = fence.group(1)
    start = body.find("class ")
    if start < 0:
        return ""
    return body[start:].rstrip()


def compile_candidate(code: str):
    """Build the class in a namespace with the engine's helpers present."""
    import numpy as np
    import pandas as pd

    from tradingview_mcp.core.quant.base import (
        BaseStrategy, DataNeed, Horizon, Regime, band_score, persist, squash)
    from tradingview_mcp.core.quant.features import FeatureSet, zscore

    ns = {"BaseStrategy": BaseStrategy, "DataNeed": DataNeed, "Horizon": Horizon,
          "Regime": Regime, "band_score": band_score, "persist": persist,
          "squash": squash, "FeatureSet": FeatureSet, "zscore": zscore,
          "np": np, "pd": pd, "__builtins__": __builtins__}
    exec(compile(code, "<draft>", "exec"), ns)
    for obj in ns.values():
        if isinstance(obj, type) and issubclass(obj, BaseStrategy) \
                and obj is not BaseStrategy:
            return obj()
    raise ValueError("no BaseStrategy subclass in the draft")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    sys.path.insert(0, str(ROOT / "tools"))
    gaps = buildable_gaps(0 if a.all else a.n)

    if a.list:
        print(f"{len(gaps)} buildable candidates\n")
        for e in gaps:
            print(f"  t={e['t_stat']:5.1f}  {e['name'][:66]}")
        return 0

    from tradingview_mcp.core.quant.candidate import admit
    from tradingview_mcp.core.quant.features import build_features
    from tradingview_mcp.core.quant.market_data import fetch_ohlcv

    print("Verifying every draft on AAPL daily, 1200 bars.\n")
    f = build_features(fetch_ohlcv("AAPL", "1d", "").df.tail(1200), "1d", "AAPL")

    DRAFTS.mkdir(exist_ok=True)
    admitted, rejected, broken = [], [], []
    for i, entry in enumerate(gaps, 1):
        print(f"[{i}/{len(gaps)}] {entry['name'][:58]}")
        source = read_source(entry)
        try:
            code = extract_class(draft_one(entry, source))
        except Exception as exc:
            print(f"          draft failed: {type(exc).__name__}: {exc}"[:110])
            broken.append((entry["name"], f"draft: {exc}"))
            continue
        if not code:
            print("          no class in the reply")
            broken.append((entry["name"], "no class produced"))
            continue
        try:
            model = compile_candidate(code)
        except Exception as exc:
            print(f"          will not compile: {type(exc).__name__}: {exc}"[:110])
            broken.append((entry["name"], f"compile: {exc}"))
            continue

        verdict = admit(model, f)
        bad = [c.name for c in verdict.failures if c.fatal]
        print(f"          {model.name[:40]:40s} "
              f"{'ADMIT' if verdict.admitted else 'reject: ' + ', '.join(bad)}")
        (admitted if verdict.admitted else rejected).append(
            (entry, model, code, verdict))

    if admitted:
        out = DRAFTS / "candidates.py"
        out.write_text(HEADER + "\n\n".join(c for _, _, c, _ in admitted) + "\n",
                       encoding="utf-8")
        print(f"\n{len(admitted)} admitted -> {out}")

    print(f"\n{'':-<64}")
    print(f"  admitted            {len(admitted)}")
    print(f"  rejected by gate    {len(rejected)}")
    print(f"  never ran           {len(broken)}")
    if rejected:
        print("\nrejected, with the check that stopped them:")
        for entry, model, _, v in rejected:
            for c in v.failures:
                if c.fatal:
                    print(f"  {model.name[:34]:34s} {c.name}: {c.detail[:56]}")
    if admitted:
        print("\nAdmitted means not cheating — causal, in-contract, not "
              "degenerate.\nIt does not mean the rule matches the paper. "
              "Read the source before\npromoting any of these into the library.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
