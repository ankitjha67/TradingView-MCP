"""
The suite must test the repository it lives in.

`import tradingview_mcp` resolves through whatever is pip-installed, and an
editable install can point anywhere — it once pointed at a zip snapshot of this
repo, so every test passed against a copy while the real tree drifted. The
pytest ``pythonpath`` setting fixes that; this test makes sure it stays fixed.
"""
from pathlib import Path

import tradingview_mcp

ROOT = Path(__file__).resolve().parents[2]


def test_the_package_under_test_is_this_checkout():
    got = Path(tradingview_mcp.__file__).resolve()
    assert got.is_relative_to(ROOT / "src"), (
        f"tests imported {got}, not the package under {ROOT / 'src'}")
