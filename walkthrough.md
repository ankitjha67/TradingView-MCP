# Walkthrough — what changed and why

_Rewritten 16 August 2026. The previous version of this file was saved as UTF-16 without a
declared encoding, so every reader rendered it as mojibake. It is now explicit UTF-8, as is
every other file the project writes._

---

## The finding that shaped this work

The repository contained 200 strategy classes. Only 30 were distinct implementations
(statistical arbitrage, volatility, machine learning — 10 each).

The other **170 were generated from a single template** by `generate_all_strategies.py`.
Every one of them ran identical code, differing only by an index number in a threshold that
was computed and then never used. There were exactly **two** behaviours across all 170,
selected by whether the index was odd or even.

They were named `Momentum & Trend Following Model 51`, `Factor & Smart Beta Model 101`, and
so on — no research provenance, no distinct mathematics.

This mattered because the consensus engine counted BUY votes across all 200. With 85 exact
clones on each branch, the "consensus of 200 institutional models" was one moving-average
rule counted 85 times, plus a second rule counted 85 times. Adding more clones would have
made the number look more impressive and the signal strictly worse.

Everything below follows from fixing that.

---

## What was rebuilt

### Strategy library — 311 models, 186 families

Every model is a published method with a citation naming author, year and journal. Each one
declares:

- **`family`** — the diversification unit. Models sharing a family split one vote, so a
  crowded style cannot win by headcount. 311 models across 186 families is an honest claim
  of roughly 186 independent views.
- **`needs`** — the data required to run truthfully. 119 models need an options chain,
  fundamentals, a peer universe, order-book depth, on-chain or news data. Without that
  feed they report **unavailable** and contribute nothing, rather than silently degrading
  to a price proxy and voting anyway.
- **`is_proxy`** — 22 models approximate their published method using substituted data
  (e.g. estimating order-flow imbalance from bar volume, since tick data is unavailable).
  Each states exactly what was substituted and is weighted at 40% of a full vote.

Categories: Trend & Momentum (32), Factor & Smart Beta (28), Crypto Native (23), Mean
Reversion (23), Options & Derivatives (22), Sentiment & Alt Data (22), Statistical
Arbitrage (22), Volatility (22), Macro & Allocation (21), Microstructure (20), Machine
Learning (19), Regime & Risk (17), Seasonality & Calendar (14), Rates & Credit (10),
Commodity & Carry (9), Options Income (7).

