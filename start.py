"""
One-command launcher.

    python start.py

Works out what your machine has and sets itself up accordingly:

1. Checks Python version and installs any missing dependencies.
2. Looks for a supported IDE (Antigravity, VS Code, Cursor, Windsurf, Claude
   Desktop, Zed, JetBrains). If one is found, it offers to write the MCP server
   config so the strategies are usable from inside that editor.
3. If no IDE is found — or you decline — it launches the Streamlit dashboard,
   which needs no IDE at all.

Nothing here requires Antigravity specifically. Antigravity is simply one of the
IDEs it can detect.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
MIN_PYTHON = (3, 10)

REQUIRED = [
    ("pandas", "pandas>=2.0"),
    ("numpy", "numpy>=1.24"),
    ("scipy", "scipy>=1.10"),
    ("streamlit", "streamlit>=1.30"),
]
OPTIONAL = [("websockets", "websockets>=12.0")]  # only for live chart detection


def _utf8_console() -> None:
    """Windows consoles default to a legacy code page; force UTF-8 before printing."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


_utf8_console()

BOLD, DIM, GREEN, YELLOW, RED, RESET = "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[31m", "\033[0m"
if platform.system() == "Windows" and not os.environ.get("WT_SESSION"):
    BOLD = DIM = GREEN = YELLOW = RED = RESET = ""


def say(msg: str, kind: str = "info") -> None:
    mark = {"ok": f"{GREEN}✓{RESET}", "warn": f"{YELLOW}!{RESET}",
            "err": f"{RED}✗{RESET}", "info": f"{DIM}·{RESET}"}[kind]
    print(f" {mark} {msg}")


def header(text: str) -> None:
    print(f"\n{BOLD}{text}{RESET}")


# ── environment ───────────────────────────────────────────────────────────────

def check_python() -> bool:
    v = sys.version_info
    if v < MIN_PYTHON:
        say(f"Python {v.major}.{v.minor} found — this needs {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer.", "err")
        print("\n   Install a current Python from https://www.python.org/downloads/")
        print("   On Windows, tick 'Add Python to PATH' during install.")
        return False
    say(f"Python {v.major}.{v.minor}.{v.micro}", "ok")
    return True


def missing_packages(pkgs) -> list[tuple[str, str]]:
    import importlib.util
    return [(mod, spec) for mod, spec in pkgs if importlib.util.find_spec(mod) is None]


def install(specs: list[str]) -> bool:
    say(f"Installing: {', '.join(specs)}")
    # uv when available (much faster), else pip.
    cmd = ([shutil.which("uv"), "pip", "install", *specs] if shutil.which("uv")
           else [sys.executable, "-m", "pip", "install", "--upgrade", *specs])
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError:
        say("Install failed. Try manually:", "err")
        print(f"   {sys.executable} -m pip install {' '.join(specs)}")
        return False


def ensure_dependencies() -> bool:
    header("Dependencies")
    missing = missing_packages(REQUIRED)
    if missing:
        say(f"{len(missing)} required package(s) missing.", "warn")
        if not install([spec for _, spec in missing]):
            return False
    say("All required packages present.", "ok")

    opt_missing = missing_packages(OPTIONAL)
    if opt_missing:
        say(f"Optional (live chart detection): {', '.join(m for m, _ in opt_missing)}", "info")
        install([spec for _, spec in opt_missing])
    return True


def verify_engine() -> bool:
    header("Strategy engine")
    sys.path.insert(0, str(SRC))
    try:
        from tradingview_mcp.core.quant.registry import get_registry
        reg = get_registry()
        s = reg.summary()
        say(f"{s['total']} models across {s['categories']} categories "
            f"({s['families']} independent families)", "ok")
        if s["load_errors"]:
            say(f"{len(s['load_errors'])} module(s) failed to load:", "warn")
            for e in s["load_errors"][:5]:
                print(f"     {e}")
        return True
    except Exception as exc:
        say(f"Engine failed to load: {type(exc).__name__}: {exc}", "err")
        return False


# ── IDE detection ─────────────────────────────────────────────────────────────

def _win_appdata() -> Path:
    return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))


def ide_candidates() -> dict[str, Path]:
    """Config file each supported IDE reads its MCP servers from, per platform."""
    home, system = Path.home(), platform.system()
    if system == "Windows":
        ad = _win_appdata()
        return {
            "Antigravity": ad / "Antigravity" / "User" / "mcp_config.json",
            "VS Code": ad / "Code" / "User" / "mcp.json",
            "Cursor": home / ".cursor" / "mcp.json",
            "Windsurf": home / ".codeium" / "windsurf" / "mcp_config.json",
            "Claude Desktop": ad / "Claude" / "claude_desktop_config.json",
            "Zed": home / ".config" / "zed" / "settings.json",
        }
    if system == "Darwin":
        app = home / "Library" / "Application Support"
        return {
            "Antigravity": app / "Antigravity" / "User" / "mcp_config.json",
            "VS Code": app / "Code" / "User" / "mcp.json",
            "Cursor": home / ".cursor" / "mcp.json",
            "Windsurf": home / ".codeium" / "windsurf" / "mcp_config.json",
            "Claude Desktop": app / "Claude" / "claude_desktop_config.json",
            "Zed": home / ".config" / "zed" / "settings.json",
        }
    cfg = home / ".config"
    return {
        "Antigravity": cfg / "Antigravity" / "User" / "mcp_config.json",
        "VS Code": cfg / "Code" / "User" / "mcp.json",
        "Cursor": home / ".cursor" / "mcp.json",
        "Windsurf": home / ".codeium" / "windsurf" / "mcp_config.json",
        "Claude Desktop": cfg / "Claude" / "claude_desktop_config.json",
        "Zed": cfg / "zed" / "settings.json",
    }


