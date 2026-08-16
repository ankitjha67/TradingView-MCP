# Setup Guide

**For everyone — no coding experience needed.**

You will type a few commands. You do not need to understand them. Follow the steps in
order and you will have a working dashboard in about ten minutes.

---

## Before you start

| | |
|---|---|
| **Time** | ~10 minutes |
| **Cost** | Free — no paid subscriptions, no API keys required |
| **TradingView plan** | Any, including **Free** |
| **Works on** | Windows, macOS, Linux |
| **Internet** | Needed to download prices |

---

## Step 1 — Install Python

Python is the language this runs on. Check whether you already have it.

**Open a terminal:**
- **Windows** — press `Win`, type `powershell`, press Enter.
- **Mac** — press `Cmd+Space`, type `terminal`, press Enter.
- **Linux** — press `Ctrl+Alt+T`.

Type this and press Enter:

```bash
python --version
```

**If you see `Python 3.10` or higher** (e.g. `Python 3.13.1`) → skip to Step 2.

**If you see an error, or a number below 3.10:**

1. Go to **https://www.python.org/downloads/**
2. Click the big yellow **Download Python** button.
3. Run the downloaded file.
4. **⚠ On Windows: tick the box "Add Python to PATH" on the first screen.** It is easy to
   miss and nothing works without it.
5. Click **Install Now** and wait.
6. **Close the terminal and open a new one**, then check again:

```bash
python --version
```

> **Mac note:** if `python` is not found, try `python3 --version`. If that works, use
> `python3` everywhere below instead of `python`.

---

## Step 2 — Download this project

**If you have the folder already** (e.g. `E:\Python\TradingViewAntigravity`), skip ahead.

Otherwise, in your terminal:

```bash
git clone https://github.com/ankitjha67/TradingViewAntigravity.git
```

No `git`? Download the ZIP from the project page, then right-click → **Extract All**.

---

## Step 3 — Go to the folder

Type `cd `, then a space, then drag the project folder into the terminal window and press
Enter. That fills in the path for you.

It looks like this:

```bash
cd E:\Python\TradingViewAntigravity
```

Check you are in the right place:

```bash
dir        # Windows
ls         # Mac / Linux
```

You should see `start.py` in the list. If not, you are in the wrong folder.

---

## Step 4 — Start it

One command does everything — installs what is missing, checks the engine, and opens the
dashboard:

```bash
python start.py
```

**What you will see:**

```
  Quant Desk — setup
  E:\Python\TradingViewAntigravity
 ✓ Python 3.13.13

Dependencies
 ✓ All required packages present.

Strategy engine
 ✓ 311 models across 16 categories (186 independent families)

Editor integration
 ✓ Found: VS Code
   Configure these editors? [Y/n]:
```

- **First run takes 2–5 minutes** while it downloads packages. That is normal.
- At the editor prompt, press **Enter** for yes, or type `n` and Enter for no. Either is
  fine — the dashboard does not need an editor.

Your browser then opens at **http://localhost:8501**.

**Done.** Everything below is optional.

---

## Step 5 — Use it

Type a symbol in the left sidebar and pick an interval.

| You want | Type this |
|---|---|
| Bitcoin | `BINANCE:BTCUSDT` |
| Ethereum | `BINANCE:ETHUSDT` |
| Apple | `AAPL` |
| Tesla | `TSLA` |
| Reliance (India) | `NSE:RELIANCE` |
| Nifty 50 | `NIFTY` |
| Bank Nifty | `BANKNIFTY` |
| S&P 500 | `SPX` |
| Euro / Dollar | `EURUSD` |
| Gold | `GC=F` |

### The five tabs

| Tab | What it does |
|---|---|
| **Live Signal** | The main view. All 311 models run and the result is one LONG / SHORT / NO POSITION verdict with entry, stop and target. |
| **Strategy Explorer** | Browse every model, read what it does and which paper it comes from, run any single one. |
| **Backtest Lab** | Test all models on past data. Includes a walk-forward check that tells you whether a result is real or overfitted. |
| **Monitor** | Run one analysis cycle and download the report. |
| **Settings** | Optional AI commentary setup. |

### Reading the verdict

- **Score** −1 to +1. Negative = short, positive = long, near zero = no view.
- **Confidence** how much weight to put on it. Below ~40% means the models disagree.
- **Agreement** the share of models on the winning side. Below 60% means genuinely split.
- **"126 voting of 192 available of 311 in library"** — this is deliberate. Models that
  need data you have not connected (options chains, company fundamentals, blockchain data)
  **do not vote** rather than guessing. You are always told how many actually ran.

---

## Step 6 — Follow your TradingView chart automatically

The app watches the chart you have open and follows whatever symbol and interval you switch
to, re-analysing at every bar close on that interval.

### If you use the TradingView desktop app

**It already works — nothing to set up.** The desktop app exposes the debug port by default.
Just open a chart, then flip **Follow my TradingView chart** in the dashboard sidebar (or
run the monitor with no `--symbol`).

### If you use TradingView in a web browser

**Close Chrome completely first**, then start it with debugging enabled:

