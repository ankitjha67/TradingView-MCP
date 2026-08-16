# Architecture & Developer Context

**Project:** Quant Desk (TradingView MCP)
**Last updated:** 16 August 2026

Read this before changing anything in `core/quant/`.

---

## 1. Layout

```
TradingViewAntigravity/
├── start.py                  # Launcher: deps → engine check → IDE detect → dashboard
├── dashboard.py              # Streamlit UI (5 tabs)
├── tools/
│   └── generate_catalog.py   # Regenerates STRATEGY_CATALOG.md from the registry
├── PRD.md                    # Requirements + honest status
├── CONTEXT.md                # This file
├── STRATEGY_CATALOG.md       # GENERATED — do not hand-edit
├── EASY_SETUP_GUIDE.md       # Non-technical install guide
└── src/tradingview_mcp/core/
    ├── quant/                # ← the engine
    │   ├── features.py       # Shared causal indicator engine
    │   ├── base.py           # BaseStrategy, Signal, DataNeed, Regime
    │   ├── registry.py       # Auto-discovery, dedupe, metadata queries
    │   ├── market_data.py    # Multi-provider fetch, symbol/interval mapping
    │   ├── consensus.py      # Weighted aggregation + risk levels
    │   ├── confidence.py     # 8-component trade score, vetoes, empirical calibration
    │   ├── sizing.py         # Capital 1k–1M, confidence-scaled position sizing
    │   ├── backtest.py       # Vectorised simulation + walk-forward
    │   ├── performance.py    # TradingView-style Strategy Tester report
    │   ├── monitor.py        # Bar-close-aligned live loop, CDP chart detection
    │   ├── llm.py            # Provider-agnostic LLM layer (stdlib only)
    │   └── library/          # 311 models in 16 modules, one per category
    └── services/             # Pre-existing MCP services (news, options, screener…)
```

## 2. The one contract

Every model implements exactly one method:

```python
def score(self, f: FeatureSet) -> pd.Series:   # continuous, -1.0 … +1.0
```

