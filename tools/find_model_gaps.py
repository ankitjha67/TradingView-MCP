"""
Find published strategies the library does not implement.

    python tools/find_model_gaps.py                 # ranked gaps
    python tools/find_model_gaps.py --covered       # what is already implemented
    python tools/find_model_gaps.py --categories    # structural coverage by family

Two sources are compared. The library carries a ``research`` citation on all
311 models — author, year, journal. The replication catalogue synced from
paperswithbacktest/awesome-systematic-trading carries 61 published strategies
that were independently replicated over their own full history, each with a
Sharpe *and* a t-statistic, selected at t >= 1.96 over at least ten years.

Matching is deliberately loose. A citation reads "Bollerslev (1986),
'Generalized Autoregressive Conditional Heteroskedasticity'" and a catalogue
row reads "The Investment CAPM"; there is no shared identifier, so the
comparison is over distinctive title words with stop-words and journal
furniture removed. It will occasionally call a match where the underlying idea
differs, so the output is a shortlist to read, not a work order.

Ranking is by the catalogue's own t-statistic rather than its Sharpe. A Sharpe
of 3.39 over 23 years and one over 16 months are not the same claim, and the
t-statistic is the figure that already accounts for the difference.

Two caveats matter enough to be in the output, not just the docs.

*Shape.* Most high-t catalogue entries cannot be expressed here at all. This
engine evaluates one instrument's bar series — ``score(f) -> Series``. A size
effect, a most-diversified portfolio or a cross-sectional factor needs a
universe; an annuity or labour-income study needs data that is not a price.
Drafting single-instrument approximations of those would recreate exactly the
proxy-models-voting-anyway failure the library was rebuilt to remove, so they
are labelled rather than queued.

*Provenance.* The catalogue measures each Sharpe "on each strategy's own active
window, not on a common calendar", so its headline can exceed what the source
page reports for the full backtest. Spot-checked: The Investment CAPM agrees
exactly (1.80 against 1.8 over 36 years), while the top-ranked entry by
t-statistic does not — catalogue 3.39 against 0.81 on its own page, a
fourfold difference. ``--verify`` re-reads the source pages so a candidate is
not promoted on a number its own publisher contradicts.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

CATALOGUE = ROOT / "data" / "replication_catalogue.json"

# What the engine can express is one instrument's bar series. Anything needing a
# peer universe, a portfolio, or non-price data is out of shape regardless of
# how strong its evidence is.
_NEEDS_UNIVERSE = (
    "cross-section", "cross section", "size effect", "value and size",
    "beta and size", "diversified portfolio", "portfolio optimization",
    "portfolio optimisation", "risk parity", "factor investing", "frontier",
    "emerging", "universe", "stock risk premia", "large and small",
    "capm", "market inefficiencies", "equity data",
)
_NEEDS_NON_MARKET = (
    "annuity", "annuities", "labor income", "labour income", "consumption",
    "pension", "demographic", "auction", "macro data", "real-time macro",
    "media tone", "sentiment", "news",
)
_PORTFOLIO_LEVEL = (
    "allocation", "asset allocation", "tactical", "rebalanc", "reserves",
    "shares in", "closed end fund", "covered call closed",
)


def shape(name: str) -> str:
    """Can this engine express the strategy at all?"""
    n = (name or "").lower()
    if any(k in n for k in _NEEDS_NON_MARKET):
        return "needs non-market data"
    if any(k in n for k in _NEEDS_UNIVERSE):
        return "needs a universe"
    if any(k in n for k in _PORTFOLIO_LEVEL):
        return "portfolio-level"
    return "single-instrument"

# Words that appear in almost every finance title and carry no signal about
# which strategy is meant.
_STOP = {
    "the", "a", "an", "of", "in", "on", "for", "and", "or", "to", "from",
    "with", "by", "at", "is", "are", "does", "do", "how", "what", "why",
    "evidence", "study", "analysis", "returns", "return", "market", "markets",
    "stock", "stocks", "asset", "assets", "portfolio", "portfolios", "risk",
    "trading", "strategy", "strategies", "investment", "investing", "new",
    "using", "based", "approach", "model", "models", "effect", "effects",
    "journal", "review", "finance", "financial", "economics", "econometrics",
    "quarterly", "vol", "no", "pp", "et", "al", "their", "there", "between",
    "cross", "section", "empirical", "test", "tests", "some", "more", "than",
}


def _tokens(text: str) -> set:
    words = re.findall(r"[a-z]{3,}", (text or "").lower())
    return {w for w in words if w not in _STOP}


def load_catalogue() -> list:
    if not CATALOGUE.exists():
        print(f"No catalogue at {CATALOGUE}. Run:\n"
              f"  python tools/sync_replication_catalogue.py", file=sys.stderr)
        return []
    return json.loads(CATALOGUE.read_text(encoding="utf-8"))["strategies"]


def library_models() -> list:
    from tradingview_mcp.core.quant.registry import get_registry
    return get_registry().all()


def match(entry: dict, models: list, threshold: float = 0.34):
    """Best library model for a catalogue entry, by distinctive-word overlap."""
    want = _tokens(entry["name"])
    if not want:
        return None, 0.0
    best, score = None, 0.0
    for m in models:
        have = _tokens(f"{m.name} {getattr(m, 'research', '')} "
                       f"{getattr(m, 'description', '')}")
        if not have:
            continue
        overlap = len(want & have) / len(want)
        if overlap > score:
            best, score = m, overlap
    return (best, score) if score >= threshold else (None, score)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--covered", action="store_true", help="show matched entries")
    ap.add_argument("--categories", action="store_true", help="coverage by category")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--buildable", action="store_true",
                    help="only strategies this engine could express")
    ap.add_argument("--verify", type=int, default=0, metavar="N",
                    help="re-read N source pages and flag Sharpes that disagree")
    a = ap.parse_args()

    rows = load_catalogue()
    if not rows:
        return 1
    models = library_models()

    if a.categories:
        by_cat = Counter(m.category for m in models)
        avail = Counter()
        for m in models:
            avail[m.category] += 0
        print(f"{len(models)} models across {len(by_cat)} categories\n")
        print(f"  {'category':28s} {'models':>7} {'families':>9}")
        fams = {}
        for m in models:
            fams.setdefault(m.category, set()).add(m.family)
        for cat, n in by_cat.most_common():
            print(f"  {cat:28s} {n:>7} {len(fams.get(cat, ())):>9}")
        print("\nCatalogue entries by asset class (what published work exists):")
        for asset, n in Counter(r["asset_class"] for r in rows).most_common():
            print(f"  {asset:28s} {n:>7}")
        return 0

    matched, gaps = [], []
    for entry in rows:
        model, score = match(entry, models)
        (matched if model else gaps).append((entry, model, score))

    if a.covered:
        print(f"{len(matched)} of {len(rows)} catalogue entries look implemented\n")
        for entry, model, score in sorted(matched, key=lambda x: -x[0]["t_stat"]):
            print(f"  t={entry['t_stat']:5.1f}  {entry['name'][:52]:52s}")
            print(f"           -> {model.name} ({score:.0%} overlap)")
        return 0

    if a.verify:
        from tradingview_mcp.core.research import read_url
        print(f"Re-reading {a.verify} source pages to check the catalogue's "
              f"own figures against them.")
        print()
        print(f"  {'strategy':40s} {'cat SR':>7} {'page SR':>8}  agreement")
        for entry, _, _ in sorted(gaps, key=lambda x: -x[0]["t_stat"])[:a.verify]:
            doc = read_url(entry["url"])
            page = None
            if doc.ok:
                m = re.search(r"Sharpe ratio\s*\n+\s*(-?[\d.]+)", doc.text)
                if m:
                    page = float(m.group(1))
            if page is None:
                verdict = "page not readable"
            elif abs(page - entry["sharpe"]) <= 0.15:
                verdict = "agrees"
            else:
                verdict = f"DISAGREES by {abs(page - entry['sharpe']):.2f}"
            print(f"  {entry['name'][:40]:40s} {entry['sharpe']:7.2f} "
                  f"{str(page) if page is not None else '-':>8}  {verdict}")
        return 0

    if a.buildable:
        gaps = [g for g in gaps if shape(g[0]["name"]) == "single-instrument"]

    gaps.sort(key=lambda x: -x[0]["t_stat"])
    print(f"{len(gaps)} of {len(rows)} catalogue strategies have no obvious "
          f"counterpart in the {len(models)}-model library.")
    print("Ranked by the catalogue's t-statistic — the evidence behind the "
          "claim, not the size of it.\n")
    by_shape = Counter(shape(g[0]["name"]) for g in gaps)
    print("  shape of the gap:")
    for k, n in by_shape.most_common():
        print(f"    {n:3d}  {k}")
    print()
    print(f"  {'t':>5} {'SR':>5} {'yrs':>4}  {'shape':22s} strategy")
    for entry, _, _ in gaps[:a.top]:
        print(f"  {entry['t_stat']:5.1f} {entry['sharpe']:5.2f} "
              f"{entry['years']:4.0f}  {shape(entry['name']):22s} "
              f"{entry['name'][:52]}")
    print(f"\n  {entry['url'] if gaps else ''}"[:100])
    print("\nMatching is by distinctive title words, so treat this as a "
          "shortlist to read rather than a work order.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
