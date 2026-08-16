"""
Pine Script v6 emitter.

Translates a model's signal logic into Pine you can paste into TradingView and
see plotted on the same chart the engine analysed.

**The correctness rule that governs this module.** A translation is only
registered when the Pine computes the *same quantity* as the Python. Emitting
Pine that looks similar but computes something else is worse than emitting
nothing, because the plot would silently disagree with the engine and there
would be no way to tell which was wrong. Models with no faithful translation say
so and are listed as untranslatable, with the reason.

Three classes of model cannot be translated and are not attempted:

* **Needs an external feed** (119 models) — options chains, fundamentals,
  cross-sectional universes, on-chain. Pine cannot reach these.
* **Online training loops** (18 ML models) — recursive least squares, SVM
  sub-gradient descent, direct reinforcement. Pine has no matrix solver and its
  execution model recomputes the whole history each bar.
* **Path-dependent Python loops** with no vectorised Pine equivalent.

Everything emitted here is an ``indicator``, not a ``strategy``. A Pine
``strategy`` implies backtested position management with its own fill
assumptions; the engine's backtest already does that, and having two
disagreeing backtests is a trap.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Optional

from .base import BaseStrategy

PINE_VERSION = 6


@dataclass
class PineTranslation:
    """Pine source for one model, plus how faithful it is."""
    body: str                    # Pine expression producing `score` in -1..+1
    overlay: bool = False        # plot on price (True) or separate pane (False)
    plots: str = ""              # extra plot statements
    note: str = ""               # any deviation from the Python, stated plainly
    exact: bool = True           # False when the translation approximates


# ── translation registry ──────────────────────────────────────────────────────
# Keyed on strategy `name`. Each body must assign `score` in [-1, 1] using the
# same maths as the Python `score()`.

_T: dict[str, PineTranslation] = {}


def _reg(name: str, body: str, *, overlay: bool = False, plots: str = "",
         note: str = "", exact: bool = True) -> None:
    _T[name] = PineTranslation(body.strip("\n"), overlay, plots.strip("\n"), note, exact)


# squash(x, s) == tanh(x/s); Pine has no tanh before v6 math, so define it once.
_HELPERS = """
// squash(): tanh, matching the Python engine's squash(x, scale).
// z is clamped before exp() because Pine has no tanh and exp(2*z) overflows to
// na for |z| > ~350; tanh is saturated to 1.0 well before that anyway.
squash(float x, float s) =>
    z = math.max(-20.0, math.min(20.0, x / s))
    e = math.exp(2.0 * z)
    (e - 1.0) / (e + 1.0)

// zscore(): rolling standardisation, population stdev (ddof=0) as in pandas
zscore(float src, int len) =>
    m = ta.sma(src, len)
    sd = ta.stdev(src, len, false)
    sd > 1e-12 ? (src - m) / sd : 0.0

// band_score(): map [lo, hi] onto [-1, +1], clipped
band_score(float x, float lo, float hi) =>
    math.max(-1.0, math.min(1.0, 2.0 * (x - lo) / (hi - lo) - 1.0))

// prank(): rolling percentile rank in 0..1, matching pandas rank(pct=True).
//
// ta.percentrank counts how many of the PRIOR len values are below the current
// one; pandas ranks the current value WITHIN its own window. That is a fixed
// 1/len offset -- negligible for a continuous score, but decisive for a model
// that tests band membership such as (rank > 0.4 and rank < 0.8), where every
// value sitting one step low flips the band on a large share of bars.
// Adding the current observation to both count and denominator aligns them.
prank(float src, int len) =>
    len > 1 ? (ta.percentrank(src, len - 1) / 100.0 * (len - 1) + 1.0) / len : 1.0

// logret / realised volatility, annualised with the interval's bars-per-year
lr() => ta.change(math.log(close))
rvol(int len) => ta.stdev(lr(), len, false) * math.sqrt(BPY)

// Kaufman efficiency ratio: net move over total path
effRatio(int p) =>
    math.abs(close - close[p]) / math.max(1e-12, math.sum(math.abs(ta.change(close)), p))

// trend_strength: the engine's blend of ADX and efficiency ratio, 0..1
trendStrength() =>
    [_dp, _dm, _adx] = ta.dmi(14, 14)
    math.max(0.0, math.min(1.0, _adx / 50.0)) * 0.5 +
      math.max(0.0, math.min(1.0, effRatio(20))) * 0.5

// vol_regime: percentile of 20-bar realised vol within its trailing year
volRegime(int rankLen) => prank(rvol(20), rankLen)

// drawdown from the running peak
ddFromPeak() =>
    var float pk = na
    pk := na(pk) ? close : math.max(pk, close)
    close / pk - 1.0

