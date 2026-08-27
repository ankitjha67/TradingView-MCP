"""
Verify that what the engine analysed is what the chart is showing.

Symbol resolution is a chain of guesses: a TradingView ticker is munged into a
Yahoo or Binance identifier, that identifier is fetched, and every model
downstream assumes the bars belong to the instrument on screen. Nothing in that
chain checks the assumption, so a wrong guess is silent — the numbers look
completely ordinary and are simply about a different asset.

That is not hypothetical. ``CRYPTOCAP:SOLANA.C`` is Solana's *market cap*; the
parser stripped the suffix, took "SOLANA", and produced ``SOLAUSDT`` — a
different token. Prices, models, consensus, backtest and position size would
all have been computed, and nothing could have flagged it.

The fix is an independent measurement. TradingView renders the price in the
chart legend, so it can be read back and compared with the last close the
engine fetched. If the two disagree materially, the resolution is wrong,
whatever the cause — a bad mapping, a stale feed, a delisted pair, the wrong
exchange. One check catches a whole family of failures that no amount of
mapping-table maintenance would.

The comparison is deliberately loose on small differences and hard on large
ones. A chart tick a few seconds ahead of the last closed bar is normal; a
market cap standing in for a unit price is nine orders of magnitude out.
"""
from __future__ import annotations

import asyncio
import json
import math
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

CDP_ENDPOINT = "http://127.0.0.1:9222/json"

# Below this the chart and the feed are simply ticking at different moments.
PRICE_TOLERANCE_PCT = 5.0
# Above this they are not the same instrument in any plausible reading.
PRICE_ABSURD_PCT = 50.0


@dataclass
class ChartContext:
    """What TradingView is actually displaying, read back from the page."""
    symbol: str = ""
    exchange: str = ""
    interval: str = ""
    price: Optional[float] = None
    ohlc: list = field(default_factory=list)
    ok: bool = False
    error: str = ""


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    fatal: bool = False        # fatal means: do not analyse this


@dataclass
class Verdict:
    checks: list = field(default_factory=list)

    @property
    def safe(self) -> bool:
        return not any(c.fatal and not c.passed for c in self.checks)

    @property
    def failures(self) -> list:
        return [c for c in self.checks if not c.passed]

    def report(self) -> str:
        lines = []
        for c in self.checks:
            mark = "ok  " if c.passed else ("STOP" if c.fatal else "warn")
            lines.append(f"  [{mark}] {c.name}: {c.detail}")
        return "\n".join(lines)


_PRICE_PROBE = r"""
(() => {
  const txt = (sels) => { for (const s of sels) {
      const el = document.querySelector(s);
      if (el && el.textContent && el.textContent.trim()) return el.textContent.trim();
  } return null; };
  const vals = [...document.querySelectorAll('[class*="valueValue-"]')]
                 .slice(0, 8).map(e => e.textContent.trim()).filter(Boolean);
  return JSON.stringify({
    symbol: txt(['#header-toolbar-symbol-search', '[class*="symbolTitle-"]',
                 '[data-name="symbol-search"]']),
    price: txt(['[class*="priceWrapper"] [class*="price"]', '[class*="lastPrice"]',
                '[class*="valueValue-"]']),
    values: vals
  });
})()
"""


# TradingView abbreviates large values, and the multiplier is the whole number.
# Reading "2.45M" as 2.45 understates it a millionfold — which would make the
# price cross-check refuse a perfectly good instrument rather than catch a bad
# one. False refusals are worse than no check: they break working setups.
_MAGNITUDE = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}

# Minus renders as several different characters depending on locale and font.
# U+2212 is what TradingView actually uses; stripping it silently flips a sign.
_MINUS = "-−–—－"


def _to_float(text: Optional[str]) -> Optional[float]:
    """
    Parse a price as any asset class renders it.

    Handles thousands separators, currency prefixes and suffixes, unicode
    minus signs, and K/M/B/T abbreviations — the forms differ by asset class
    and locale, and a parser that only understands plain decimals silently
    mis-reads most of them.
    """
    if not text:
        return None
    raw = text.strip()

    negative = any(raw.startswith(ch) for ch in _MINUS)
    scale = 1.0
    # The suffix must be the last non-space character to count as a magnitude;
    # a trailing currency code ("104.17 USD") must not be read as one.
    stripped = raw.rstrip()
    if stripped and stripped[-1].upper() in _MAGNITUDE:
        head = stripped[:-1].rstrip()
        if head and head[-1].isdigit():
            scale = _MAGNITUDE[stripped[-1].upper()]
            raw = head

    cleaned = "".join(ch for ch in raw if ch.isdigit() or ch == ".")
    if not cleaned or cleaned == ".":
        return None
    # Guard against a stray second point from grouping conventions.
    if cleaned.count(".") > 1:
        head, _, tail = cleaned.rpartition(".")
        cleaned = head.replace(".", "") + "." + tail
    try:
        v = float(cleaned) * scale
    except ValueError:
        return None
    if not math.isfinite(v):
        return None
    return -v if negative else v


