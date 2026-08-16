# Product Requirements Document

**Product:** Quant Desk — a systematic multi-strategy analysis engine for TradingView users
**Version:** 2.0.0
**Status:** Core engine complete and verified; feed integrations outstanding (§9)
**Last updated:** 16 August 2026

---

## 1. What this is

A local, self-hosted engine that reads whatever chart you have open in TradingView, fetches
that instrument's price history from free public sources, evaluates **311 published
quantitative models** against it, and produces one auditable consensus view with
volatility-scaled risk levels.

It runs entirely on your machine. It needs no TradingView subscription, no market-data
vendor, and no paid API. An LLM can be attached for narrative commentary, but every signal,
backtest and risk level is computed without one.

## 2. What this is not

Stating this plainly, because the category is full of products that blur it:

- **Not a signal service or a trading bot.** It does not place orders and has no broker
  integration. It produces analysis; you decide what to do with it.
- **Not investment advice.** Model output is research output.
- **Not a claim of edge.** The backtester routinely shows that most models fail to beat
  buy-and-hold on any given instrument. That result is reported, not hidden.
- **Not a TradingView data client.** It reads only the symbol and interval you are looking
  at. Price data comes from separate free sources.

## 3. Users

| User | Needs | Entry point |
|---|---|---|
| Non-technical retail trader | Install and run without touching a terminal | `python start.py` → dashboard |
| Discretionary trader | A second opinion on the chart they are watching | Live Signal tab / monitor daemon |
| Quant-curious developer | A strategy library and backtester to extend | `core/quant/` package |
| IDE user (any assistant) | Query the engine conversationally | MCP server, auto-configured |

## 4. Functional requirements

### 4.1 Strategy library — **met**

| Requirement | Status |
|---|---|
| 200+ distinct published models | **311** across 16 categories |
| Every model carries a verifiable citation | Yes — author, year, journal in `research` |
| Models are genuinely distinct, not parameter clones | **186 independent families** tracked and enforced |
| Full library evaluates in under 2 seconds | **~1.0–2.4s** for all 311 |
| Adding a model requires no wiring | Yes — drop a class in `core/quant/library/`, auto-discovered |

**Design requirement that drives everything else:** a model that cannot run honestly on the
available data must report as unavailable rather than degrade to a price proxy and vote
anyway. 119 of 311 models require an external feed; on plain OHLCV roughly 190 are available
and the rest stand down. The UI always shows "N voting of M available of 311 in library".

### 4.2 Data — **met**

- Intervals: `1m 2m 5m 15m 30m 1h 2h 4h 1d 1wk 1mo` — all first-class.
- Sources tried in order: Binance (crypto) → Yahoo Finance → Stooq. First success wins.
- Asset classes: crypto, US equities, international equities (18 exchange suffixes),
  indices, forex.
- Works on **any TradingView plan including Free**, because no TradingView data API is called.
- Verified live: BTCUSDT @ 1m and 15m via Binance; AAPL and NSE:RELIANCE @ 1d via Yahoo.

### 4.3 Consensus — **met**

Weighted aggregation, not a vote count:

1. **Family weighting** — models sharing a family split one family's vote.
2. **Category normalisation** — each category contributes equally regardless of size.
3. **Regime fit** — models suited to current conditions weigh more.
4. **Proxy discount** — proxy implementations weigh 40%.

Outputs direction, score (−1…+1), confidence, agreement %, per-category breakdown, the
strongest models on each side with their reasoning, and an explicit list of why models did
not run.

### 4.4 Confidence engine — **met**

Every prospective trade is scored 0–100 from all 311 model inputs, across eight weighted
components:

| Component | Weight | Question |
|---|---:|---|
| Family diversity | 20% | How many *independent ideas* agree — not how many models |
| Conviction | 18% | How strong is the weighted signal |
| Agreement | 18% | How one-sided is the weighted vote |
| Concordance | 14% | Do structurally opposed categories agree (trend vs mean-reversion) |
| Regime alignment | 12% | Are the agreeing models suited to current conditions |
| Signal stability | 8% | Persistent across recent bars, or flipped on this one |
| Data quality | 6% | Model coverage, bar depth, proxy share of the vote |
| Reward geometry | 4% | Is the risk/reward worth taking |

