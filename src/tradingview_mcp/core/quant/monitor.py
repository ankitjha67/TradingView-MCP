"""
Live monitor.

**Answering the cadence question directly.** The monitor follows the interval on
your TradingView chart, not a fixed 60-second timer.

* It watches the browser ~every 2 seconds, but that is only to notice that you
  changed symbol or interval. It is not an analysis cycle.
* A full re-analysis runs **when the current bar closes** on whatever interval
  the chart is set to. On a 1-minute chart that is every minute; on 15-minute,
  every 15 minutes; on daily, once per day.
* Changing symbol or interval triggers an immediate re-analysis rather than
  waiting for the next close.
* ``force_interval_seconds`` overrides this if you genuinely want a fixed cadence.

Why bar-close alignment rather than a fixed timer: every model reads the *last
closed bar*. Re-running mid-bar re-reads a bar that is still forming, so the
signal flickers as the candle moves and then settles at close. Aligning to the
close means one stable reading per bar — which is also what a discretionary
trader watching the same chart would act on.

The previous daemon polled every 60 seconds regardless of chart interval and
then mapped every intraday interval to hourly data, so a 1-minute chart was
re-analysed 60 times per hour against the same unchanged hourly candle.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .confidence import ConfidenceReport, consensus_series, score_trade
from .consensus import compute_consensus, compute_risk_levels, evaluate_all
from .features import build_features
from .market_data import (
    fetch_ohlcv, interval_seconds, normalize_interval, parse_symbol,
    seconds_to_next_close,
)
from .sizing import CapitalConfig, build_trade_plan

CDP_ENDPOINT = "http://127.0.0.1:9222/json"
WATCH_POLL_SECONDS = 2.0

# While the feed is stale (closed market, halted symbol), re-check on this cycle
# instead of the interval's own cadence. Frequent enough to catch the reopen
# promptly, slow enough not to hammer the provider through a weekend.
STALE_RECHECK_SECONDS = 600.0

# Retry pacing after a failed cycle. Doubles per consecutive failure so an
# unresolvable symbol settles into an occasional retry rather than a tight loop.
FAILURE_BACKOFF_BASE = 30.0
FAILURE_BACKOFF_MAX = 900.0


def ensure_utf8_console() -> None:
    """
    Force stdout/stderr to UTF-8.

    Windows consoles default to a legacy code page (cp1252 here), which raises
    UnicodeEncodeError the moment a report contains an arrow, a rupee sign or a
    box character. This is the same root cause as the mojibake in the old
    walkthrough file: text written or printed under an assumed encoding rather
    than an explicit one. Call this before printing anything non-ASCII.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


ensure_utf8_console()


@dataclass
class ChartState:
    """What the browser says you are currently looking at."""
    symbol: str = ""
    exchange: str = ""
    interval: str = "1d"
    url: str = ""
    detected_at: float = 0.0

    def key(self) -> tuple:
        return (self.symbol, self.exchange, self.interval)

    def is_valid(self) -> bool:
        return bool(self.symbol)


@dataclass
class MonitorConfig:
    symbol: str = ""                      # manual override; empty = follow browser
    interval: str = ""                    # manual override; empty = follow browser
    force_interval_seconds: Optional[int] = None
    output_dir: Path = field(default_factory=lambda: Path.cwd())
    write_markdown: bool = True
    write_json: bool = True
    llm_commentary: bool = False
    max_lookback_bars: int = 1500
    # Only a guard against a runaway loop. Bar-close alignment is what actually
    # paces the monitor, and the fastest supported interval is 1m — so a floor
    # anywhere near 30 s would skip closes on a 1-minute chart rather than
    # protect anything.
    min_seconds_between_runs: int = 5
    # Account settings driving the confidence-scaled position sizer.
    capital: float = 100_000.0        # supported range 1,000 … 1,000,000
    currency: str = "INR"
    risk_pct: float = 1.0
    max_position_pct: float = 25.0
    use_leverage: bool = False
    # Stability scoring needs the historical consensus path — an extra ~1s pass.
    compute_stability: bool = True

    def capital_config(self) -> CapitalConfig:
        return CapitalConfig(capital=self.capital, currency=self.currency,
                             risk_pct=self.risk_pct,
                             max_position_pct=self.max_position_pct,
                             use_leverage=self.use_leverage)


