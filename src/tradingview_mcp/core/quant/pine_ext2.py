"""
Extended Pine v6 translations, part two.

Statistical arbitrage, microstructure, regime & risk, factor, macro, seasonality,
options income, crypto and sentiment. Registers into the same table as
``pine.py``.
"""
from __future__ import annotations

from .pine import _PARAM_MAP, _reg

# ── Statistical Arbitrage ─────────────────────────────────────────────────────

_reg("Ornstein-Uhlenbeck Process Fit", """
lag = close[1]
delta = close - lag
cov = rollCov(delta, lag, W)
vr = ta.variance(lag, W)
theta = vr > 1e-12 ? -(cov / vr) : 0.0
mu = math.abs(theta) > 1e-12 ? ta.sma(delta, W) / theta + ta.sma(lag, W) : close
sd = ta.stdev(delta, W, false)
dev = sd > 1e-12 ? (close - mu) / sd : 0.0
score = theta > 0 ? -squash(dev, 2.0) : 0.0
""")

_reg("Kalman Filter State Estimate", """
sc = ta.median(math.abs(ta.change(close)), 200)
scl = sc > 0 ? sc : 1.0
q = PVAR * math.pow(scl, 2) * 10000.0
r = MVAR * math.pow(scl, 2)
var float xh = na
var float p = na
xh := na(xh) ? close : nz(xh[1], close)
p  := na(p) ? 1.0 : nz(p[1], 1.0) + q
k = p / (p + r)
xh := xh + k * (close - xh)
p  := (1.0 - k) * p
atr = ta.atr(14)
score = -squash(atr > 1e-12 ? (close - xh) / atr : 0.0, 1.5)
""", overlay=True)

_reg("Lo-MacKinlay Variance Ratio", """
v1 = ta.variance(lr(), W)
vq = ta.variance(math.sum(lr(), Q), W)
vratio = v1 > 1e-16 ? vq / (Q * v1) : 1.0
z = squash(zscore(close, 20), 1.5)
trending = math.max(-0.5, math.min(0.5, vratio - 1.0)) * 2.0
score = z * math.max(0.0, math.min(1.0, trending)) - z * math.max(0.0, math.min(1.0, -trending))
""")

_reg("Hurst Exponent Regime Switch", """
// Rescaled-range Hurst over the last W log returns
rsHurst(int len) =>
    m = ta.sma(lr(), len)
    float cum = 0.0
    float mx = -1e18
    float mn = 1e18
    for i = 0 to len - 1
        cum := cum + (nz(lr()[i]) - m)
        mx := math.max(mx, cum)
        mn := math.min(mn, cum)
    s = ta.stdev(lr(), len, false)
    (mx - mn) > 1e-12 and s > 1e-12 ? math.log((mx - mn) / s) / math.log(len) : 0.5
h = rsHurst(W)
z = squash(zscore(close, 20), 1.5)
tilt = math.max(-1.0, math.min(1.0, (h - 0.5) * 4.0))
score = z * tilt
""")

_reg("Two-State Gaussian Regime Filter", """
vs = ta.stdev(lr(), SHORT, false)
vl = ta.stdev(lr(), LONG, false)
ratio = vl > 1e-12 ? vs / vl : 1.0
z = squash(zscore(close, 20), 1.5)
calm = ratio < 0.9 ? 1.0 : 0.0
stressed = ratio > 1.4 ? 1.0 : 0.0
score = -z * calm + squash(zscore(close, 20), 2.5) * stressed
""")

_reg("ADF Stationarity-Gated Reversion", """
lag = close[1]
delta = close - lag
cov = rollCov(delta, lag, W)
vr = ta.variance(lag, W)
gamma = vr > 1e-12 ? cov / vr : 0.0
rsd = ta.stdev(delta, W, false)
se = vr > 1e-12 ? rsd / (math.sqrt(vr) * math.sqrt(W)) : 1e9
tstat = se > 1e-14 ? gamma / se : 0.0
stationary = tstat < CRIT ? 1.0 : 0.0
score = -squash(zscore(close, 20), 1.5) * stationary
""")

_reg("Return Autocorrelation Sign", """
r = ta.change(close) / close[1]
ac = ta.correlation(r, r[1], W)
last = squash(zscore(r, 20), 1.5)
score = last * math.max(-1.0, math.min(1.0, ac * 4.0))
""")

_reg("Bayesian Posterior Fair Value", """
pm = ta.sma(close, PW)
pv = ta.variance(close, PW)
om = ta.sma(close, OW)
ov = ta.variance(close, OW)
pp = pv > 1e-12 ? 1.0 / pv : 0.0
po = ov > 1e-12 ? 1.0 / ov : 0.0
post = (pp + po) > 1e-18 ? (pm * pp + om * po) / (pp + po) : close
dev = pv > 1e-12 ? (close - post) / math.sqrt(pv) : 0.0
score = -squash(dev, 1.5)
""")

_reg("CUSUM Structural Break Filter", """
sd = ta.stdev(lr(), VW, false)
var float sp = 0.0
var float sn = 0.0
var float ev = 0.0
lim = THRESH * sd
sp := math.max(0.0, sp + nz(lr()))
sn := math.min(0.0, sn + nz(lr()))
ev := 0.0
if lim > 0 and sp > lim
    ev := 1.0
    sp := 0.0
else if lim > 0 and sn < -lim
    ev := -1.0
    sn := 0.0
score = persist(ev, 5)
""")

_reg("Copula Tail Dependence", """
u = prank(ta.change(close) / close[1], W)
v = prank((close - close[10]) / close[10], W)
score = squash((v - u) * 2.0, 0.7)
""", exact=False, note="Percent-rank convention differs marginally from pandas rank(pct=True).")