Family diversity carries the most weight because model count is not evidence — 50 models
from 3 families is one idea restated, and the naive vote count cannot see the difference.

**Hard vetoes** override any score: neutral consensus, agreement below 55%, fewer than 4
independent families agreeing, fewer than 15 models voting, under 120 bars, or R:R below
1.2. A veto caps the score at 35 and forces a zero size multiplier. **Cautions** (extreme
volatility, deep drawdown, proxy-heavy vote, near-random-walk Hurst) each halve position
size without blocking.

Output: grade (A+…F), verdict (TRADE / REDUCED / STAND ASIDE), and a **size multiplier**
(0…1) consumed directly by the sizing engine.

**Empirical calibration.** `calibrate()` reconstructs the historical consensus path,
buckets every past bar into quintiles by signal strength, and measures the realised forward
return and hit rate in each. Verified output: AAPL daily — strongest quintile hit 56.7% vs
50.7% weakest (+6.0 points, "tracked"). BTCUSDT hourly — strongest 38.9% vs 46.0% weakest
("has NOT reliably tracked; treat the score as evidence quality, not expected return").
Reporting the negative result is the point.

### 4.5 Capital and position sizing — **met**

Capital range **1,000 to 1,000,000** in the account currency. The previous sizer
hard-clamped every account to 1,000–5,000 INR, discarding anything above ₹5,000.

Sizing is risk-first:

```
risk budget   = capital × risk%
scaled budget = risk budget × confidence multiplier
raw quantity  = scaled budget ÷ (entry − stop)
```

Sizing from the **stop distance** rather than from capital is what holds risk constant
across instruments — verified: AAPL sizes to 0.96–0.98% actual risk at every tier from
5,000 to 1,000,000.

Then constrained in order by: instrument granularity (crypto fractional to 6dp, whole
shares, NIFTY 75 / BANKNIFTY 15 lots, forex 1,000-unit micro lots), exposure cap
(default 25% of capital), and available capital or margin. Cross-currency positions are
converted to the account currency.

When a trade cannot be taken, the engine **refuses with the exact remedy** rather than
falling back to a minimum position: *"One minimum position (15 contracts) risks INR 11,700
= 11.70% of INR 100,000, above the 1.00% budget. Tradeable at capital of INR 1,170,000 or
risk of 11.70% per trade."*

A `capital_ladder()` sizes the same trade across the full 1,000 → 1,000,000 range so the
threshold at which an instrument becomes tradeable is explicit.

### 4.6 Backtesting — **met**

- Vectorised: all 311 models over 1,000 bars in **~2.5 s**.
- **Signals act on the next bar**, never the signalling bar.
- Commission and slippage charged on both legs, configurable.
- Metrics: return, annualised return, Sharpe, Sortino, Calmar, max drawdown, win rate,
  profit factor, expectancy, exposure, and excess return over buy-and-hold.
- **Walk-forward validation** across sequential folds, with an explicit overfitting verdict.
- Ranked by Sharpe by default — total return rewards whichever model took the most risk.

### 4.7 Monitoring cadence — **met**

Re-analysis is aligned to the **close of the bar on the interval your chart is set to**:
1m chart → every minute; 15m → every 15 minutes; 1d → daily. The browser is polled every
2 seconds, but only to notice a symbol or interval change, which triggers an immediate
re-run. A fixed cadence can be forced with `--every N`.

Rationale: models read the last *closed* bar. Re-running mid-bar re-reads a forming candle,
so the signal flickers and then settles at close. One stable reading per bar is both
correct and what a trader watching the same chart would act on.

### 4.8 LLM integration — **met**

- Save one API key; the whole pipeline runs. No IDE required.
- Providers: OpenAI, Anthropic, Gemini, NVIDIA NIM, Groq, OpenRouter, DeepSeek, Mistral,
  Together, xAI, Ollama, LM Studio, vLLM, any OpenAI-compatible endpoint.
- Zero dependencies — standard-library HTTP only.
- Keys stored in `~/.tradingview_mcp/llm_config.json`, outside the repo, mode `0600`.
- The LLM reads engine output and cannot override it. It is an explanation layer.
- Every failure mode returns actionable text ("key revoked", "wrong model name") rather
  than a stack trace, and the dashboard degrades to numbers-only.

### 4.9 Interfaces — **met**