def read_chart_from_browser(timeout: float = 2.0) -> Optional[ChartState]:
    """
    Read symbol and interval from an open TradingView tab via Chrome DevTools.

    Requires Chrome started with ``--remote-debugging-port=9222``. Returns None
    when no debuggable TradingView tab is present — a normal, non-error state.

    Note this reads *only* the chart's symbol and interval from the page you
    already have open. It does not read or transmit account data, and it does not
    call any TradingView data API, which is why the free plan is sufficient.
    """
    try:
        req = urllib.request.Request(CDP_ENDPOINT, headers={"User-Agent": "tvmcp-monitor"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            tabs = json.loads(resp.read().decode())
    except Exception:
        return None

    tab = next((t for t in tabs if "tradingview.com" in (t.get("url") or "")), None)
    if not tab:
        return None

    ws_url = tab.get("webSocketDebuggerUrl")
    if not ws_url:
        return _state_from_url(tab.get("url", ""))

    try:
        import websockets  # optional; URL parsing is the fallback
    except ImportError:
        return _state_from_url(tab.get("url", ""))

    # asyncio.run() creates and disposes its own loop. get_event_loop() is deprecated
    # and, inside a host that already runs a loop (Streamlit), raises "loop is already
    # running" — so the probe is dispatched to a worker thread in that case.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            return asyncio.run(_query_tab(ws_url, tab.get("url", "")))
        except Exception:
            return _state_from_url(tab.get("url", ""))

    import concurrent.futures
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(
                lambda: asyncio.run(_query_tab(ws_url, tab.get("url", "")))
            ).result(timeout=8)
    except Exception:
        return _state_from_url(tab.get("url", ""))


_JS_PROBE = """
(() => {
  const pick = (sels) => {
    for (const s of sels) {
      const el = document.querySelector(s);
      if (el && el.textContent && el.textContent.trim()) return el.textContent.trim();
    }
    return null;
  };
  return {
    symbol: pick(['#header-toolbar-symbol-search','[data-name="symbol-search"]',
                  '[class*="symbolTitle-"]','[class*="symbol-search"]']),
    exchange: pick(['[class*="exchangeTitle-"]','[class*="exchange-"]']),
    interval: pick(['[data-name="resolution"] [class*="value-"]',
                    '[class*="intervalTitle-"]','#header-toolbar-intervals [aria-checked="true"]']),
    href: window.location.href
  };
})()
"""


async def _query_tab(ws_url: str, fallback_url: str) -> Optional[ChartState]:
    import websockets
    try:
        async with websockets.connect(ws_url, close_timeout=2, open_timeout=3) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                      "params": {"expression": _JS_PROBE, "returnByValue": True}}))
            for _ in range(20):
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
                if msg.get("id") == 1:
                    v = msg.get("result", {}).get("result", {}).get("value") or {}
                    if v.get("symbol"):
                        return ChartState(
                            symbol=str(v["symbol"]).strip(),
                            exchange=str(v.get("exchange") or "").strip(),
                            interval=normalize_interval(v.get("interval")),
                            url=v.get("href") or fallback_url,
                            detected_at=time.time())
                    return _state_from_url(v.get("href") or fallback_url)
    except Exception:
        pass
    return _state_from_url(fallback_url)


def _state_from_url(url: str) -> Optional[ChartState]:
    """Fall back to the ``?symbol=&interval=`` query string on the chart URL."""
    if not url:
        return None
    try:
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(url).query)
        sym = (q.get("symbol") or [""])[0]
        if not sym:
            return None
        exch = sym.split(":")[0] if ":" in sym else ""
        return ChartState(symbol=sym, exchange=exch,
                          interval=normalize_interval((q.get("interval") or ["1D"])[0]),
                          url=url, detected_at=time.time())
    except Exception:
        return None


@dataclass
class MonitorSnapshot:
    """One completed analysis cycle."""
    chart: ChartState
    consensus: dict
    risk: dict
    data_meta: dict
    confidence: dict = field(default_factory=dict)
    trade_plan: dict = field(default_factory=dict)
    freshness: dict = field(default_factory=dict)
    llm: dict = field(default_factory=dict)
    generated_at: str = ""
    next_run_in_seconds: float = 0.0
    trigger: str = "scheduled"

    def to_dict(self) -> dict:
        return {"chart": asdict(self.chart), "consensus": self.consensus,
                "confidence": self.confidence, "trade_plan": self.trade_plan,
                "freshness": self.freshness,
                "risk": self.risk, "data": self.data_meta, "llm": self.llm,
                "generated_at": self.generated_at,
                "next_run_in_seconds": round(self.next_run_in_seconds, 1),
                "trigger": self.trigger}


