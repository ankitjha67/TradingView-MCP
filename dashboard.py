"""
Quant Desk — Streamlit dashboard.

Run with:  streamlit run dashboard.py
Or simply: python start.py

Five pages: Live Signal, Strategy Explorer, Backtest Lab, Monitor, Settings.

Design note: every number shown here is computed from real fetched market data.
Where something cannot be computed, the page says so rather than showing a
plausible-looking placeholder. The previous dashboard drew a random-number
"equity curve" next to real metrics, which is worse than showing nothing.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))

from tradingview_mcp.core.quant.backtest import compare_strategies, run_backtest, walk_forward
from tradingview_mcp.core.quant.confidence import (
    calibrate, consensus_series, score_trade,
)
from tradingview_mcp.core.quant.consensus import (
    compute_consensus, compute_risk_levels, evaluate_all,
)
from tradingview_mcp.core.quant.features import build_features
from tradingview_mcp.core.quant.sizing import (
    CAPITAL_TIERS, MAX_CAPITAL, MIN_CAPITAL, CapitalConfig, build_trade_plan,
    resolve_instrument,
)
from tradingview_mcp.core.quant.llm import (
    PROVIDERS, LLMConfig, analyze as llm_analyze, list_local_models,
    load_config, save_config, test_connection,
)
from tradingview_mcp.core.quant.performance import analyse as analyse_performance
from tradingview_mcp.core.quant.performance import render_markdown as render_performance
from tradingview_mcp.core.quant.market_data import (
    CANONICAL_INTERVALS, fetch_ohlcv, parse_symbol, seconds_to_next_close,
)
from tradingview_mcp.core.quant.monitor import analyze_once, read_chart_from_browser, render_markdown
from tradingview_mcp.core.quant.registry import get_registry

st.set_page_config(page_title="Quant Desk", page_icon="◧", layout="wide",
                   initial_sidebar_state="expanded")

# ── theme ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  :root {
    --bg:#0c1017; --panel:#141a24; --line:#232b38; --ink:#e8edf5;
    --muted:#9aa7bd; --long:#22c55e; --short:#ef4444; --flat:#94a3b8; --accent:#5b8def;
  }
  .stApp { background: var(--bg); color: var(--ink); }

  /* Streamlit renders the sidebar and main pane in their own containers; without
     these the panel colour stops at the app shell and leaves white gutters. */
  section[data-testid="stSidebar"] > div { background: var(--panel); }
  section[data-testid="stSidebar"] { border-right:1px solid var(--line); }
  [data-testid="stAppViewContainer"], [data-testid="stHeader"] { background: var(--bg); }
  [data-testid="stVerticalBlock"] { gap: 0.75rem; }

  h1,h2,h3,h4 { color: var(--ink); font-weight:650; letter-spacing:-0.01em; }
  /* Captions defaulted to a grey that failed contrast on this background. */
  .stCaption, [data-testid="stCaptionContainer"], small { color: var(--muted) !important; }
  section[data-testid="stSidebar"] label,
  section[data-testid="stSidebar"] .stMarkdown p { color: var(--ink); }

  .card { background: var(--panel); border:1px solid var(--line); border-radius:12px;
          padding:16px 18px; height:100%; }
  .card-label { font-size:.7rem; text-transform:uppercase; letter-spacing:.09em;
                color: var(--muted); margin-bottom:6px; }
  .card-value { font-size:1.6rem; font-weight:650; line-height:1.15;
                font-variant-numeric: tabular-nums; }
  .card-sub { font-size:.78rem; color: var(--muted); margin-top:4px; }
  .verdict { border-radius:14px; padding:22px 26px; border:1px solid var(--line);
             background: var(--panel); }
  .verdict-dir { font-size:2.4rem; font-weight:700; letter-spacing:-0.02em; }
  .long { color: var(--long); } .short { color: var(--short); } .flat { color: var(--flat); }
  .bar { height:9px; border-radius:5px; background:#1e2634; overflow:hidden; display:flex; }
  .bar > span { display:block; height:100%; }
  .pill { display:inline-block; padding:2px 9px; border-radius:999px; font-size:.7rem;
          border:1px solid var(--line); color:var(--muted); margin-right:5px; }

  /* Inputs and tables ship light by default and stood out badly against the panel. */
  .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] > div {
      background: #0f1520 !important; color: var(--ink) !important;
      border-color: var(--line) !important; }
  [data-testid="stDataFrame"], [data-testid="stTable"] { background: var(--panel); }
  .stTabs [data-baseweb="tab"] { font-size:.9rem; color: var(--muted); }
  .stTabs [aria-selected="true"] { color: var(--ink); }
  .stExpander { border:1px solid var(--line) !important; border-radius:10px; background: var(--panel); }
  code { color:#9ec5ff; background:#0f1520; padding:1px 5px; border-radius:4px; }
  .note { font-size:.8rem; color:var(--muted); border-left:2px solid var(--line);
          padding-left:10px; margin:8px 0; }
</style>
""", unsafe_allow_html=True)


def card(label: str, value: str, sub: str = "", color: str = "") -> str:
    style = f' style="color:{color}"' if color else ""
    return (f'<div class="card"><div class="card-label">{label}</div>'
            f'<div class="card-value"{style}>{value}</div>'
            f'<div class="card-sub">{sub}</div></div>')



# ── charts ────────────────────────────────────────────────────────────────────
# Built with Altair rather than st.line_chart so three things can be controlled
# that the shorthand cannot: y-axis scaling, label orientation, and colour.

CHART_BG = "#141a24"
GRID = "#232b38"
INK = "#e8edf5"
MUTED = "#8b97ab"


def _theme(chart: alt.Chart, height: int) -> alt.Chart:
    return (chart
            .properties(height=height, background=CHART_BG)
            .configure_view(strokeWidth=0)
            .configure_axis(gridColor=GRID, domainColor=GRID, tickColor=GRID,
                            labelColor=MUTED, titleColor=MUTED, labelFontSize=11)
            .configure_legend(labelColor=INK, titleColor=MUTED, orient="top",
                              direction="horizontal"))