_reg("Financial Turbulence Index", """
mu = ta.sma(lr(), W)
sd = ta.stdev(lr(), W, false)
d2 = sd > 1e-12 ? math.pow((lr() - mu) / sd, 2) : 0.0
turb = prank(d2, W)
score = -squash(zscore(close, 20), 1.5) * math.max(0.0, math.min(1.0, 1.0 - turb))
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Volatility-Conditional Spread Trade", """
calm = math.max(0.0, math.min(1.0, 1.0 - volRegime(RANKW)))
score = -squash(zscore(close, W), 1.5) * calm
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Fractionally Differentiated Price", """
// Binomial weights for the fractional difference operator, order d
fracDiff(float d, int width) =>
    float acc = 0.0
    float w = 1.0
    for k = 0 to width - 1
        acc := acc + w * nz(math.log(close)[k])
        w := -w * (d - k) / (k + 1)
    acc
fd = fracDiff(DVAL, WIDTH)
score = -squash(zscore(fd, 60), 1.5)
""")

_reg("Shape-Matched Reversal Template", """
// Correlation of the normalised recent path against a V-shaped template
vCorr(int w) =>
    float m = 0.0
    for i = 0 to w - 1
        m := m + nz(close[i])
    m := m / w
    float sd = 0.0
    for i = 0 to w - 1
        sd := sd + math.pow(nz(close[i]) - m, 2)
    sd := math.sqrt(sd / w)
    if sd < 1e-12
        0.0
    else
        // template: descends over the first half, ascends over the second
        float tm = 0.0
        float dot = 0.0
        float tsd = 0.0
        for i = 0 to w - 1
            int pos = w - 1 - i
            float t = pos < w / 2 ? 1.0 - 2.0 * pos / (w / 2.0 - 1.0) : -1.0 + 2.0 * (pos - w / 2.0) / (w - w / 2.0 - 1.0)
            tm := tm + t
        tm := tm / w
        for i = 0 to w - 1
            int pos = w - 1 - i
            float t = pos < w / 2 ? 1.0 - 2.0 * pos / (w / 2.0 - 1.0) : -1.0 + 2.0 * (pos - w / 2.0) / (w - w / 2.0 - 1.0)
            tsd := tsd + math.pow(t - tm, 2)
        tsd := math.sqrt(tsd / w)
        for i = 0 to w - 1
            int pos = w - 1 - i
            float t = pos < w / 2 ? 1.0 - 2.0 * pos / (w / 2.0 - 1.0) : -1.0 + 2.0 * (pos - w / 2.0) / (w - w / 2.0 - 1.0)
            dot := dot + ((nz(close[i]) - m) / sd) * ((t - tm) / (tsd > 1e-12 ? tsd : 1.0))
        dot / w
score = squash(vCorr(W) * 2.0, 0.8)
""", exact=False, note="Template is rebuilt inline each bar; the Python precomputes it once. Same shape, same correlation.")

# ── Microstructure ────────────────────────────────────────────────────────────

_reg("Kyle's Lambda (Price Impact)", """
sv = math.sign(ta.change(close)) * volume
dp = ta.change(close)
cov = rollCov(dp, sv, W)
vr = ta.variance(sv, W)
lam = vr > 1e-12 ? cov / vr : 0.0
score = -squash(zscore(lam, 120), 1.5) * math.sign(lr())
""")

_reg("Corwin-Schultz High-Low Spread", """
hl = math.pow(math.log(high / low), 2)
beta = hl + hl[1]
h2 = math.max(high, high[1])
l2 = math.min(low, low[1])
gamma = math.pow(math.log(h2 / l2), 2)
k = 3.0 - 2.0 * math.sqrt(2.0)
alpha = (math.sqrt(2.0 * beta) - math.sqrt(beta)) / k - math.sqrt(gamma / k)
spread = math.max(0.0, 2.0 * (math.exp(alpha) - 1.0) / (1.0 + math.exp(alpha)))
score = -squash(zscore(spread, 120), 1.5)
""")

_reg("VPIN Order Flow Toxicity", """
buy = close > open ? volume : 0.0
sell = close < open ? volume : 0.0
tot = math.sum(buy + sell, W)
imb = tot > 0 ? math.sum(math.abs(buy - sell), W) / tot : 0.0
score = -squash(zscore(imb, 120), 1.5)
""")

_reg("Glosten-Milgrom Adverse Selection", """
d = math.sign(ta.change(close))
pers = ta.sma(d, W)
conf = zscore(volume, 20) > 0 ? 1.0 : 0.0
score = squash(pers * 2.0, 0.6) * conf
""")

_reg("Almgren-Chriss Temporary Impact", """
adv = ta.sma(volume, W)
part = adv > 0 ? volume / adv : 1.0
natr = ta.atr(14) / close
expd = math.sqrt(math.max(0.0, part)) * natr
act = math.abs(ta.change(close) / close[1])
exc = expd > 1e-9 ? (act - expd) / expd : 0.0
score = -math.sign(ta.change(close)) * math.max(0.0, math.min(1.0, squash(exc, 1.0)))
""")

_reg("Avellaneda-Stoikov Reservation Price", """
mid = (high + low) / 2.0
vr = ta.variance(lr(), W)
inv = zscore(close - ta.sma(mid, W), W)
skew = -inv * GAMMA * vr * 10000.0
score = squash(skew, 0.5) - squash(inv, 2.0) * 0.5
""")

_reg("Hawkes Self-Exciting Intensity", """
big = ta.tr(true) > ta.atr(14) * THRESH ? 1.0 : 0.0
intensity = ta.ema(big, math.round(2.0 / (1.0 - DECAY) - 1.0))
score = -math.sign(lr()) * math.abs(squash(zscore(intensity, 60), 1.5))
""", exact=False, note="Exponential decay expressed as an EMA span of 2/(1-decay)-1.")

_reg("Bid-Ask Bounce Reversal", """
r = ta.change(close) / close[1]
ac = ta.correlation(r, r[1], W)
regime = math.max(0.0, math.min(1.0, -ac))
score = -squash(zscore(r, 20), 1.5) * regime
""")

_reg("Volume Clock Information Arrival", """
vt = math.sum(volume, W)
mv = (close - close[W]) / close[W]
eff = vt > 0 ? math.abs(mv) / math.sqrt(vt) : 0.0
score = -math.sign(mv) * math.max(0.0, math.min(1.0, squash(zscore(eff, 120), 1.5)))
""")

_reg("Volume Concentration (Iceberg Detection)", """
rk = prank(volume, W)
stealth = (rk > 0.4 and rk < 0.8) ? 1.0 : 0.0
d = math.sign(ta.change(close))
score = squash(ta.sma(stealth * d, W) * 3.0, 0.5)
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Realized Spread Price Reversal", """
imm = ta.change(close) / close[1]
rev = -ta.sma(imm, H)
score = squash(zscore(rev, 60), 1.5)
""")

_reg("Microstructure Noise Ratio", """
fv = math.sum(math.pow(lr(), 2), FAST)
sv = math.sum(math.pow(math.log(close / close[FAST]), 2), math.max(2, SLOW / FAST))
noise = fv > 1e-14 ? (fv - sv) / fv : 0.0
score = -math.sign(lr()) * squash(math.max(0.0, math.min(1.0, noise)), 0.4)
""")

_reg("Liquidity Provision Premium", """
stress = volRegime(RANKW)
rev = -squash(zscore(ta.change(close) / close[1], W), 1.5)
score = rev * math.max(0.0, math.min(1.0, stress))
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Closing Auction Pressure", """
rng = high - low
cp = rng > 1e-12 ? (close - low) / rng : 0.5
heavy = zscore(volume, W) > 1.0 ? 1.0 : 0.0
score = -band_score(cp, 0.0, 1.0) * heavy
""")

# ── Regime & Risk ─────────────────────────────────────────────────────────────

_reg("Volatility Regime Switch", """
vr = volRegime(RANKW)
z = squash(zscore(close, 20), 1.5)
trend = math.sign(ta.ema(close, 20) - ta.ema(close, 50))
score = trend * math.max(0.0, math.min(1.0, 1.0 - vr)) - z * math.max(0.0, math.min(1.0, vr))
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Bull-Bear Market Classifier", """
dd = ddFromPeak()
trough = close / ta.lowest(close, 252) - 1.0
var float st = 0.0
st := dd <= BEAR ? -1.0 : trough >= BULL ? 1.0 : st
score = st * 0.7
""")

_reg("Maximum Drawdown Guard", """
dd = ddFromPeak()
cap = math.max(0.0, math.min(1.0, 1.0 + dd / LIMIT))
trend = math.sign(ta.ema(close, 20) - ta.ema(close, 50))
score = trend * cap
""")

_reg("Cornish-Fisher Modified VaR", """
mu = ta.sma(lr(), W)
sd = ta.stdev(lr(), W, false)
s = rollSkew(lr(), W)
k = rollKurt(lr(), W)
z = 1.645
zcf = z + (z * z - 1.0) * s / 6.0 + (z * z * z - 3.0 * z) * k / 24.0 -
      (2.0 * z * z * z - 5.0 * z) * s * s / 36.0
v = mu - zcf * sd
trend = math.sign(ta.ema(close, 50) - ta.ema(close, 200))
score = trend * math.max(0.0, math.min(1.0, 1.0 + squash(zscore(v, W), 1.5)))
""")

_reg("Extreme Value Theory Tail Estimate", """
thr = ta.percentile_linear_interpolation(lr(), W, 5)
exceed = ta.sma(lr() < thr ? 1.0 : 0.0, W)
fatten = math.max(-1.0, math.min(2.0, (exceed - TF) / TF))
trend = math.sign(ta.ema(close, 50) - ta.ema(close, 200))
score = trend * (1.0 - math.max(0.0, math.min(1.0, fatten)))
""")

_reg("Ulcer Index Downside Risk", """
dd = ddFromPeak() * 100.0
ulcer = math.sqrt(ta.sma(math.pow(dd, 2), W))
score = -squash(zscore(ulcer, 120), 1.5)
""")

_reg("Sortino Downside Deviation", """
mu = ta.sma(lr(), W)
ds = ta.stdev(lr() < 0 ? lr() : 0.0, W, false)
score = squash(ds > 1e-12 ? mu / ds * math.sqrt(BPY) : 0.0, 1.5)
""")

_reg("Regime-Conditional Leverage", """
calm = math.max(0.0, math.min(1.0, 1.0 - volRegime(RANKW)))
quality = math.max(0.0, math.min(1.0, trendStrength()))
healthy = math.max(0.0, math.min(1.0, 1.0 + ddFromPeak() / 0.25))
exposure = math.pow(calm * quality * healthy, 1.0 / 3.0)
score = math.sign(ta.ema(close, 50) - ta.ema(close, 200)) * exposure
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Trend Fragility Index", """
accel = (close - close[10]) / close[10] - ((close - close[40]) / close[40]) / 4.0
volFade = -zscore(volume, 40)
fragile = math.abs(squash(zscore(accel, 60), 1.5)) * math.max(0.0, math.min(2.0, 1.0 + volFade)) / 2.0
score = -math.sign(accel) * math.max(0.0, math.min(1.0, fragile))
""")

_reg("Composite Liquidity Stress", """
vs = volRegime(RANKW)
rs = prank(ta.atr(14) / close, 120)
vd = 1.0 - prank(volume, 120)
stress = (vs + rs + vd) / 3.0
trend = math.sign(ta.ema(close, 20) - ta.ema(close, 50))
score = trend * math.max(0.0, math.min(1.0, 1.0 - stress))
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Momentum Crash Risk", """
mom = squash(zscore((close - close[126]) / close[126], 252), 1.5)
bear = ddFromPeak() < -0.20 ? 1.0 : 0.0
volRising = rvol(20) > rvol(60) ? 1.0 : 0.0
score = mom * (1.0 - bear * volRising)
""")

_reg("Skewness Risk Premium", """
score = -squash(zscore(rollSkew(lr(), W), 250), 1.5)
""")

_reg("Drawdown Recovery Momentum", """
dd = ddFromPeak()
trough = ta.lowest(dd, W)
rec = trough < -0.01 ? math.max(0.0, math.min(1.0, (dd - trough) / -trough)) : 0.0
deep = math.max(0.0, math.min(1.0, -trough / 0.15))
score = squash(rec * deep * 2.0, 0.8)
""")

_reg("Volatility Budget Allocation", """
v = rvol(W)
size = math.max(0.0, math.min(1.0, v > 1e-6 ? BUDGET / v : 0.0))
score = math.sign(ta.ema(close, 20) - ta.ema(close, 50)) * size
""")

# ── Factor & Smart Beta ───────────────────────────────────────────────────────

_reg("Low Volatility Anomaly", """
score = -band_score(prank(rvol(VW), RANKW), 0.0, 1.0)
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Technical Value (5-Year Mean Reversion)", """
lm = ta.sma(close, W)
score = -squash(math.log(close / lm), 0.25)
""")

_reg("Return Stability (Technical Quality)", """
hit = ta.sma(lr() > 0 ? 1.0 : 0.0, W)
volStab = 1.0 - prank(ta.stdev(rvol(20), W, false), W)
dd = math.max(0.0, math.min(1.0, 1.0 + ta.lowest(ddFromPeak(), W)))
score = band_score((hit + volStab + dd) / 3.0, 0.35, 0.65)
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Defensive Equity Tilt", """
lowVol = 1.0 - volRegime(252)
shallow = math.max(0.0, math.min(1.0, 1.0 + ta.lowest(ddFromPeak(), 120)))
smooth = 1.0 - prank(ta.sma(math.abs(lr()), 20), 252)
score = band_score((lowVol + shallow + smooth) / 3.0, 0.35, 0.7)
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Kelly Criterion Optimal Fraction", """
mu = ta.sma(lr(), W)
v = ta.variance(lr(), W)
kelly = v > 1e-14 ? (mu / v) * FRAC : 0.0
score = squash(kelly, 20.0)
""")

_reg("Maximum Sharpe Tilt", """
mu = ta.sma(lr(), W) * BPY
sd = ta.stdev(lr(), W, false) * math.sqrt(BPY)
score = squash(sd > 1e-9 ? mu / sd : 0.0, 1.0)
""")

_reg("Risk Parity Exposure", """
v = rvol(W)
w = math.max(0.0, math.min(1.5, v > 1e-6 ? TGT / v : 0.0))
score = math.max(-1.0, math.min(1.0, math.sign(ta.ema(close, 50) - ta.ema(close, 200)) * w / 1.5))
""")

_reg("Black-Litterman Blended View", """
prior = squash(ta.sma(lr(), 252) * 252.0, 0.1)
view = squash(zscore((close - close[W]) / close[W], 120), 1.5)
conf = math.max(0.0, math.min(1.0, effRatio(W))) * VC
score = prior * (1.0 - conf) + view * conf
""")

_reg("Large Gap Continuation Drift", """
gap = (open - close[1]) / close[1]
z = zscore(gap, 120)
shock = math.abs(z) > THRESH ? math.sign(z) : 0.0
score = persist(shock, HOLD) * 0.7
""")

_reg("Liquidity Risk Factor", """
sv = math.sign(ta.change(close)) * volume
gamma = ta.correlation(ta.change(close) / close[1], sv[1], W)
score = -squash(zscore(gamma, W), 1.5)
""", note="The engine correlates next-bar return with signed volume then lags the result; lagging the volume by one bar is the identical causal quantity.")

_reg("Momentum-Reversal Horizon Rotation", """
rev = -squash(zscore((close - close[5]) / close[5], 60), 1.5)
mom = squash(zscore((close - close[63]) / close[63], 120), 1.5)
revP = ta.sma(rev[1] * lr(), EW)
momP = ta.sma(mom[1] * lr(), EW)
score = revP > momP ? rev : mom
""")

_reg("Factor Momentum Timing", """
mom = squash(zscore((close - close[126]) / close[126], 252), 1.5)
val = -squash(math.log(close / ta.sma(close, 504)), 0.25)
mp = math.max(0.0, ta.sma(mom[1] * lr(), W))
vp = math.max(0.0, ta.sma(val[1] * lr(), W))
tot = mp + vp
score = tot > 1e-12 ? math.max(-1.0, math.min(1.0, (mom * mp + val * vp) / tot)) : 0.0
""")

# ── Macro & Allocation ────────────────────────────────────────────────────────

_reg("Faber 10-Month Timing Model", """
ma = ta.sma(close, W)
above = close > ma ? 1.0 : 0.0
margin = squash(math.abs(ma) > 1e-12 ? (close - ma) / math.abs(ma) : 0.0, 0.05)
score = above * math.max(0.0, math.min(1.0, margin)) -
        (1.0 - above) * math.max(0.0, math.min(1.0, math.abs(margin)))
""", overlay=True, plots="""
plot(ta.sma(close, W), "SMA", color.new(color.orange, 0), 2)
""")

_reg("Absolute Momentum Filter", """
score = squash((close - close[LB]) / close[LB], 0.15)
""")

_reg("Volatility Target Overlay", """
rz = rvol(W)
lev = math.max(0.0, math.min(MAXL, rz > 1e-6 ? TGT / rz : 0.0))
trend = math.sign(ta.sma(close, 200) - ta.sma(close, 200)[1])
score = math.max(-1.0, math.min(1.0, trend * lev / MAXL))
""")

_reg("Trend + Carry Composite", """
vol = ta.stdev(lr(), 60, false)
trend = squash(vol > 1e-9 ? math.log(close / close[252]) / (vol * math.sqrt(252)) : 0.0, 1.0)
carry = squash(vol > 1e-9 ? ta.sma(lr(), 63) / vol : 0.0, 0.2)
score = math.max(-1.0, math.min(1.0, 0.6 * trend + 0.4 * carry))
""")

_reg("Drawdown-Scaled Allocation", """
var float pk = na
pk := na(pk) ? close : math.max(pk, close)
cushion = math.max(0.0, (close - pk * FLOOR) / pk)
exposure = math.max(0.0, math.min(1.0, cushion * MULT))
score = math.sign(ta.sma(close, 50) - ta.sma(close, 200)) * exposure
""")

_reg("Two-Regime Allocation Switch", """
stressed = (volRegime(RANKW) > 0.7 or ddFromPeak() < -0.15) ? 1.0 : 0.0
riskOn = math.sign(ta.sma(close, 50) - ta.sma(close, 200))
riskOff = -squash(zscore(close, 20), 1.5) * 0.5
score = riskOn * (1.0 - stressed) + riskOff * stressed
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Macro Seasonality Overlay", """
seasonal = (month >= 11 or month <= 4) ? 0.5 : -0.2
trend = math.sign(ta.sma(close, 50) - ta.sma(close, 200))
score = math.sign(seasonal) == trend ? seasonal : seasonal * 0.25
""")

# ── Seasonality ───────────────────────────────────────────────────────────────

_reg("Day-of-Week Effect", """
var float[] dSum = array.new_float(7, 0.0)
var int[]   dCnt = array.new_int(7, 0)
d = dayofweek - 1
prior = array.get(dCnt, d) >= 10 ? array.get(dSum, d) / array.get(dCnt, d) : 0.0
array.set(dSum, d, array.get(dSum, d) + nz(lr()))
array.set(dCnt, d, array.get(dCnt, d) + 1)
vol = expStdev(lr(), 20)
score = squash(vol > 1e-12 ? prior / vol : 0.0, 0.4)
""", note="Per-weekday edge accumulates expanding-window, matching the engine's groupby-transform.")

_reg("Month-of-Year Seasonality", """
var float[] mSum = array.new_float(13, 0.0)
var int[]   mCnt = array.new_int(13, 0)
prior = array.get(mCnt, month) >= 6 ? array.get(mSum, month) / array.get(mCnt, month) : 0.0
array.set(mSum, month, array.get(mSum, month) + nz(lr()))
array.set(mCnt, month, array.get(mCnt, month) + 1)
vol = expStdev(lr(), 30)
score = squash(vol > 1e-12 ? prior / vol : 0.0, 0.4)
""")

_reg("Week-of-Month Pattern", """
var float[] wSum = array.new_float(6, 0.0)
var int[]   wCnt = array.new_int(6, 0)
w = math.floor((dayofmonth - 1) / 7)
prior = array.get(wCnt, w) >= 8 ? array.get(wSum, w) / array.get(wCnt, w) : 0.0
array.set(wSum, w, array.get(wSum, w) + nz(lr()))
array.set(wCnt, w, array.get(wCnt, w) + 1)
vol = expStdev(lr(), 30)
score = squash(vol > 1e-12 ? prior / vol : 0.0, 0.4)
""")

_reg("Time-of-Day Momentum", """
var float[] tSum = array.new_float(1440, 0.0)
var int[]   tCnt = array.new_int(1440, 0)
slot = hour * 60 + minute
prior = array.get(tCnt, slot) >= 5 ? array.get(tSum, slot) / array.get(tCnt, slot) : 0.0
array.set(tSum, slot, array.get(tSum, slot) + nz(lr()))
array.set(tCnt, slot, array.get(tCnt, slot) + 1)
vol = ta.stdev(lr(), 60, false)
score = squash(vol > 1e-12 ? prior / vol : 0.0, 0.5)
""", exact=False, note="Engine uses a rolling 20-observation mean per slot; Pine accumulates expanding per slot.")

_reg("January Effect", """
score = (month == 1 and dayofmonth <= 15) ? 0.5 : (month == 12 and dayofmonth >= 20) ? 0.3 : 0.0
""")

_reg("Quarter-End Rebalancing Flow", """
dim = dayofmonth(timestamp(year, month + 1, 1, 0, 0) - 86400000)
qEnd = (month == 3 or month == 6 or month == 9 or month == 12) and (dim - dayofmonth) <= 3
score = -squash(zscore((close - close[63]) / close[63], 120), 1.5) * (qEnd ? 1.0 : 0.0)
""")

_reg("Pre-Holiday Effect", """
gapAhead = nz(time[0] - time[1])
typical = ta.median(gapAhead, 100)
score = (gapAhead > typical * 2.5) ? 0.55 : 0.0
""", exact=False, note="Engine looks one bar ahead at the calendar gap; Pine can only see the gap already opened, so this fires on the bar after a closure rather than before it.")

_reg("Overnight vs Intraday Return Split", """
onr = math.log(open / close[1])
idr = math.log(close / open)
oe = ta.sma(onr, 60)
ie = ta.sma(idr, 60)
vol = ta.stdev(lr(), 60, false)
score = squash(vol > 1e-12 ? (oe - ie) / vol : 0.0, 0.5)
""")

_reg("Intraday U-Shape Volume Pattern", """
var int firstH = na
var int lastH = na
firstH := na(firstH) ? hour : math.min(firstH, hour)
lastH  := na(lastH) ? hour : math.max(lastH, hour)
midday = (hour != firstH and hour != lastH) ? 1.0 : 0.0
z = squash(zscore(ta.change(close) / close[1], 20), 1.5)
score = -z * midday + squash(zscore(ta.change(close) / close[1], 20), 2.0) * (1.0 - midday) * 0.5
""", exact=False, note="Session bounds are learned from observed hours rather than an exchange calendar.")

_reg("Seasonal Volatility Pattern", """
var float[] vSum = array.new_float(13, 0.0)
var int[]   vCnt = array.new_int(13, 0)
rz = rvol(20)
prior = array.get(vCnt, month) >= 6 ? array.get(vSum, month) / array.get(vCnt, month) : rz
array.set(vSum, month, array.get(vSum, month) + nz(rz))
array.set(vCnt, month, array.get(vCnt, month) + 1)
var float ovN = 0.0
var float ovS = 0.0
ovN := ovN + 1.0
ovS := ovS + nz(rz)
overall = ovN >= 60 ? ovS / ovN : na
elevated = overall > 1e-9 ? prior / overall : 1.0
trend = math.sign(ta.ema(close, 50) - ta.ema(close, 200))
score = trend * math.max(0.0, math.min(1.0, 2.0 - elevated))
""")

# ── Options Income / Derivatives (regime-favourability proxies) ───────────────

_reg("Realized Volatility Cone", """
avg = (prank(rvol(10), RANKW) + prank(rvol(20), RANKW) + prank(rvol(60), RANKW)) / 3.0
score = -band_score(avg, 0.0, 1.0) * math.sign(zscore(close, 20))
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Straddle-Implied Move vs Realized", """
expd = ta.stdev(lr(), 60, false) * math.sqrt(H)
act = math.abs((close - close[H]) / close[H])
ratio = expd > 1e-9 ? act / expd : 1.0
score = -math.sign((close - close[H]) / close[H]) * math.max(0.0, math.min(1.0, squash(ratio - 1.0, 0.6)))
""")

_reg("Volatility Risk Premium Proxy", """
realized = rvol(SHORT)
implied = rvol(LONG) * PREM
score = squash(zscore(implied - realized, 120), 1.5)
""")

_reg("Volatility Curve Slope Proxy", """
n = rvol(NEAR)
f = rvol(FAR)
basis = f > 1e-9 ? (n - f) / f : 0.0
score = -squash(basis, 0.25)
""")

_reg("Gamma Scalping Profitability", """
pv = math.sum(math.abs(lr()), W)
nm = math.abs(math.log(close / close[W]))
chop = pv > 1e-12 ? (pv - nm) / pv : 0.0
score = squash(zscore(chop, 120), 1.5)
""")

_reg("Round-Number Pin Proxy", """
step = ta.sma(close, 60) * GRAN
nearest = step > 1e-9 ? math.round(close / step) * step : close
atr = ta.atr(14)
score = squash(atr > 1e-12 ? (nearest - close) / atr : 0.0, 0.8) * 0.6
""", overlay=True)

_reg("Covered Call Overlay", """
volRich = volRegime(RANKW)
flat = 1.0 - math.max(0.0, math.min(1.0, trendStrength()))
attractive = math.max(0.0, math.min(1.0, volRich * flat))
score = (0.3 + 0.5 * attractive) * math.max(0.0, math.sign(ta.sma(close, 50) - ta.sma(close, 200)))
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Cash-Secured Put", """
spike = volRegime(RANKW)
oversold = math.max(0.0, -math.min(0.0, band_score(ta.rsi(close, 14), 0.0, 100.0)))
score = math.max(0.0, math.min(1.0, spike * oversold))
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Options Wheel", """
choppy = 1.0 - math.max(0.0, math.min(1.0, trendStrength()))
volOk = math.max(0.0, math.min(1.0, volRegime(RANKW)))
noCrash = math.max(0.0, math.min(1.0, 1.0 + ddFromPeak() / 0.25))
score = math.max(0.0, math.min(1.0, choppy * volOk * noCrash)) * 0.8
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Systematic Short Strangle", """
volRich = volRegime(RANKW)
ranging = 1.0 - math.max(0.0, math.min(1.0, trendStrength()))
tailSafe = math.max(0.0, math.min(1.0, 1.0 - math.max(0.0, math.min(1.0, rollKurt(lr(), 60) / 6.0))))
score = math.max(0.0, math.min(1.0, volRich * ranging * tailSafe)) * 0.7
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Systematic Iron Condor", """
ranging = 1.0 - math.max(0.0, math.min(1.0, trendStrength()))
volRich = volRegime(RANKW)
stable = 1.0 - prank(ta.atr(14) / close, 120)
score = math.max(0.0, math.min(1.0, ranging * volRich * stable)) * 0.7
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Protective Put Overlay", """
volCheap = 1.0 - volRegime(RANKW)
tailRisk = math.max(0.0, math.min(1.0, rollKurt(lr(), 60) / 6.0))
skewRisk = math.max(0.0, math.min(1.0, -rollSkew(lr(), 60) / 2.0))
hedgeValue = math.max(0.0, math.min(1.0, volCheap * (tailRisk + skewRisk) / 2.0))
score = math.max(0.0, math.sign(ta.sma(close, 50) - ta.sma(close, 200))) * (1.0 - hedgeValue * 0.5)
""", exact=False, note="Percent-rank convention; see prank().")

_reg("VIX Roll Short (Contango Harvest)", """
n = rvol(10)
f = rvol(60)
basis = f > 1e-9 ? (f - n) / f : 0.0
score = math.max(-1.0, math.min(1.0, squash(basis, 0.25)))
""")

# ── Crypto / Sentiment / Commodity / Rates ────────────────────────────────────

_reg("Crypto Time-Series Momentum", """
r = math.log(close / close[LB])
vol = ta.stdev(lr(), 60, false) * math.sqrt(LB)
score = squash(vol > 1e-9 ? r / vol : 0.0, 1.0)
""")

_reg("Crypto Volatility Regime", """
rank = volRegime(RANKW)
trend = math.sign(ta.ema(close, 20) - ta.ema(close, 50))
score = trend * math.max(0.0, math.min(1.0, 1.0 - rank))
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Liquidation Cascade Reversal", """
violent = ta.tr(true) > ta.atr(14) * RMULT
heavy = zscore(volume, 20) > VOLZ
rng = high - low
lw = rng > 1e-12 ? (close - low) / rng : 0.5
uw = rng > 1e-12 ? (high - close) / rng : 0.5
cd = (violent and heavy and lw > 0.6) ? 1.0 : 0.0
cu = (violent and heavy and uw > 0.6) ? 1.0 : 0.0
score = persist(cd - cu, HOLD)
""", overlay=True)

_reg("Crypto Weekend Liquidity Effect", """
weekend = (dayofweek == dayofweek.saturday or dayofweek == dayofweek.sunday) ? 1.0 : 0.0
score = -squash(zscore(ta.change(close) / close[1], 20), 1.5) * weekend
""")

_reg("Volume Profile Value Area", """
pv = math.sum(hlc3 * volume, W)
vv = math.sum(volume, W)
poc = vv > 1e-12 ? pv / vv : ta.sma(hlc3, W)
atr = ta.atr(14)
score = -squash(atr > 1e-12 ? (close - poc) / atr : 0.0, 1.5)
""", overlay=True, plots="""
plot(math.sum(volume, W) > 1e-12 ? math.sum(hlc3 * volume, W) / math.sum(volume, W) : na,
     "Point of control", color.new(color.yellow, 0), 2)
""")

_reg("Capitulation Volume Climax", """
rng = high - low
cp = rng > 1e-12 ? (close - low) / rng : 0.5
climax = zscore(volume, 20) > VOLZ
wide = ta.tr(true) > ta.atr(14) * 1.8
buyC = (climax and wide and close < open and cp > 0.55) ? 1.0 : 0.0
sellC = (climax and wide and close > open and cp < 0.45) ? 1.0 : 0.0
score = persist(buyC - sellC, HOLD)
""", overlay=True)

_reg("Volatility Fear Gauge", """
fear = volRegime(252)
falling = (close - close[5]) / close[5] < 0 ? 1.0 : 0.0
score = math.max(-1.0, math.min(1.0, fear * falling * 2.0 - fear * (1.0 - falling) * 0.5))
""", exact=False, note="Percent-rank convention; see prank().")

_reg("Price-Based Fear & Greed Composite", """
momentum = prank(close / ta.sma(close, 125) - 1.0, 252)
strength = prank((close - close[20]) / close[20], 252)
volInv = 1.0 - volRegime(252)
ddHealth = math.max(0.0, math.min(1.0, 1.0 + ddFromPeak() / 0.20))
greed = (momentum + strength + volInv + ddHealth) / 4.0
score = -math.max(-1.0, math.min(1.0, (greed - 0.5) * 2.0))
""", exact=False, note="Percent-rank convention; see prank(). Partial reconstruction — options and credit components are absent, as in the Python.")

_reg("Commodity Time-Series Momentum", """
vol = ta.stdev(lr(), 60, false) * math.sqrt(LB)
score = squash(vol > 1e-9 ? math.log(close / close[LB]) / vol : 0.0, 1.0)
""")

_reg("Commodity Seasonal Pattern", """
var float[] cSum = array.new_float(13, 0.0)
var int[]   cCnt = array.new_int(13, 0)
prior = array.get(cCnt, month) >= 8 ? array.get(cSum, month) / array.get(cCnt, month) : 0.0
array.set(cSum, month, array.get(cSum, month) + nz(lr()))
array.set(cCnt, month, array.get(cCnt, month) + 1)
vol = expStdev(lr(), 30)
score = squash(vol > 1e-12 ? prior / vol : 0.0, 0.4)
""")

_reg("Duration Timing (Price-Based)", """
slow = ta.sma(close, 200)
trend = squash(math.abs(slow) > 1e-12 ? (ta.sma(close, 50) - slow) / math.abs(slow) : 0.0, 0.02)
calm = math.max(0.0, math.min(1.0, 1.0 - volRegime(252)))
score = trend * calm
""", exact=False, note="Percent-rank convention; see prank().")


_PARAM_MAP.update({
    "Ornstein-Uhlenbeck Process Fit": {"W": "window"},
    "Kalman Filter State Estimate": {"PVAR": "process_var", "MVAR": "measure_var"},
    "Lo-MacKinlay Variance Ratio": {"Q": "q", "W": "window"},
    "Hurst Exponent Regime Switch": {"W": "window"},
    "Two-State Gaussian Regime Filter": {"SHORT": "short", "LONG": "long"},
    "ADF Stationarity-Gated Reversion": {"W": "window", "CRIT": "crit"},
    "Return Autocorrelation Sign": {"W": "window"},
    "Bayesian Posterior Fair Value": {"PW": "prior_window", "OW": "obs_window"},
    "CUSUM Structural Break Filter": {"THRESH": "threshold_sd", "VW": "vol_window"},
    "Copula Tail Dependence": {"W": "window"},
    "Financial Turbulence Index": {"W": "window"},
    "Volatility-Conditional Spread Trade": {"W": "window", "RANKW": "rank_window"},
    "Fractionally Differentiated Price": {"DVAL": "d", "WIDTH": "width"},
    "Shape-Matched Reversal Template": {"W": "window"},
    "Kyle's Lambda (Price Impact)": {"W": "window"},
    "Corwin-Schultz High-Low Spread": {},
    "VPIN Order Flow Toxicity": {"W": "window"},
    "Glosten-Milgrom Adverse Selection": {"W": "window"},
    "Almgren-Chriss Temporary Impact": {"W": "window"},
    "Avellaneda-Stoikov Reservation Price": {"W": "window", "GAMMA": "gamma"},
    "Hawkes Self-Exciting Intensity": {"DECAY": "decay", "THRESH": "threshold"},
    "Bid-Ask Bounce Reversal": {"W": "window"},
    "Volume Clock Information Arrival": {"W": "window"},
    "Volume Concentration (Iceberg Detection)": {"W": "window"},
    "Realized Spread Price Reversal": {"H": "horizon"},
    "Microstructure Noise Ratio": {"FAST": "fast", "SLOW": "slow"},
    "Liquidity Provision Premium": {"W": "window", "RANKW": "rank_window"},
    "Closing Auction Pressure": {"W": "window"},
    "Volatility Regime Switch": {"RANKW": "rank_window"},
    "Bull-Bear Market Classifier": {"BEAR": "bear_threshold", "BULL": "bull_threshold"},
    "Cornish-Fisher Modified VaR": {"W": "window"},
    "Extreme Value Theory Tail Estimate": {"W": "window", "TF": "tail_frac"},
    "Regime-Conditional Leverage": {"RANKW": "rank_window"},
    "Trend Fragility Index": {},
    "Composite Liquidity Stress": {"RANKW": "rank_window"},
    "Momentum Crash Risk": {},
    "Skewness Risk Premium": {"W": "window"},
    "Drawdown Recovery Momentum": {"W": "window"},
    "Volatility Budget Allocation": {"BUDGET": "budget", "W": "window"},
    "Low Volatility Anomaly": {"VW": "window", "RANKW": "rank_window"},
    "Technical Value (5-Year Mean Reversion)": {"W": "window"},
    "Return Stability (Technical Quality)": {"W": "window"},
    "Defensive Equity Tilt": {},
    "Kelly Criterion Optimal Fraction": {"W": "window", "FRAC": "fraction"},
    "Maximum Sharpe Tilt": {"W": "window"},
    "Risk Parity Exposure": {"W": "window", "TGT": "target"},
    "Black-Litterman Blended View": {"W": "window", "VC": "view_confidence"},
    "Large Gap Continuation Drift": {"THRESH": "threshold_sd", "HOLD": "hold"},
    "Liquidity Risk Factor": {"W": "window"},
    "Momentum-Reversal Horizon Rotation": {"EW": "eval_window"},
    "Factor Momentum Timing": {"W": "window"},
    "Faber 10-Month Timing Model": {"W": "window"},
    "Absolute Momentum Filter": {"LB": "lookback"},
    "Volatility Target Overlay": {"TGT": "target", "W": "window", "MAXL": "max_leverage"},
    "Trend + Carry Composite": {},
    "Drawdown-Scaled Allocation": {"FLOOR": "floor", "MULT": "multiplier"},
    "Two-Regime Allocation Switch": {"RANKW": "rank_window"},
    "Macro Seasonality Overlay": {},
    "Day-of-Week Effect": {},
    "Month-of-Year Seasonality": {},
    "Week-of-Month Pattern": {},
    "Time-of-Day Momentum": {},
    "January Effect": {},
    "Quarter-End Rebalancing Flow": {},
    "Pre-Holiday Effect": {},
    "Overnight vs Intraday Return Split": {},
    "Intraday U-Shape Volume Pattern": {},
    "Seasonal Volatility Pattern": {},
    "Realized Volatility Cone": {"RANKW": "rank_window"},
    "Straddle-Implied Move vs Realized": {"H": "horizon"},
    "Volatility Risk Premium Proxy": {"SHORT": "short", "LONG": "long", "PREM": "premium"},
    "Volatility Curve Slope Proxy": {"NEAR": "near", "FAR": "far"},
    "Gamma Scalping Profitability": {"W": "window"},
    "Round-Number Pin Proxy": {"GRAN": "granularity"},
    "Covered Call Overlay": {"RANKW": "rank_window"},
    "Cash-Secured Put": {"RANKW": "rank_window"},
    "Options Wheel": {"RANKW": "rank_window"},
    "Systematic Short Strangle": {"RANKW": "rank_window"},
    "Systematic Iron Condor": {"RANKW": "rank_window"},
    "Protective Put Overlay": {"RANKW": "rank_window"},
    "VIX Roll Short (Contango Harvest)": {},
    "Crypto Time-Series Momentum": {"LB": "lookback"},
    "Crypto Volatility Regime": {"RANKW": "rank_window"},
    "Liquidation Cascade Reversal": {"VOLZ": "vol_z", "RMULT": "range_mult", "HOLD": "hold"},
    "Crypto Weekend Liquidity Effect": {},
    "Volume Profile Value Area": {"W": "window"},
    "Capitulation Volume Climax": {"VOLZ": "vol_z", "HOLD": "hold"},
    "Volatility Fear Gauge": {},
    "Price-Based Fear & Greed Composite": {},
    "Commodity Time-Series Momentum": {"LB": "lookback"},
    "Commodity Seasonal Pattern": {},
    "Duration Timing (Price-Based)": {},
})