// Rolling skewness / excess kurtosis.
//
// The central moments must be expanded rather than written as
// ta.sma(pow(src - m, 3), len): that form subtracts each bar's OWN rolling mean
// inside the average, not the window's mean, and overstates skew several-fold.
// Expanding E[(x-m)^3] = E[x^3] - 3m*E[x^2] + 2m^3 uses a single window mean,
// which is what pandas computes.
//
// pandas .skew()/.kurt() also apply Fisher-Pearson bias correction, reproduced here.
rollSkew(float src, int len) =>
    m  = ta.sma(src, len)
    m2 = ta.sma(math.pow(src, 2), len) - math.pow(m, 2)
    m3 = ta.sma(math.pow(src, 3), len) - 3.0 * m * ta.sma(math.pow(src, 2), len) + 2.0 * math.pow(m, 3)
    g1 = m2 > 1e-18 ? m3 / math.pow(m2, 1.5) : 0.0
    len > 2 ? g1 * math.sqrt(len * (len - 1.0)) / (len - 2.0) : 0.0

rollKurt(float src, int len) =>
    m  = ta.sma(src, len)
    e2 = ta.sma(math.pow(src, 2), len)
    e3 = ta.sma(math.pow(src, 3), len)
    e4 = ta.sma(math.pow(src, 4), len)
    m2 = e2 - math.pow(m, 2)
    m4 = e4 - 4.0 * m * e3 + 6.0 * math.pow(m, 2) * e2 - 3.0 * math.pow(m, 4)
    g2 = m2 > 1e-18 ? m4 / math.pow(m2, 2) - 3.0 : 0.0
    len > 3 ? ((len + 1.0) * g2 + 6.0) * (len - 1.0) / ((len - 2.0) * (len - 3.0)) : 0.0

// zscoreSkipNa(): rolling z-score that IGNORES na, as pandas rolling does.
// Pine's ta.sma returns na when any window element is na, so a sparse series
// (e.g. returns masked to those at or below VaR) cannot be standardised with the
// plain zscore() above.
zscoreSkipNa(float src, int len) =>
    valid = na(src) ? 0.0 : 1.0
    fill  = nz(src, 0.0)
    n  = math.sum(valid, len)
    m  = n > 0 ? math.sum(fill, len) / n : na
    v  = n > 0 ? math.max(0.0, math.sum(fill * fill, len) / n - m * m) : na
    sd = math.sqrt(v)
    not na(src) and sd > 1e-12 ? (src - m) / sd : 0.0

// Expanding (since-inception) mean / stdev / variance via running sums.
// Several models call pandas .expanding(); a fixed-length ta.stdev is a different
// quantity and drifts as history accumulates.
expStdev(float src, int minN) =>
    var float en = 0.0
    var float es1 = 0.0
    var float es2 = 0.0
    if not na(src)
        en := en + 1.0
        es1 := es1 + src
        es2 := es2 + src * src
    m = en > 0 ? es1 / en : 0.0
    v = en > 0 ? math.max(0.0, es2 / en - m * m) : 0.0
    en >= minN ? math.sqrt(v) : na

expVariance(float src, int minN) =>
    var float vn = 0.0
    var float vs1 = 0.0
    var float vs2 = 0.0
    if not na(src)
        vn := vn + 1.0
        vs1 := vs1 + src
        vs2 := vs2 + src * src
    m = vn > 0 ? vs1 / vn : 0.0
    vn >= minN ? math.max(0.0, vs2 / vn - m * m) : na

// rolling covariance / correlation-free beta helper
rollCov(float x, float y, int len) => ta.sma(x * y, len) - ta.sma(x, len) * ta.sma(y, len)

// persist(): hold a sparse event signal for `bars` bars, as the engine's persist()
persist(float raw, int bars) =>
    var float held = 0.0
    var int   age  = 0
    if raw != 0.0
        held := raw
        age  := 0
    else
        age := age + 1
        if age > bars
            held := 0.0
    held
"""

# ── Trend & Momentum ──────────────────────────────────────────────────────────

_reg("Donchian Channel Breakout", """
up  = ta.highest(high, P)[1]
lo  = ta.lowest(low, P)[1]
raw = close > up ? 1.0 : close < lo ? -1.0 : 0.0
var float held = 0.0
var int   age  = 0
if raw != 0.0
    held := raw
    age  := 0
else
    age := age + 1
    if age > HOLD
        held := 0.0