def price_chart(df: pd.DataFrame, height: int = 300) -> alt.Chart:
    """
    Price with EMAs, y-axis fitted to the data.

    `zero=False` is the point: a default axis anchored at 0 renders BTC at 63,000
    as a flat line across the top of an empty plot.
    """
    d = df.reset_index()
    d.columns = ["t"] + list(d.columns[1:])
    long = d.melt("t", value_vars=[c for c in d.columns if c != "t"],
                  var_name="series", value_name="value").dropna()
    lo, hi = float(long["value"].min()), float(long["value"].max())
    pad = (hi - lo) * 0.06 or hi * 0.01
    return _theme(
        alt.Chart(long).mark_line(strokeWidth=1.6).encode(
            x=alt.X("t:T", title=None),
            y=alt.Y("value:Q", title=None,
                    scale=alt.Scale(domain=[lo - pad, hi + pad], zero=False, nice=False)),
            color=alt.Color("series:N", title=None,
                            scale=alt.Scale(range=["#e8edf5", "#5b8def", "#f59e0b"])),
            tooltip=[alt.Tooltip("t:T", title="time"), "series:N",
                     alt.Tooltip("value:Q", format=",.4f")]),
        height)


def category_chart(rows: list[dict], height: int = 300) -> alt.Chart:
    """
    Category scores as horizontal bars.

    Vertical bars force 16 long category names into rotated, overlapping labels;
    horizontal bars give each one a full readable row.
    """
    d = pd.DataFrame(rows)
    return _theme(
        alt.Chart(d).mark_bar().encode(
            y=alt.Y("category:N", sort="-x", title=None),
            x=alt.X("score:Q", title="consensus score",
                    scale=alt.Scale(domain=[-1, 1])),
            color=alt.condition(alt.datum.score > 0,
                                alt.value("#22c55e"), alt.value("#ef4444")),
            tooltip=["category:N", alt.Tooltip("score:Q", format="+.3f"),
                     alt.Tooltip("buy:Q", title="long"),
                     alt.Tooltip("sell:Q", title="short"),
                     alt.Tooltip("available:Q", title="models available")]),
        height)


def equity_chart(equity: pd.Series, height: int = 240) -> alt.Chart:
    """Equity against its running peak, so drawdowns read at a glance."""
    d = pd.DataFrame({"t": equity.index, "Equity": equity.to_numpy(),
                      "Peak": equity.cummax().to_numpy()})
    long = d.melt("t", var_name="series", value_name="value")
    lo, hi = float(long["value"].min()), float(long["value"].max())
    pad = (hi - lo) * 0.05 or 0.01
    return _theme(
        alt.Chart(long).mark_line(strokeWidth=1.6).encode(
            x=alt.X("t:T", title=None),
            y=alt.Y("value:Q", title=None,
                    scale=alt.Scale(domain=[lo - pad, hi + pad], zero=False, nice=False)),
            color=alt.Color("series:N", title=None,
                            scale=alt.Scale(range=["#5b8def", "#4b5563"])),
            tooltip=[alt.Tooltip("t:T", title="time"), "series:N",
                     alt.Tooltip("value:Q", format=",.4f")]),
        height)


def drawdown_chart(equity: pd.Series, height: int = 150) -> alt.Chart:
    dd = (equity / equity.cummax() - 1) * 100
    d = pd.DataFrame({"t": dd.index, "drawdown": dd.to_numpy()})
    return _theme(
        alt.Chart(d).mark_area(color="#ef4444", opacity=0.75, line={"color": "#ef4444"}).encode(
            x=alt.X("t:T", title=None),
            y=alt.Y("drawdown:Q", title="drawdown %"),
            tooltip=[alt.Tooltip("t:T", title="time"),
                     alt.Tooltip("drawdown:Q", format=".2f")]),
        height)


def dir_class(d: str) -> str:
    return {"BUY": "long", "SELL": "short"}.get(d, "flat")


@st.cache_resource
def registry():
    return get_registry()


@st.cache_data(ttl=45, show_spinner=False)
def load_market(symbol: str, interval: str, exchange: str = ""):
    md = fetch_ohlcv(symbol, interval, exchange)
    return md.df, md.to_dict()


REG = registry()
SUMMARY = REG.summary()

# ── sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ◧ Quant Desk")
    st.caption(f"{SUMMARY['total']} models · {SUMMARY['families']} families · "
               f"{SUMMARY['categories']} categories")

    st.divider()
    follow = st.toggle(
        "Follow my TradingView chart", value=st.session_state.get("follow", False),
        help="Reads the symbol and interval from your open TradingView chart and re-analyses "
             "at every bar close on that interval. Works with the TradingView desktop app "
             "out of the box, or Chrome started with --remote-debugging-port=9222.")
    st.session_state["follow"] = follow

    if follow:
        chart = read_chart_from_browser()
        if chart and chart.is_valid():
            st.session_state["symbol"] = (f"{chart.exchange}:{chart.symbol}"
                                          if chart.exchange else chart.symbol)
            st.session_state["interval"] = chart.interval
            st.success(f"Following **{chart.exchange}:{chart.symbol}** @ **{chart.interval}**")
        else:
            st.error("No TradingView chart detected. Open a chart in the TradingView desktop "
                     "app, or start Chrome with `--remote-debugging-port=9222`.")
    elif st.button("Detect chart once", use_container_width=True):
        chart = read_chart_from_browser()
        if chart and chart.is_valid():
            st.session_state["symbol"] = (f"{chart.exchange}:{chart.symbol}"
                                          if chart.exchange else chart.symbol)
            st.session_state["interval"] = chart.interval
            st.rerun()
        else:
            st.info("No TradingView chart detected — type a symbol below instead.")

    symbol = st.text_input("Symbol", value=st.session_state.get("symbol", "BINANCE:BTCUSDT"),
                           disabled=follow,
                           help="TradingView format (BINANCE:BTCUSDT, NSE:RELIANCE) or a plain ticker (AAPL)")
    _iv = st.session_state.get("interval", "1h")
    interval = st.selectbox("Interval", CANONICAL_INTERVALS, disabled=follow,
                            index=CANONICAL_INTERVALS.index(_iv) if _iv in CANONICAL_INTERVALS else 5)
    if not follow:
        st.session_state["symbol"], st.session_state["interval"] = symbol, interval
    else:
        symbol, interval = st.session_state["symbol"], st.session_state["interval"]

    # Show how the symbol was resolved — a TradingView ticker is not always the
    # ticker a data provider uses, and a silent mismatch is the hardest failure
    # to diagnose from the UI.
    _spec = parse_symbol(symbol)
    if _spec.asset_class == "aggregate":
        st.warning(f"`{symbol}` is a TradingView aggregate series (market cap / dominance). "
                   "There is no tradeable instrument behind it — switch to a pair such as "
                   "`BINANCE:BTCUSDT`.", icon="⚠")
    elif not (_spec.yahoo or _spec.binance):
        st.error(f"`{symbol}` could not be mapped to any data provider.", icon="⚠")

    spec = parse_symbol(symbol)
    st.caption(f"→ `{spec.asset_class}` · resolves to `{spec.yahoo or spec.binance or spec.ticker}`")

    st.divider()
    st.markdown("**Account**")
    currency = st.selectbox("Currency", ["INR", "USD", "EUR", "GBP"], index=0)
    capital = st.number_input(
        f"Capital ({currency})", min_value=float(MIN_CAPITAL), max_value=float(MAX_CAPITAL),
        value=float(st.session_state.get("capital", 100_000.0)), step=1_000.0, format="%.0f",
        help=f"Supported range {MIN_CAPITAL:,.0f} – {MAX_CAPITAL:,.0f}")
    st.session_state["capital"] = capital
    capital = st.select_slider(
        "…or pick a tier", options=list(CAPITAL_TIERS),
        value=min(CAPITAL_TIERS, key=lambda t: abs(t - capital)),
        format_func=lambda v: f"{v:,.0f}")
    risk_pct = st.slider("Risk per trade (%)", 0.1, 5.0,
                         float(st.session_state.get("risk_pct", 1.0)), 0.1,
                         help="Percentage of capital risked if the stop is hit. "
                              "Professional desks rarely exceed 1–2%.")
    st.session_state["risk_pct"] = risk_pct
    max_exposure = st.slider("Max exposure (% of capital)", 5, 100, 25, 5,
                             help="Cap on notional position value.")
    use_leverage = st.checkbox("Allow leverage where available", value=False,
                               help="Applies to F&O and forex. Losses scale with notional, "
                                    "not with margin posted.")
    cap_cfg = CapitalConfig(capital=float(capital), currency=currency, risk_pct=risk_pct,
                            max_position_pct=float(max_exposure), use_leverage=use_leverage)

    st.divider()
    st.markdown("**Filters**")
    include_proxies = st.checkbox("Include proxy models", value=True,
                                  help="Models approximating a published method from substituted data. "
                                       f"{SUMMARY['proxies']} of {SUMMARY['total']} are proxies.")
    chosen_cats = st.multiselect("Categories", REG.categories(), default=[],
                                 help="Empty = all categories")
    score_stability = st.checkbox("Score signal stability", value=True,
                                  help="Computes the historical consensus path (~1s extra) so "
                                       "the confidence engine can tell a persistent read from "
                                       "one that flipped on this bar.")

    st.divider()
    cfg = load_config()
    st.caption(f"LLM: {'on · ' + PROVIDERS[cfg.provider].label if cfg.enabled else 'off'}")


def selected_models():
    models = REG.all()
    if chosen_cats:
        models = [m for m in models if m.category in chosen_cats]
    if not include_proxies:
        models = [m for m in models if not m.is_proxy]
    return models


tabs = st.tabs(["Live Signal", "Strategy Explorer", "Backtest Lab", "Monitor", "Settings"])