| Interface | Command | Requires |
|---|---|---|
| Streamlit dashboard | `python start.py` | Nothing but Python |
| Terminal monitor | `python -m tradingview_mcp.core.quant.monitor` | Nothing |
| MCP server | Auto-configured into detected IDEs | An MCP-capable editor |
| Python API | `from tradingview_mcp.core.quant import ...` | — |

### 4.10 Situation-aware setup — **met**

`start.py` checks Python, installs missing dependencies (uv when present, else pip),
verifies the engine loads, detects Antigravity / VS Code / Cursor / Windsurf / Claude
Desktop / Zed and offers to merge MCP config into each without clobbering existing
settings, then launches the dashboard. No IDE found means the dashboard, which needs none.

## 5. Non-functional requirements

| Requirement | Target | Actual |
|---|---|---|
| Full-library scan | < 2 s | 1.0–2.4 s |
| Full-library backtest | < 10 s | ~2.5 s |
| Cold start to dashboard | < 60 s | ~25 s |
| Runtime errors across 311 models | 0 | 0 |
| Duplicate model names | 0 | 0 |
| External paid dependencies | 0 | 0 |

**Encoding:** all file I/O and console output is explicitly UTF-8. Windows consoles default
to a legacy code page, which is what corrupted the original `walkthrough.md` into mojibake
and would crash any report containing an arrow or a currency symbol.

## 6. Correctness properties

These are the properties that separate a real engine from a plausible-looking one:

1. **No look-ahead.** Every indicator is causal. Backtest positions are shifted one bar.
   Rolling channels exclude the current bar.
2. **No silent degradation.** A model without its required data reports unavailable.
3. **No vote stuffing.** Family weighting prevents a crowded style from dominating.
4. **No free lunch in reporting.** Costs are charged; buy-and-hold is always shown alongside.
5. **No fabricated data.** Synthetic series exist for offline demos and are labelled as such.
   They are never a fallback for a failed fetch — that raises.

## 7. Success criteria

- [x] 200+ genuinely distinct, research-cited models
- [x] Full scan under 2 seconds
- [x] Works on TradingView Free
- [x] All intervals from 1m to 1mo
- [x] Any LLM provider via a saved key
- [x] Runs with no IDE
- [x] Auto-configures an IDE when present
- [x] Non-technical install guide
- [x] Zero runtime errors across the library
- [ ] External feeds wired (§9)

## 8. Known limitations

1. **119 of 311 models need a feed that is not connected.** They are implemented and will
   activate when the feed is supplied; today they stand down. This is disclosed everywhere.
2. **22 models are proxies.** Each states what was substituted; each is down-weighted.
3. **Free data has limits.** Yahoo serves 1-minute bars for roughly 7 days; Binance returns
   1,000 bars per request. Long intraday histories are not available without a paid feed.
4. **Backtests are single-instrument, single-window.** Walk-forward is provided precisely
   because a single-window result is weak evidence.
5. **Chart detection needs Chrome with `--remote-debugging-port=9222`.** Without it, type
   the symbol manually — everything else works identically.
6. **No transaction-cost model beyond flat commission plus slippage.** No market impact,
   no borrow cost, no funding.

## 9. Roadmap

**Next — activate the standing-down models.** The repo already ships `news_service`,
`marketaux_service`, `sentiment_service`, `options_service` and `screener_service`. Wiring
each into `FeatureSet.meta` activates a block of models with no new strategy code:

| Work | Models activated |
|---|---|
| Cross-sectional universe from `screener_service` | ~40 |
| Benchmark series (index per asset class) | ~25 |
| Options chain from `options_service` | ~16 |
| News/sentiment from existing services | ~19 |
| On-chain feed | ~18 |
| Fundamentals | ~20 |

**Then:** per-model live performance tracking; regime-conditional weight learning;
alerting; multi-symbol watchlist scanning.

**Not planned:** order execution, broker integration, or anything that turns analysis into
automated trading.

## 10. Related work

The companion library **[alphakit](https://github.com/ankitjha67/alphakit)** organises the
same territory as an installable, multi-engine package with per-strategy `paper.md` and
benchmark files. This project's `Macro & Allocation`, `Rates & Credit`, `Commodity & Carry`
and `Options Income` categories follow its family layout. Both projects independently
adopted the same disclosure convention — explicitly flagging price-derived proxies — which
is the correct default for this class of tool.