score = held
""", overlay=True, plots="""
plot(ta.highest(high, P)[1], "Upper", color.new(color.teal, 40))
plot(ta.lowest(low, P)[1],  "Lower", color.new(color.red, 40))
""")

_reg("EMA 50/200 Golden Cross", """
f = ta.ema(close, FAST)
s = ta.ema(close, SLOW)
score = squash((f - s) / math.abs(s), 0.03)
""", overlay=True, plots="""
plot(ta.ema(close, FAST), "EMA fast", color.new(color.teal, 0))
plot(ta.ema(close, SLOW), "EMA slow", color.new(color.orange, 0))
""")

_reg("MACD Histogram Momentum", """
[macdLine, signalLine, histLine] = ta.macd(close, FAST, SLOW, SIGNAL)
atr = ta.atr(14)
score = squash(histLine / (atr > 1e-12 ? atr : 1e-12), 0.6)
""")

_reg("ADX Directional Movement", """
[diPlus, diMinus, adxVal] = ta.dmi(P, P)
gate = math.max(0.0, math.min(1.0, (adxVal - FLOOR) / 20.0))
score = squash((diPlus - diMinus) / 25.0, 1.0) * gate
""", plots="""
hline(0, "", color.new(color.gray, 60))
""")

_reg("Aroon Oscillator", """
upIdx = ta.highestbars(high, P + 1)
dnIdx = ta.lowestbars(low, P + 1)
aroonUp = 100.0 * (P + upIdx) / P
aroonDn = 100.0 * (P + dnIdx) / P
score = (aroonUp - aroonDn) / 100.0
""")

_reg("Keltner Channel Trend", """
mid = ta.ema(close, P)
atr = ta.atr(ATRP)
up  = mid + MULT * atr
lo  = mid - MULT * atr
width = up - lo
score = squash(width > 1e-12 ? (close - mid) / width * 4.0 : 0.0, 1.2)
""", overlay=True, plots="""
plot(ta.ema(close, P) + MULT * ta.atr(ATRP), "Upper", color.new(color.teal, 50))
plot(ta.ema(close, P),                        "Mid",   color.new(color.gray, 40))
plot(ta.ema(close, P) - MULT * ta.atr(ATRP), "Lower", color.new(color.red, 50))
""")

_reg("Supertrend (ATR Bands)", """
[stLine, stDir] = ta.supertrend(MULT, P)
strength = math.max(0.3, math.min(1.0, trendStrength()))
score = (stDir < 0 ? 1.0 : -1.0) * strength
""", overlay=True, plots="""
[stL, stD] = ta.supertrend(MULT, P)
plot(stL, "Supertrend", stD < 0 ? color.teal : color.red, 2)
""", note="ta.supertrend returns direction -1 when bullish, hence the sign flip.")

_reg("Vortex Indicator", """
tr  = math.sum(ta.tr(true), P)
vmP = math.sum(math.abs(high - low[1]), P)
vmM = math.sum(math.abs(low - high[1]), P)
viP = tr > 1e-12 ? vmP / tr : 0.0
viM = tr > 1e-12 ? vmM / tr : 0.0
score = squash(viP - viM, 0.15)
""")

_reg("Rolling Regression Slope (t-stat)", """
lg    = math.log(close)
slope = ta.linreg(lg, W, 0) - ta.linreg(lg, W, 1)
noise = ta.stdev(ta.change(lg), W, false)
score = squash(noise > 1e-12 ? slope / noise * math.sqrt(W) : 0.0, 2.0)
""")

_reg("Hull Moving Average Slope", """
hma = ta.hma(close, P)
atr = ta.atr(14)
score = squash(atr > 1e-12 ? (hma - hma[1]) / atr : 0.0, 0.3)
""", overlay=True, plots="""
plot(ta.hma(close, P), "HMA", color.new(color.purple, 0), 2)
""")

_reg("TRIX Triple-Smoothed Momentum", """
lg = math.log(close)
e1 = ta.ema(lg, P)
e2 = ta.ema(e1, P)
e3 = ta.ema(e2, P)
trix = (e3 - e3[1]) * 10000.0
sig  = ta.ema(trix, SIGNAL)
score = squash(trix - sig, 5.0)
""")

_reg("Chande Momentum Oscillator", """
d  = ta.change(close)
up = math.sum(math.max(d, 0.0), P)
dn = math.sum(math.max(-d, 0.0), P)
tot = up + dn
score = tot > 1e-12 ? (up - dn) / tot : 0.0
""")

_reg("52-Week High Proximity", """
hi = ta.highest(high, W)
lo = ta.lowest(low, W)
rng = hi - lo
pos = rng > 1e-12 ? (close - lo) / rng : 0.5
score = band_score(pos, 0.35, 0.98)
""")

_reg("Time-Series Momentum (12-1)", """
past = math.log(close[SKIP] / close[SKIP + LB])
vol  = ta.stdev(ta.change(math.log(close)), VOLW, false) * math.sqrt(LB)
score = squash(vol > 1e-9 ? past / vol : 0.0, 1.0)
""")

_reg("Ichimoku Kinko Hyo", """
midOf(int p) => (ta.highest(high, p) + ta.lowest(low, p)) / 2.0
tenkan = midOf(TENKAN)
kijun  = midOf(KIJUN)
spanA  = ((tenkan + kijun) / 2.0)[KIJUN]
spanB  = midOf(SENKOU)[KIJUN]
above  = close > spanA and close > spanB ? 1.0 : 0.0
below  = close < spanA and close < spanB ? 1.0 : 0.0
score  = math.max(-1.0, math.min(1.0, 0.5 * math.sign(tenkan - kijun) + 0.5 * (above - below)))
""", overlay=True, plots="""
midOf2(int p) => (ta.highest(high, p) + ta.lowest(low, p)) / 2.0
plot(midOf2(TENKAN), "Tenkan", color.new(color.blue, 0))
plot(midOf2(KIJUN),  "Kijun",  color.new(color.red, 0))
""")

_reg("Trend Quality (R-squared Gated)", """
er = math.abs(close - close[W]) / math.max(1e-12, math.sum(math.abs(ta.change(close)), W))
gate = math.max(0.0, math.min(1.0, (er - MINER) / (1.0 - MINER)))
score = math.sign(close - close[W]) * gate
""")

_reg("Volume-Confirmed Range Breakout", """
up = ta.highest(high, P)[1]
lo = ta.lowest(low, P)[1]
volZ = zscore(volume, 20)
conf = volZ > VOLZ ? 1.0 : 0.0
raw  = (close > up ? 1.0 : close < lo ? -1.0 : 0.0) * conf
var float held = 0.0
var int   age  = 0
if raw != 0.0
    held := raw
    age  := 0