# ══ LIVE SIGNAL ═══════════════════════════════════════════════════════════════
with tabs[0]:
    if follow:
        # Re-run the whole page at each bar close, so the dashboard tracks the chart
        # on the chart's own interval rather than on an arbitrary timer.
        @st.fragment(run_every=5)
        def _bar_close_watch():
            remaining = seconds_to_next_close(interval)
            st.caption(f"Following **{symbol}** @ **{interval}** · next analysis in "
                       f"{remaining:.0f}s (at bar close)")
            if remaining <= 5:
                load_market.clear()
                st.rerun()
        _bar_close_watch()

    try:
        with st.spinner(f"Fetching {symbol} @ {interval}…"):
            df, meta = load_market(symbol, interval, spec.exchange)
    except Exception as exc:
        st.error(f"Could not load market data for **{symbol}** at **{interval}**.")
        st.code(str(exc), language="text")
        res = spec.yahoo or spec.binance or "(unresolved)"
        st.info(f"`{symbol}` resolved to `{res}` ({spec.asset_class}). "
                "If that mapping looks wrong, the symbol may need adding to the map in "
                "`market_data.py`. If it looks right, the provider may have no history at "
                "this interval — 1-minute data is typically kept for about 7 days.")
        st.stop()

    f = build_features(df.tail(1500), interval, spec.ticker or symbol)
    models = selected_models()
    with st.spinner(f"Evaluating {len(models)} models…"):
        t0 = time.time()
        _, all_signals = evaluate_all(f, interval, symbol, strategies=models)
        con = compute_consensus(f, interval, symbol, strategies=models)
        risk = compute_risk_levels(f, con.direction)
        voting = [(s, sg) for s, sg in all_signals if sg.available and abs(sg.score) >= 0.15]
        path = consensus_series(f, models) if score_stability else None
        conf = score_trade(con, f, voting, risk_reward=risk.risk_reward, score_path=path)
        plan = build_trade_plan(symbol, con, risk, conf, cap_cfg)
        elapsed = time.time() - t0

    dc = dir_class(con.direction)
    label = {"BUY": "LONG", "SELL": "SHORT", "NEUTRAL": "NO POSITION"}[con.direction]

    left, right = st.columns([3, 2])
    with left:
        st.markdown(f"""
        <div class="verdict">
          <div class="card-label">Consensus · {con.symbol} · {con.interval}</div>
          <div class="verdict-dir {dc}">{label}</div>
          <div class="card-sub">score <b>{con.score:+.3f}</b> · confidence <b>{con.confidence:.0%}</b>
            · agreement <b>{con.agreement:.0%}</b></div>
          <div style="margin-top:14px">
            <div class="bar">
              <span style="width:{con.buy_votes / max(con.models_voting,1) * 100:.1f}%;background:var(--long)"></span>
              <span style="width:{con.sell_votes / max(con.models_voting,1) * 100:.1f}%;background:var(--short)"></span>
            </div>
            <div class="card-sub">{con.buy_votes} long · {con.sell_votes} short ·
              {con.models_voting} voting of {con.models_available} available
              ({con.models_total} in library)</div>
          </div>
        </div>""", unsafe_allow_html=True)
    with right:
        st.markdown(f"""
        <div class="card">
          <div class="card-label">Market state</div>
          <div style="font-size:1.05rem;font-weight:600;margin-bottom:10px">{con.regime.get('label','—')}</div>
          <div class="card-sub">
            Price <b>{con.price:,.4f}</b><br>
            ADX <b>{con.regime.get('adx',0):.1f}</b> ·
            Hurst <b>{con.regime.get('hurst',0):.2f}</b><br>
            Realised vol <b>{con.regime.get('realized_vol_pct',0):.1f}%</b>
            (pct <b>{con.regime.get('vol_percentile',0):.2f}</b>)<br>
            Drawdown <b>{con.regime.get('drawdown_pct',0):.1f}%</b>
          </div>
        </div>""", unsafe_allow_html=True)

    for w in con.warnings:
        st.warning(w, icon="⚠")

    # ── confidence ───────────────────────────────────────────────────────────
    st.write("")
    grade_colour = {"A+": "#22c55e", "A": "#22c55e", "B": "#84cc16",
                    "C": "#eab308", "D": "#f97316", "F": "#ef4444"}[conf.grade]
    verdict_colour = {"TRADE": "#22c55e", "REDUCED": "#eab308",
                      "STAND ASIDE": "#ef4444"}[conf.verdict]

    gcol, ccol = st.columns([1, 3])
    with gcol:
        st.markdown(f"""
        <div class="card" style="text-align:center">
          <div class="card-label">Confidence</div>
          <div style="font-size:3rem;font-weight:700;color:{grade_colour};line-height:1.05">
            {conf.grade}</div>
          <div class="card-value" style="font-size:1.15rem">{conf.score:.0f}<span
            style="color:var(--muted);font-size:.9rem">/100</span></div>
          <div style="margin-top:8px;color:{verdict_colour};font-weight:600;font-size:.85rem">
            {conf.verdict}</div>
          <div class="card-sub">size ×{conf.size_multiplier:.2f}</div>
        </div>""", unsafe_allow_html=True)
    with ccol:
        comp_df = pd.DataFrame([{
            "Component": c.name, "Score": c.score, "Weight": c.weight,
            "Points": c.contribution, "Basis": c.detail} for c in conf.components])
        st.dataframe(
            comp_df.style.format({"Score": "{:.2f}", "Weight": "{:.0%}", "Points": "{:.1f}"})
            .background_gradient(subset=["Points"], cmap="RdYlGn", vmin=0, vmax=20),
            use_container_width=True, hide_index=True, height=310)

    for v in conf.vetoes:
        st.error(f"**Veto** — {v}", icon="⛔")
    for v in conf.cautions:
        st.warning(f"{v}  \n_Position size halved._", icon="⚠")

    st.write("")
    cols = st.columns(5)
    rr = risk.risk_reward
    items = [
        ("Entry", f"{risk.entry:,.4f}", "last close", ""),
        ("Stop", f"{risk.stop_loss:,.4f}", f"1.5 × ATR ({risk.atr:,.4f})", "var(--short)"),
        ("Target", f"{risk.take_profit:,.4f}", "3.0 × ATR", "var(--long)"),
        ("Risk : Reward", f"{rr:.2f}", "reward per unit risked", ""),
        ("Scan time", f"{elapsed:.2f}s", f"{len(models)} models", ""),
    ]
    for col, (l, v, s, c) in zip(cols, items):
        col.markdown(card(l, v, s, c), unsafe_allow_html=True)

    # ── position ─────────────────────────────────────────────────────────────
    st.markdown("#### Position")
    pos, inst = plan["position"], resolve_instrument(symbol, spec)
    if pos["tradeable"]:
        lots_txt = f" ({pos['lots']:g} lots)" if pos.get("lots") else ""
        p = st.columns(5)
        p[0].markdown(card("Size", f"{pos['quantity']:g}",
                           f"{pos['units_label']}{lots_txt}"), unsafe_allow_html=True)
        p[1].markdown(card("Deployed", f"{currency} {pos['capital_required']:,.0f}",
                           f"of {currency} {pos['capital']:,.0f} capital"), unsafe_allow_html=True)
        p[2].markdown(card("At risk", f"{currency} {pos['risk_amount']:,.0f}",
                           f"{pos['risk_pct_of_capital']:.2f}% of capital",
                           "var(--short)"), unsafe_allow_html=True)
        p[3].markdown(card("Reward at target", f"{currency} {pos['reward_amount']:,.0f}",
                           f"{pos['return_on_capital_pct']:.2f}% of capital",
                           "var(--long)"), unsafe_allow_html=True)
        p[4].markdown(card("Notional", f"{currency} {pos['notional_account_ccy']:,.0f}",
                           f"{pos['leverage_used']:g}× leverage" if pos["leverage_used"] > 1
                           else "unlevered"), unsafe_allow_html=True)
        for w in pos.get("warnings", []):
            st.caption(f"⚠ {w}")
    else:
        st.error("**No position.** " + " ".join(pos.get("reasons", [])), icon="🚫")

    st.caption(f"{inst.asset_class} · {inst.note} · quoted in {inst.quote_currency}"
               + (f" (converted at {pos['fx_rate']:.2f} {currency}/{inst.quote_currency})"
                  if pos["fx_rate"] != 1.0 else ""))

    ladder = plan.get("capital_ladder") or []
    if ladder:
        with st.expander(f"Same trade sized across {MIN_CAPITAL:,.0f} → {MAX_CAPITAL:,.0f}"):
            lad = pd.DataFrame(ladder)
            lad["status"] = np.where(lad["tradeable"], "", lad["note"])
            st.dataframe(
                lad[["capital", "quantity", "lots", "capital_required", "risk_amount",
                     "risk_pct", "reward_amount", "status"]]
                .rename(columns={"capital": f"Capital ({currency})", "quantity": "Size",
                                 "lots": "Lots", "capital_required": "Deployed",
                                 "risk_amount": "At risk", "risk_pct": "Risk %",
                                 "reward_amount": "Reward", "status": "Note"}),
                use_container_width=True, hide_index=True)
            st.caption("Risk % stays near your target across the range — that is the point of "
                       "sizing from the stop distance rather than from capital. Where a row is "
                       "not tradeable, the note says exactly what would change that.")

    st.write("")
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("#### Price")
        plot = df.tail(320).copy()
        plot["EMA 20"] = plot["close"].ewm(span=20, adjust=False).mean()
        plot["EMA 50"] = plot["close"].ewm(span=50, adjust=False).mean()
        st.altair_chart(price_chart(plot[["close", "EMA 20", "EMA 50"]]),
                        use_container_width=True)
        st.caption(f"{meta['bars']} bars from **{meta['provider']}** · last bar `{meta['last_bar']}`"
                   + (" · cached" if meta["from_cache"] else ""))
    with c2:
        st.markdown("#### Category scores")
        cat_rows = [c.to_dict() for c in con.categories if c.available > 0]
        if cat_rows:
            st.altair_chart(category_chart(cat_rows, height=max(300, 20 * len(cat_rows))),
                            use_container_width=True)

    st.markdown("#### Where the conviction comes from")
    lc, rc = st.columns(2)
    for col, rows, title in ((lc, con.top_long, "Strongest long"), (rc, con.top_short, "Strongest short")):
        with col:
            st.markdown(f"**{title}**")
            if not rows:
                st.caption("No models on this side.")
            for s in rows[:6]:
                with st.expander(f"`{s.score:+.2f}`  {s.strategy}"):
                    st.write(s.rationale)
                    strat = REG.get(s.strategy)
                    if strat:
                        st.caption(f"**Research:** {strat.research}")
                        if strat.is_proxy:
                            st.caption(f"⚠ **Proxy:** {strat.proxy_note}")
                    if s.diagnostics:
                        st.json(s.diagnostics, expanded=False)

    if con.unavailable_reasons:
        with st.expander(f"{con.models_total - con.models_available} models did not run — why"):
            for reason, n in sorted(con.unavailable_reasons.items(), key=lambda x: -x[1]):
                st.write(f"- **{n}** × {reason}")
            st.caption("Models needing a data feed you have not connected (options chains, "
                       "fundamentals, on-chain, cross-sectional universes) stand down rather "
                       "than voting on a substitute.")

    st.markdown("#### Commentary")
    cfg = load_config()
    if not cfg.enabled:
        st.info("LLM commentary is off. Enable it in **Settings** — everything above works without it.")
    elif st.button("Generate analysis"):
        with st.spinner("Asking the model…"):
            res = llm_analyze(con.to_dict(), risk.to_dict(), cfg,
                              extra={"confidence": conf.to_dict(),
                                     "position": plan["position"]})
        if res.get("ok"):
            st.caption(f"{res['provider']} · {res['model']}")
            st.markdown(res["analysis"])
        else:
            st.error(res.get("error", res.get("message", "unavailable")))

