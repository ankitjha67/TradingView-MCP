"""
Extended Pine v6 translations.

Registers into the same table as ``pine.py``. Split out purely for file size —
``pine.py`` holds the emitter plus the first tranche; this holds the rest, so the
two together cover every price-only model in the library.

Same correctness rule applies: a translation is registered only when the Pine
computes the same quantity as the Python. Where the engine uses a construct Pine
cannot reproduce exactly — notably ``rolling_rank`` (see ``prank`` in the shared
helpers) — the translation is registered with ``exact=False`` and the deviation
is stated in the emitted header rather than hidden.
"""
from __future__ import annotations

from .pine import _PARAM_MAP, _reg

_RANK = "RANKW"  # placeholder for the percentile-rank window

# ── Volatility ────────────────────────────────────────────────────────────────

_reg("GARCH(1,1) Volatility Forecast", """
r = lr()
lrv = expVariance(r, 30)
om = lrv * (1.0 - A - B)
var float v = na
v := na(v) ? lrv : om + A * math.pow(nz(r[1]), 2) + B * nz(v[1], lrv)
fc = math.sqrt(v * BPY)
rz = rvol(20)
gap = rz > 1e-9 ? (fc - rz) / rz : 0.0
score = -squash(gap, 0.35) * math.sign(zscore(close, 20))
""", note="Long-run variance is an EXPANDING estimate here. The Python derives it from the full sample, which peeks ahead; the Pine form is causal and the two therefore differ by construction.")

_reg("EGARCH Leverage Asymmetry", """
r = lr()
dn = ta.stdev(r < 0 ? r : 0.0, W, false)
up = ta.stdev(r > 0 ? r : 0.0, W, false)
asym = (dn + up) > 1e-12 ? (dn - up) / (dn + up) : 0.0
score = -squash(asym, 0.25)
""")

_reg("GJR-GARCH Threshold Volatility", """
r = lr()
lrv = expVariance(r, 30)
om = lrv * math.max(1e-6, 1.0 - A - G / 2.0 - B)
var float v = na
sh = math.pow(nz(r[1]), 2)
v := na(v) ? lrv : om + A * sh + G * sh * (nz(r[1]) < 0 ? 1.0 : 0.0) + B * nz(v[1], lrv)
cond = math.sqrt(v * BPY)
score = -squash(zscore(cond, 60), 1.5)
""")

_reg("HAR-RV Heterogeneous Autoregression", """
rv = math.pow(lr(), 2)
d = ta.sma(rv, D)
w = ta.sma(rv, W)
m = ta.sma(rv, M)
fc = 0.35 * d + 0.35 * w + 0.30 * m
cur = ta.sma(rv, 5)
gap = cur > 1e-14 ? (fc - cur) / cur : 0.0
score = -squash(gap, 0.5)
""")

_reg("Garman-Klass Volatility Efficiency", """
hl = 0.5 * math.pow(math.log(high / low), 2)
co = (2.0 * math.log(2.0) - 1.0) * math.pow(math.log(close / open), 2)
gk = math.sqrt(math.max(0.0, ta.sma(hl - co, W))) * math.sqrt(BPY)
score = -squash(zscore(gk, 60), 1.5) * math.sign(zscore(close, 20))
""")

_reg("Rogers-Satchell Drift-Robust Volatility", """
rs = math.log(high / close) * math.log(high / open) + math.log(low / close) * math.log(low / open)
rsv = math.sqrt(math.max(0.0, ta.sma(rs, W))) * math.sqrt(BPY)
cc = rvol(W)
score = -squash(zscore(cc > 1e-9 ? rsv / cc : 1.0, 60), 1.5)
""")

_reg("Bipower Variation Jump Detection", """
ar = math.abs(lr())
rv = math.sum(math.pow(lr(), 2), W)
bv = (math.pi / 2.0) * math.sum(ar * ar[1], W)
jr = rv > 1e-14 ? math.max(0.0, math.min(1.0, (rv - bv) / rv)) : 0.0
score = -math.sign(lr()) * jr
""")

_reg("Merton Jump-Diffusion Discrepancy", """
sd = ta.stdev(lr(), W, false)
z = sd > 1e-12 ? lr() / sd : 0.0
ex = math.max(0.0, math.min(3.0, math.abs(z) - THRESH)) / 3.0
score = -math.sign(z) * ex
""")

_reg("Realized Skewness Premium", """
score = -squash(rollSkew(lr(), W), 0.8)
""")

_reg("Volatility of Volatility", """
rz = rvol(VW)
vov = ta.stdev(rz, VVW, false)
score = -squash(zscore(vov, 120), 1.5)
""")