def _provisional_notional(f, risk, cfg) -> float:
    """
    Rough position notional in the instrument's quote currency, for the liquidity
    gate. Computed before the real sizing pass because the gate has to influence
    the confidence multiplier that sizing then consumes.
    """
    try:
        stop_distance = abs(risk.entry - risk.stop_loss)
        if stop_distance <= 0:
            return 0.0
        qty = (cfg.capital * (cfg.risk_pct / 100.0)) / stop_distance
        return float(qty * risk.entry)
    except Exception:
        return 0.0


def analyze_once(symbol: str, interval: str, exchange: str = "",
                 cfg: Optional[MonitorConfig] = None, trigger: str = "manual") -> MonitorSnapshot:
    """
    One full cycle: fetch → evaluate all models → consensus → confidence → position.

    The four stages are deliberately sequential and separable. Confidence reads
    the consensus and the individual model signals; sizing reads the confidence.
    Nothing downstream can inflate a weak signal, because size is multiplied by
    the confidence engine's multiplier, which can be zero.
    """
    cfg = cfg or MonitorConfig()
    interval = normalize_interval(interval)

    md = fetch_ohlcv(symbol, interval, exchange)
    df = md.df.tail(cfg.max_lookback_bars)
    f = build_features(df, interval, md.symbol.ticker or symbol)

    # Evaluate once and reuse — consensus and confidence need the same signals.
    _, all_signals = evaluate_all(f, interval, symbol)
    consensus = compute_consensus(f, interval, symbol)
    risk = compute_risk_levels(f, consensus.direction)

    voting = [(s, sig) for s, sig in all_signals
              if sig.available and abs(sig.score) >= 0.15]

    score_path, calib = None, {}
    if cfg.compute_stability:
        try:
            from .confidence import calibrate
            from .registry import get_registry
            models = get_registry().all()
            score_path = consensus_series(f, models)
            # Measure how this score has actually performed here, and let that
            # measurement feed back into the verdict.
            calib = calibrate(f, models, horizon=10)
        except Exception:
            score_path, calib = None, {}  # degrades to neutral, never to a crash

    # Distance to target as a % of price, checked against round-trip costs.
    target_move_pct = (abs(risk.take_profit - risk.entry) / risk.entry * 100
                       if risk.entry else float("nan"))
    confidence = score_trade(consensus, f, voting,
                             risk_reward=risk.risk_reward, score_path=score_path,
                             target_move_pct=target_move_pct,
                             asset_class=md.symbol.asset_class,
                             calibration=calib,
                             notional_quote=_provisional_notional(f, risk, cfg))
    # Pass the fully-qualified symbol. Sizing re-parses it to determine asset class,
    # lot granularity and venue minimums — and a bare ticker loses the exchange, so
    # a crypto pair silently resolves as an equity with no minimum-order rule.
    qualified = f"{exchange}:{symbol}" if exchange and ":" not in symbol else symbol
    plan = build_trade_plan(qualified, consensus, risk, confidence, cfg.capital_config())

    fresh = staleness(md, interval)

    snap = MonitorSnapshot(
        chart=ChartState(symbol=symbol, exchange=exchange, interval=interval,
                         detected_at=time.time()),
        consensus=consensus.to_dict(), risk=risk.to_dict(),
        confidence=confidence.to_dict(), trade_plan=plan, freshness=fresh,
        data_meta=md.to_dict(),
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        next_run_in_seconds=seconds_to_next_close(interval), trigger=trigger)

    if cfg.llm_commentary:
        from .llm import analyze as llm_analyze
        snap.llm = llm_analyze(snap.consensus, snap.risk,
                               extra={"confidence": snap.confidence,
                                      "position": plan.get("position")})
    return snap


# ── report rendering ──────────────────────────────────────────────────────────

def staleness(md, interval: str) -> dict:
    """
    How far behind live is the most recent bar?

    Without this the monitor re-analyses a closed market every minute and prints
    the result as a live reading. Over a weekend that means ~2,800 identical
    "analyses" of Friday's close, each one looking like fresh information.

    A bar is expected to be at most ~2 intervals old on a live feed. Beyond that
    the market is closed, halted, or the feed has stopped.
    """
    try:
        last = md.last_bar_time.to_pydatetime()
    except Exception:
        return {"stale": False, "lag_minutes": 0.0, "reason": ""}

    lag_s = (datetime.now(timezone.utc) - last).total_seconds()
    bar_s = interval_seconds(interval)
    # Daily and slower legitimately sit a day behind; allow a wider tolerance.
    tolerance = bar_s * (3 if bar_s < 86400 else 2)
    stale = lag_s > tolerance

    reason = ""
    if stale:
        lag_h = lag_s / 3600
        if lag_h >= 48:
            reason = "market closed for the weekend"
        elif lag_h >= 12:
            reason = "market closed (outside trading hours)"
        else:
            reason = "feed has not produced a new bar"
    return {"stale": stale, "lag_minutes": round(lag_s / 60, 1),
            "lag_bars": round(lag_s / bar_s, 1), "reason": reason,
            "last_bar": last.isoformat()}


