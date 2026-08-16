"""
Check which models an API key can actually use — not just address.

    # verify the curated list for the saved provider
    python tools/verify_llm_models.py

    # verify everything the key can reach, not just the curated list
    python tools/verify_llm_models.py --provider nvidia --all

    # emit a Python tuple ready to paste into llm.py
    python tools/verify_llm_models.py --provider nvidia --all --emit

A provider's /v1/models endpoint answers a different question from the one that
matters. It says which model names the key may address. It does not say which
of them can hold a conversation. NVIDIA's catalog mixes embedding, reranking,
OCR, safety-classifier and translation endpoints in with the chat models, and
most of them accept a /chat/completions call and return HTTP 200 — a safety
model replies {"User Safety": "safe"}, a translation model hands back your
prompt in another language. Both look healthy to any check based on status
codes, then produce nonsense in the dashboard.

So this asks every model a real position-sizing question with one checkable
answer, and reports only the ones that get it right.
"""
from __future__ import annotations

import argparse
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

from tradingview_mcp.core.quant.llm import (  # noqa: E402
    PROVIDERS, LLMConfig, list_models, load_config, verify_models,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="", help="default: whatever is saved")
    ap.add_argument("--all", action="store_true",
                    help="probe the whole live catalog, not just the curated list")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--emit", action="store_true",
                    help="print a Python tuple of the passing models")
    a = ap.parse_args()

    saved = load_config()
    pkey = a.provider or saved.provider
    if pkey not in PROVIDERS:
        print(f"Unknown provider {pkey!r}. Known: {', '.join(PROVIDERS)}", file=sys.stderr)
        return 1
    prov = PROVIDERS[pkey]

    # Reuse the saved key only when the provider matches, so --provider does not
    # silently send one vendor's key to another.
    key = saved.api_key if pkey == saved.provider else ""
    cfg = LLMConfig(provider=pkey, api_key=key)
    _, _, base, resolved_key = cfg.resolved()
    if prov.needs_key and not resolved_key:
        print(f"No API key for {prov.label}. Save one in the dashboard's Settings "
              f"page, or export {prov.env_var}.", file=sys.stderr)
        return 1

    if a.all:
        targets = list_models(cfg)
        if not targets:
            print(f"{base}/models returned nothing. Check the key and base URL.",
                  file=sys.stderr)
            return 1
        print(f"{prov.label}: {len(targets)} models addressable with this key")
    else:
        targets = list(prov.models) or [prov.default_model]
        print(f"{prov.label}: verifying the {len(targets)} curated models")
    print(f"(blocked as wrong-modality, not probed: {len(prov.exclude)})\n")

    def tick(done: int, total: int, rec: dict) -> None:
        mark = "PASS" if rec["usable"] else rec["status"]
        print(f"  [{done:>3}/{total}] {mark:<8} {rec['ms']//1000:>3}s  {rec['model']}",
              flush=True)

    results = verify_models(targets, cfg, workers=a.workers, progress=tick)
    usable = sorted(r["model"] for r in results if r["usable"])

    print(f"\n{'':-<70}")
    for status, n in Counter(r["status"] for r in results).most_common():
        print(f"  {status:<10} {n}")
    print(f"\n  USABLE: {len(usable)} of {len(results)}")

    bad = [r for r in results if not r["usable"] and r.get("reply")]
    if bad:
        print("\nAnswered but wrong — what they actually returned:")
        for r in sorted(bad, key=lambda r: r["model"]):
            print(f"  {r['model']:<48} {r['reply'][-60:]!r}")

    if a.emit:
        print("\n# paste into llm.py\nVERIFIED = (")
        for m in usable:
            print(f'    "{m}",')
        print(")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