_reg("Realized Volatility Term Structure", """
s = rvol(SHORT)
l = rvol(LONG)
slope = l > 1e-9 ? (s - l) / l : 0.0
score = -squash(slope, 0.3)
""")

_reg("Volatility Clustering Persistence", """
ar = math.abs(lr())
cl = ta.correlation(ar, ar[1], W)
trend = math.sign(ta.ema(close, 20) - ta.ema(close, 50))
score = trend * (1.0 - math.max(0.0, math.min(1.0, cl))) * 0.7
""")

_reg("Volatility Mean Reversion", """
vr = volRegime(RANKW)
dirn = -math.sign(zscore(close, 20))
score = dirn * math.max(0.0, band_score(vr, 0.5, 0.95))
""", exact=False, note="Uses ta.percentrank for the volatility percentile; see prank() note.")

_reg("Volatility-Managed Portfolio", """
rz = rvol(W)
sc = math.max(0.0, math.min(2.0, rz > 1e-6 ? TGT / rz : 0.0))
trend = math.sign(ta.ema(close, 50) - ta.ema(close, 200))
score = math.max(-1.0, math.min(1.0, trend * sc / 2.0))
""")

_reg("Conditional Tail Risk (CVaR)", """
q = ta.percentile_linear_interpolation(lr(), W, 5)
below = lr() <= q ? 1.0 : 0.0
cvSum = math.sum(lr() <= q ? lr() : 0.0, W)
cvCnt = math.sum(below, W)
cv = cvCnt >= 5 ? cvSum / cvCnt : na
trend = math.sign(ta.ema(close, 20) - ta.ema(close, 50))
score = trend * math.max(0.0, math.min(1.0, 1.0 + squash(zscoreSkipNa(cv, W), 1.5)))
""", note="Averages every below-VaR return inside the window, matching the engine's masked rolling mean.")

_reg("Intraday Volatility Seasonality", """
rng = ta.tr(true) / close
var float[] hSum = array.new_float(24, 0.0)
var int[]   hCnt = array.new_int(24, 0)
h = hour
prevMean = array.get(hCnt, h) > 0 ? array.get(hSum, h) / array.get(hCnt, h) : rng
array.set(hSum, h, array.get(hSum, h) + rng)
array.set(hCnt, h, array.get(hCnt, h) + 1)
ex = prevMean > 1e-12 ? (rng - prevMean) / prevMean : 0.0
score = -math.sign(lr()) * math.abs(squash(ex, 0.5))
""", note="Seasonal mean accumulates per hour-of-day, matching the engine's expanding groupby.")

# ── Trend & Momentum ──────────────────────────────────────────────────────────

_reg("Turtle Trading System 1", """
eU = ta.highest(high, ENTRY)[1]
eL = ta.lowest(low, ENTRY)[1]
xU = ta.highest(high, EXIT)[1]
xL = ta.lowest(low, EXIT)[1]
var float st = 0.0
if st > 0 and close < xL
    st := 0.0
else if st < 0 and close > xU
    st := 0.0
if st == 0.0
    st := close > eU ? 1.0 : close < eL ? -1.0 : 0.0
score = st
""", overlay=True)

_reg("Parabolic SAR", """
psar = ta.sar(STEP, STEP, MAXAF)
score = (close > psar ? 1.0 : -1.0) * 0.8
""", overlay=True, plots="""
plot(ta.sar(STEP, STEP, MAXAF), "SAR", color.new(color.orange, 0), 1, plot.style_cross)
""")

_reg("Kaufman Adaptive Moving Average", """
er = effRatio(P)
sc = math.pow(er * (2.0 / (FAST + 1.0) - 2.0 / (SLOW + 1.0)) + 2.0 / (SLOW + 1.0), 2)
var float k = na
k := na(k) ? close : nz(k[1], close) + sc * (close - nz(k[1], close))
atr = ta.atr(14)
score = squash(atr > 1e-12 ? (close - k) / atr : 0.0, 1.5) * math.max(0.0, math.min(1.0, er))
""", overlay=True, plots="""
var float kplot = na
kplot := na(kplot) ? close : nz(kplot[1], close) +
     math.pow(effRatio(P) * (2.0 / (FAST + 1.0) - 2.0 / (SLOW + 1.0)) + 2.0 / (SLOW + 1.0), 2) *
     (close - nz(kplot[1], close))
plot(kplot, "KAMA", color.new(color.aqua, 0), 2)
""")

_reg("Coppock Curve", """
roc = ((close - close[R1]) / close[R1] + (close - close[R2]) / close[R2]) * 100.0
cc = ta.wma(roc, WMA)
score = squash(cc, 8.0)
""")