# ══ STRATEGY EXPLORER ═════════════════════════════════════════════════════════
with tabs[1]:
    st.markdown("### Strategy library")
    st.caption(f"{SUMMARY['total']} models · {SUMMARY['families']} independent families · "
               f"{SUMMARY['proxies']} proxies. Every model carries its source citation.")

    specs = pd.DataFrame(REG.specs())
    a, b, c = st.columns(3)
    cat_f = a.multiselect("Category", sorted(specs["category"].unique()), key="ex_cat")
    hor_f = b.multiselect("Horizon", sorted(specs["horizon"].unique()), key="ex_hor")
    q = c.text_input("Search name, description or citation", key="ex_q")

    view = specs.copy()
    if cat_f:
        view = view[view["category"].isin(cat_f)]
    if hor_f:
        view = view[view["horizon"].isin(hor_f)]
    if q:
        ql = q.lower()
        view = view[view.apply(lambda r: ql in f"{r['name']} {r['description']} {r['research']}".lower(), axis=1)]

    st.caption(f"{len(view)} of {len(specs)} models")
    st.dataframe(
        view[["name", "category", "family", "horizon", "min_bars", "is_proxy", "research"]]
        .rename(columns={"min_bars": "min bars", "is_proxy": "proxy"}),
        use_container_width=True, height=380, hide_index=True)

    if len(view):
        pick = st.selectbox("Inspect model", view["name"].tolist())
        row = view[view["name"] == pick].iloc[0]
        st.markdown(f"#### {row['name']}")
        st.write(row["description"])
        m1, m2 = st.columns([2, 1])
        with m1:
            st.markdown(f"**Research:** {row['research']}")
            if row["is_proxy"]:
                st.warning(f"**Proxy implementation.** {row['proxy_note']}", icon="⚠")
        with m2:
            st.markdown(f"<span class='pill'>{row['category']}</span>"
                        f"<span class='pill'>{row['horizon']}</span>"
                        f"<span class='pill'>family: {row['family']}</span>",
                        unsafe_allow_html=True)
            st.caption(f"Needs: {', '.join(row['needs'])} · min {row['min_bars']} bars")
            if row["params"]:
                st.json(row["params"], expanded=False)

        if st.button("Run this model on the selected symbol"):
            try:
                df2, _ = load_market(symbol, interval, spec.exchange)
                f2 = build_features(df2.tail(1500), interval, symbol)
                strat = REG.get(pick)
                sig = strat.analyze(f2)
                bt = run_backtest(strat, f2)
                if sig.available:
                    k = st.columns(4)
                    k[0].markdown(card("Signal", sig.direction, f"score {sig.score:+.3f}",
                                       {"BUY": "#22c55e", "SELL": "#ef4444"}.get(sig.direction, "")),
                                  unsafe_allow_html=True)
                    k[1].markdown(card("Sharpe", f"{bt.sharpe_ratio:.2f}", "net of costs"), unsafe_allow_html=True)
                    k[2].markdown(card("Return", f"{bt.total_return_pct:+.1f}%",
                                       f"vs {bt.buy_and_hold_pct:+.1f}% hold"), unsafe_allow_html=True)
                    k[3].markdown(card("Trades", f"{bt.total_trades}", f"{bt.win_rate_pct:.0f}% win"),
                                  unsafe_allow_html=True)
                    st.info(sig.rationale)
                    if len(bt.equity_curve):
                        st.altair_chart(equity_chart(bt.equity_curve, 220),
                                        use_container_width=True)
                else:
                    st.warning(f"Cannot run here: {sig.reason_unavailable}")
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}")