def fmt_price(x: float) -> str:
    """
    Format a price with enough decimals to be meaningful at its magnitude.

    A fixed 4-decimal format renders DOGE at 0.07001 as "0.0700" and its ATR as
    "0.0000", making entry, stop and target look identical. Precision has to
    scale with the price.
    """
    if x is None or not isinstance(x, (int, float)) or not math.isfinite(x):
        return "n/a"
    ax = abs(x)
    if ax == 0:
        return "0"
    if ax >= 1000:
        return f"{x:,.2f}"
    if ax >= 1:
        return f"{x:,.4f}"
    if ax >= 0.01:
        return f"{x:.6f}"
    if ax >= 0.0001:
        return f"{x:.8f}"
    return f"{x:.10f}"


def render_markdown(snap: MonitorSnapshot) -> str:
    c, r, d = snap.consensus, snap.risk, snap.data_meta
    m = c.get("models", {})
    reg = c.get("regime", {})
    arrow = {"BUY": "▲ LONG", "SELL": "▼ SHORT", "NEUTRAL": "■ NO POSITION"}.get(c["direction"], c["direction"])

    lines = [
        f"# {c['symbol']} · {c['interval']}",
        "",
        f"**{arrow}** — consensus score `{c['score']:+.3f}`, confidence `{c['confidence']:.0%}`",
        "",
        f"- **Price** `{fmt_price(c['price'])}`  ·  bar as of `{c['as_of']}`",
        f"- **Data** {d['bars']} bars from `{d['provider']}` (fetched {d['fetched_at']})",
        f"- **Regime** {reg.get('label', 'n/a')} · ADX `{reg.get('adx', 0):.1f}` · "
        f"realised vol `{reg.get('realized_vol_pct', 0):.1f}%` (percentile `{reg.get('vol_percentile', 0):.2f}`)",
        f"- **Next analysis** in ~{snap.next_run_in_seconds:.0f}s (at the close of the current "
        f"{c['interval']} bar)",
        "",
        "## Model vote",
        "",
        f"| Voting | Long | Short | Available | In library |",
        f"|---|---|---|---|---|",
        f"| {m.get('voting', 0)} | {m.get('buy', 0)} | {m.get('sell', 0)} | "
        f"{m.get('available', 0)} | {m.get('total', 0)} |",
        "",
        f"Agreement: **{c['agreement']:.0%}** of weighted vote on the leading side.",
    ]

    if c.get("warnings"):
        lines += ["", "> " + "  \n> ".join(f"⚠ {w}" for w in c["warnings"])]

    # ── confidence ──
    cf = snap.confidence
    if cf:
        lines += ["", "## Confidence", "",
                  f"### {cf['grade']} · {cf['score']:.0f}/100 · **{cf['verdict']}** "
                  f"· size ×{cf['size_multiplier']:.2f}", "",
                  "| Component | Score | Weight | Points | Basis |",
                  "|---|---:|---:|---:|---|"]
        for comp in cf.get("components", []):
            lines.append(f"| {comp['name']} | {comp['score']:.2f} | {comp['weight']:.0%} "
                         f"| {comp['contribution']:.1f} | {comp['detail']} |")
        if cf.get("vetoes"):
            lines += ["", "**Vetoes — no position regardless of score:**", ""]
            lines += [f"- ⛔ {v}" for v in cf["vetoes"]]
        if cf.get("cautions"):
            lines += ["", "**Cautions — each halves position size:**", ""]
            lines += [f"- ⚠ {v}" for v in cf["cautions"]]

    lines += ["", "## Risk levels (ATR-derived)", "",
              "| Entry | Stop | Target | R:R | ATR |", "|---|---|---|---|---|",
              f"| `{fmt_price(r['entry'])}` | `{fmt_price(r['stop_loss'])}` "
              f"| `{fmt_price(r['take_profit'])}` "
              f"| `{r['risk_reward']:.2f}` | `{fmt_price(r['atr'])}` |"]

    # ── position ──
    tp = snap.trade_plan or {}
    pos, acct = tp.get("position"), tp.get("account", {})
    if pos:
        cur = pos.get("currency", "")
        lines += ["", "## Position", ""]
        if pos.get("tradeable"):
            lines += [
                f"**{pos['direction']} {pos['quantity']:g} {pos['units_label']}**"
                + (f" ({pos['lots']:g} lots)" if pos.get("lots") else ""),
                "",
                "| | |", "|---|---|",
                f"| Account capital | {cur} {pos['capital']:,.0f} |",
                f"| Capital deployed | {cur} {pos['capital_required']:,.2f} |",
                f"| Notional exposure | {cur} {pos['notional_account_ccy']:,.2f} |",
                f"| Amount at risk | {cur} {pos['risk_amount']:,.2f} "
                f"({pos['risk_pct_of_capital']:.2f}% of capital) |",
                f"| Reward if target hit | {cur} {pos['reward_amount']:,.2f} "
                f"({pos['return_on_capital_pct']:.2f}% of capital) |",
                f"| Instrument | {pos['asset_class']} |",
                f"| Confidence multiplier | ×{pos['confidence_multiplier']:.2f} "
                f"(of {acct.get('risk_pct', 1):.2f}% base risk) |",
            ]
            if pos.get("leverage_used", 1) > 1:
                lines.append(f"| Leverage assumed | {pos['leverage_used']:g}x |")
            for w in pos.get("warnings", []):
                lines.append(f"\n> ⚠ {w}")
        else:
            lines.append(f"**No position taken.**\n")
            for reason in pos.get("reasons", []):
                lines.append(f"> {reason}")

        ladder = tp.get("capital_ladder") or []
        if ladder:
            lines += ["", "### Same trade across the capital range", "",
                      f"| Capital ({cur}) | Size | Deployed | At risk | Risk % | Reward |",
                      "|---:|---:|---:|---:|---:|---:|"]
            for row in ladder:
                if row["tradeable"]:
                    size = f"{row['quantity']:g}"
                    if row.get("lots"):
                        size += f" ({row['lots']:g}L)"
                    lines.append(f"| {row['capital']:,} | {size} | {row['capital_required']:,.0f} "
                                 f"| {row['risk_amount']:,.0f} | {row['risk_pct']:.2f}% "
                                 f"| {row['reward_amount']:,.0f} |")
                else:
                    lines.append(f"| {row['capital']:,} | — | — | — | — | not tradeable |")

    cats = sorted(c.get("categories", []), key=lambda x: -abs(x.get("score", 0)))
    if cats:
        lines += ["", "## By category", "", "| Category | Score | Long | Short | Available |",
                  "|---|---|---|---|---|"]
        for cv in cats:
            if cv["available"]:
                lines.append(f"| {cv['category']} | `{cv['score']:+.2f}` | {cv['buy']} | "
                             f"{cv['sell']} | {cv['available']}/{cv['total']} |")

    for label, key in (("Strongest long signals", "top_long"), ("Strongest short signals", "top_short")):
        rows = c.get(key, [])
        if rows:
            lines += ["", f"## {label}", ""]
            for s in rows[:5]:
                lines.append(f"- **`{s['score']:+.2f}`  {s['strategy']}** — {s['rationale']}")

    if c.get("unavailable_reasons"):
        lines += ["", "## Models that did not run", ""]
        for reason, n in sorted(c["unavailable_reasons"].items(), key=lambda x: -x[1]):
            lines.append(f"- {n} × {reason}")

    if snap.llm.get("ok"):
        lines += ["", f"## Commentary ({snap.llm.get('provider')} · {snap.llm.get('model')})",
                  "", snap.llm["analysis"]]
    elif snap.llm.get("error"):
        lines += ["", f"_Commentary unavailable: {snap.llm['error']}_"]

    lines += ["", "---", "",
              "_Systematic model output for research and analysis. Not investment advice._"]
    return "\n".join(lines)