_reg("Dual Momentum (Absolute + Relative)", """
absolute = math.sign((close - close[ABS]) / close[ABS])
relative = squash(zscore((close - close[REL]) / close[REL], 126), 1.5)
score = math.sign(relative) == absolute ? relative : 0.0
""")

_reg("Elder Triple Screen", """
trend = math.sign(ta.ema(close, TSPAN) - ta.ema(close, TSPAN)[1])
force = ta.ema(ta.change(close) * volume, OSC)
pullback = -squash(zscore(force, 40), 1.5)
score = math.sign(pullback) == trend ? math.abs(pullback) * trend : 0.0
""")

_reg("Guppy Multiple Moving Average", """
sh = (ta.ema(close, 3) + ta.ema(close, 5) + ta.ema(close, 8) + ta.ema(close, 10) +
      ta.ema(close, 12) + ta.ema(close, 15)) / 6.0
ln = (ta.ema(close, 30) + ta.ema(close, 35) + ta.ema(close, 40) + ta.ema(close, 45) +
      ta.ema(close, 50) + ta.ema(close, 60)) / 6.0
score = squash((sh - ln) / math.abs(ln), 0.02)
""", overlay=True)

_reg("Ehlers Instantaneous Trendline", """
src = (high + low) / 2.0
a = ALPHA
var float it = na
it := bar_index < 3 ? src :
     (a - a * a / 4.0) * src + 0.5 * a * a * nz(src[1]) - (a - 0.75 * a * a) * nz(src[2]) +
     2.0 * (1.0 - a) * nz(it[1], src) - math.pow(1.0 - a, 2) * nz(it[2], src)
atr = ta.atr(14)
score = squash(atr > 1e-12 ? (close - it) / atr : 0.0, 1.5)
""")

_reg("Ehlers Fisher Transform", """
mid = (high + low) / 2.0
ll = ta.lowest(mid, P)
hh = ta.highest(mid, P)
rng = hh - ll
raw = rng > 1e-12 ? math.max(-0.999, math.min(0.999, 2.0 * (mid - ll) / rng - 1.0)) : 0.0
sm = math.max(-0.999, math.min(0.999, ta.ema(raw, 5)))
fish = 0.5 * math.log((1.0 + sm) / (1.0 - sm))
score = squash(ta.ema(fish, 3), 1.5)
""", exact=False, note="Python uses ewm(alpha=0.33)/ewm(alpha=0.5); Pine ta.ema spans 5 and 3 are the nearest equivalents.")

_reg("Momentum Acceleration (2nd Derivative)", """
mf = (close - close[FAST]) / close[FAST]
ms = (close - close[SLOW]) / close[SLOW]
accel = mf - ms * (FAST / SLOW)
score = squash(zscore(accel, 63), 1.5)
""")

_reg("Volatility-Scaled Trend (CTA Core)", """
vol = ta.stdev(lr(), 60, false)
leg(int lb) => squash(vol > 1e-9 ? math.log(close / close[lb]) / (vol * math.sqrt(lb)) : 0.0, 1.0)
score = (leg(21) + leg(63) + leg(252)) / 3.0
""")

_reg("Failed Breakout Reversal", """
up = ta.highest(high, P)[1]
lo = ta.lowest(low, P)[1]
fu = (high > up and close < up) ? 1.0 : 0.0
fd = (low < lo and close > lo) ? 1.0 : 0.0
score = persist(fd - fu, HOLD)
""", overlay=True)

# ── Mean Reversion ────────────────────────────────────────────────────────────

_reg("Connors RSI Composite", """
var float streak = 0.0
d = math.sign(ta.change(close))
streak := d != 0 and d == math.sign(nz(streak[1])) ? nz(streak[1]) + d : d
sRsi = 50.0 + 50.0 * squash(streak / 3.0, 1.0)
rank = prank(ta.change(close) / close[1], RANKP) * 100.0
crsi = (ta.rsi(close, RSIP) + sRsi + rank) / 3.0
score = -band_score(crsi, 0.0, 100.0)
""", exact=False, note="Streak RSI uses tanh(streak/3) as the Python does; percent-rank convention differs slightly.")

_reg("Half-Life Gated Reversion", """
lag = close[1]
delta = close - lag
cov = rollCov(delta, lag, HLW)
vr = ta.variance(lag, HLW)
beta = vr > 1e-12 ? cov / vr : 0.0
hl = beta < -1e-9 ? -math.log(2.0) / beta : 1e9
gate = math.max(0.0, math.min(1.0, 1.0 - hl / MAXHL))
score = -squash(zscore(close, W), 1.5) * gate
""")