# ══ BACKTEST LAB ══════════════════════════════════════════════════════════════
with tabs[2]:
    st.markdown("### Backtest lab")
    st.caption("Signals act on the **next** bar, never the signalling bar. Commission and "
               "slippage are charged on both legs. Ranked by Sharpe, not total return.")

    a, b, c, d = st.columns(4)
    comm = a.number_input("Commission %", 0.0, 1.0, 0.05, 0.01)
    slip = b.number_input("Slippage %", 0.0, 1.0, 0.05, 0.01)
    shorts = c.checkbox("Allow shorts", value=True)
    sort_by = d.selectbox("Rank by", ["sharpe_ratio", "total_return_pct", "calmar_ratio",
                                      "profit_factor", "win_rate_pct", "max_drawdown_pct"])

    if st.button("Run full library backtest", type="primary"):
        try:
            df3, _ = load_market(symbol, interval, spec.exchange)
            f3 = build_features(df3.tail(1500), interval, symbol)
            with st.spinner(f"Backtesting {len(selected_models())} models…"):
                t0 = time.time()
                res = compare_strategies(f3, strategies=selected_models(), commission_pct=comm,
                                         slippage_pct=slip, allow_short=shorts, sort_by=sort_by)
                st.session_state["bt"] = (res, time.time() - t0)
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}")

    if "bt" in st.session_state:
        res, took = st.session_state["bt"]
        k = st.columns(5)
        k[0].markdown(card("Tested", f"{res['models_tested']}", f"in {took:.1f}s"), unsafe_allow_html=True)
        k[1].markdown(card("Ranked", f"{res['models_ranked']}", "enough trades"), unsafe_allow_html=True)
        k[2].markdown(card("Buy & hold", f"{res['buy_and_hold_pct']:+.2f}%", "same window"),
                      unsafe_allow_html=True)
        k[3].markdown(card("Beat hold", f"{res['beat_buy_and_hold']}",
                           f"of {res['models_ranked']} ranked"), unsafe_allow_html=True)
        k[4].markdown(card("Skipped", f"{res['models_skipped']}", "could not run"), unsafe_allow_html=True)

        st.markdown(f'<div class="note">Window: {res["period_start"][:10]} → {res["period_end"][:10]} '
                    f'({res["bars"]} bars). A model beating buy-and-hold on one window and one symbol '
                    f'is not evidence of edge — use walk-forward below before believing any ranking.</div>',
                    unsafe_allow_html=True)

        rank = pd.DataFrame(res["ranking"])
        if not rank.empty:
            show = rank[["rank", "strategy", "category", "total_return_pct", "sharpe_ratio",
                         "max_drawdown_pct", "win_rate_pct", "total_trades", "exposure_pct"]]
            st.dataframe(show.rename(columns={
                "total_return_pct": "return %", "sharpe_ratio": "sharpe",
                "max_drawdown_pct": "max DD %", "win_rate_pct": "win %",
                "total_trades": "trades", "exposure_pct": "exposure %"}),
                use_container_width=True, height=420, hide_index=True)

            st.markdown("#### Full performance report")
            st.caption("The TradingView Strategy Tester view: All / Long / Short breakdown, "
                       "MAE/MFE, run-up, streaks, risk ratios and a monthly grid.")
            perf_pick = st.selectbox("Model", rank["strategy"].head(30).tolist(),
                                     key="perf_pick")
            if st.button("Build performance report"):
                df6, _ = load_market(symbol, interval, spec.exchange)
                f6 = build_features(df6.tail(1500), interval, symbol)
                strat6 = REG.get(perf_pick)
                bt6 = run_backtest(strat6, f6, commission_pct=comm, slippage_pct=slip,
                                   allow_short=shorts)
                if bt6.error:
                    st.warning(bt6.error)
                else:
                    rep = analyse_performance(
                        bt6, f6.df, bars_per_year=f6.bars_per_year,
                        commission_pct=comm, slippage_pct=slip, position=bt6.position)
                    a_, l_, s_ = rep.all_trades, rep.long_trades, rep.short_trades
                    r_ = rep.risk

                    k = st.columns(5)
                    k[0].markdown(card("Net profit", f"{a_.net_profit_pct:+.1f}%",
                                       f"vs {rep.buy_and_hold_pct:+.1f}% hold",
                                       "var(--long)" if a_.net_profit_pct > 0 else "var(--short)"),
                                  unsafe_allow_html=True)
                    k[1].markdown(card("Max drawdown", f"{r_.max_drawdown_pct:.1f}%",
                                       f"over {r_.max_drawdown_bars} bars", "var(--short)"),
                                  unsafe_allow_html=True)
                    k[2].markdown(card("Max run-up", f"{r_.max_runup_pct:+.1f}%",
                                       f"over {r_.max_runup_bars} bars", "var(--long)"),
                                  unsafe_allow_html=True)
                    k[3].markdown(card("Profit factor", f"{a_.profit_factor:.2f}",
                                       f"{a_.total_trades} trades"), unsafe_allow_html=True)
                    k[4].markdown(card("Sharpe / Sortino",
                                       f"{r_.sharpe:.2f} / {r_.sortino:.2f}",
                                       f"Calmar {r_.calmar:.2f}"), unsafe_allow_html=True)

                    for c_ in rep.caveats:
                        st.warning(c_, icon="⚠")

                    st.markdown("**Performance summary — All / Long / Short**")
                    side_rows = [
                        ("Net profit %", "net_profit_pct"), ("Profit factor", "profit_factor"),
                        ("Total trades", "total_trades"), ("Percent profitable", "percent_profitable"),
                        ("Avg trade %", "avg_trade_pct"), ("Avg win %", "avg_win_pct"),
                        ("Avg loss %", "avg_loss_pct"), ("Win/loss ratio", "win_loss_ratio"),
                        ("Largest win %", "largest_win_pct"), ("Largest loss %", "largest_loss_pct"),
                        ("Avg bars held", "avg_bars"),
                        ("Max consec. wins", "max_consecutive_wins"),
                        ("Max consec. losses", "max_consecutive_losses"),
                        ("Avg MAE %", "avg_mae_pct"), ("Avg MFE %", "avg_mfe_pct"),
                    ]
                    st.dataframe(pd.DataFrame(
                        [{"Metric": lbl, "All": getattr(a_, at),
                          "Long": getattr(l_, at), "Short": getattr(s_, at)}
                         for lbl, at in side_rows]),
                        use_container_width=True, hide_index=True, height=560)

                    rr, dd = st.columns(2)
                    with rr:
                        st.markdown("**Risk & return ratios**")
                        st.dataframe(pd.DataFrame([
                            {"Ratio": "Sharpe", "Value": r_.sharpe},
                            {"Ratio": "Sortino", "Value": r_.sortino},
                            {"Ratio": "Calmar", "Value": r_.calmar},
                            {"Ratio": "Omega", "Value": r_.omega},
                            {"Ratio": "Martin (UPI)", "Value": r_.martin_ratio},
                            {"Ratio": "K-ratio", "Value": r_.k_ratio},
                            {"Ratio": "Recovery factor", "Value": r_.recovery_factor},
                            {"Ratio": "Ulcer Index", "Value": r_.ulcer_index},
                            {"Ratio": "Tail ratio", "Value": r_.tail_ratio},
                        ]), use_container_width=True, hide_index=True, height=350)
                    with dd:
                        st.markdown("**Return distribution**")
                        st.dataframe(pd.DataFrame([
                            {"Metric": "CAGR %", "Value": r_.cagr_pct},
                            {"Metric": "Volatility %", "Value": r_.volatility_pct},
                            {"Metric": "Downside deviation %", "Value": r_.downside_deviation_pct},
                            {"Metric": "VaR 95% per bar", "Value": r_.var_95_pct},
                            {"Metric": "CVaR 95% per bar", "Value": r_.cvar_95_pct},
                            {"Metric": "Skew", "Value": r_.skew},
                            {"Metric": "Excess kurtosis", "Value": r_.excess_kurtosis},
                            {"Metric": "Time in market %", "Value": r_.time_in_market_pct},
                            {"Metric": "Positive bars %", "Value": r_.positive_bars_pct},
                        ]), use_container_width=True, hide_index=True, height=350)

                    if len(bt6.equity_curve):
                        st.markdown("**Equity curve and drawdown**")
                        eq = bt6.equity_curve
                        st.altair_chart(equity_chart(eq, 240), use_container_width=True)
                        st.altair_chart(drawdown_chart(eq, 150), use_container_width=True)

                    if rep.monthly_returns:
                        st.markdown("**Monthly returns (%)**")
                        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "YEAR"]
                        grid = pd.DataFrame(rep.monthly_returns).T.reindex(columns=months)
                        st.dataframe(
                            grid.style.format("{:+.1f}", na_rep="—")
                            .background_gradient(cmap="RdYlGn", vmin=-15, vmax=15),
                            use_container_width=True)

                    st.download_button("Download full report (Markdown)",
                                       render_performance(rep),
                                       file_name=f"{perf_pick.replace(' ', '_')}_performance.md")

            st.markdown("#### Is the confidence score worth anything here?")
            st.caption("Buckets every historical bar by consensus strength and measures what "
                       "actually happened next. This is a measurement of the past on this one "
                       "instrument — not a forecast, and not a win probability.")
            if st.button("Measure confidence calibration"):
                with st.spinner("Reconstructing the historical consensus path…"):
                    df5, _ = load_market(symbol, interval, spec.exchange)
                    f5 = build_features(df5.tail(1500), interval, symbol)
                    cal = calibrate(f5, selected_models(), horizon=10)
                if not cal.get("ok"):
                    st.warning(f"Could not calibrate: {cal.get('reason')}")
                else:
                    verdict = cal["verdict"]
                    (st.success if cal.get("stronger_signal_paid_more") else st.warning)(verdict)
                    cal_df = pd.DataFrame(cal["buckets"])
                    st.dataframe(cal_df, use_container_width=True, hide_index=True)
                    st.caption(f"Horizon {cal['horizon_bars']} bars · {cal['sample_bars']} usable "
                               f"bars. {cal['caveat']}")

            st.markdown("#### Walk-forward check")
            st.caption("Splits the sample into sequential folds. A model that only works in one "
                       "fold is fitted to that fold.")
            wf_pick = st.selectbox("Model", rank["strategy"].head(30).tolist())
            if st.button("Run walk-forward"):
                df4, _ = load_market(symbol, interval, spec.exchange)
                f4 = build_features(df4.tail(1500), interval, symbol)
                wf = walk_forward(REG.get(wf_pick), f4)
                if "error" in wf:
                    st.warning(wf["error"])
                else:
                    verdict = wf["verdict"]
                    (st.success if "consistent across" in verdict else
                     st.warning if "mixed" in verdict else st.error)(
                        f"**{verdict}** — profitable in {wf['profitable_folds']} folds, "
                        f"mean Sharpe {wf['mean_sharpe']} (± {wf['sharpe_std']})")
                    st.dataframe(pd.DataFrame(wf["folds"]), use_container_width=True, hide_index=True)