**Windows (PowerShell):**
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222
```

**Mac:**
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

**Linux:**
```bash
google-chrome --remote-debugging-port=9222
```

Open TradingView in that Chrome window, then flip **Follow my TradingView chart** in the
dashboard sidebar.

### What "following" actually does

| Your chart | The app re-analyses |
|---|---|
| 1-minute | every minute, at bar close |
| 5-minute | every 5 minutes, at bar close |
| 15-minute | every 15 minutes, at bar close |
| 1-hour | every hour, at bar close |
| Daily | once a day |

Switching symbol or interval on the chart re-analyses **immediately** rather than waiting.

It analyses at *bar close* rather than continuously because every model reads the last
**closed** bar. Re-reading a candle that is still forming makes the signal flicker and then
settle — one stable reading per bar is what you actually want to act on.

> **What this does and does not do.** It reads only the symbol name and the timeframe from
> the page you already have open. It does not read your account, your positions, your
> watchlists, or anything else — and it does not use TradingView's data. Prices come from
> free public sources, which is why the Free plan is enough.

If you would rather not do this, just type symbols manually. Everything works the same.

---

## Step 7 (optional) — Continuous background monitoring

To have it re-analyse automatically, open a **second** terminal, go to the project folder,
and run:

```bash
python -m tradingview_mcp.core.quant.monitor --symbol "BINANCE:BTCUSDT" --interval 15m
```

Or, to follow whatever chart you have open:

```bash
python -m tradingview_mcp.core.quant.monitor
```

**How often does it refresh?** It follows your chart's interval and updates **when each bar
closes** — every minute on a 1-minute chart, every 15 minutes on a 15-minute chart, once a
day on a daily chart. Switching symbol or interval updates immediately.

It writes `tv_active_chart.md` (readable report) and `tv_active_chart.json` (raw data) into
the folder, refreshed each cycle. Press `Ctrl+C` to stop.

---

## Step 8 (optional) — AI commentary

The dashboard writes a plain-English reading of the numbers if you connect an AI model.
**Everything works without this** — signals, backtests and risk levels never depend on it.

### Free options

**Run it on your own computer (no key, no cost):**
1. Install Ollama from **https://ollama.com**
2. In a terminal: `ollama pull llama3.2`
3. In the dashboard → **Settings** → Provider: **Ollama (local)** → **Save** → **Test
   connection**

**Or use a free cloud tier:**
- **Google Gemini** — free key at https://aistudio.google.com/apikey
- **Groq** — free tier at https://console.groq.com
- **NVIDIA NIM** — free credits at https://build.nvidia.com

### Paid options
OpenAI, Anthropic, DeepSeek, Mistral, OpenRouter, xAI — all supported.

### Setting it up
Dashboard → **Settings** → pick your provider → paste the key → **Save settings** →
**Test connection**. A green message means it works.

Your key is saved in your home folder (`~/.tradingview_mcp/llm_config.json`), deliberately
outside the project folder so it can never be accidentally uploaded to GitHub.

---

## Fixing problems

### `python: command not found` / `'python' is not recognized`
Python is not installed, or the PATH box was not ticked. Redo **Step 1**, tick **Add Python
to PATH**, and open a **new** terminal afterwards.
On Mac, try `python3` instead of `python`.

### `pip is not recognized`
```bash
python -m ensurepip --upgrade
```
Then retry `python start.py`.

### Installing packages fails with a permissions error
```bash
python -m pip install --user pandas numpy scipy streamlit
```

### `Could not load market data`
1. Check the spelling. Crypto needs the exchange: `BINANCE:BTCUSDT`, not `BTCUSDT`.
2. Check your internet connection.
3. Try a different interval — 1-minute data is only kept for about 7 days.
4. Try `AAPL` to confirm the connection works at all.

### The browser did not open
Open it yourself and go to **http://localhost:8501**.

### Port 8501 already in use
```bash
python -m streamlit run dashboard.py --server.port 8502
```

### "No TradingView tab found"
Chrome must be started with `--remote-debugging-port=9222` (**Step 6**), and Chrome must be
fully closed before you start it that way. Or skip it and type symbols manually.

### Odd characters like `â–²` in the terminal
Your terminal is using an old text encoding:
```powershell
$env:PYTHONIOENCODING="utf-8"
python start.py
```

### Something else
Run this and include the output when asking for help:
```bash
python start.py --setup-only --no-ide
```

---

## Everyday commands

| Task | Command |
|---|---|
| Open the dashboard | `python start.py` |
| Set up without launching | `python start.py --setup-only` |
| Skip editor configuration | `python start.py --no-ide` |
| Monitor one symbol | `python -m tradingview_mcp.core.quant.monitor --symbol AAPL --interval 1h` |
| Follow the open chart | `python -m tradingview_mcp.core.quant.monitor` |
| One-off report | `python -m tradingview_mcp.core.quant.monitor --symbol AAPL --interval 1d --once` |
| Rebuild the strategy list | `python tools/generate_catalog.py` |

---

## Please read this part

This tool analyses markets. It does not predict them.

- **It is not investment advice.** It is model output for research.
- **Most models fail most of the time.** The Backtest Lab will show you this directly —
  typically only a handful of the 311 beat simply buying and holding. That is the honest
  result, and it is displayed rather than hidden.
- **A backtest is not a forecast.** Always run the walk-forward check. If it says
  *"inconsistent — likely overfit"*, believe it.
- **Never risk money you cannot afford to lose.**
- **Nobody here can see your data.** Everything runs on your machine. The only outbound
  requests are for public price data and, if you enable it, your chosen AI provider.

---

## Where to look next

| File | Contents |
|---|---|
| `STRATEGY_CATALOG.md` | All 311 models with citations and data requirements |
| `PRD.md` | What is built, what is not, and what is coming |
| `CONTEXT.md` | Architecture — read before changing code |