else
    age := age + 1
    if age > 5
        held := 0.0
score = held
""", overlay=True)

# ── Mean Reversion ────────────────────────────────────────────────────────────

_reg("Bollinger Band Mean Reversion", """
mid = ta.sma(close, P)
sd  = ta.stdev(close, P, false)
up  = mid + K * sd
lo  = mid - K * sd
pctB = (up - lo) > 1e-12 ? (close - lo) / (up - lo) : 0.5
score = -band_score(pctB, 0.0, 1.0)
""", overlay=True, plots="""
plot(ta.sma(close, P) + K * ta.stdev(close, P, false), "Upper", color.new(color.red, 40))
plot(ta.sma(close, P),                                  "Mid",   color.new(color.gray, 50))
plot(ta.sma(close, P) - K * ta.stdev(close, P, false), "Lower", color.new(color.teal, 40))
""")

_reg("RSI(2) Extreme Reversion", """
r     = ta.rsi(close, RSIP)
trend = math.sign(close - ta.sma(close, TRENDP))
raw   = -band_score(r, 0.0, 100.0)
score = math.sign(raw) == trend ? raw : raw * 0.25
""")

_reg("Price Z-Score Reversion", """
score = -squash(zscore(close, W), 1.5)
""")

_reg("Stochastic Oscillator Reversion", """
k = ta.sma(ta.stoch(close, high, low, P), SMOOTH)
score = -band_score(k, 0.0, 100.0)
""")

_reg("Williams %R Reversion", """
wr = ta.stoch(close, high, low, P) - 100.0
score = -band_score(wr, -100.0, 0.0)
""")

_reg("Commodity Channel Index Reversion", """
score = -squash(ta.cci(close, P) / 100.0, 1.5)
""")

_reg("Money Flow Index Reversion", """
score = -band_score(ta.mfi(hlc3, P), 0.0, 100.0)
""")

_reg("Ultimate Oscillator", """
bp = close - math.min(low, close[1])
trv = ta.tr(true)
avgOf(int p) => math.sum(bp, p) / math.max(1e-12, math.sum(trv, p))
uo = 100.0 * (4.0 * avgOf(P1) + 2.0 * avgOf(P2) + avgOf(P3)) / 7.0
score = -band_score(uo, 0.0, 100.0)
""")

_reg("Keltner Channel Reversion", """
mid = ta.ema(close, P)
atr = ta.atr(14)
up = mid + MULT * atr
lo = mid - MULT * atr
w  = up - lo
score = -squash(w > 1e-12 ? (close - mid) / w * 4.0 : 0.0, 1.2)
""", overlay=True)

_reg("VWAP Reversion", """
pv = math.sum(hlc3 * volume, W)
vv = math.sum(volume, W)
vw = vv > 1e-12 ? pv / vv : ta.sma(hlc3, W)
atr = ta.atr(14)
score = -squash(atr > 1e-12 ? (close - vw) / atr : 0.0, 1.2)
""", overlay=True, plots="""
plot(math.sum(volume, W) > 1e-12 ? math.sum(hlc3 * volume, W) / math.sum(volume, W) : na,
     "Rolling VWAP", color.new(color.yellow, 0), 2)
""")

_reg("Short-Term Reversal (1-Period)", """
ret = (close - close[LB]) / close[LB]
score = -squash(zscore(ret, 60), 1.5)
""")

_reg("Overnight Gap Fade", """
gap = (open - close[1]) / close[1]
score = -squash(zscore(gap, ZW), 1.5)
""")

_reg("Bollinger Squeeze Release", """
bbU = ta.sma(close, P) + 2.0 * ta.stdev(close, P, false)
bbL = ta.sma(close, P) - 2.0 * ta.stdev(close, P, false)
kcU = ta.ema(close, P) + 1.5 * ta.atr(14)
kcL = ta.ema(close, P) - 1.5 * ta.atr(14)
squeezed = bbU < kcU and bbL > kcL
released = squeezed[1] and not squeezed
dirn = math.sign(close - ta.sma(close, P))
raw = released ? dirn : 0.0
var float held = 0.0
var int   age  = 0
if raw != 0.0
    held := raw
    age  := 0
else
    age := age + 1
    if age > HOLD
        held := 0.0