# ══ MONITOR ═══════════════════════════════════════════════════════════════════
with tabs[3]:
    st.markdown("### Live monitor")
    nxt = seconds_to_next_close(interval)
    st.markdown(f"""
    <div class="card">
      <div class="card-label">Refresh cadence</div>
      <div class="card-value">every {interval} bar close</div>
      <div class="card-sub">Next close in about <b>{nxt:.0f}s</b>. The monitor follows the interval on your
      TradingView chart — a 1m chart re-analyses every minute, a 15m chart every 15 minutes, a daily chart
      once a day. It checks the browser every 2s only to notice you switching symbol or interval, which
      triggers an immediate re-run.</div>
    </div>""", unsafe_allow_html=True)

    st.write("")
    if st.button("Run one analysis cycle now", type="primary"):
        with st.spinner("Running…"):
            try:
                snap = analyze_once(symbol, interval, spec.exchange, trigger="dashboard")
                st.session_state["snap"] = snap
            except Exception as exc:
                st.error(f"{type(exc).__name__}: {exc}")

    if "snap" in st.session_state:
        snap = st.session_state["snap"]
        st.markdown(render_markdown(snap))
        st.download_button("Download report (Markdown)", render_markdown(snap),
                           file_name=f"{symbol.replace(':', '_')}_{interval}.md")
        st.download_button("Download data (JSON)", json.dumps(snap.to_dict(), indent=2, default=str),
                           file_name=f"{symbol.replace(':', '_')}_{interval}.json")

    st.divider()
    st.markdown("#### Run continuously in a terminal")
    st.code(f"python -m tradingview_mcp.core.quant.monitor --symbol \"{symbol}\" --interval {interval}",
            language="bash")
    st.caption("Or omit `--symbol` to follow whatever chart you have open in TradingView. "
               "Add `--llm` for commentary, `--every 300` to force a fixed cadence.")