def write_outputs(snap: MonitorSnapshot, cfg: MonitorConfig) -> list[Path]:
    """Write the snapshot to disk as UTF-8 (the encoding bug that produced mojibake)."""
    written = []
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    if cfg.write_json:
        p = cfg.output_dir / "tv_active_chart.json"
        p.write_text(json.dumps(snap.to_dict(), indent=2, default=str), encoding="utf-8")
        written.append(p)
    if cfg.write_markdown:
        p = cfg.output_dir / "tv_active_chart.md"
        p.write_text(render_markdown(snap), encoding="utf-8")
        written.append(p)
    return written


def write_error_report(chart: ChartState, error: Exception, cfg: MonitorConfig) -> list[Path]:
    """
    Overwrite the report files when a cycle fails.

    This exists because the previous behaviour was to log the error and retry,
    leaving the *last successful* report on disk. A stale file showing a symbol
    you are no longer charting reads as a live recommendation — the failure was
    invisible, and the wrong instrument stayed on screen indefinitely.
    """
    spec = parse_symbol(chart.symbol, chart.exchange)
    resolved = spec.yahoo or spec.binance or "(could not resolve)"

    hint = ""
    if spec.asset_class == "aggregate":
        hint = (f"`{chart.exchange}:{chart.symbol}` is a TradingView **aggregate series** "
                f"(total market cap, dominance). There is no tradeable instrument behind it, "
                f"so there is nothing to price, size or recommend. Switch the chart to a "
                f"tradeable pair such as `BINANCE:BTCUSDT`.")
    elif not resolved or resolved == "(could not resolve)":
        hint = (f"The symbol could not be mapped to any free data provider. If this is a "
                f"valid instrument, it may need adding to the symbol map in `market_data.py`.")
    else:
        hint = (f"The symbol resolved to `{resolved}` but no provider returned data at the "
                f"`{chart.interval}` interval. Common causes: the interval is too fine for "
                f"the provider's history (1-minute data is typically kept ~7 days), the "
                f"market has never traded on this feed, or the provider is rate-limiting.")

    body = f"""# Monitor error

**Chart detected:** `{chart.exchange}:{chart.symbol}` at `{chart.interval}`
**Resolved to:** `{resolved}` ({spec.asset_class})
**Time:** `{datetime.now(timezone.utc).isoformat(timespec='seconds')}`

## No analysis was produced

{hint}

### Underlying error

```
{type(error).__name__}: {error}
```

---

_This file is overwritten every cycle. It is showing an error rather than the previous
successful reading, so that a stale result is never mistaken for a live one._
"""
    written = []
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    if cfg.write_json:
        p = cfg.output_dir / "tv_active_chart.json"
        p.write_text(json.dumps({
            "status": "error",
            "chart": asdict(chart),
            "resolved_symbol": resolved,
            "asset_class": spec.asset_class,
            "error": f"{type(error).__name__}: {error}",
            "hint": hint,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }, indent=2, default=str), encoding="utf-8")
        written.append(p)
    if cfg.write_markdown:
        p = cfg.output_dir / "tv_active_chart.md"
        p.write_text(body, encoding="utf-8")
        written.append(p)
    return written