score = held
""")

_reg("Average Daily Range Exhaustion", """
atr = ta.atr(ATRP)
travelled = atr > 1e-12 ? (close - open) / atr : 0.0
excess = math.abs(travelled) - THRESH
score = -math.sign(travelled) * math.max(0.0, math.min(2.0, excess)) / 2.0
""")

_reg("Range-Bound Channel Oscillator", """
up = ta.highest(high, P)[1]
lo = ta.lowest(low, P)[1]
rng = up - lo
pos = rng > 1e-12 ? (close - lo) / rng : 0.5
er  = math.abs(close - close[P]) / math.max(1e-12, math.sum(math.abs(ta.change(close)), P))
ranging = math.max(0.0, math.min(1.0, 1.0 - er / MAXER))
score = -band_score(pos, 0.0, 1.0) * ranging
""")

# ── Volatility ────────────────────────────────────────────────────────────────

_reg("Yang-Zhang Drift-Independent Volatility", """
lgOC = math.log(open / close[1])
lgCO = math.log(close / open)
vo = ta.variance(lgOC, W)
vc = ta.variance(lgCO, W)
rs = math.log(high / close) * math.log(high / open) + math.log(low / close) * math.log(low / open)
vrs = ta.sma(rs, W)
k = 0.34 / (1.34 + (W + 1.0) / (W - 1.0))
yz = math.sqrt(math.max(0.0, vo + k * vc + (1.0 - k) * vrs)) * math.sqrt(BPY)
score = -squash(zscore(yz, 60), 1.5)
""")

_reg("Parkinson Range Volatility Divergence", """
hl = math.pow(math.log(high / low), 2)
pk = math.sqrt(ta.sma(hl, W) / (4.0 * math.log(2.0))) * math.sqrt(BPY)
cc = ta.stdev(ta.change(math.log(close)), W, false) * math.sqrt(BPY)
ratio = cc > 1e-9 ? pk / cc : 1.0
score = -squash(zscore(ratio, 60), 1.5)
""")

_reg("Volatility Expansion Breakout", """
rng = ta.tr(true)
narrow = ta.highest(rng, CW)
q25 = ta.percentile_linear_interpolation(rng, LB, 25)
wasNarrow = narrow[1] <= q25[1]
expanding = rng > ta.sma(rng, 20) * 1.5
raw = (wasNarrow and expanding) ? math.sign(close - open) : 0.0
var float held = 0.0
var int   age  = 0
if raw != 0.0
    held := raw
    age  := 0
else
    age := age + 1
    if age > HOLD
        held := 0.0