# ══ SETTINGS ══════════════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown("### Settings")
    st.markdown("#### AI commentary provider")
    st.caption("Optional. Save one API key and the whole pipeline runs — no IDE required. "
               "Signals, backtests and risk levels never depend on this.")

    cfg = load_config()
    keys = list(PROVIDERS)
    pcol, mcol = st.columns([1, 1])
    with pcol:
        pkey = st.selectbox("Provider", keys, index=keys.index(cfg.provider) if cfg.provider in keys else 0,
                            format_func=lambda k: PROVIDERS[k].label)
    prov = PROVIDERS[pkey]
    if prov.notes:
        st.caption(prov.notes)

    with mcol:
        opts = list(prov.models) or [prov.default_model]
        if prov.local:
            live = list_local_models(LLMConfig(provider=pkey))
            if live:
                opts = live
        model = st.selectbox("Model", opts + ["(type a custom name)"],
                             index=opts.index(cfg.model) if cfg.model in opts else 0)
        if model == "(type a custom name)":
            model = st.text_input("Custom model name", value=cfg.model or prov.default_model)

    api_key = ""
    if prov.needs_key:
        api_key = st.text_input(f"{prov.label} API key", type="password", value=cfg.api_key,
                                help=f"Or set the {prov.env_var} environment variable.")
    base_url = st.text_input("Base URL", value=cfg.base_url or prov.base_url,
                             help="Change only for a self-hosted or proxied endpoint.")

    o1, o2, o3 = st.columns(3)
    temperature = o1.slider("Temperature", 0.0, 1.0, float(cfg.temperature), 0.05)
    max_tokens = o2.number_input("Max tokens", 200, 8000, int(cfg.max_tokens), 100)
    enabled = o3.toggle("Enable commentary", value=cfg.enabled)

    new_cfg = LLMConfig(provider=pkey, model=model, api_key=api_key, base_url=base_url,
                        temperature=temperature, max_tokens=int(max_tokens), enabled=enabled)

    s1, s2 = st.columns(2)
    if s1.button("Save settings", type="primary", use_container_width=True):
        path = save_config(new_cfg)
        st.success(f"Saved to `{path}` (outside the project folder, so a key is never committed).")
    if s2.button("Test connection", use_container_width=True):
        with st.spinner("Testing…"):
            r = test_connection(new_cfg)
        if r["ok"]:
            st.success(f"Connected to **{r['provider']}** · `{r['model']}` in {r['latency_ms']} ms. "
                       f"Reply: `{r['reply']}`")
        else:
            st.error(r["error"])

    st.divider()
    st.markdown("#### Library health")
    h = st.columns(4)
    h[0].markdown(card("Models", str(SUMMARY["total"]), "loaded"), unsafe_allow_html=True)
    h[1].markdown(card("Families", str(SUMMARY["families"]), "independent"), unsafe_allow_html=True)
    h[2].markdown(card("Proxies", str(SUMMARY["proxies"]), "flagged & down-weighted"), unsafe_allow_html=True)
    h[3].markdown(card("Load errors", str(len(SUMMARY["load_errors"])),
                       "should be 0"), unsafe_allow_html=True)
    if SUMMARY["load_errors"]:
        st.error("\n".join(SUMMARY["load_errors"]))
    if SUMMARY["conflicts"]:
        st.warning("\n".join(SUMMARY["conflicts"]))

    st.markdown("#### Models by category")
    st.dataframe(pd.DataFrame(sorted(SUMMARY["by_category"].items(), key=lambda x: -x[1]),
                              columns=["category", "models"]),
                 use_container_width=True, hide_index=True, height=280)

st.divider()
st.caption("Systematic model output for research and analysis. Not investment advice. "
           "Backtested performance does not predict future results.")
