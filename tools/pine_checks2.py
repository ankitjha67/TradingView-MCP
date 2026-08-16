"""
Independent re-implementations, part two: the stateful and recursive bodies.

These are the translations the first pass left unverified — recursive filters
(GARCH, Ehlers, Parabolic SAR, Supertrend), per-slot seasonal accumulators, and
regime composites. Same rule as ``pine_checks``: written from the Pine source
using ``pine_sim`` primitives, never by calling the Python model.

The seasonal models deserve a note. The Pine reads the per-slot mean **before**
folding the current bar into it, then updates the accumulator. That is an
expanding groupby mean shifted one observation within each group — not the same
as a plain expanding mean, and reproducing it faithfully is the whole point of
checking them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pine_sim import (
    atr, band_score, dd_from_peak, dmi, eff_ratio, ema, highest, lowest, lr,
    median, percentile_nearest_rank, percentrank, persist, roll_kurt, roll_skew,
    rsi, rsum, rvol, sma, squash, stdev, trend_strength, true_range, variance,
    zscore_skipna,
    vol_regime, wma, zscore,
)

C = "close"


def exp_stdev(src: pd.Series, min_n: int) -> pd.Series:
    """Pine expStdev(): since-inception population stdev via running sums."""
    v = src.fillna(0.0)
    n = src.notna().cumsum()
    s1 = v.cumsum()
    s2 = (v ** 2).cumsum()
    m = s1 / n.where(n > 0)
    var = (s2 / n.where(n > 0) - m ** 2).clip(lower=0)
    return np.sqrt(var).where(n >= min_n)


def exp_variance(src: pd.Series, min_n: int) -> pd.Series:
    """Pine expVariance(): since-inception population variance."""
    v = src.fillna(0.0)
    n = src.notna().cumsum()
    m = v.cumsum() / n.where(n > 0)
    return ((v ** 2).cumsum() / n.where(n > 0) - m ** 2).clip(lower=0).where(n >= min_n)


def _prior_group_mean(values: pd.Series, slot: pd.Series, min_count: int,
                      fallback: float | pd.Series = 0.0) -> pd.Series:
    """
    Per-slot mean of everything seen *before* the current bar.

    Mirrors the Pine accumulator: read, then update. A plain expanding mean would
    include the current observation and quietly differ.
    """
    v = values.fillna(0.0).to_numpy(dtype=float)
    s = slot.to_numpy()
    totals: dict = {}
    counts: dict = {}
    out = np.zeros(len(v))
    fb = (fallback.to_numpy(dtype=float) if isinstance(fallback, pd.Series)
          else np.full(len(v), float(fallback)))
    for i in range(len(v)):
        k = s[i]
        n = counts.get(k, 0)
        out[i] = totals[k] / n if n >= min_count else fb[i]
        totals[k] = totals.get(k, 0.0) + v[i]
        counts[k] = n + 1
    return pd.Series(out, index=values.index)


# ── Seasonality ───────────────────────────────────────────────────────────────

def day_of_week(df, p, bpy):
    slot = pd.Series(df.index.dayofweek, index=df.index)
    prior = _prior_group_mean(lr(df[C]), slot, 10)
    vol = exp_stdev(lr(df[C]), 20)
    return pd.Series(squash((prior / vol.where(vol > 1e-12)).fillna(0.0), 0.4), index=df.index)


def month_of_year(df, p, bpy):
    slot = pd.Series(df.index.month, index=df.index)
    prior = _prior_group_mean(lr(df[C]), slot, 6)
    vol = exp_stdev(lr(df[C]), 30)
    return pd.Series(squash((prior / vol.where(vol > 1e-12)).fillna(0.0), 0.4), index=df.index)


def week_of_month(df, p, bpy):
    slot = pd.Series((df.index.day - 1) // 7, index=df.index)
    prior = _prior_group_mean(lr(df[C]), slot, 8)
    vol = exp_stdev(lr(df[C]), 30)
    return pd.Series(squash((prior / vol.where(vol > 1e-12)).fillna(0.0), 0.4), index=df.index)


def time_of_day(df, p, bpy):
    slot = pd.Series(df.index.hour * 60 + df.index.minute, index=df.index)
    prior = _prior_group_mean(lr(df[C]), slot, 5)
    vol = stdev(lr(df[C]), 60)
    return pd.Series(squash((prior / vol.where(vol > 1e-12)).fillna(0.0), 0.5), index=df.index)


def commodity_seasonal(df, p, bpy):
    slot = pd.Series(df.index.month, index=df.index)
    prior = _prior_group_mean(lr(df[C]), slot, 8)
    vol = exp_stdev(lr(df[C]), 30)
    return pd.Series(squash((prior / vol.where(vol > 1e-12)).fillna(0.0), 0.4), index=df.index)


def seasonal_volatility(df, p, bpy):
    rz = rvol(df[C], 20, bpy)
    slot = pd.Series(df.index.month, index=df.index)
    prior = _prior_group_mean(rz, slot, 6, fallback=rz)
    overall = (rz.fillna(0).cumsum() / rz.notna().cumsum().where(rz.notna().cumsum() >= 60))
    elevated = (prior / overall.where(overall > 1e-9)).fillna(1.0)
    trend = np.sign(ema(df[C], 50) - ema(df[C], 200))
    return trend * (2.0 - elevated).clip(0, 1)


def pre_holiday(df, p, bpy):
    gap = pd.Series(df.index, index=df.index).diff().dt.total_seconds()
    typical = gap.rolling(100, min_periods=100).median()
    return pd.Series(np.where(gap > typical * 2.5, 0.55, 0.0), index=df.index)


def intraday_u_shape(df, p, bpy):
    hours = pd.Series(df.index.hour, index=df.index)
    first = hours.cummin()
    last = hours.cummax()
    midday = (~((hours == first) | (hours == last))).astype(float)
    z = pd.Series(squash(zscore(df[C].pct_change(), 20), 1.5), index=df.index)
    z2 = pd.Series(squash(zscore(df[C].pct_change(), 20), 2.0), index=df.index)
    return -z * midday + z2 * (1 - midday) * 0.5


def intraday_vol_seasonality(df, p, bpy):
    rng = true_range(df) / df[C]
    slot = pd.Series(df.index.hour, index=df.index)
    prior = _prior_group_mean(rng, slot, 5, fallback=rng)
    ex = ((rng - prior) / prior.where(prior > 1e-12)).fillna(0.0)
    return -np.sign(lr(df[C])) * pd.Series(squash(ex, 0.5), index=df.index).abs()


# ── Recursive trend filters ───────────────────────────────────────────────────

def supertrend(df, p, bpy):
    mult, per = p["multiplier"], p["period"]
    a = atr(df, per) * mult
    hl2 = (df["high"] + df["low"]) / 2
    ub, lb = (hl2 + a).to_numpy(), (hl2 - a).to_numpy()
    c = df[C].to_numpy()
    fu, fl = ub.copy(), lb.copy()
    trend = np.ones(len(c))
    for i in range(1, len(c)):
        fu[i] = min(ub[i], fu[i - 1]) if c[i - 1] <= fu[i - 1] else ub[i]
        fl[i] = max(lb[i], fl[i - 1]) if c[i - 1] >= fl[i - 1] else lb[i]
        trend[i] = 1.0 if c[i] > fu[i - 1] else (-1.0 if c[i] < fl[i - 1] else trend[i - 1])
    strength = trend_strength(df).clip(0.3, 1.0)
    return pd.Series(trend, index=df.index) * strength


def parabolic_sar(df, p, bpy):
    step, cap = p["af_step"], p["af_max"]
    h, l = df["high"].to_numpy(), df["low"].to_numpy()
    sar = np.zeros(len(h))
    trend = np.ones(len(h))
    sar[0], ep, af = l[0], h[0], step
    for i in range(1, len(h)):
        sar[i] = sar[i - 1] + af * (ep - sar[i - 1])
        if trend[i - 1] > 0:
            if l[i] < sar[i]:
                trend[i], sar[i], ep, af = -1.0, ep, l[i], step
            else:
                trend[i] = 1.0
                if h[i] > ep:
                    ep, af = h[i], min(af + step, cap)
        else:
            if h[i] > sar[i]:
                trend[i], sar[i], ep, af = 1.0, ep, h[i], step
            else:
                trend[i] = -1.0
                if l[i] < ep:
                    ep, af = l[i], min(af + step, cap)
    return pd.Series(trend, index=df.index) * 0.8


def ichimoku(df, p, bpy):
    def mid(n):
        return (highest(df["high"], n) + lowest(df["low"], n)) / 2
    tenkan, kijun = mid(p["tenkan"]), mid(p["kijun"])
    span_a = ((tenkan + kijun) / 2).shift(p["kijun"])
    span_b = mid(p["senkou"]).shift(p["kijun"])
    above = ((df[C] > span_a) & (df[C] > span_b)).astype(float)
    below = ((df[C] < span_a) & (df[C] < span_b)).astype(float)
    return (0.5 * np.sign(tenkan - kijun) + 0.5 * (above - below)).clip(-1, 1)


def ehlers_trendline(df, p, bpy):
    a = p["alpha"]
    src = ((df["high"] + df["low"]) / 2).to_numpy(dtype=float)
    it = src.copy()
    for i in range(2, len(src)):
        it[i] = ((a - a * a / 4) * src[i] + 0.5 * a * a * src[i - 1]
                 - (a - 0.75 * a * a) * src[i - 2]
                 + 2 * (1 - a) * it[i - 1] - (1 - a) ** 2 * it[i - 2])
    trend = pd.Series(it, index=df.index)
    at = atr(df, 14)
    return pd.Series(squash(((df[C] - trend) / at.where(at > 1e-12)).fillna(0.0), 1.5),
                     index=df.index)


def ehlers_fisher(df, p, bpy):
    n = p["period"]
    mid = (df["high"] + df["low"]) / 2
    ll, hh = lowest(mid, n), highest(mid, n)
    rng = hh - ll
    raw = ((2 * (mid - ll) / rng.where(rng > 1e-12)) - 1).clip(-0.999, 0.999).fillna(0.0)
    sm = ema(raw, 5).clip(-0.999, 0.999)
    fish = 0.5 * np.log((1 + sm) / (1 - sm))
    return pd.Series(squash(ema(fish, 3), 1.5), index=df.index)


def elder_triple(df, p, bpy):
    e = ema(df[C], p["trend_span"])
    trend = np.sign(e.diff())
    force = ema(df[C].diff() * df["volume"], p["osc_period"])
    pullback = pd.Series(-squash(zscore(force, 40), 1.5), index=df.index)
    return (pullback.abs() * trend).where(np.sign(pullback) == trend, 0.0)


# ── Volatility recursions ─────────────────────────────────────────────────────

def garch(df, p, bpy):
    r = lr(df[C]).fillna(0.0)
    a, b = p["alpha"], p["beta"]
    lrv = exp_variance(r, 30)
    om = lrv * (1 - a - b)
    rv = r.to_numpy()
    ov = om.to_numpy()
    lv = lrv.to_numpy()
    v = np.full(len(rv), np.nan)
    for i in range(len(rv)):
        if np.isnan(ov[i]):
            v[i] = lv[i] if not np.isnan(lv[i]) else np.nan
            continue
        prev = v[i - 1] if i > 0 and not np.isnan(v[i - 1]) else lv[i]
        v[i] = ov[i] + a * rv[i - 1] ** 2 + b * prev
    fc = pd.Series(np.sqrt(v * bpy), index=df.index)
    rz = rvol(df[C], 20, bpy)
    gap = ((fc - rz) / rz.where(rz > 1e-9)).fillna(0.0)
    return pd.Series(-squash(gap, 0.35), index=df.index) * np.sign(zscore(df[C], 20))


def gjr_garch(df, p, bpy):
    r = lr(df[C]).fillna(0.0)
    a, g, b = p["alpha"], p["gamma"], p["beta"]
    lrv = exp_variance(r, 30)
    om = lrv * np.maximum(1e-6, 1 - a - g / 2 - b)
    rv = r.to_numpy()
    ov = om.to_numpy()
    lv = lrv.to_numpy()
    v = np.full(len(rv), np.nan)
    for i in range(len(rv)):
        if np.isnan(ov[i]):
            v[i] = lv[i] if not np.isnan(lv[i]) else np.nan
            continue
        prev = v[i - 1] if i > 0 and not np.isnan(v[i - 1]) else lv[i]
        shock = rv[i - 1] ** 2
        v[i] = ov[i] + a * shock + g * shock * (rv[i - 1] < 0) + b * prev
    cond = pd.Series(np.sqrt(v * bpy), index=df.index)
    return pd.Series(-squash(zscore(cond, 60), 1.5), index=df.index)


def cvar(df, p, bpy):
    w = p["window"]
    r = lr(df[C])
    q = percentile_nearest_rank(r, w, 5)
    below = (r <= q).astype(float)
    cv_sum = rsum(r.where(r <= q, 0.0), w)
    cv_cnt = rsum(below, w)
    cv = cv_sum / cv_cnt.where(cv_cnt >= 5)
    trend = np.sign(ema(df[C], 20) - ema(df[C], 50))
    return trend * (1 + pd.Series(squash(zscore_skipna(cv, w), 1.5), index=df.index)).clip(0, 1)


# ── Microstructure ────────────────────────────────────────────────────────────

def almgren_chriss(df, p, bpy):
    w = p["window"]
    adv = sma(df["volume"], w)
    part = (df["volume"] / adv.where(adv > 0)).fillna(1.0)
    natr = atr(df, 14) / df[C]
    expd = np.sqrt(part.clip(lower=0)) * natr
    act = (df[C].diff() / df[C].shift(1)).abs()
    exc = ((act - expd) / expd.where(expd > 1e-9)).fillna(0.0)
    return -np.sign(df[C].diff()) * pd.Series(squash(exc, 1.0), index=df.index).clip(0, 1)


def avellaneda_stoikov(df, p, bpy):
    w, gamma = p["window"], p["gamma"]
    mid = (df["high"] + df["low"]) / 2
    var = variance(lr(df[C]), w)
    inv = zscore(df[C] - sma(mid, w), w)
    skew = -inv * gamma * var * 1e4
    return pd.Series(squash(skew, 0.5), index=df.index) - \
        pd.Series(squash(inv, 2.0), index=df.index) * 0.5


def hawkes(df, p, bpy):
    decay, thresh = p["decay"], p["threshold"]
    big = (true_range(df) > atr(df, 14) * thresh).astype(float)
    span = int(round(2.0 / (1.0 - decay) - 1.0))
    intensity = ema(big, span)
    return -np.sign(lr(df[C])) * pd.Series(squash(zscore(intensity, 60), 1.5),
                                           index=df.index).abs()


def micro_noise(df, p, bpy):
    fast, slow = p["fast"], p["slow"]
    fv = rsum(lr(df[C]) ** 2, fast)
    sv = rsum(np.log(df[C] / df[C].shift(fast)) ** 2, max(2, slow // fast))
    noise = ((fv - sv) / fv.where(fv > 1e-14)).fillna(0.0)
    return -np.sign(lr(df[C])) * pd.Series(squash(noise.clip(0, 1), 0.4), index=df.index)


# ── Statistical arbitrage ─────────────────────────────────────────────────────

def cusum(df, p, bpy):
    thr, vw = p["threshold_sd"], p["vol_window"]
    r = lr(df[C]).fillna(0.0).to_numpy()
    sd = stdev(lr(df[C]), vw).fillna(0.0).to_numpy()
    sp = sn = 0.0
    out = np.zeros(len(r))
    for i in range(len(r)):
        lim = thr * sd[i]
        sp, sn = max(0.0, sp + r[i]), min(0.0, sn + r[i])
        if lim > 0 and sp > lim:
            out[i], sp = 1.0, 0.0
        elif lim > 0 and sn < -lim:
            out[i], sn = -1.0, 0.0
    return persist(pd.Series(out, index=df.index), 5)


def frac_diff(df, p, bpy):
    d, width = p["d"], p["width"]
    lg = np.log(df[C]).to_numpy(dtype=float)
    w = 1.0
    weights = []
    for k in range(width):
        weights.append(w)
        w = -w * (d - k) / (k + 1)
    weights = np.array(weights)
    out = np.full(len(lg), np.nan)
    for i in range(width - 1, len(lg)):
        window = lg[i - width + 1:i + 1][::-1]
        out[i] = float(np.dot(weights, window))
    return pd.Series(-squash(zscore(pd.Series(out, index=df.index), 60), 1.5), index=df.index)


def shape_match(df, p, bpy):
    w = p["window"]
    pos = np.arange(w - 1, -1, -1)
    tmpl = np.where(pos < w // 2,
                    1.0 - 2.0 * pos / (w / 2.0 - 1.0),
                    -1.0 + 2.0 * (pos - w / 2.0) / (w - w // 2 - 1.0))
    tm, tsd = tmpl.mean(), tmpl.std()

    def _corr(win: np.ndarray) -> float:
        sd = win.std()
        if sd < 1e-12:
            return 0.0
        return float(np.dot((win - win.mean()) / sd, (tmpl - tm) / (tsd if tsd > 1e-12 else 1.0)) / w)

    corr = df[C].rolling(w, min_periods=w).apply(_corr, raw=True)
    return pd.Series(squash(corr * 2.0, 0.8), index=df.index)


# ── Factor / composites ───────────────────────────────────────────────────────

def connors_rsi(df, p, bpy):
    d = np.sign(df[C].diff()).fillna(0.0).to_numpy()
    streak = np.zeros(len(d))
    for i in range(1, len(d)):
        streak[i] = streak[i - 1] + d[i] if d[i] != 0 and d[i] == np.sign(streak[i - 1]) else d[i]
    s_rsi = 50 + 50 * np.tanh(streak / 3.0)
    rank = percentrank(df[C].pct_change(), p["rank_p"]) * 100
    crsi = (rsi(df[C], p["rsi_p"]) + pd.Series(s_rsi, index=df.index) + rank) / 3.0
    return pd.Series(-band_score(crsi, 0.0, 100.0), index=df.index)


def return_stability(df, p, bpy):
    w = p["window"]
    hit = sma((lr(df[C]) > 0).astype(float), w)
    vol_stab = 1 - percentrank(stdev(rvol(df[C], 20, bpy), w), w)
    dd = (1 + lowest(dd_from_peak(df[C]), w)).clip(0, 1)
    return pd.Series(band_score((hit + vol_stab + dd) / 3, 0.35, 0.65), index=df.index)


def defensive_tilt(df, p, bpy):
    low_vol = 1 - vol_regime(df, 252, bpy)
    shallow = (1 + lowest(dd_from_peak(df[C]), 120)).clip(0, 1)
    smooth = 1 - percentrank(sma(lr(df[C]).abs(), 20), 252)
    return pd.Series(band_score((low_vol + shallow + smooth) / 3, 0.35, 0.7), index=df.index)


def black_litterman(df, p, bpy):
    w, vc = p["window"], p["view_confidence"]
    prior = pd.Series(squash(sma(lr(df[C]), 252) * 252, 0.1), index=df.index)
    view = pd.Series(squash(zscore(df[C].pct_change(w), 120), 1.5), index=df.index)
    conf = eff_ratio(df[C], w).clip(0, 1) * vc
    return prior * (1 - conf) + view * conf


def liquidity_risk_factor(df, p, bpy):
    w = p["window"]
    sv = np.sign(df[C].pct_change()) * df["volume"]
    gamma = (df[C].pct_change()).rolling(w, min_periods=w).corr(sv.shift(1))
    return pd.Series(-squash(zscore(gamma, w), 1.5), index=df.index)


def momentum_reversal_rotation(df, p, bpy):
    ew = p["eval_window"]
    rev = pd.Series(-squash(zscore(df[C].pct_change(5), 60), 1.5), index=df.index)
    mom = pd.Series(squash(zscore(df[C].pct_change(63), 120), 1.5), index=df.index)
    rev_p = sma(rev.shift(1) * lr(df[C]), ew)
    mom_p = sma(mom.shift(1) * lr(df[C]), ew)
    return pd.Series(np.where(rev_p > mom_p, rev, mom), index=df.index)


def factor_momentum_timing(df, p, bpy):
    w = p["window"]
    mom = pd.Series(squash(zscore(df[C].pct_change(126), 252), 1.5), index=df.index)
    val = pd.Series(-squash(np.log(df[C] / sma(df[C], 504)), 0.25), index=df.index)
    mp = sma(mom.shift(1) * lr(df[C]), w).clip(lower=0)
    vp = sma(val.shift(1) * lr(df[C]), w).clip(lower=0)
    tot = mp + vp
    return ((mom * mp + val * vp) / tot.where(tot > 1e-12)).fillna(0.0).clip(-1, 1)


def fear_greed(df, p, bpy):
    momentum = percentrank(df[C] / sma(df[C], 125) - 1, 252)
    strength = percentrank(df[C].pct_change(20), 252)
    vol_inv = 1 - vol_regime(df, 252, bpy)
    dd_health = (1 + dd_from_peak(df[C]) / 0.20).clip(0, 1)
    greed = (momentum + strength + vol_inv + dd_health) / 4
    return -((greed - 0.5) * 2).clip(-1, 1)


# ── Options income (regime-favourability composites) ──────────────────────────

def covered_call(df, p, bpy):
    rich = vol_regime(df, 252, bpy)
    flat = 1 - trend_strength(df).clip(0, 1)
    attractive = (rich * flat).clip(0, 1)
    return (0.3 + 0.5 * attractive) * np.sign(sma(df[C], 50) - sma(df[C], 200)).clip(0, 1)


def cash_secured_put(df, p, bpy):
    spike = vol_regime(df, 252, bpy)
    oversold = (-pd.Series(band_score(rsi(df[C], 14), 0, 100), index=df.index)).clip(0, 1)
    return (spike * oversold).clip(0, 1)


def options_wheel(df, p, bpy):
    choppy = 1 - trend_strength(df).clip(0, 1)
    vol_ok = vol_regime(df, 252, bpy).clip(0, 1)
    no_crash = (1 + dd_from_peak(df[C]) / 0.25).clip(0, 1)
    return (choppy * vol_ok * no_crash).clip(0, 1) * 0.8


def short_strangle(df, p, bpy):
    rich = vol_regime(df, 252, bpy)
    ranging = 1 - trend_strength(df).clip(0, 1)
    tail_safe = (1 - (roll_kurt(lr(df[C]), 60) / 6).clip(0, 1)).clip(0, 1)
    return (rich * ranging * tail_safe).clip(0, 1) * 0.7


def iron_condor(df, p, bpy):
    ranging = 1 - trend_strength(df).clip(0, 1)
    rich = vol_regime(df, 252, bpy)
    stable = 1 - percentrank(atr(df, 14) / df[C], 120)
    return (ranging * rich * stable).clip(0, 1) * 0.7


def protective_put(df, p, bpy):
    vol_cheap = 1 - vol_regime(df, 252, bpy)
    tail = (roll_kurt(lr(df[C]), 60) / 6).clip(0, 1)
    skew = (-roll_skew(lr(df[C]), 60) / 2).clip(0, 1)
    hedge = (vol_cheap * (tail + skew) / 2).clip(0, 1)
    return np.sign(sma(df[C], 50) - sma(df[C], 200)).clip(0, 1) * (1 - hedge * 0.5)


def round_number_pin(df, p, bpy):
    step = sma(df[C], 60) * p["granularity"]
    nearest = (df[C] / step.where(step > 1e-9)).round() * step
    a = atr(df, 14)
    return pd.Series(squash(((nearest - df[C]) / a.where(a > 1e-12)).fillna(0.0), 0.8),
                     index=df.index) * 0.6


CHECKS2 = {
    "Day-of-Week Effect": day_of_week,
    "Month-of-Year Seasonality": month_of_year,
    "Week-of-Month Pattern": week_of_month,
    "Time-of-Day Momentum": time_of_day,
    "Commodity Seasonal Pattern": commodity_seasonal,
    "Seasonal Volatility Pattern": seasonal_volatility,
    "Pre-Holiday Effect": pre_holiday,
    "Intraday U-Shape Volume Pattern": intraday_u_shape,
    "Intraday Volatility Seasonality": intraday_vol_seasonality,
    "Supertrend (ATR Bands)": supertrend,
    "Parabolic SAR": parabolic_sar,
    "Ichimoku Kinko Hyo": ichimoku,
    "Ehlers Instantaneous Trendline": ehlers_trendline,
    "Ehlers Fisher Transform": ehlers_fisher,
    "Elder Triple Screen": elder_triple,
    "GARCH(1,1) Volatility Forecast": garch,
    "GJR-GARCH Threshold Volatility": gjr_garch,
    "Conditional Tail Risk (CVaR)": cvar,
    "Almgren-Chriss Temporary Impact": almgren_chriss,
    "Avellaneda-Stoikov Reservation Price": avellaneda_stoikov,
    "Hawkes Self-Exciting Intensity": hawkes,
    "Microstructure Noise Ratio": micro_noise,
    "CUSUM Structural Break Filter": cusum,
    "Fractionally Differentiated Price": frac_diff,
    "Shape-Matched Reversal Template": shape_match,
    "Connors RSI Composite": connors_rsi,
    "Return Stability (Technical Quality)": return_stability,
    "Defensive Equity Tilt": defensive_tilt,
    "Black-Litterman Blended View": black_litterman,
    "Liquidity Risk Factor": liquidity_risk_factor,
    "Momentum-Reversal Horizon Rotation": momentum_reversal_rotation,
    "Factor Momentum Timing": factor_momentum_timing,
    "Price-Based Fear & Greed Composite": fear_greed,
    "Covered Call Overlay": covered_call,
    "Cash-Secured Put": cash_secured_put,
    "Options Wheel": options_wheel,
    "Systematic Short Strangle": short_strangle,
    "Systematic Iron Condor": iron_condor,
    "Protective Put Overlay": protective_put,
    "Round-Number Pin Proxy": round_number_pin,
}