_reg("Fat-Tail Move Reversion", """
rk = prank(ta.change(close) / close[1], W)
score = (rk < TAIL ? 1.0 : rk > 1.0 - TAIL ? -1.0 : 0.0) * 0.85
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Long-Term Reversal (De Bondt-Thaler)", """
r = (close - close[LB]) / close[LB]
score = -squash(zscore(r, 252), 1.5)
""")

_reg("Opening Range Reversal", """
atr = ta.atr(14)
exc = atr > 1e-12 ? (close - open) / atr : 0.0
stalling = ta.tr(true) < atr ? 1.0 : 0.0
score = -squash(exc, 1.5) * stalling
""")

_reg("RSI Regular Divergence", """
r = ta.rsi(close, P)
pxHi = close >= ta.highest(close, W)
pxLo = close <= ta.lowest(close, W)
rLowerHi = r < ta.highest(r, W)
rHigherLo = r > ta.lowest(r, W)
bear = (pxHi and rLowerHi) ? 1.0 : 0.0
bull = (pxLo and rHigherLo) ? 1.0 : 0.0
score = persist(bull - bear, HOLD)
""")

_reg("TD Sequential Setup Count", """
var int cu = 0
var int cd = 0
cu := close > close[LAG] ? cu + 1 : 0
cd := close < close[LAG] ? cd + 1 : 0
score = math.min(cd, TARGET) / TARGET - math.min(cu, TARGET) / TARGET
""", overlay=True)


_PARAM_MAP.update({
    "GARCH(1,1) Volatility Forecast": {"A": "alpha", "B": "beta"},
    "EGARCH Leverage Asymmetry": {"W": "window"},
    "GJR-GARCH Threshold Volatility": {"A": "alpha", "G": "gamma", "B": "beta"},
    "HAR-RV Heterogeneous Autoregression": {"D": "daily", "W": "weekly", "M": "monthly"},
    "Garman-Klass Volatility Efficiency": {"W": "window"},
    "Rogers-Satchell Drift-Robust Volatility": {"W": "window"},
    "Bipower Variation Jump Detection": {"W": "window"},
    "Merton Jump-Diffusion Discrepancy": {"W": "window", "THRESH": "threshold"},
    "Realized Skewness Premium": {"W": "window"},
    "Volatility of Volatility": {"VW": "vol_window", "VVW": "vov_window"},
    "Realized Volatility Term Structure": {"SHORT": "short", "LONG": "long"},
    "Volatility Clustering Persistence": {"W": "window"},
    "Volatility Mean Reversion": {"RANKW": "rank_window"},
    "Volatility-Managed Portfolio": {"TGT": "target_vol", "W": "window"},
    "Conditional Tail Risk (CVaR)": {"W": "window"},
    "Intraday Volatility Seasonality": {},
    "Turtle Trading System 1": {"ENTRY": "entry", "EXIT": "exit"},
    "Parabolic SAR": {"STEP": "af_step", "MAXAF": "af_max"},
    "Kaufman Adaptive Moving Average": {"P": "period", "FAST": "fast", "SLOW": "slow"},
    "Coppock Curve": {"R1": "roc1", "R2": "roc2", "WMA": "wma"},
    "Dual Momentum (Absolute + Relative)": {"ABS": "abs_lb", "REL": "rel_lb"},
    "Elder Triple Screen": {"TSPAN": "trend_span", "OSC": "osc_period"},
    "Guppy Multiple Moving Average": {},
    "Ehlers Instantaneous Trendline": {"ALPHA": "alpha"},
    "Ehlers Fisher Transform": {"P": "period"},
    "Momentum Acceleration (2nd Derivative)": {"FAST": "fast", "SLOW": "slow"},
    "Volatility-Scaled Trend (CTA Core)": {},
    "Failed Breakout Reversal": {"P": "period", "HOLD": "hold"},
    "Connors RSI Composite": {"RSIP": "rsi_p", "RANKP": "rank_p"},
    "Half-Life Gated Reversion": {"W": "window", "HLW": "hl_window", "MAXHL": "max_hl"},
    "Fat-Tail Move Reversion": {"W": "window", "TAIL": "tail_pct"},
    "Long-Term Reversal (De Bondt-Thaler)": {"LB": "lookback"},
    "Opening Range Reversal": {},
    "RSI Regular Divergence": {"P": "period", "W": "window", "HOLD": "hold"},
    "TD Sequential Setup Count": {"LAG": "lag", "TARGET": "target"},
})