Vectorised over the **whole frame**, not bar-by-bar. Positive = long conviction,
negative = short, magnitude = strength (not position size — sizing is the risk layer's job).

One call yields both:
- the **live signal** (last element), and
- the **complete historical signal path** the backtester needs.

That single decision is why 311 models scan in ~1s and backtest in ~2.5s. The previous
design called `evaluate(df) -> str` inside a per-bar loop with a growing DataFrame slice:
O(n²) per model, minutes per comparison.

### Adding a model

Drop a class into any module under `core/quant/library/`. The registry finds it. Required:

```python
class MyModel(BaseStrategy):
    name = "Unique Display Name"          # must be unique — duplicates are reported
    category = "Trend & Momentum"
    family = "tsmom"                      # models sharing a family split one vote
    research = "Author (Year), 'Title', Journal Vol(Issue)"
    description = "One sentence on the mechanism."
    needs = (DataNeed.OHLC,)              # gates availability
    min_bars = 60
    regimes = (Regime.TRENDING,)          # drives regime-fit weighting
    horizon = Horizon.SWING
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        return squash(zscore(f.close, self.params["window"]), 1.5)

    def diagnostics(self, f: FeatureSet) -> dict:   # optional, adds depth
        return {"zscore": float(zscore(f.close, 20).iloc[-1])}

    def explain(self, f, value, diag) -> str:       # optional, adds narrative
        return f"Z-score {diag['zscore']:+.2f} → conviction {abs(value):.2f}."
```

**`family` is not decoration.** It is the diversification unit. Give a genuinely new idea a
new family; give a variation the existing one. Getting this wrong is how a library ends up
with 200 "strategies" that are one strategy repeated.

## 3. Invariants — do not break these

### 3.1 Causality
Every series must use only information available at or before its own bar. `donchian()`
applies `.shift(1)` for exactly this reason. Backtest positions are `target.shift(1)`.
A backtest that enters on the signalling bar's close is reading the future.

### 3.2 Honest availability
`DataNeed` gates execution. A model needing `OPTIONS_CHAIN` without one returns
`available=False` and contributes nothing. **Never** substitute a price indicator and let it
vote. If an approximation is genuinely useful, set `is_proxy = True` and write
`proxy_note` saying exactly what was substituted — it is then weighted at 40%.

### 3.3 Single import path
Import as `tradingview_mcp.*`, never `src.tradingview_mcp.*`. Python treats those as two
packages and loads the whole tree twice; `BaseStrategy` from one fails `issubclass` against
the other and the registry silently holds two incompatible copies of every model. This was
a live bug. `registry.py` raises on import if it is reached via the `src.` prefix.

### 3.4 Explicit UTF-8
Every `open()`/`write_text()` passes `encoding="utf-8"`, and console entry points call
`ensure_utf8_console()`. Windows defaults to a legacy code page. This is what turned the
original `walkthrough.md` into UTF-16 mojibake, and it will crash any report containing
`₹`, `→` or `■`.

### 3.5 No fabricated data
`synthetic_ohlcv()` exists for offline demos and is labelled synthetic. It is never a
fallback for a failed fetch — `fetch_ohlcv` raises instead. Showing invented numbers beside
real ones is worse than showing an error.

## 4. Data flow

```
TradingView tab (Chrome DevTools :9222)
        │  symbol + interval only — no data API, no account access
        ▼
parse_symbol() ──► SymbolSpec {yahoo, binance, stooq, asset_class}
        │
        ▼
fetch_ohlcv()  ──► Binance → Yahoo → Stooq (first success wins; stale cache on total failure)
        │
        ▼
build_features() ─► FeatureSet   ← computed ONCE, shared by all 311 models
        │
        ├──► strategy.score(f) × 311  (vectorised, cached indicators)
        │
        ├──► compute_consensus()  ─► family/category/regime/proxy weighting
        ├──► compute_risk_levels() ─► ATR-scaled entry/stop/target
        └──► compare_strategies()  ─► vectorised backtest + walk-forward
```

`FeatureSet` memoises per-indicator: `f.rsi(14)` called by forty models computes once.

## 5. Consensus weighting

```
weight = (1 / family_size) × regime_fit × proxy_discount
       → then normalised so every category contributes equally
```

Naive vote counting treats 30 moving-average variants as 30 independent opinions. Under
that scheme whichever style is most numerous wins every vote and *adding models makes the
bias worse*. Family weighting is the fix.

## 5a. Confidence engine (`confidence.py`)

Eight components, weights in `COMPONENT_WEIGHTS`, combined into 0–100:

```
family diversity 20% | conviction 18% | agreement 18% | concordance 14%
regime alignment 12% | stability 8%   | data quality 6% | reward geometry 4%
```

**Family diversity carries the most weight on purpose.** It counts distinct *families* on
the winning side, saturating at ~12 (`1 - exp(-n/5)`), plus the share of ideas rather than
of models. This is the component the naive vote count cannot express.

**Concordance** rewards agreement between structurally opposed categories
(`OPPOSED_PAIRS` — trend vs mean-reversion, etc.). Two trend models agreeing is expected;
trend and mean-reversion agreeing is information.

**Stability** needs `consensus_series(f, strategies)` — the weighted consensus recomputed
for every historical bar using the same live weights. Costs ~1 s. Skipped with
`--fast` / the dashboard toggle, in which case it scores neutral (0.5), never assumed good.

**Vetoes cap the score at 35 and force `size_multiplier = 0`.** Cautions each halve the
multiplier, floored at 0.15. If you add a component, add its weight to `COMPONENT_WEIGHTS`
and keep the total at 1.0 — the score is a weighted sum, not a normalised average.

**Calibration** (`calibrate`) buckets historical bars into **quintiles** of |score| and
measures realised forward returns. Quantiles, not fixed edges: family/category
normalisation compresses the score into a narrow band whose width varies by instrument, so
fixed cut-points leave the top buckets empty. The verdict requires *both* a positive
strength/return correlation *and* the top quintile beating the bottom on hit rate and
return — one 5-point correlation alone is too noisy to trust.

## 5b. Sizing engine (`sizing.py`)

```
quantity = (capital × risk% × confidence_multiplier) ÷ (entry − stop) × fx
```

Sizing from the **stop distance** is what holds risk constant across instruments. Then
constrained in order: granularity → exposure cap → capital/margin. Each constraint that
binds appends a warning naming itself, so a position smaller than requested always says why.

`resolve_instrument()` owns the granularity table (crypto 1e-6, equities whole shares,
NIFTY 75 / BANKNIFTY 15, forex 1,000-unit micro lots). Add instruments there, not in
`build_position`.

**Refuse, never fall back.** When a trade cannot be sized within the risk budget,
`build_position` returns `tradeable=False` with the exact remedy computed (`capital_needed`,
`risk_pct_needed`). A minimum-size fallback would silently exceed the user's stated risk
limit, which is the failure mode the whole module exists to prevent.

## 6. Monitoring cadence

Two separate clocks:
- **Watch clock** (2 s) — detects symbol/interval changes only. Not an analysis cycle.
- **Bar-close clock** — triggers analysis at the close of the current bar on the chart's
  interval.

A chart change re-runs immediately. `--every N` forces a fixed cadence.

## 7. What changed in v2, and why

| Was | Problem | Now |
|---|---|---|
| 200 classes, 30 real | 170 were template clones with 2 distinct behaviours; consensus counted 85 identical clones as 85 opinions | 311 models, 186 families, family-weighted voting |
| `evaluate(df) -> str` in a per-bar loop | O(n²); full comparison took minutes and ran on a 60 s timer | Vectorised `score(f) -> Series`; ~1 s scan, ~2.5 s full backtest |
| `StrategyFactory` missing 3 methods | `app.py` crashed on line 120 every run | `StrategyRegistry` with full query API |
| `src.tradingview_mcp` vs `tradingview_mcp` | Whole package tree loaded twice | Single canonical path, enforced at import |
| `_VALID_INTERVALS = {"1d","1h"}`; all intraday → `1h` | A 1-minute chart was analysed on hourly bars | 11 first-class intervals, bar-close alignment |
| Two conflicting position sizers | Divergent APIs, unclear which was authoritative | One ATR-based risk layer in `consensus.py` |
| `litellm` imported but never installed | Entire LLM path raised ImportError | Stdlib-only layer, 14 providers |
| Random-number "equity curve" in the UI | Fabricated data displayed beside real metrics | Real equity curves from the backtester |
| `walkthrough.md` as UTF-16 | Mojibake | Explicit UTF-8 everywhere |
| Backtest entered on the signal bar | Look-ahead — results meaningless | `position = target.shift(1)` |
| No transaction costs | Flattering, unrealistic results | Commission + slippage on both legs |

## 8. Testing

```bash
python -c "import sys; sys.path.insert(0,'src'); \
  from tradingview_mcp.core.quant.registry import get_registry; \
  r=get_registry(); print(r.summary())"          # expect 0 load_errors, 0 conflicts

python tools/generate_catalog.py                 # regenerate the catalog
python start.py --setup-only --no-ide            # verify env + engine
```

When adding models, confirm: no duplicate names, no load errors, scan time still ~1 s, and
`analyze()` returns `available=False` (not an exception) on short or feed-less data.

## 9. Dependencies

Required: `pandas`, `numpy`, `scipy`, `streamlit`.
Optional: `websockets` (live chart detection only).
The LLM layer deliberately has **none** — `urllib` only.

## 10. Related work

**[alphakit](https://github.com/ankitjha67/alphakit)** covers the same territory as an
installable multi-engine package. The `Macro & Allocation`, `Rates & Credit`,
`Commodity & Carry` and `Options Income` categories here follow its family layout. If you
want strategies as independently versioned packages with per-strategy benchmark files,
that is the better structure; this repo optimises for a single fast in-process scan.


## 11. Pine Script export and its verification

`core/quant/pine.py` (+ `pine_ext.py`, `pine_ext2.py`) emit Pine v6 for all **174**
price-only models. `tools/emit_pine.py` writes one script per signalling model plus
a family-weighted consensus; `tools/verify_pine.py` proves they match.

**The rule.** A translation is registered only when the Pine computes the same
quantity as the Python. Nothing is approximated silently — 119 feed-dependent and
9 ML models are reported as untranslatable with the reason.

**Verification is independent by construction.** `tools/pine_sim.py` re-implements
Pine semantics from the Pine docs, and `tools/pine_checks*.py` re-implement each
body on top of it. Neither may call the model it is checking; if both sides were
derived from the same code a shared mistake would verify as a match.

### Pine/pandas traps this caught — check these first when adding a translation

| Trap | Symptom | Correct form |
|---|---|---|
| `ta.sma(pow(src - m, 3), n)` | skew ~4× too large | expand the moment: `E[x³] − 3m·E[x²] + 2m³` |
| pandas `.skew()/.kurt()` are bias-corrected | small constant factor off | apply the Fisher-Pearson correction |
| `ta.percentrank` excludes the current value | band-membership tests flip on ~50% of bars | `prank()` adds it to count and denominator |
| pandas rolling **skips** NaN; Pine propagates `na` | sparse series (masked returns) diverge | `zscoreSkipNa()` |
| pandas `.expanding()` | drifts as history grows | `expStdev()` / `expVariance()` |
| `.quantile()` interpolates linearly | tail estimates drift | `ta.percentile_linear_interpolation` |
| Nested `f() =>` inside another function | **does not compile** | `_hoist_functions()` lifts declarations |
| Engine looks ahead (`shift(-1)`) | correlation near zero or negative | lag the other operand, or declare a deviation |

### Verification status

All 174 have an independent check. Runs clean across equities, ETFs, gold and
crypto on 1d and 4h. Three cannot be verified because Pine cannot express the
construct — listed in `KNOWN_DEVIATIONS` with the reason, and documented in the
emitted script rather than hidden.

`DECLARED_WARMUP` records models whose internal lookbacks exceed their declared
params; that number is real information, not a fudge.

```bash
python tools/verify_pine.py --symbol SPY --interval 1d --bars 2500 --verbose
```


## 12. Performance analytics (`performance.py`)

`backtest.py` returns headline numbers; `performance.analyse()` returns the full
Strategy Tester view — **All / Long / Short** columns, MAE/MFE per trade, drawdown *and*
run-up with durations, streaks, a monthly grid, and the risk-ratio block.

```bash
python tools/strategy_report.py --symbol AAPL --interval 1d --top
python tools/strategy_report.py --strategy "Turtle Trading System 1" --long-only
```

**Why the side split is the headline.** A strategy profitable overall but losing on every
short is two strategies wearing one name, and the blended row hides it. Donchian on AAPL:
+34% net looks mediocre until the split shows **long +142% (PF 2.39) against short −108%
(PF 0.37)**. Running it long-only takes Sharpe 0.22 → 0.94 and drawdown −51.7% → −24.6%.
The report emits that as a caveat automatically.

**Caveats are part of the result**, not a footnote — thin trade counts, short samples,
near-zero drawdown denominators, and single-trade-dominated profit all self-report.

**Ratio definitions matter.** Several of these have competing formulations:

| Ratio | Form used |
|---|---|
| Omega | Σ gains ÷ Σ losses at a zero threshold (Keating & Shadwick 2002) |
| Ulcer Index | RMS drawdown — penalises depth *and* duration (Martin & McCann 1989) |
| Martin (UPI) | CAGR ÷ Ulcer Index |
| K-ratio | slope t-stat ÷ √n (Kestner). Multiplying by √n instead yields values in the thousands — a bug caught in review |
| Recovery factor | net profit ÷ max drawdown |
| Tail ratio | \|95th pct\| ÷ \|5th pct\| of bar returns |
| MAE / MFE | worst / best unrealised excursion while the position was open |
