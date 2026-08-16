"""
Regenerate STRATEGY_CATALOG.md from the live registry.

    python tools/generate_catalog.py

The catalog is generated rather than hand-written so it cannot drift from the
code. If a model is renamed, retired or added, re-run this and the document is
correct by construction.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from tradingview_mcp.core.quant.registry import get_registry  # noqa: E402

NEED_LABEL = {
    "ohlc": "price only", "volume": "volume", "cross_section": "peer universe",
    "benchmark": "benchmark series", "fundamentals": "fundamentals",
    "options_chain": "options chain", "order_book": "L2 order book",
    "onchain": "on-chain / exchange", "news": "news / alt-data",
}


def main() -> int:
    reg = get_registry()
    specs = reg.specs()
    summary = reg.summary()

    price_only = [s for s in specs if set(s["needs"]) <= {"ohlc", "volume"}]
    needs_feed = [s for s in specs if not set(s["needs"]) <= {"ohlc", "volume"}]
    proxies = [s for s in specs if s["is_proxy"]]

    out: list[str] = [
        "# Strategy Catalog",
        "",
        f"_Generated {date.today().isoformat()} by `tools/generate_catalog.py`. "
        "Do not edit by hand — re-run the generator._",
        "",
        "## Summary",
        "",
        f"| | |",
        f"|---|---|",
        f"| **Total models** | {summary['total']} |",
        f"| **Categories** | {summary['categories']} |",
        f"| **Independent families** | {summary['families']} |",
        f"| **Runnable on price/volume alone** | {len(price_only)} |",
        f"| **Require an external feed** | {len(needs_feed)} |",
        f"| **Proxy implementations** | {len(proxies)} |",
        "",
        "### How to read this",
        "",
        "**Family** is the honest unit of diversification. Two models in the same family are "
        "variations on one idea, not two independent opinions — the consensus engine splits a "
        "single vote between them. "
        f"{summary['total']} models across {summary['families']} families means roughly "
        f"{summary['families']} genuinely distinct views.",
        "",
        "**Needs** is what the model requires to run honestly. A model needing an options chain "
        "or a peer universe reports as *unavailable* when that feed is absent instead of "
        "silently substituting a price indicator and voting anyway.",
        "",
        "**Proxy** marks a model that approximates its published method using substituted data — "
        "for example estimating order-flow imbalance from bar volume because tick data is not "
        "available. Proxies are labelled everywhere they appear and are weighted at 40% of a "
        "full vote in the consensus.",
        "",
        "---",
        "",
        "## Models by category",
        "",
    ]

    out.append("| Category | Models | Families | Price-only | Needs feed | Proxies |")
    out.append("|---|---:|---:|---:|---:|---:|")
    for cat in sorted(summary["by_category"], key=lambda c: -summary["by_category"][c]):
        rows = [s for s in specs if s["category"] == cat]
        fams = len({s["family"] for s in rows})
        po = sum(1 for s in rows if set(s["needs"]) <= {"ohlc", "volume"})
        px = sum(1 for s in rows if s["is_proxy"])
        out.append(f"| {cat} | {len(rows)} | {fams} | {po} | {len(rows) - po} | {px} |")

    out += ["", "---", ""]

    for cat in sorted(summary["by_category"], key=lambda c: -summary["by_category"][c]):
        rows = sorted((s for s in specs if s["category"] == cat), key=lambda s: s["name"])
        out += [f"## {cat}", "", f"_{len(rows)} models · "
                f"{len({s['family'] for s in rows})} families_", ""]
        for i, s in enumerate(rows, 1):
            flags = []
            if s["is_proxy"]:
                flags.append("**PROXY**")
            needs = ", ".join(NEED_LABEL.get(n, n) for n in s["needs"])
            out.append(f"{i}. **{s['name']}**{' — ' + ' '.join(flags) if flags else ''}")
            out.append(f"   - {s['description']}")
            out.append(f"   - *Research:* {s['research']}")
            out.append(f"   - *Needs:* {needs} · *Horizon:* {s['horizon']} · "
                       f"*Min bars:* {s['min_bars']} · *Family:* `{s['family']}`")
            if s["is_proxy"] and s["proxy_note"]:
                out.append(f"   - *Proxy note:* {s['proxy_note']}")
            out.append("")
        out.append("---")
        out.append("")

    out += [
        "## Models requiring an external data feed",
        "",
        f"{len(needs_feed)} models need something beyond the symbol's own price history. "
        "They are implemented and registered, and activate automatically once the "
        "corresponding feed is wired into `FeatureSet.meta`. Until then they report as "
        "unavailable rather than voting on a substitute.",
        "",
        "| Feed | Models | What it unlocks |",
        "|---|---:|---|",
    ]
    feed_desc = {
        "cross_section": "Cross-sectional factors, pairs trading, portfolio allocation, dispersion",
        "benchmark": "Beta, residual momentum, relative strength, correlation regime",
        "fundamentals": "Value, quality, accruals, insider and short-interest signals",
        "options_chain": "Implied vol surface, skew, gamma exposure, variance premium",
        "order_book": "True order-flow imbalance, L2 depth, DeepLOB",
        "onchain": "MVRV, SOPR, NVT, funding rates, exchange flows",
        "news": "News tone, search attention, social sentiment, macro calendar",
    }
    for feed, desc in feed_desc.items():
        n = sum(1 for s in needs_feed if feed in s["needs"])
        if n:
            out.append(f"| `{feed}` | {n} | {desc} |")

    out += [
        "",
        "---",
        "",
        "## Proxy implementations",
        "",
        f"These {len(proxies)} models approximate their published method. Each states what was "
        "substituted. They are down-weighted to 40% of a full vote.",
        "",
    ]
    for s in sorted(proxies, key=lambda x: x["name"]):
        out.append(f"- **{s['name']}** ({s['category']}) — {s['proxy_note']}")

    out += [
        "",
        "---",
        "",
        "## Deliberate omissions",
        "",
        "Some widely-circulated strategies are **not** included, because including them would "
        "mean presenting a discredited or unfalsifiable claim as a signal:",
        "",
        "- **Stock-to-Flow (PlanB)** — the model's central prediction failed out of sample after "
        "2021 and its statistical basis (regression on a deterministic time trend) is unsound.",
        "- **Elliott Wave / Gann angles** — no falsifiable rule set; wave counts are assigned "
        "after the fact and are not reproducible between analysts.",
        "- **Fixed-ratio martingale sizing** — mathematically guarantees ruin at a finite horizon.",
        "",
        "_Not investment advice. Model output is for research and analysis._",
        "",
    ]

    path = ROOT / "STRATEGY_CATALOG.md"
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"Wrote {path} — {summary['total']} models, {summary['categories']} categories, "
          f"{summary['families']} families")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
