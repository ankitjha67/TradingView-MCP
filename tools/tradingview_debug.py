"""
Make the TradingView desktop app readable by the chart detector.

    python tools/tradingview_debug.py --check     # diagnose, change nothing
    python tools/tradingview_debug.py --restart   # relaunch it with the flag

Chart detection speaks the Chrome DevTools Protocol on port 9222. The desktop
app is Electron — its process tree shows --type=renderer, a gpu-process and a
crashpad handler, and it identifies as --app-user-model-id=electron — so it
*can* serve CDP. It simply is not started with the switch that turns it on.

Three things were tried and ruled out before settling on a restart:

  * Passing --remote-debugging-port to a running instance. Electron holds a
    single-instance lock, so the second launch hands its arguments to the first
    process and exits. Verified: process count unchanged, port still closed.
  * A persisted setting. There is no config file carrying launch arguments.
  * An environment variable. Electron has no supported variable for arbitrary
    Chromium switches; ELECTRON_EXTRA_LAUNCH_ARGS is not a real mechanism.

So the switch must be present at a cold start, which means closing the app
first. TradingView keeps layouts server-side, so nothing local is lost — but
this does close a running application, and it is never done without --restart.

The executable is resolved through the package family name rather than the
versioned path under WindowsApps: that path contains the build number
(TradingView.Desktop_3.4.0.8149_x64__...), so hard-coding it would break at
the next update.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

PACKAGE = "TradingView.Desktop"
PORT = 9222
CDP = f"http://127.0.0.1:{PORT}/json"


def _ps(script: str, timeout: int = 60) -> str:
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                           capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def find_exe() -> str:
    """Locate TradingView.exe via package identity, not a versioned path."""
    out = _ps(f"(Get-AppxPackage -Name '*{PACKAGE}*' | "
              f"Select-Object -First 1).InstallLocation")
    if not out:
        return ""
    exe = Path(out) / "TradingView.exe"
    return str(exe) if exe.exists() else ""


def running_pids() -> list[int]:
    out = _ps("Get-Process TradingView -ErrorAction SilentlyContinue | "
              "ForEach-Object { $_.Id }")
    return [int(x) for x in out.split() if x.strip().isdigit()]


def cdp_up(timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version",
                                    timeout=timeout):
            return True
    except Exception:
        return False


def tradingview_tabs() -> list[dict]:
    try:
        with urllib.request.urlopen(CDP, timeout=4) as r:
            tabs = json.loads(r.read().decode())
    except Exception:
        return []
    return [t for t in tabs if "tradingview.com" in (t.get("url") or "")]


def check() -> int:
    exe = find_exe()
    pids = running_pids()
    print("TradingView desktop")
    print(f"  package     {PACKAGE}")
    print(f"  executable  {exe or 'NOT FOUND — is the app installed?'}")
    print(f"  running     {len(pids)} process(es)")
    print(f"  port {PORT}  {'open' if cdp_up() else 'closed'}")

    tabs = tradingview_tabs()
    print(f"  tv tabs     {len(tabs)}")
    for t in tabs[:5]:
        print(f"    - {(t.get('url') or '')[:80]}")

    if not cdp_up():
        print("\nThe detector cannot read your chart: nothing is serving CDP on "
              f"{PORT}.")
        if pids:
            print("The app is running, but was started without the debug switch. "
                  "Electron only reads it at a cold start, so it has to be "
                  "restarted:")
            print("  python tools/tradingview_debug.py --restart")
        else:
            print("The app is not running. Start it with:")
            print("  python tools/tradingview_debug.py --restart")
        return 1

    try:
        from tradingview_mcp.core.quant.monitor import read_chart_from_browser
        state = read_chart_from_browser()
    except Exception as exc:
        print(f"\nCDP is up but the detector errored: {exc}")
        return 1
    if state and state.is_valid():
        label = f"{state.exchange}:{state.symbol}" if state.exchange else state.symbol
        print(f"\nDetector reads: {label} @ {state.interval}")
        print("Chart following will work — run the monitor with no --symbol.")
        return 0
    print("\nCDP is up but no TradingView chart was found. Open one, then "
          "re-run --check.")
    return 1


def restart(force: bool) -> int:
    exe = find_exe()
    if not exe:
        print(f"Could not locate {PACKAGE}. Is the desktop app installed?",
              file=sys.stderr)
        return 1

    pids = running_pids()
    if pids and not force:
        print(f"TradingView is running ({len(pids)} processes). Restarting it is "
              "the only way to enable the debug port.\nLayouts live on "
              "TradingView's servers, so nothing local is lost.\nRe-run with "
              "--restart --force to proceed.")
        return 1

    if pids:
        print(f"closing TradingView ({len(pids)} processes)…")
        _ps("Get-Process TradingView -ErrorAction SilentlyContinue | "
            "Stop-Process -Force")
        for _ in range(20):
            if not running_pids():
                break
            time.sleep(0.5)
        if running_pids():
            print("  some processes did not exit; continuing anyway")

    print(f"launching with --remote-debugging-port={PORT}…")
    _ps(f"Start-Process -FilePath '{exe}' "
        f"-ArgumentList '--remote-debugging-port={PORT}'")

    for i in range(40):
        time.sleep(1)
        if cdp_up():
            print(f"  port {PORT} open after {i + 1}s")
            break
    else:
        print(f"\nPort {PORT} never opened. The build may no longer honour the "
              "switch; use --symbol instead, which needs no browser.",
              file=sys.stderr)
        return 1

    print("\nWaiting for a chart to load…")
    for _ in range(30):
        time.sleep(1)
        if tradingview_tabs():
            break
    return check()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="diagnose only")
    ap.add_argument("--restart", action="store_true",
                    help="close the app and relaunch it with the debug port")
    ap.add_argument("--force", action="store_true",
                    help="with --restart, close it without asking")
    a = ap.parse_args()
    if a.restart:
        return restart(a.force)
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
