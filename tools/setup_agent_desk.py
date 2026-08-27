"""
Install the TradingAgents desk into its own virtualenv.

    python tools/setup_agent_desk.py            # create and install
    python tools/setup_agent_desk.py --check    # report status, change nothing
    python tools/setup_agent_desk.py --force    # rebuild from scratch

Why a separate environment rather than `pip install tradingagents`:

    tradingagents 0.7.0 resolves pandas to 3.0.5. This project pins
    `pandas>=2.3.1` with no upper bound, so a plain install silently upgrades
    the interpreter the quant engine runs on — 21 modules and 311 models
    written against pandas 2.x, plus a test suite that passes on it. The
    install also pulls chainlit, redis, textual and roughly forty
    opentelemetry instrumentation packages.

    None of that is a criticism of tradingagents; it is a different kind of
    program with different needs. Keeping the two apart lets each have the
    dependency tree it wants, and the cost is one subprocess call per debate —
    which already takes minutes.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv-agents"
PY = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def status() -> dict:
    out = {"venv": str(VENV), "exists": VENV.exists(),
           "python": str(PY), "python_exists": PY.exists(),
           "installed": False, "agents_pandas": "", "main_pandas": ""}
    try:
        import pandas as _pd
        out["main_pandas"] = _pd.__version__
    except Exception:
        pass
    if PY.exists():
        probe = subprocess.run(
            [str(PY), "-c",
             "import tradingagents, pandas; print(pandas.__version__)"],
            capture_output=True, text=True)
        out["installed"] = probe.returncode == 0
        out["agents_pandas"] = (probe.stdout or probe.stderr).strip()[:60]
    return out


def report(s: dict) -> None:
    mark = "yes" if s["installed"] else "no"
    print(f"  virtualenv     {s['venv']}")
    print(f"  interpreter    {'found' if s['python_exists'] else 'missing'}")
    print(f"  tradingagents  {mark}")
    if s["installed"]:
        print(f"  pandas here    {s['main_pandas']}   (quant engine)")
        print(f"  pandas there   {s['agents_pandas']}   (agent desk)")
        if s["main_pandas"] and s["agents_pandas"] and \
                s["main_pandas"].split(".")[0] != s["agents_pandas"].split(".")[0]:
            print("  -> different majors, which is exactly why they are separated.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report status only")
    ap.add_argument("--force", action="store_true", help="rebuild the venv")
    a = ap.parse_args()

    if a.check:
        print("Agent desk status:")
        report(status())
        return 0 if status()["installed"] else 1

    if a.force and VENV.exists():
        import shutil
        print(f"removing {VENV}")
        shutil.rmtree(VENV, ignore_errors=True)

    if not PY.exists():
        print(f"creating virtualenv at {VENV}")
        r = subprocess.run([sys.executable, "-m", "venv", str(VENV)])
        if r.returncode != 0:
            print("could not create the virtualenv", file=sys.stderr)
            return 1

    print("installing tradingagents (this pulls a large tree; several minutes)")
    r = subprocess.run([str(PY), "-m", "pip", "install", "--upgrade",
                        "pip", "tradingagents"])
    if r.returncode != 0:
        print("install failed", file=sys.stderr)
        return 1

    print("\nDone.")
    report(status())
    print("\nThe desk needs an LLM key. It reads OPENAI_API_KEY (or the key "
          "saved in the dashboard's Settings page) and works with any "
          "OpenAI-compatible endpoint.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