The Macro, Rates, Commodity and Options Income families follow the layout of the companion
[alphakit](https://github.com/ankitjha67/alphakit) library.

### Performance — a different order of magnitude

The old contract was `evaluate(df) -> str`, called inside a per-bar loop over a growing
DataFrame slice. Every indicator was recomputed on every bar, for every strategy: O(n²) per
model. A full comparison took minutes — and the monitor called it on a 60-second timer.

The new contract is `score(f: FeatureSet) -> pd.Series`: one vectorised pass over the whole
frame, producing the live signal and the full historical path together. Indicators are
computed once into a shared `FeatureSet` and reused across all 311 models.

| | Before | Now |
|---|---|---|
| Full library scan | minutes | **~1.0 s** |
| Full library backtest (1,000 bars) | minutes | **~2.5 s** |

### Bugs fixed

| Bug | Consequence |
|---|---|
| `StrategyFactory` was missing `list_strategies`, `get_categories`, `get_strategies_by_category` | `app.py` crashed on line 120 on every single run |
| `backtest_service` imported `src.tradingview_mcp.*` while everything else used `tradingview_mcp.*` | Python loaded the entire package tree twice; `issubclass` failed across the two copies |
| `_VALID_INTERVALS = {"1d", "1h"}`, and every intraday interval mapped to `1h` | A 1-minute chart was analysed on hourly bars |
| Backtest entered at the close of the signalling bar | Look-ahead bias — results were meaningless |
| No transaction costs | Flattering, unachievable returns |
| `litellm` imported but never installed | The entire LLM path raised ImportError on first use |
| `app.py` drew a random-number "equity curve" | Fabricated data displayed beside real metrics |
| Two conflicting position sizers | Divergent APIs; unclear which was authoritative |
| `walkthrough.md` written as UTF-16 | Mojibake — this file |

### Data — works on TradingView Free

No TradingView data API is called. TradingView is used only to observe which symbol and
interval you are looking at, which any logged-in browser session exposes on any plan.

Prices come from free public sources, tried in order: Binance (crypto) → Yahoo Finance →
Stooq. Eleven intervals from 1-minute to monthly are first-class. Verified live on
BTCUSDT (1m, 15m), AAPL (1d) and NSE:RELIANCE (1d).

### Consensus — weighted, not counted

```
weight = (1 / family_size) × regime_fit × proxy_discount
       → normalised so each category contributes equally
```

Reported alongside every verdict: how many models voted, how many were available, how many
exist, the agreement percentage, per-category scores, the strongest models on each side
with their reasoning, and a breakdown of why models did not run.

### Backtesting — with the checks that matter

Signals act on the **next** bar. Commission and slippage are charged on both legs. Ranked
by Sharpe, not total return. Buy-and-hold is always shown for comparison, and walk-forward
validation across sequential folds returns an explicit verdict — *consistent*, *mixed*, or
*inconsistent — likely overfit*.

On a representative run (BTCUSDT, 1h, 1,000 bars): of 165 models with enough trades to
rank, **3 beat buy-and-hold**, and the top-ranked model's walk-forward came back
*"mixed — performance is fold-dependent"*. That is the honest result, and it is displayed
rather than buried.

### Monitoring cadence

Re-analysis is aligned to the **close of the bar on your chart's interval** — every minute
on a 1m chart, every 15 minutes on a 15m chart, daily on a daily chart. The browser is
polled every 2 seconds, but only to detect a symbol or interval change, which triggers an
immediate re-run.

Models read the last *closed* bar. Re-running mid-bar re-reads a forming candle, so the
signal flickers and then settles at close. One stable reading per bar is both correct and
what a trader watching the same chart would act on.

### LLM — any provider, one key, zero dependencies

Fourteen providers across three wire formats: OpenAI-compatible (OpenAI, Groq, OpenRouter,
DeepSeek, Mistral, Together, xAI, NVIDIA NIM, Ollama, LM Studio, vLLM), Anthropic Messages,
and Google Gemini. Standard-library HTTP only — nothing to install.

Keys are stored in `~/.tradingview_mcp/llm_config.json`, deliberately outside the repository
so a key cannot be committed by accident.

The LLM reads engine output and cannot override it. It is an explanation layer, and it is
prompted to state the strongest argument *against* the consensus rather than just narrating
it.

### Interfaces

`python start.py` checks Python, installs missing dependencies, verifies the engine,
detects Antigravity / VS Code / Cursor / Windsurf / Claude Desktop / Zed and offers to merge
MCP configuration into each without clobbering existing settings, then launches the
Streamlit dashboard. No IDE found means the dashboard, which needs none.

---

## What is still outstanding

119 of 311 models need a feed that is not yet connected. They are fully implemented and
activate the moment the feed is supplied. The repository already ships `news_service`,
`marketaux_service`, `sentiment_service`, `options_service` and `screener_service` — wiring
each into `FeatureSet.meta` activates a block of models with no new strategy code:

| Feed | Models activated |
|---|---|
| Cross-sectional universe | ~40 |
| Benchmark series | ~25 |
| Fundamentals | ~20 |
| News / sentiment | ~19 |
| On-chain | ~18 |
| Options chain | ~16 |

Until then, the dashboard states on every screen how many models actually ran.

---

## Verifying any of this yourself

```bash
python start.py --setup-only --no-ide     # engine loads, model count, zero errors
python tools/generate_catalog.py          # regenerate the catalog from live code
```

The catalog is generated from the registry rather than hand-written, so it cannot drift
from what is actually implemented.