# ── the loop ──────────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


class SingleInstance:
    """
    An OS lock that stops a second monitor writing the same report files.

    Every launch used to start another daemon. Five accumulated here over one
    session, all polling the same chart and all overwriting tv_active_chart.json
    a few hundred milliseconds apart — so the report on disk came from whichever
    process happened to finish last, and killing one changed nothing visible.

    The lock is advisory and held by the OS, so it dies with the process. A
    crashed monitor leaves a stale file but not a stale lock, which is why this
    does not try to validate a recorded PID: that check races, and an unrelated
    process can inherit the number.
    """

    # Two files, on purpose. Windows locks a byte *range* and denies ordinary
    # reads that overlap it — and because reads are buffered, a read of a
    # 40-byte file still issues an 8 KB request that can collide with a lock
    # placed well past the data. Storing the holder's identity in the file
    # being locked therefore makes it unreadable exactly when it is wanted.
    # So: `.lock` is locked and never read, `.lock.who` is read and never
    # locked, and no byte-range subtlety can affect the message.

    def __init__(self, path: Path):
        self.path = path
        self.who_path = path.with_suffix(path.suffix + ".who")
        self._fh = None

    def _identity(self) -> str:
        return (f"pid {os.getpid()} started "
                f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}")

    def acquire(self) -> Optional[str]:
        """None if we got it, else a description of who holds it."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self.path, "a+", encoding="utf-8")
        except OSError as exc:
            return f"could not open the lock file {self.path}: {exc}"

        try:
            if sys.platform == "win32":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._fh.close()
            self._fh = None
            try:
                return self.who_path.read_text(encoding="utf-8").strip() \
                    or "an unidentified process"
            except OSError:
                return "an unidentified process"

        try:
            self.who_path.write_text(self._identity(), encoding="utf-8")
        except OSError:
            pass          # the lock is what matters; the label is a courtesy
        return None

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self._fh.close()
            self._fh = None
            for p in (self.who_path, self.path):
                try:
                    p.unlink()
                except OSError:
                    pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()


def run_monitor(cfg: Optional[MonitorConfig] = None,
                on_snapshot: Optional[Callable[[MonitorSnapshot], None]] = None,
                max_cycles: Optional[int] = None) -> None:
    """
    Main loop.

    Two clocks, deliberately separate:
      * a fast **watch** clock (2s) that only detects chart changes;
      * a **bar-close** clock that triggers the actual analysis.
    """
    cfg = cfg or MonitorConfig()
    manual = bool(cfg.symbol)

    last_key: Optional[tuple] = None
    next_run_at = 0.0
    cycles = 0
    consecutive_failures = 0

    if manual:
        _log(f"Manual mode: {cfg.symbol} @ {normalize_interval(cfg.interval or '1d')} "
             f"(fixed symbol — will NOT follow your chart)")
    else:
        probe = read_chart_from_browser()
        if probe and probe.is_valid():
            _log(f"Following your chart. Currently: {probe.exchange}:{probe.symbol} "
                 f"@ {probe.interval}")
        else:
            _log("Following the active TradingView chart — none detected yet.")
            _log("  The TradingView desktop app exposes port 9222 automatically.")
            _log("  For Chrome, start it with --remote-debugging-port=9222.")

    while max_cycles is None or cycles < max_cycles:
        try:
            if manual:
                # `--symbol NSE:RELIANCE` carries its exchange in the string;
                # parse_symbol recovers it. A bare `--symbol RELIANCE` genuinely has
                # none, and the resulting failure names the fix.
                _spec = parse_symbol(cfg.symbol)
                state = ChartState(symbol=_spec.ticker or cfg.symbol,
                                   interval=normalize_interval(cfg.interval or "1d"),
                                   exchange=_spec.exchange,
                                   detected_at=time.time())
            else:
                state = read_chart_from_browser()
                if not state or not state.is_valid():
                    if last_key is not None:
                        _log("No TradingView tab detected — waiting.")
                        last_key = None
                    time.sleep(WATCH_POLL_SECONDS)
                    continue

            changed = state.key() != last_key
            due = time.time() >= next_run_at

            if not (changed or due):
                time.sleep(WATCH_POLL_SECONDS)
                continue

            label = f"{state.exchange}:{state.symbol}" if state.exchange else state.symbol
            trigger = "chart changed" if changed else "bar close"
            if changed:
                spec = parse_symbol(state.symbol, state.exchange)
                resolved = spec.yahoo or spec.binance or "unresolved"
                _log(f"Chart: {label} @ {state.interval} "
                     f"→ {resolved} ({spec.asset_class})")

            t0 = time.time()
            try:
                snap = analyze_once(state.symbol, state.interval, state.exchange, cfg, trigger)
            except Exception as exc:
                # Report the failure in the output files. Leaving the previous
                # successful report on disk would present a stale reading for a
                # symbol the user is no longer looking at.
                paths = write_error_report(state, exc, cfg)
                consecutive_failures += 1
                # Escalating backoff. A symbol that cannot be resolved fails on every
                # attempt, and a fixed short retry would hammer the providers forever.
                backoff = min(FAILURE_BACKOFF_MAX,
                              FAILURE_BACKOFF_BASE * (2 ** (consecutive_failures - 1)))
                _log(f"FAILED {label} @ {state.interval} — "
                     f"{type(exc).__name__}: {str(exc)[:120]}")
                if consecutive_failures > 1:
                    _log(f"  failure {consecutive_failures} in a row; retrying in {backoff:.0f}s")
                for p in paths:
                    _log(f"  wrote {p.name} (error report)")
                last_key = state.key()
                next_run_at = time.time() + backoff
                # A failed cycle is still a cycle. Without this, `continue` skipped the
                # counter below and max_cycles never terminated a run whose symbol was
                # permanently unresolvable — a bounded run became an infinite loop.
                cycles += 1
                time.sleep(WATCH_POLL_SECONDS)
                continue
            elapsed = time.time() - t0

            # Schedule the next run at the next bar close.
            #
            # The rate-limit floor must never exceed the bar interval itself: with a
            # 30 s floor on a 1-minute chart, a close arriving 15 s from now would be
            # skipped and the next update would land a full bar late — an update every
            # two minutes on a one-minute chart. Clamp the floor to the interval so
            # every bar close is honoured.
            bar_seconds = interval_seconds(state.interval)
            floor = min(cfg.min_seconds_between_runs, bar_seconds)
            wait = max(seconds_to_next_close(state.interval), floor)

            # Stale feed: the point is to notice when data starts flowing again.
            #
            # This was `max(wait, 300)`, which is backwards for slow intervals — on a
            # daily chart `seconds_to_next_close` is 86400, so max(86400, 300) left the
            # monitor scheduled 24 hours out and blind to the market reopening. The
            # correct behaviour is a CAP: while stale, re-check on a fixed short cycle
            # so the first fresh bar is picked up within minutes of the open.
            fresh = snap.freshness or {}
            if fresh.get("stale"):
                wait = min(wait, STALE_RECHECK_SECONDS)

            if cfg.force_interval_seconds:
                wait = float(cfg.force_interval_seconds)
            snap.next_run_in_seconds = wait
            next_run_at = time.time() + wait
            last_key = state.key()

            consecutive_failures = 0
            paths = write_outputs(snap, cfg)
            c, cf = snap.consensus, snap.confidence
            pos = (snap.trade_plan or {}).get("position", {})
            size_txt = (f"{pos.get('quantity', 0):g} {pos.get('units_label', '')}"
                        if pos.get("tradeable") else "no position")
            stale_txt = ""
            if (snap.freshness or {}).get("stale"):
                stale_txt = (f" | STALE {snap.freshness['lag_minutes']:,.0f}m "
                             f"({snap.freshness['reason']})")
            _log(f"{c['direction']:7s} {c['symbol']} @ {c['interval']} | "
                 f"score {c['score']:+.2f} | "
                 f"conf {cf.get('grade', '?')} {cf.get('score', 0):.0f}/100 "
                 f"{cf.get('verdict', '')} | {size_txt} | "
                 f"{c['models']['voting']}/{c['models']['available']} models{stale_txt} | "
                 f"{elapsed:.1f}s | next in {wait:.0f}s")
            for p in paths:
                _log(f"  wrote {p.name}")

            if on_snapshot:
                on_snapshot(snap)
            cycles += 1

        except KeyboardInterrupt:
            _log("Stopped.")
            return
        except Exception as exc:
            _log(f"Cycle error: {type(exc).__name__}: {exc}")
            next_run_at = time.time() + 30
        time.sleep(WATCH_POLL_SECONDS)


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Live monitor. Follows your TradingView chart's symbol and interval, "
                    "and re-analyses at each bar close.")
    ap.add_argument("--symbol", default="", help="Analyse this symbol instead of following the browser")
    ap.add_argument("--interval", default="", help="1m 5m 15m 30m 1h 4h 1d 1wk")
    ap.add_argument("--every", type=int, default=None,
                    help="Force a fixed cadence in seconds instead of bar-close alignment")
    ap.add_argument("--out", default=".", help="Output directory for the report files")
    ap.add_argument("--llm", action="store_true", help="Add LLM commentary (needs a configured provider)")
    ap.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    ap.add_argument("--capital", type=float, default=100_000.0,
                    help="Account capital, 1000 to 1000000 (default 100000)")
    ap.add_argument("--currency", default="INR", help="Account currency (INR, USD, EUR, GBP)")
    ap.add_argument("--risk", type=float, default=1.0,
                    help="Risk per trade as %% of capital (default 1.0)")
    ap.add_argument("--max-exposure", type=float, default=25.0,
                    help="Max notional as %% of capital (default 25)")
    ap.add_argument("--leverage", action="store_true",
                    help="Allow instrument leverage where available")
    ap.add_argument("--fast", action="store_true",
                    help="Skip the historical-consensus pass (stability scored neutral)")
    ap.add_argument("--force", action="store_true",
                    help="Start even if another monitor already owns this output "
                         "directory. Both will overwrite the same report files.")
    a = ap.parse_args(argv)

    cfg = MonitorConfig(symbol=a.symbol, interval=a.interval,
                        force_interval_seconds=a.every, output_dir=Path(a.out),
                        llm_commentary=a.llm, capital=a.capital, currency=a.currency,
                        risk_pct=a.risk, max_position_pct=a.max_exposure,
                        use_leverage=a.leverage, compute_stability=not a.fast)
    if a.once:
        if not a.symbol:
            state = read_chart_from_browser()
            if not state:
                print("No TradingView tab found and no --symbol given.", file=sys.stderr)
                return 1
            cfg.symbol, cfg.interval = state.symbol, state.interval
        snap = analyze_once(cfg.symbol, cfg.interval or "1d", cfg=cfg, trigger="once")
        for p in write_outputs(snap, cfg):
            print(f"wrote {p}")
        print(render_markdown(snap))
        return 0

    # One daemon per output directory. Without this every launch adds another
    # process writing the same files, and the report you read is whichever one
    # finished last.
    lock = SingleInstance(cfg.output_dir / ".monitor.lock")
    holder = lock.acquire()
    if holder and not a.force:
        print(f"A monitor is already running for {cfg.output_dir.resolve()} "
              f"({holder}).\nStop it first, or pass --force to run a second one "
              f"anyway, or use --out to write somewhere else.", file=sys.stderr)
        return 1
    if holder and a.force:
        _log(f"WARNING: {holder} already owns this directory; both will overwrite "
             f"the same report files.")
    try:
        run_monitor(cfg)
    finally:
        lock.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