def detect_ides() -> list[tuple[str, Path]]:
    """An IDE counts as present if its config file OR its parent directory exists."""
    found = []
    for name, path in ide_candidates().items():
        if path.exists() or path.parent.exists() or path.parent.parent.exists():
            found.append((name, path))
    return found


def mcp_entry() -> dict:
    return {
        "command": sys.executable,
        "args": ["-m", "tradingview_mcp.server"],
        "env": {"PYTHONPATH": str(SRC), "PYTHONIOENCODING": "utf-8"},
    }


def write_mcp_config(name: str, path: Path) -> bool:
    """Merge our server into the IDE's existing config without clobbering it."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                backup = path.with_suffix(path.suffix + ".backup")
                shutil.copy2(path, backup)
                say(f"Existing config was not valid JSON — backed up to {backup.name}", "warn")
                data = {}

        # Zed nests differently from the rest.
        key = "context_servers" if name == "Zed" else "mcpServers"
        data.setdefault(key, {})["tradingview-quant"] = mcp_entry()
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        say(f"{name} → {path}", "ok")
        return True
    except Exception as exc:
        say(f"{name}: could not write config ({exc})", "err")
        return False


def setup_ides() -> bool:
    header("Editor integration")
    found = detect_ides()
    if not found:
        say("No supported IDE detected — the dashboard needs none.", "info")
        return False

    say(f"Found: {', '.join(n for n, _ in found)}", "ok")
    print(f"\n   {DIM}This adds the strategy engine as an MCP server so you can query it"
          f"\n   from inside the editor. Your existing settings are preserved.{RESET}")
    ans = input("\n   Configure these editors? [Y/n]: ").strip().lower()
    if ans and ans not in ("y", "yes"):
        say("Skipped.", "info")
        return False

    ok = sum(write_mcp_config(n, p) for n, p in found)
    if ok:
        say(f"Configured {ok} editor(s). Restart them to pick up the change.", "ok")
    return bool(ok)


# ── launch ────────────────────────────────────────────────────────────────────

def port_is_busy(port: int) -> bool:
    """True if anything is already serving on `port`.

    This connects rather than binds. A bind probe lies in two ways on Windows:
    SO_REUSEADDR lets it succeed on a port that is already listening, and a
    server bound to the IPv6 wildcard is invisible to an IPv4-only bind. Both
    produce a "free" verdict for a port that then rejects Streamlit. Trying to
    connect over both families answers the question that actually matters.
    """
    import socket
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as s:
                s.settimeout(0.25)
                if s.connect_ex((host, port)) == 0:
                    return True
        except OSError:
            continue          # family unavailable on this host
    return False


def free_port(start: int = 8501, tries: int = 40) -> int:
    """First port from `start` that nothing is serving on.

    Streamlit does not fall back when its port is taken — it exits with "Port
    is already in use", which reads to the user as the dashboard simply never
    appearing. Choosing the port ourselves means another app on 8501 costs
    them nothing.
    """
    for port in range(start, start + tries):
        if not port_is_busy(port):
            return port
    return start


def launch_dashboard() -> int:
    header("Dashboard")
    port = free_port()
    if port != 8501:
        say(f"Port 8501 is busy — using {port} instead.", "info")
    say(f"Starting Streamlit — your browser will open at http://localhost:{port}")
    say("Press Ctrl+C here to stop.", "info")
    print()
    env = {**os.environ, "PYTHONPATH": str(SRC), "PYTHONIOENCODING": "utf-8"}
    try:
        return subprocess.call([sys.executable, "-m", "streamlit", "run",
                                str(ROOT / "dashboard.py"),
                                f"--server.port={port}",
                                "--server.headless=false",
                                "--browser.gatherUsageStats=false"], env=env)
    except KeyboardInterrupt:
        print("\n")
        say("Stopped.", "ok")
        return 0


def main() -> int:
    print(f"\n{BOLD}  Quant Desk — setup{RESET}")
    print(f"  {DIM}{ROOT}{RESET}")

    if not check_python():
        return 1
    if not ensure_dependencies():
        return 1
    if not verify_engine():
        return 1

    if "--no-ide" not in sys.argv:
        setup_ides()

    if "--setup-only" in sys.argv:
        header("Done")
        say("Setup complete. Start the dashboard with: python start.py", "ok")
        return 0

    return launch_dashboard()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)