def read_chart_context(timeout: float = 6.0) -> ChartContext:
    """Read symbol and displayed price back from the open chart."""
    try:
        raw = urllib.request.urlopen(CDP_ENDPOINT, timeout=3).read()
        tabs = json.loads(raw)
    except Exception as exc:
        return ChartContext(error=f"no DevTools endpoint: {exc}")

    tab = next((t for t in tabs if "tradingview.com" in (t.get("url") or "")), None)
    if not tab:
        return ChartContext(error="no TradingView tab is open")
    ws_url = tab.get("webSocketDebuggerUrl")
    if not ws_url:
        return ChartContext(error="the tab exposes no debugger socket")

    try:
        import websockets  # noqa: F401
    except ImportError:
        return ChartContext(error="websockets is not installed; cannot read the page")

    async def probe():
        import websockets
        async with websockets.connect(ws_url, max_size=None) as conn:
            await conn.send(json.dumps({
                "id": 1, "method": "Runtime.evaluate",
                "params": {"expression": _PRICE_PROBE, "returnByValue": True}}))
            while True:
                msg = json.loads(await conn.recv())
                if msg.get("id") == 1:
                    return msg["result"]["result"].get("value")

    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            payload = asyncio.run(asyncio.wait_for(probe(), timeout))
        else:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                payload = pool.submit(
                    lambda: asyncio.run(asyncio.wait_for(probe(), timeout))
                ).result(timeout=timeout + 3)
    except Exception as exc:
        return ChartContext(error=f"could not read the page: {type(exc).__name__}")

    if not payload:
        return ChartContext(error="the page returned nothing")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return ChartContext(error="the page returned unparseable data")

    values = [v for v in (_to_float(x) for x in (data.get("values") or [])) if v]
    return ChartContext(symbol=(data.get("symbol") or "").strip(),
                        price=_to_float(data.get("price")),
                        ohlc=values[:4], ok=True)


def verify(spec, market_data, chart: Optional[ChartContext] = None,
           interval: str = "", min_bars: int = 120) -> Verdict:
    """
    Decide whether the fetched data can be trusted to be the charted symbol.

    ``spec`` is a parsed SymbolSpec, ``market_data`` the fetched MarketData.
    Checks marked fatal mean the analysis should not run at all — better no
    answer than a confident one about the wrong asset.
    """
    v = Verdict()

    # 1. Is there an instrument behind this symbol at all?
    if getattr(spec, "asset_class", "") == "aggregate":
        v.checks.append(Check(
            "tradeable", False,
            f"{spec.raw} is a computed index (market cap or dominance), not an "
            f"instrument. There is nothing to price or size.", fatal=True))
        return v
    v.checks.append(Check("tradeable", True,
                          f"{spec.raw} resolves to a tradeable {spec.asset_class}"))

    # 2. Did the mapping produce anything?
    resolved = getattr(spec, "yahoo", "") or getattr(spec, "binance", "")
    if not resolved:
        v.checks.append(Check("resolution", False,
                              f"{spec.raw} maps to no data provider", fatal=True))
        return v
    v.checks.append(Check("resolution", True, f"{spec.raw} -> {resolved}"))

    # 3. Enough history to mean anything.
    # `df or []` would call DataFrame.__bool__, which raises. Length directly.
    _df = getattr(market_data, "df", None)
    bars = 0 if _df is None else len(_df)
    v.checks.append(Check(
        "history", bars >= min_bars,
        f"{bars} bars fetched" + ("" if bars >= min_bars
                                  else f" — under the {min_bars} needed"),
        fatal=bars < 20))

    # 4. The check that catches a wrong instrument: does the price agree with
    #    what is on screen? This is independent of every mapping table.
    chart = chart if chart is not None else read_chart_context()
    fetched = None
    try:
        fetched = float(market_data.df["close"].iloc[-1])
    except Exception:
        pass

    if not chart.ok or chart.price is None:
        v.checks.append(Check(
            "price cross-check", True,
            f"skipped — {chart.error or 'no price on the chart'}. The resolution "
            f"is unverified, not wrong."))
    elif fetched is None or fetched <= 0:
        v.checks.append(Check("price cross-check", False,
                              "no usable close in the fetched data", fatal=True))
    else:
        diff = abs(chart.price - fetched) / max(abs(chart.price), 1e-9) * 100
        if diff <= PRICE_TOLERANCE_PCT:
            v.checks.append(Check(
                "price cross-check", True,
                f"chart {chart.price:,.4f} vs fetched {fetched:,.4f} "
                f"({diff:.2f}% apart)"))
        else:
            v.checks.append(Check(
                "price cross-check", False,
                f"chart shows {chart.price:,.4f} but the fetched series ends at "
                f"{fetched:,.4f} — {diff:,.1f}% apart. "
                + ("These are not the same instrument; the symbol resolved to "
                   "the wrong asset."
                   if diff >= PRICE_ABSURD_PCT else
                   "Possibly a stale feed, a different exchange, or an "
                   "adjusted series."),
                fatal=diff >= PRICE_ABSURD_PCT))

    # 5. Symbol echo — weak on its own, useful alongside the price check.
    if chart.ok and chart.symbol:
        want = (getattr(spec, "ticker", "") or "").upper()
        got = chart.symbol.upper()
        agree = bool(want) and (want in got or got in want)
        v.checks.append(Check(
            "symbol echo", agree or not want,
            f"chart says {chart.symbol!r}, engine parsed {want!r}"))

    return v
