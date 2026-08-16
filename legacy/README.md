# Legacy files

Moved here rather than deleted, so nothing is lost. Nothing in this folder is imported by
the running system. Delete the folder whenever you are satisfied with the replacement.

| File | Why it was retired | Replaced by |
|---|---|---|
| `app.py` | Crashed on every run — called `factory.list_strategies()`, `get_categories()` and `get_strategies_by_category()`, none of which existed on `StrategyFactory`. Also drew a random-number "equity curve" beside real metrics. | `dashboard.py` |
| `streamlit_app.py` | Second, divergent dashboard reading the daemon's JSON file. | `dashboard.py` |
| `live_monitor.py` | Ran the library against `generate_synthetic_data()` — a random walk — and printed the result as a market verdict. | `core/quant/monitor.py` |
| `llm_analyzer.py` | Imported `litellm`, which was never in the dependencies, so the whole LLM path raised `ImportError` on first call. | `core/quant/llm.py` (14 providers, zero dependencies) |
| `run.py` | Launcher that hard-required `uv` and started the two files above. | `start.py` |
| `tv_monitor_daemon.py` | Polled every 60 s regardless of chart interval, then mapped every intraday interval to `1h` — a 1-minute chart was analysed on hourly bars. Called an O(n²) comparison on that timer. | `core/quant/monitor.py` (bar-close aligned) |
| `generate_all_strategies.py` | Generated the 170 clone strategies below. Running it would recreate them. | `core/quant/library/` — hand-written, cited models |
| `clone_strategies/` | 170 classes generated from one template. Every one ran identical code; only two distinct behaviours existed across all of them, selected by whether the class index was odd or even. Consensus counted them as 170 independent opinions. | `core/quant/library/` — 311 models across 186 genuinely independent families |

## The clone problem, concretely

Every one of the 170 generated classes contained exactly this body, differing only in the
index substituted into a threshold that was then never used:

```python
def evaluate(self, df):
    c = df['close']
    sma_short  = c.rolling(10).mean().iloc[-1]
    sma_long   = c.rolling(50).mean().iloc[-1]
    volatility = c.pct_change().rolling(20).std().iloc[-1]
    z_score    = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
    threshold  = 1.5 + ((51 % 5) * 0.2)      # computed, never referenced below

    if sma_short > sma_long and z_score > 0:   # odd index
        return "BUY"
    ...
```

Named `Momentum & Trend Following Model 51`, `Factor & Smart Beta Model 101`, and so on —
no research provenance and no distinct mathematics. A "consensus of 200 institutional
models" over this set was one moving-average rule counted ~85 times against a second rule
counted ~85 times.
