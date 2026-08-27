"""
Pull the replication catalogue out of awesome-systematic-trading into JSON.

    python tools/sync_replication_catalogue.py            # fetch and save
    python tools/sync_replication_catalogue.py --show     # print what is stored
    python tools/sync_replication_catalogue.py --compare  # against our library

paperswithbacktest/awesome-systematic-trading is a bibliography, not a package:
111 libraries, 55 books, and a generated table of paper replications. There is
no code in it to run and nothing to import. What it does carry, and what this
script extracts, is two things worth having.

**A yardstick.** Its table publishes Sharpe *and* t-statistic for every entry,
selected at t >= 1.96 over at least ten years, with the blunt note that half
its 1,687 replications fail that bar. Those published pairs let us verify the
relationship t = annualised Sharpe x sqrt(years) against real data before
trusting it in our own backtester — see SIGNIFICANCE_T in backtest.py.

**A reference set.** Knowing what a published, independently replicated
strategy actually scores is the only way to judge whether our own numbers are
plausible. The top equity replication there manages Sharpe 1.89 over 37 years.
A model here reporting Sharpe 8 over six days is not four times better.

The catalogue is markdown, so this parses the generated table rather than
pretending an API exists. If the upstream format changes the parse will find
nothing and say so, rather than silently storing an empty file.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

SOURCE = ("https://raw.githubusercontent.com/paperswithbacktest/"
          "awesome-systematic-trading/main/README.md")
OUT = ROOT / "data" / "replication_catalogue.json"

# | [Name](url) | `1.89` | `11.4` | `6.4%` | `37` |
ROW = re.compile(
    r"^\|\s*\[(?P<name>.+?)\]\((?P<url>[^)]+)\)\s*\|"
    r"\s*`(?P<sharpe>-?[\d.]+)`\s*\|"
    r"\s*`(?P<t>-?[\d.]+)`\s*\|"
    r"\s*`(?P<vol>[\d.]+)%`\s*\|"
    r"\s*`(?P<years>[\d.]+)`\s*\|")


def fetch(url: str = SOURCE) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "quant-desk"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse(md: str) -> list[dict]:
    """Walk the Strategies section, tagging each row with its asset class."""
    rows, asset = [], ""
    in_strategies = False
    for line in md.splitlines():
        if line.startswith("# "):
            in_strategies = line.strip() == "# Strategies"
            continue
        if not in_strategies:
            continue
        if line.startswith("## "):
            asset = line[3:].strip()
            continue
        m = ROW.match(line)
        if m:
            rows.append({
                "name": m["name"].strip(),
                "url": m["url"].strip(),
                "asset_class": asset,
                "sharpe": float(m["sharpe"]),
                "t_stat": float(m["t"]),
                "volatility_pct": float(m["vol"]),
                "years": float(m["years"]),
            })
    return rows


def verify_relationship(rows: list[dict]) -> dict:
    """
    Check t == sharpe * sqrt(years) on the catalogue's own published numbers.

    This is the point of storing the table. If the identity holds on 60-odd
    independently replicated strategies, the same arithmetic is sound in our
    backtester; if upstream ever changes convention, this stops agreeing and
    we find out here rather than by trusting a wrong number downstream.
    """
    errs = [abs(r["sharpe"] * math.sqrt(r["years"]) - r["t_stat"]) for r in rows]
    return {"rows": len(errs),
            "max_abs_error": round(max(errs), 3) if errs else None,
            "mean_abs_error": round(sum(errs) / len(errs), 4) if errs else None,
            "holds": bool(errs) and max(errs) < 0.15}


def load() -> dict:
    if not OUT.exists():
        return {}
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def compare_to_library(rows: list[dict]) -> None:
    """Put our reported Sharpes next to independently replicated ones."""
    from tradingview_mcp.core.quant.registry import get_registry

    reg = get_registry()
    by_asset: dict[str, list[dict]] = {}
    for r in rows:
        by_asset.setdefault(r["asset_class"], []).append(r)

    print("Published replications, by asset class "
          "(these are the numbers real papers achieve):\n")
    print(f"  {'asset class':18s} {'n':>3} {'best SR':>8} {'median SR':>10} "
          f"{'best t':>7} {'median yrs':>11}")
    for asset, group in sorted(by_asset.items()):
        srs = sorted(r["sharpe"] for r in group)
        yrs = sorted(r["years"] for r in group)
        print(f"  {asset:18s} {len(group):>3} {max(srs):>8.2f} "
              f"{srs[len(srs) // 2]:>10.2f} "
              f"{max(r['t_stat'] for r in group):>7.1f} "
              f"{yrs[len(yrs) // 2]:>11.0f}")

    all_sr = [r["sharpe"] for r in rows]
    print(f"\n  Across all {len(rows)} entries: best Sharpe {max(all_sr):.2f}, "
          f"median {sorted(all_sr)[len(all_sr) // 2]:.2f}.")
    print(f"  Every one is measured over {min(r['years'] for r in rows):.0f}+ years "
          f"and clears t = 1.96.\n")
    print(f"  Our library holds {len(reg.all())} models across "
          f"{len(reg.categories())} categories. Their backtest Sharpes are now "
          f"reported with a t-statistic on the same convention, so the two are "
          f"comparable — and a six-day window will not clear the bar however "
          f"good the ratio looks.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true", help="print the stored catalogue")
    ap.add_argument("--compare", action="store_true", help="set against our library")
    ap.add_argument("--url", default=SOURCE)
    a = ap.parse_args()

    if a.show or a.compare:
        data = load()
        if not data:
            print("Nothing stored yet — run without --show first.", file=sys.stderr)
            return 1
        rows = data["strategies"]
        if a.compare:
            compare_to_library(rows)
            return 0
        print(f"{len(rows)} replications from {data['source']}\n")
        print(f"  {'asset':16s} {'SR':>5} {'t':>6} {'yrs':>4}  name")
        for r in rows:
            print(f"  {r['asset_class']:16s} {r['sharpe']:5.2f} {r['t_stat']:6.1f} "
                  f"{r['years']:4.0f}  {r['name'][:60]}")
        return 0

    print(f"fetching {a.url}")
    rows = parse(fetch(a.url))
    if not rows:
        print("Parsed zero rows — the upstream table format has probably changed. "
              "Nothing written.", file=sys.stderr)
        return 1

    check = verify_relationship(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": a.url,
        "note": ("Curated by paperswithbacktest/awesome-systematic-trading. Each "
                 "row is a published paper replicated over its own full history; "
                 "Sharpe ratios are gross of costs and measured on each "
                 "strategy's own active window."),
        "significance_check": check,
        "strategies": rows,
    }, indent=1), encoding="utf-8")

    print(f"{len(rows)} replications -> {OUT}")
    print(f"t = SR x sqrt(years) holds: {check['holds']} "
          f"(max error {check['max_abs_error']}, mean {check['mean_abs_error']})")
    if not check["holds"]:
        print("  WARNING: the identity no longer reproduces upstream's own "
              "numbers. Check before relying on t-stats downstream.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