score = held
""", overlay=True)

_reg("ATR-Normalised Trend Exposure", """
mv  = close - close[TW]
atr = ta.atr(ATRP)
score = squash(atr > 1e-12 ? mv / atr / math.sqrt(TW) : 0.0, 1.0)
""")

_reg("Drawdown-Controlled Exposure", """
var float peak = na
peak := na(peak) ? close : math.max(peak, close)
dd = close / peak - 1.0
allowed = math.max(0.0, math.min(1.0, 1.0 + dd / MAXDD))
trend = math.sign(ta.ema(close, 50) - ta.ema(close, 200))
score = trend * allowed
""")

# ── Regime & Risk ─────────────────────────────────────────────────────────────

_reg("Maximum Drawdown Guard", """
var float peak = na
peak := na(peak) ? close : math.max(peak, close)
dd = close / peak - 1.0
capacity = math.max(0.0, math.min(1.0, 1.0 + dd / LIMIT))
trend = math.sign(ta.ema(close, 20) - ta.ema(close, 50))
score = trend * capacity
""")

_reg("Ulcer Index Downside Risk", """
var float peak = na
peak := na(peak) ? close : math.max(peak, close)
dd = (close / peak - 1.0) * 100.0
ulcer = math.sqrt(ta.sma(math.pow(dd, 2), W))
score = -squash(zscore(ulcer, 120), 1.5)
""")

_reg("Sortino Downside Deviation", """
r  = ta.change(math.log(close))
mu = ta.sma(r, W)
neg = r < 0 ? r : 0.0
ds = ta.stdev(neg, W, false)
score = squash(ds > 1e-12 ? mu / ds * math.sqrt(BPY) : 0.0, 1.5)
""")

# ── Microstructure ────────────────────────────────────────────────────────────

_reg("Order Flow Imbalance", """
rng = high - low
pressure = rng > 1e-12 ? 2.0 * (close - low) / rng - 1.0 : 0.0
ofi = math.sum(pressure * volume, W)
score = squash(zscore(ofi, 60), 1.5)
""", note="Proxy in the Python too: bar close position stands in for L1 book updates.",
     exact=True)

_reg("Tick Rule Signed Flow", """
var float tick = 0.0
ch = ta.change(close)
tick := ch > 0 ? 1.0 : ch < 0 ? -1.0 : tick
score = squash(ta.sma(tick, W) * 2.0, 0.6)
""")

_reg("Roll Effective Spread Estimator", """
r = ta.change(close) / close[1]
cov = ta.sma(r * r[1], W) - ta.sma(r, W) * ta.sma(r[1], W)
spread = 2.0 * math.sqrt(math.max(0.0, -cov))
score = -squash(zscore(spread, 120), 1.5)
""")

_reg("Amihud Illiquidity Ratio", """
r  = math.abs(ta.change(close) / close[1])
dv = close * volume
illiq = ta.sma(dv > 0 ? r / dv : 0.0, W)
score = -squash(zscore(illiq, 120), 1.5)
""")

# ── Seasonality ───────────────────────────────────────────────────────────────

_reg("Turn-of-the-Month Effect", """
dim  = dayofmonth(timestamp(year, month + 1, 1, 0, 0) - 86400000)
near = (dim - dayofmonth) <= BEFORE or dayofmonth <= AFTER
score = near ? 0.6 : -0.15
""")

_reg("Halloween Indicator (Sell in May)", """
winter = month >= 11 or month <= 4
score = winter ? 0.45 : -0.25
""")

_reg("Options Expiry Week Effect", """
inWeek = dayofmonth >= 15 and dayofmonth <= 21
score = -squash(zscore(close, 20), 1.5) * (inWeek ? 0.8 : 0.0)
""")


# Default parameter substitutions, keyed by the placeholder used in each body.
_PARAM_MAP = {
    "Donchian Channel Breakout": {"P": "period", "HOLD": "hold"},
    "EMA 50/200 Golden Cross": {"FAST": "fast", "SLOW": "slow"},
    "MACD Histogram Momentum": {"FAST": "fast", "SLOW": "slow", "SIGNAL": "signal"},
    "ADX Directional Movement": {"P": "period", "FLOOR": "adx_floor"},
    "Aroon Oscillator": {"P": "period"},
    "Keltner Channel Trend": {"P": "period", "ATRP": "atr_period", "MULT": "mult"},
    "Supertrend (ATR Bands)": {"P": "period", "MULT": "multiplier", "ERP": "period"},
    "Vortex Indicator": {"P": "period"},
    "Rolling Regression Slope (t-stat)": {"W": "window"},
    "Hull Moving Average Slope": {"P": "period"},
    "TRIX Triple-Smoothed Momentum": {"P": "period", "SIGNAL": "signal"},
    "Chande Momentum Oscillator": {"P": "period"},
    "52-Week High Proximity": {"W": "window"},
    "Time-Series Momentum (12-1)": {"LB": "lookback", "SKIP": "skip", "VOLW": "vol_window"},
    "Ichimoku Kinko Hyo": {"TENKAN": "tenkan", "KIJUN": "kijun", "SENKOU": "senkou"},
    "Trend Quality (R-squared Gated)": {"W": "window", "MINER": "min_er"},
    "Volume-Confirmed Range Breakout": {"P": "period", "VOLZ": "vol_z"},
    "Bollinger Band Mean Reversion": {"P": "period", "K": "k"},
    "RSI(2) Extreme Reversion": {"RSIP": "rsi_period", "TRENDP": "trend_period"},
    "Price Z-Score Reversion": {"W": "window"},
    "Stochastic Oscillator Reversion": {"P": "period", "SMOOTH": "smooth"},
    "Williams %R Reversion": {"P": "period"},
    "Commodity Channel Index Reversion": {"P": "period"},
    "Money Flow Index Reversion": {"P": "period"},
    "Ultimate Oscillator": {"P1": "p1", "P2": "p2", "P3": "p3"},
    "Keltner Channel Reversion": {"P": "period", "MULT": "mult"},
    "VWAP Reversion": {"W": "window"},
    "Short-Term Reversal (1-Period)": {"LB": "lookback"},
    "Overnight Gap Fade": {"ZW": "z_window"},
    "Bollinger Squeeze Release": {"P": "period", "HOLD": "hold"},
    "Average Daily Range Exhaustion": {"ATRP": "atr_period", "THRESH": "threshold"},
    "Range-Bound Channel Oscillator": {"P": "period", "MAXER": "max_er"},
    "Yang-Zhang Drift-Independent Volatility": {"W": "window"},
    "Parkinson Range Volatility Divergence": {"W": "window"},
    "Volatility Expansion Breakout": {"CW": "compress_window", "LB": "lookback", "HOLD": "hold"},
    "ATR-Normalised Trend Exposure": {"TW": "trend_window", "ATRP": "atr_period"},
    "Drawdown-Controlled Exposure": {"MAXDD": "max_dd"},
    "Maximum Drawdown Guard": {"LIMIT": "limit"},
    "Ulcer Index Downside Risk": {"W": "window"},
    "Sortino Downside Deviation": {"W": "window"},
    "Order Flow Imbalance": {"W": "window"},
    "Tick Rule Signed Flow": {"W": "window"},
    "Roll Effective Spread Estimator": {"W": "window"},
    "Amihud Illiquidity Ratio": {"W": "window"},
    "Turn-of-the-Month Effect": {"BEFORE": "days_before", "AFTER": "days_after"},
    "Options Expiry Week Effect": {},
    "Halloween Indicator (Sell in May)": {},
}

BARS_PER_YEAR_PINE = {
    "1m": 98280, "5m": 19656, "15m": 6552, "30m": 3276,
    "1h": 1764, "4h": 504, "1d": 252, "1wk": 52, "1mo": 12,
}


def is_translatable(strategy: BaseStrategy) -> bool:
    return strategy.name in _T


def untranslatable_reason(strategy: BaseStrategy) -> str:
    """Why a model has no Pine translation. Never guesses."""
    needs = {n.value for n in strategy.needs}
    if not needs <= {"ohlc", "volume"}:
        external = sorted(needs - {"ohlc", "volume"})
        return f"needs data Pine cannot reach ({', '.join(external)})"
    if strategy.category == "Machine Learning":
        return "online training loop (matrix solve / gradient descent) has no Pine equivalent"
    return "no faithful translation written yet"


# Fallbacks for placeholders whose model declares no matching parameter. These
# mirror the defaults baked into the Python (FeatureSet.vol_regime ranks over a
# 252-bar window), so an omitted parameter still substitutes rather than leaving
# a bare token in the emitted Pine.
_PLACEHOLDER_DEFAULTS = {"RANKW": 252}



def _hoist_functions(body: str) -> tuple[str, str]:
    """
    Split a translation body into (top-level function declarations, remainder).

    Pine requires every user function to be declared at the script's top level;
    a declaration inside another function body is a compile error. A declaration
    is a zero-indent line matching ``name(args) =>``, and it owns every indented
    line that follows it.
    """
    lines = body.splitlines()
    decl_re = re.compile(r"^[A-Za-z_]\w*\s*\([^)]*\)\s*=>")
    funcs: list[str] = []
    rest: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if decl_re.match(line):
            block = [line]
            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith((" ", "	"))):
                block.append(lines[i])
                i += 1
            # Trailing blank lines belong to neither part.
            while block and not block[-1].strip():
                block.pop()
            funcs.append("\n".join(block))
        else:
            rest.append(line)
            i += 1
    return "\n".join(funcs), "\n".join(rest)


def _substitute(body: str, name: str, params: dict, interval: str) -> str:
    mapping = _PARAM_MAP.get(name, {})
    out = body
    # Longest placeholder first, so SLOW is not clobbered by a substring match.
    for placeholder in sorted(mapping, key=len, reverse=True):
        val = params.get(mapping[placeholder], _PLACEHOLDER_DEFAULTS.get(placeholder))
        if val is None:
            continue
        out = out.replace(placeholder, repr(val) if not isinstance(val, float) else f"{val}")
    # Any placeholder with a default but no mapping entry at all.
    for placeholder, val in _PLACEHOLDER_DEFAULTS.items():
        out = out.replace(placeholder, str(val))
    out = out.replace("BPY", str(BARS_PER_YEAR_PINE.get(interval, 252)))
    return out


def emit(strategy: BaseStrategy, interval: str = "1d",
         band: float = 0.15) -> Optional[str]:
    """
    Generate a complete, pasteable Pine v6 indicator for one model.

    Returns None when no faithful translation exists.
    """
    t = _T.get(strategy.name)
    if t is None:
        return None

    params = dict(strategy.params)
    body = _substitute(t.body, strategy.name, params, interval)
    plots = _substitute(t.plots, strategy.name, params, interval) if t.plots else ""

    param_lines = "\n".join(f"//   {k} = {v!r}" for k, v in params.items()) or "//   (none)"
    # Longest lookback in the model's parameters — how many bars Pine needs before
    # its output can agree with the Python, which uses partial windows.
    numeric = [v for v in params.values()
               if isinstance(v, (int, float)) and not isinstance(v, bool)]
    warmup = int(max(numeric)) if numeric else strategy.min_bars
    note = f"//\n// NOTE: {t.note}\n" if t.note else ""
    proxy = ""
    if strategy.is_proxy:
        proxy = (f"//\n// PROXY: {strategy.proxy_note}\n")

    # Pine forbids nested function declarations — every `name(args) =>` must sit
    # at the top level. Several bodies declare a local helper (rsHurst, midOf,
    # fracDiff...), so those declarations and their indented blocks are hoisted
    # out above calcScore(). Without this the script does not compile at all.
    hoisted, remainder = _hoist_functions(body)
    indented = "\n".join("    " + ln if ln.strip() else ln for ln in remainder.splitlines())
    hoisted_block = (hoisted + "\n") if hoisted else ""

    # Built outside the f-string: nested quotes and escapes inside an f-string
    # expression are a syntax error on the Python versions this has to run on.
    if t.overlay:
        score_plot = ''
        bands = ""
    else:
        score_plot = 'plot(s, "Score", color.new(color.blue, 0), 2)'
        bands = (
            'hline(BAND, "Buy band", color.new(color.teal, 50), hline.style_dashed)\n'
            'hline(-BAND, "Sell band", color.new(color.red, 50), hline.style_dashed)\n'
            'hline(0, "", color.new(color.gray, 70))'
        )

    return f'''//@version={PINE_VERSION}
// ─────────────────────────────────────────────────────────────────────────────
// {strategy.name}
// Category : {strategy.category}   Family: {strategy.family}
// Research : {strategy.research}
//
// {strategy.description}
//
// Generated from the Python model of the same name. The maths below computes the
// same score the engine computes; a BUY plots where score >= {band}, a SELL where
// score <= -{band}.
//
// Parameters (matching the engine's defaults):
{param_lines}
//
// WARM-UP: Pine's ta.* functions return na until the full lookback exists, while
// the Python engine uses partial windows (min_periods = window/2). The two agree
// to floating-point precision once warmed up; expect the first ~{warmup} bars to
// differ. Pine's behaviour is the stricter of the two.
{note}{proxy}// ─────────────────────────────────────────────────────────────────────────────
indicator("{strategy.name}", overlay={"true" if t.overlay else "false"})
{_HELPERS}
BAND = input.float({band}, "Signal band", minval=0.01, maxval=0.9,
     tooltip="|score| below this is treated as no opinion, matching the engine.")

{hoisted_block}calcScore() =>
{indented}
    score

s = math.max(-1.0, math.min(1.0, calcScore()))

isBuy  = s >= BAND
isSell = s <= -BAND

{plots}
{score_plot}
{bands}

plotshape(isBuy and not isBuy[1],  "BUY",  shape.triangleup,
     location.belowbar, color.new(color.teal, 0), size=size.small)
plotshape(isSell and not isSell[1], "SELL", shape.triangledown,
     location.abovebar, color.new(color.red, 0), size=size.small)

bgcolor(isBuy ? color.new(color.teal, 92) : isSell ? color.new(color.red, 92) : na)

alertcondition(isBuy  and not isBuy[1],  "BUY signal",  "{strategy.name}: BUY")
alertcondition(isSell and not isSell[1], "SELL signal", "{strategy.name}: SELL")
'''


def emit_consensus(strategies: list[BaseStrategy], interval: str = "1d",
                   band: float = 0.15, title: str = "Quant Desk Consensus") -> str:
    """
    One indicator combining every translatable model, equally weighted per family.

    Family weighting is carried over from the Python consensus: without it, a
    crowded family would dominate the plotted average exactly as it would
    dominate a naive vote.
    """
    usable = [s for s in strategies if s.name in _T]
    if not usable:
        return "// No translatable models in the supplied set."

    by_family: dict[str, int] = {}
    for s in usable:
        by_family[s.family] = by_family.get(s.family, 0) + 1

    blocks, weights, names = [], [], []
    for i, s in enumerate(usable):
        body = _substitute(_T[s.name].body, s.name, dict(s.params), interval)
        indented = "\n".join("    " + ln if ln.strip() else ln for ln in body.splitlines())
        # No `float score = 0.0` pre-declaration: each body declares `score` itself,
        # and re-assigning a declared variable with `=` is a Pine syntax error.
        blocks.append(f"f{i}() =>\n{indented}\n    math.max(-1.0, math.min(1.0, score))")
        weights.append(round(1.0 / by_family[s.family], 6))
        names.append(s.name)

    total_w = sum(weights) or 1.0
    terms = " + ".join(f"f{i}() * {w}" for i, w in enumerate(weights))
    roster = "\n".join(f"//   [{w:.3f}]  {n}" for w, n in zip(weights, names))

    return f'''//@version={PINE_VERSION}
// ─────────────────────────────────────────────────────────────────────────────
// {title}
//
// Weighted consensus across {len(usable)} models spanning {len(by_family)} independent
// families, using the same family weighting as the Python engine: models sharing
// a family split one family's vote, so a crowded style cannot win on headcount.
//
// Models included (weight, name):
{roster}
//
// This covers only the models expressible in Pine. The full engine runs 311,
// including many that need options, fundamentals or cross-sectional data that
// Pine cannot access — so this plot is a subset, not the whole consensus.
// ─────────────────────────────────────────────────────────────────────────────
indicator("{title}", overlay=false)
{_HELPERS}
BAND = input.float({band}, "Signal band", minval=0.01, maxval=0.9)

{chr(10).join(blocks)}

raw = ({terms}) / {round(total_w, 6)}
s = math.max(-1.0, math.min(1.0, raw))

isBuy  = s >= BAND
isSell = s <= -BAND

plot(s, "Consensus", color.new(color.blue, 0), 2)
hline(BAND,  "Buy band",  color.new(color.teal, 50), hline.style_dashed)
hline(-BAND, "Sell band", color.new(color.red, 50),  hline.style_dashed)
hline(0, "", color.new(color.gray, 70))

plotshape(isBuy and not isBuy[1],   "BUY",  shape.triangleup,
     location.bottom, color.new(color.teal, 0), size=size.small)
plotshape(isSell and not isSell[1], "SELL", shape.triangledown,
     location.top, color.new(color.red, 0), size=size.small)

bgcolor(isBuy ? color.new(color.teal, 92) : isSell ? color.new(color.red, 92) : na)

alertcondition(isBuy  and not isBuy[1],  "Consensus BUY",  "{title}: BUY")
alertcondition(isSell and not isSell[1], "Consensus SELL", "{title}: SELL")
'''


def coverage() -> dict:
    """How much of the library has a Pine translation."""
    return {"translations": len(_T), "names": sorted(_T)}


# Extended translations live in sibling modules and register into _T on import.
# Imported at the bottom so _reg and _PARAM_MAP already exist.
from . import pine_ext as _ext1  # noqa: E402,F401
from . import pine_ext2 as _ext2  # noqa: E402,F401
