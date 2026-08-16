# Quant Desk — TradingView MCP

**A systematic multi-strategy analysis engine that follows your TradingView chart.**

Reads whatever chart you have open, fetches that instrument's history from free public
sources, evaluates **311 published quantitative models** against it, and produces one
auditable verdict with a confidence score and a concrete position size.

Runs entirely on your machine. No TradingView subscription, no market-data vendor, no paid
API. Works on the **free TradingView tier**.

```bash
python start.py
```

---

## What it does

| | |
|---|---|
| **311 models** across 16 categories, every one with a paper citation | ~1s full scan |
| **186 independent families** — the honest unit of diversification | family-weighted consensus |
| **Confidence engine** — 8 components, hard vetoes, empirical calibration | 0–100 score |
| **Position sizing** — capital 1,000 → 1,000,000, risk-first | refuses rather than guesses |
| **Vectorised backtest** with walk-forward validation | 311 models in ~2.5s |
| **Pine Script v6 export** for all 174 price-only models | numerically verified |
| **Any LLM provider** via one saved key | 14 providers, zero dependencies |

## The design principle

**A model that cannot run honestly reports unavailable rather than degrading to a price
proxy and voting anyway.**

119 of the 311 models need an options chain, fundamentals, a peer universe, order-book
depth, on-chain or news data. Without that feed they stand down. Every screen shows
*"N voting of M available of 311 in library"* — never "311 models agree".

22 models approximate their published method from substituted data. Each is labelled a
**proxy**, states exactly what was substituted, and counts for 40% of a vote.

### Why family weighting

Counting BUY votes treats 30 moving-average variants as 30 independent opinions. Under
that scheme whichever style is most numerous wins every vote, and *adding models makes the
bias worse*. Models sharing a `family` split one family's vote.

---

## Quick start

```bash
git clone https://github.com/ankitjha67/TradingView-MCP.git
cd TradingView-MCP
python start.py
```

`start.py` checks Python, installs what's missing, verifies the engine loads, detects any
IDE (Antigravity, VS Code, Cursor, Windsurf, Claude Desktop, Zed) and offers to wire up MCP,
then launches the dashboard. No IDE found means the dashboard, which needs none.

Non-technical walkthrough: **[EASY_SETUP_GUIDE.md](EASY_SETUP_GUIDE.md)**

## Interfaces

| Interface | Command |
|---|---|
| Streamlit dashboard | `python start.py` |
| Live monitor | `python -m tradingview_mcp.core.quant.monitor --capital 50000` |
| Universe scan | `python tools/scan_universe.py --capital 50000 --risk 1.0` |
| Pine export | `python tools/emit_pine.py --symbol AAPL --interval 1d` |
| Verify Pine | `python tools/verify_pine.py --symbol SPY --bars 2500` |
| MCP server | auto-configured into detected IDEs |

## Monitoring cadence

Re-analysis is aligned to the **close of the bar on your chart's interval** — every minute
on a 1m chart, every 15 minutes on 15m, daily on daily. Changing symbol or interval
re-analyses immediately. Stale feeds (weekends, closed markets) are detected, labelled and
backed off rather than re-reported as live.

Models read the last *closed* bar; re-running mid-bar re-reads a forming candle, so the
signal flickers then settles. One stable reading per bar is what you act on.

## Data

Free public sources, tried in order: **Binance** (crypto) → **Yahoo Finance** → **Stooq**.
Eleven intervals from 1-minute to monthly. Crypto, US and international equities, indices,
forex, commodities.

TradingView is used only to observe *which symbol and interval you are looking at* — no
TradingView data API is called, which is why the free plan suffices.

## Confidence engine

| Component | Weight | Question |
|---|---:|---|
| Family diversity | 20% | How many *independent ideas* agree |
| Conviction | 18% | Signal strength |
| Agreement | 18% | How one-sided the vote is |
| Concordance | 14% | Do structurally opposed categories agree |
| Regime alignment | 12% | Are agreeing models suited to conditions |
| Signal stability | 8% | Persistent, or flipped on this bar |
| Data quality | 6% | Coverage, depth, proxy share |
| Reward geometry | 4% | Does the target clear transaction costs |

**Hard vetoes** override any score: neutral consensus, agreement below 55%, fewer than 4
independent families, target move below 2× round-trip cost, turnover too thin to fill,
or an *inverted historical calibration* on that instrument.

**Empirical calibration** measures what the score has actually been worth: it buckets past
bars by signal strength and reports realised forward returns. Sometimes the answer is
*"has NOT reliably tracked forward returns here"* — and that becomes a veto.

## Position sizing

```
quantity = (capital × risk% × confidence_multiplier) ÷ (entry − stop)
```

Sizing from the **stop distance** holds risk constant across instruments. Then constrained
by lot granularity (crypto fractional, whole shares, NIFTY 75 / BANKNIFTY 15, forex micro
lots), exchange minimum order value, exposure cap, and available margin.

When a trade can't be taken it **refuses with the exact remedy** — *"Tradeable at ₹638,545
capital or 6.39% risk per trade"* — rather than silently falling back to a minimum position
that would exceed your stated risk limit.

## Pine Script export

All **174** price-only models export to Pine v6, plus a family-weighted consensus
indicator. Every translation is checked against an independent re-implementation of Pine
semantics — verified across equities, ETFs, gold and crypto on multiple intervals.

Models that cannot be faithfully translated (feed-dependent, or online training loops with
no Pine equivalent) are **not approximated**; they're listed with the reason.

## Documentation

| File | Contents |
|---|---|
| [EASY_SETUP_GUIDE.md](EASY_SETUP_GUIDE.md) | Non-technical install, start to finish |
| [STRATEGY_CATALOG.md](STRATEGY_CATALOG.md) | All 311 models, citations, data requirements |
| [PRD.md](PRD.md) | Requirements and honest status |
| [CONTEXT.md](CONTEXT.md) | Architecture — read before changing `core/quant/` |
| [walkthrough.md](walkthrough.md) | What was rebuilt and why |

---

## Credits

This project builds on **[atilaahmettaner/tradingview-mcp](https://github.com/atilaahmettaner/tradingview-mcp)**
by Ahmet Taner Atila, which provides the MCP server, TradingView screener and scanner
services, exchange symbol lists, and the news/sentiment integrations. Licensed MIT; the
original copyright is preserved in [LICENSE](LICENSE).

The `core/quant/` engine — strategy library, consensus, confidence, sizing, backtester,
Pine export and their verification — is added on top.

Category coverage for macro, rates, commodity carry and options income follows the family
layout of **[alphakit](https://github.com/ankitjha67/alphakit)**.

## Licence

MIT — see [LICENSE](LICENSE). Original work © 2025 Ahmet Taner Atila.

---

**Not investment advice.** Model output is research output. The backtester routinely shows
most models failing to beat buy-and-hold, and the calibration check sometimes reports that
a high score has been worth nothing on a given instrument. Those results are displayed, not
hidden. Never risk money you cannot afford to lose.
