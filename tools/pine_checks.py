"""
Independent re-implementations of every emitted Pine body.

Each function here is written from the **Pine source**, using the Pine-semantics
primitives in ``pine_sim``. It must never call the Python model it is checking —
that would verify the translation against itself and prove nothing.

Signature: ``fn(df, p, bpy) -> pd.Series`` where ``p`` is the model's parameter
dict and ``bpy`` is bars-per-year for the interval.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from pine_sim import (  # noqa: F401
    atr, band_score, cci, correlation, dd_from_peak, dmi, eff_ratio, ema,
    highest, hma, linreg, lowest, lr, mfi, median, percentile_nearest_rank,
    percentrank, persist, roll_cov, roll_kurt, roll_skew, rsi, rsum, rvol, sma,
    squash, stdev, stoch, trend_strength, true_range, variance, vol_regime, wma,
    zscore,
)

C = "close"


# ── Trend & Momentum ──────────────────────────────────────────────────────────

def donchian_breakout(df, p, bpy):
    up = highest(df["high"], p["period"]).shift(1)
    lo = lowest(df["low"], p["period"]).shift(1)
    raw = pd.Series(np.where(df[C] > up, 1.0, np.where(df[C] < lo, -1.0, 0.0)), index=df.index)
    return persist(raw, p["hold"])


def ema_cross(df, p, bpy):
    f, s = ema(df[C], p["fast"]), ema(df[C], p["slow"])
    return pd.Series(squash((f - s) / s.abs(), 0.03), index=df.index)


def macd_hist(df, p, bpy):
    line = ema(df[C], p["fast"]) - ema(df[C], p["slow"])
    hist = line - ema(line, p["signal"])
    a = atr(df, 14)
    return pd.Series(squash(hist / a.where(a > 1e-12, 1e-12), 0.6), index=df.index)


def adx_dm(df, p, bpy):
    pdi, mdi, adx = dmi(df, p["period"])
    gate = ((adx - p["adx_floor"]) / 20.0).clip(0, 1)
    return pd.Series(squash((pdi - mdi) / 25.0, 1.0), index=df.index) * gate


def aroon(df, p, bpy):
    n = p["period"]
    up_i = df["high"].rolling(n + 1, min_periods=n + 1).apply(
        lambda x: -(len(x) - 1 - int(np.argmax(x))), raw=True)
    dn_i = df["low"].rolling(n + 1, min_periods=n + 1).apply(
        lambda x: -(len(x) - 1 - int(np.argmin(x))), raw=True)
    return (100.0 * (n + up_i) / n - 100.0 * (n + dn_i) / n) / 100.0


def keltner_trend(df, p, bpy):
    mid = ema(df[C], p["period"])
    a = atr(df, p["atr_period"])
    w = 2 * p["mult"] * a
    return pd.Series(squash(((df[C] - mid) / w.where(w > 1e-12) * 4.0).fillna(0.0), 1.2),
                     index=df.index)


def vortex(df, p, bpy):
    n = p["period"]
    tr = rsum(true_range(df), n)
    vip = rsum((df["high"] - df["low"].shift(1)).abs(), n) / tr.where(tr > 1e-12)
    vim = rsum((df["low"] - df["high"].shift(1)).abs(), n) / tr.where(tr > 1e-12)
    return pd.Series(squash((vip - vim).fillna(0.0), 0.15), index=df.index)


def regression_slope(df, p, bpy):
    w = p["window"]
    lg = np.log(df[C])
    slope = linreg(lg, w, 0) - linreg(lg, w, 1)
    noise = stdev(lg.diff(), w)
    return pd.Series(squash((slope / noise.where(noise > 1e-12) * np.sqrt(w)).fillna(0.0), 2.0),
                     index=df.index)


def hull_slope(df, p, bpy):
    h = hma(df[C], p["period"])
    a = atr(df, 14)
    return pd.Series(squash(((h - h.shift(1)) / a.where(a > 1e-12)).fillna(0.0), 0.3),
                     index=df.index)


def trix(df, p, bpy):
    lg = np.log(df[C])
    e = lg
    for _ in range(3):
        e = ema(e, p["period"])
    t = (e - e.shift(1)) * 10000.0
    return pd.Series(squash(t - ema(t, p["signal"]), 5.0), index=df.index)


def cmo(df, p, bpy):
    n = p["period"]
    d = df[C].diff()
    up, dn = rsum(d.clip(lower=0), n), rsum((-d).clip(lower=0), n)
    tot = up + dn
    return ((up - dn) / tot.where(tot > 1e-12)).fillna(0.0)


def high52w(df, p, bpy):
    w = p["window"]
    hi, lo = highest(df["high"], w), lowest(df["low"], w)
    rng = hi - lo
    pos = ((df[C] - lo) / rng.where(rng > 1e-12)).fillna(0.5)
    return pd.Series(band_score(pos, 0.35, 0.98), index=df.index)


def tsmom(df, p, bpy):
    lb, sk, vw = p["lookback"], p["skip"], p["vol_window"]
    past = np.log(df[C].shift(sk) / df[C].shift(sk + lb))
    vol = stdev(lr(df[C]), vw) * np.sqrt(lb)
    return pd.Series(squash((past / vol.where(vol > 1e-9)).fillna(0.0), 1.0), index=df.index)


def trend_quality(df, p, bpy):
    w, me = p["window"], p["min_er"]
    er = eff_ratio(df[C], w)
    gate = ((er - me) / (1.0 - me)).clip(0, 1)
    return np.sign(df[C] - df[C].shift(w)) * gate


def failed_breakout(df, p, bpy):
    up = highest(df["high"], p["period"]).shift(1)
    lo = lowest(df["low"], p["period"]).shift(1)
    fu = ((df["high"] > up) & (df[C] < up)).astype(float)
    fd = ((df["low"] < lo) & (df[C] > lo)).astype(float)
    return persist(fd - fu, p["hold"])


def volume_breakout(df, p, bpy):
    up = highest(df["high"], p["period"]).shift(1)
    lo = lowest(df["low"], p["period"]).shift(1)
    conf = (zscore(df["volume"], 20) > p["vol_z"]).astype(float)
    raw = pd.Series(np.where(df[C] > up, 1.0, np.where(df[C] < lo, -1.0, 0.0)), index=df.index)
    return persist(raw * conf, 5)


def turtle(df, p, bpy):
    eu = highest(df["high"], p["entry"]).shift(1).to_numpy()
    el = lowest(df["low"], p["entry"]).shift(1).to_numpy()
    xu = highest(df["high"], p["exit"]).shift(1).to_numpy()
    xl = lowest(df["low"], p["exit"]).shift(1).to_numpy()
    c = df[C].to_numpy()
    st, out = 0.0, np.zeros(len(c))
    for i in range(len(c)):
        if st > 0 and c[i] < xl[i]:
            st = 0.0
        elif st < 0 and c[i] > xu[i]:
            st = 0.0
        if st == 0.0:
            st = 1.0 if c[i] > eu[i] else (-1.0 if c[i] < el[i] else 0.0)
        out[i] = st
    return pd.Series(out, index=df.index)


def kama(df, p, bpy):
    per, fast, slow = p["period"], p["fast"], p["slow"]
    er = eff_ratio(df[C], per)
    sc = (er * (2.0 / (fast + 1) - 2.0 / (slow + 1)) + 2.0 / (slow + 1)) ** 2
    c = df[C].to_numpy(dtype=float)
    s = sc.fillna(0.0).to_numpy()
    k = np.full(len(c), np.nan)
    k[0] = c[0]
    for i in range(1, len(c)):
        k[i] = k[i - 1] + s[i] * (c[i] - k[i - 1])
    kk = pd.Series(k, index=df.index)
    a = atr(df, 14)
    return pd.Series(squash(((df[C] - kk) / a.where(a > 1e-12)).fillna(0.0), 1.5),
                     index=df.index) * er.clip(0, 1)


def coppock(df, p, bpy):
    roc = ((df[C] - df[C].shift(p["roc1"])) / df[C].shift(p["roc1"]) +
           (df[C] - df[C].shift(p["roc2"])) / df[C].shift(p["roc2"])) * 100.0
    return pd.Series(squash(wma(roc, p["wma"]), 8.0), index=df.index)


def dual_momentum(df, p, bpy):
    a, r = p["abs_lb"], p["rel_lb"]
    absolute = np.sign((df[C] - df[C].shift(a)) / df[C].shift(a))
    relative = pd.Series(squash(zscore((df[C] - df[C].shift(r)) / df[C].shift(r), 126), 1.5),
                         index=df.index)
    return relative.where(np.sign(relative) == absolute, 0.0)


def guppy(df, p, bpy):
    sh = sum(ema(df[C], n) for n in (3, 5, 8, 10, 12, 15)) / 6.0
    ln = sum(ema(df[C], n) for n in (30, 35, 40, 45, 50, 60)) / 6.0
    return pd.Series(squash((sh - ln) / ln.abs(), 0.02), index=df.index)


def momentum_accel(df, p, bpy):
    f, s = p["fast"], p["slow"]
    mf = (df[C] - df[C].shift(f)) / df[C].shift(f)
    ms = (df[C] - df[C].shift(s)) / df[C].shift(s)
    return pd.Series(squash(zscore(mf - ms * (f / s), 63), 1.5), index=df.index)


def cta_core(df, p, bpy):
    vol = stdev(lr(df[C]), 60)
    legs = [pd.Series(squash((np.log(df[C] / df[C].shift(lb)) /
                              (vol.where(vol > 1e-9) * np.sqrt(lb))).fillna(0.0), 1.0),
                      index=df.index) for lb in (21, 63, 252)]
    return sum(legs) / 3.0


def atr_trend_exposure(df, p, bpy):
    tw, ap = p["trend_window"], p["atr_period"]
    a = atr(df, ap)
    mv = df[C] - df[C].shift(tw)
    return pd.Series(squash((mv / a.where(a > 1e-12) / np.sqrt(tw)).fillna(0.0), 1.0),
                     index=df.index)


# ── Mean Reversion ────────────────────────────────────────────────────────────

def bollinger_rev(df, p, bpy):
    mid, sd = sma(df[C], p["period"]), stdev(df[C], p["period"])
    up, lo = mid + p["k"] * sd, mid - p["k"] * sd
    rng = up - lo
    pct = ((df[C] - lo) / rng.where(rng > 1e-12)).fillna(0.5)
    return pd.Series(-band_score(pct, 0.0, 1.0), index=df.index)


def rsi2(df, p, bpy):
    r = rsi(df[C], p["rsi_period"])
    trend = np.sign(df[C] - sma(df[C], p["trend_period"]))
    raw = pd.Series(-band_score(r, 0.0, 100.0), index=df.index)
    return raw.where(np.sign(raw) == trend, raw * 0.25)


def zscore_rev(df, p, bpy):
    return pd.Series(-squash(zscore(df[C], p["window"]), 1.5), index=df.index)


def stoch_rev(df, p, bpy):
    k = sma(stoch(df[C], df["high"], df["low"], p["period"]), p["smooth"])
    return pd.Series(-band_score(k, 0.0, 100.0), index=df.index)


def williams_r(df, p, bpy):
    wr = stoch(df[C], df["high"], df["low"], p["period"]) - 100.0
    return pd.Series(-band_score(wr, -100.0, 0.0), index=df.index)


def cci_rev(df, p, bpy):
    return pd.Series(-squash(cci(df, p["period"]) / 100.0, 1.5), index=df.index)


def mfi_rev(df, p, bpy):
    return pd.Series(-band_score(mfi(df, p["period"]), 0.0, 100.0), index=df.index)


def ultimate_osc(df, p, bpy):
    prev = df[C].shift(1)
    bp = df[C] - pd.concat([df["low"], prev], axis=1).min(axis=1)
    tr = true_range(df)
    avg = lambda n: rsum(bp, n) / rsum(tr, n)
    uo = 100.0 * (4 * avg(p["p1"]) + 2 * avg(p["p2"]) + avg(p["p3"])) / 7.0
    return pd.Series(-band_score(uo, 0.0, 100.0), index=df.index)


def keltner_rev(df, p, bpy):
    mid, a = ema(df[C], p["period"]), atr(df, 14)
    w = 2 * p["mult"] * a
    return pd.Series(-squash(((df[C] - mid) / w.where(w > 1e-12) * 4.0).fillna(0.0), 1.2),
                     index=df.index)


def vwap_rev(df, p, bpy):
    w = p["window"]
    tp = (df["high"] + df["low"] + df[C]) / 3
    vv = rsum(df["volume"], w)
    vw = (rsum(tp * df["volume"], w) / vv.where(vv > 1e-12)).fillna(sma(tp, w))
    a = atr(df, 14)
    return pd.Series(-squash(((df[C] - vw) / a.where(a > 1e-12)).fillna(0.0), 1.2),
                     index=df.index)


def short_reversal(df, p, bpy):
    lb = p["lookback"]
    return pd.Series(-squash(zscore((df[C] - df[C].shift(lb)) / df[C].shift(lb), 60), 1.5),
                     index=df.index)


def long_reversal(df, p, bpy):
    lb = p["lookback"]
    return pd.Series(-squash(zscore((df[C] - df[C].shift(lb)) / df[C].shift(lb), 252), 1.5),
                     index=df.index)


def gap_fade(df, p, bpy):
    gap = (df["open"] - df[C].shift(1)) / df[C].shift(1)
    return pd.Series(-squash(zscore(gap, p["z_window"]), 1.5), index=df.index)


def squeeze_release(df, p, bpy):
    n = p["period"]
    mid, sd = sma(df[C], n), stdev(df[C], n)
    bbu, bbl = mid + 2 * sd, mid - 2 * sd
    e, a = ema(df[C], n), atr(df, 14)
    kcu, kcl = e + 1.5 * a, e - 1.5 * a
    sq = (bbu < kcu) & (bbl > kcl)
    rel = sq.shift(1).fillna(False) & ~sq
    return persist(rel.astype(float) * np.sign(df[C] - mid), p["hold"])


def adr_exhaustion(df, p, bpy):
    a = atr(df, p["atr_period"])
    tr = ((df[C] - df["open"]) / a.where(a > 1e-12)).fillna(0.0)
    ex = (tr.abs() - p["threshold"]).clip(0, 2) / 2.0
    return -np.sign(tr) * ex


def range_oscillator(df, p, bpy):
    n = p["period"]
    up, lo = highest(df["high"], n).shift(1), lowest(df["low"], n).shift(1)
    rng = up - lo
    pos = ((df[C] - lo) / rng.where(rng > 1e-12)).fillna(0.5)
    ranging = (1.0 - eff_ratio(df[C], n) / p["max_er"]).clip(0, 1)
    return pd.Series(-band_score(pos, 0.0, 1.0), index=df.index) * ranging


def opening_range_rev(df, p, bpy):
    a = atr(df, 14)
    exc = ((df[C] - df["open"]) / a.where(a > 1e-12)).fillna(0.0)
    stalling = (true_range(df) < a).astype(float)
    return pd.Series(-squash(exc, 1.5), index=df.index) * stalling


def rsi_divergence(df, p, bpy):
    w = p["window"]
    r = rsi(df[C], p["period"])
    px_hi = df[C] >= highest(df[C], w)
    px_lo = df[C] <= lowest(df[C], w)
    bear = (px_hi & (r < highest(r, w))).astype(float)
    bull = (px_lo & (r > lowest(r, w))).astype(float)
    return persist(bull - bear, p["hold"])


def td_sequential(df, p, bpy):
    lag, tgt = p["lag"], p["target"]
    up = (df[C] > df[C].shift(lag)).to_numpy()
    dn = (df[C] < df[C].shift(lag)).to_numpy()
    cu = cd = 0
    out = np.zeros(len(df))
    for i in range(len(df)):
        cu = cu + 1 if up[i] else 0
        cd = cd + 1 if dn[i] else 0
        out[i] = min(cd, tgt) / tgt - min(cu, tgt) / tgt
    return pd.Series(out, index=df.index)


def half_life_gated(df, p, bpy):
    hw, mh = p["hl_window"], p["max_hl"]
    lag, delta = df[C].shift(1), df[C].diff()
    beta = roll_cov(delta, lag, hw) / variance(lag, hw).where(variance(lag, hw) > 1e-12)
    hl = (-np.log(2) / beta.where(beta < -1e-9)).fillna(1e9)
    gate = (1.0 - hl / mh).clip(0, 1)
    return pd.Series(-squash(zscore(df[C], p["window"]), 1.5), index=df.index) * gate


def fat_tail_rev(df, p, bpy):
    rk = percentrank(df[C].pct_change(), p["window"])
    t = p["tail_pct"]
    return pd.Series(np.where(rk < t, 1.0, np.where(rk > 1 - t, -1.0, 0.0)),
                     index=df.index) * 0.85


# ── Volatility ────────────────────────────────────────────────────────────────

def yang_zhang(df, p, bpy):
    w = p["window"]
    o = np.log(df["open"] / df[C].shift(1))
    c = np.log(df[C] / df["open"])
    vo, vc = variance(o, w), variance(c, w)
    rs = (np.log(df["high"] / df[C]) * np.log(df["high"] / df["open"]) +
          np.log(df["low"] / df[C]) * np.log(df["low"] / df["open"]))
    k = 0.34 / (1.34 + (w + 1) / (w - 1))
    yz = np.sqrt((vo + k * vc + (1 - k) * sma(rs, w)).clip(lower=0)) * np.sqrt(bpy)
    return pd.Series(-squash(zscore(yz, 60), 1.5), index=df.index)


def parkinson_div(df, p, bpy):
    w = p["window"]
    hl = np.log(df["high"] / df["low"]) ** 2
    pk = np.sqrt(sma(hl, w) / (4 * np.log(2))) * np.sqrt(bpy)
    cc = stdev(lr(df[C]), w) * np.sqrt(bpy)
    ratio = (pk / cc.where(cc > 1e-9)).fillna(1.0)
    return pd.Series(-squash(zscore(ratio, 60), 1.5), index=df.index)


def garman_klass(df, p, bpy):
    w = p["window"]
    hl = 0.5 * np.log(df["high"] / df["low"]) ** 2
    co = (2 * np.log(2) - 1) * np.log(df[C] / df["open"]) ** 2
    gk = np.sqrt(sma(hl - co, w).clip(lower=0)) * np.sqrt(bpy)
    return pd.Series(-squash(zscore(gk, 60), 1.5), index=df.index) * np.sign(zscore(df[C], 20))


def rogers_satchell(df, p, bpy):
    w = p["window"]
    rs = (np.log(df["high"] / df[C]) * np.log(df["high"] / df["open"]) +
          np.log(df["low"] / df[C]) * np.log(df["low"] / df["open"]))
    rsv = np.sqrt(sma(rs, w).clip(lower=0)) * np.sqrt(bpy)
    cc = rvol(df[C], w, bpy)
    return pd.Series(-squash(zscore((rsv / cc.where(cc > 1e-9)).fillna(1.0), 60), 1.5),
                     index=df.index)


def bipower(df, p, bpy):
    w = p["window"]
    r = lr(df[C])
    rv = rsum(r ** 2, w)
    bv = (np.pi / 2) * rsum(r.abs() * r.abs().shift(1), w)
    jr = ((rv - bv) / rv.where(rv > 1e-14)).clip(0, 1).fillna(0.0)
    return -np.sign(r) * jr


def merton_jump(df, p, bpy):
    sd = stdev(lr(df[C]), p["window"])
    z = (lr(df[C]) / sd.where(sd > 1e-12)).fillna(0.0)
    ex = (z.abs() - p["threshold"]).clip(0, 3) / 3.0
    return -np.sign(z) * ex


def realized_skew(df, p, bpy):
    return pd.Series(-squash(roll_skew(lr(df[C]), p["window"]), 0.8), index=df.index)


def vol_of_vol(df, p, bpy):
    rz = rvol(df[C], p["vol_window"], bpy)
    return pd.Series(-squash(zscore(stdev(rz, p["vov_window"]), 120), 1.5), index=df.index)


def vol_term_structure(df, p, bpy):
    s, l = rvol(df[C], p["short"], bpy), rvol(df[C], p["long"], bpy)
    return pd.Series(-squash(((s - l) / l.where(l > 1e-9)).fillna(0.0), 0.3), index=df.index)


def vol_clustering(df, p, bpy):
    ar = lr(df[C]).abs()
    cl = correlation(ar, ar.shift(1), p["window"])
    trend = np.sign(ema(df[C], 20) - ema(df[C], 50))
    return trend * (1 - cl.clip(0, 1)) * 0.7


def vol_managed(df, p, bpy):
    rz = rvol(df[C], p["window"], bpy)
    sc = (p["target_vol"] / rz.where(rz > 1e-6)).clip(0, 2.0).fillna(0.0)
    trend = np.sign(ema(df[C], 50) - ema(df[C], 200))
    return (trend * sc / 2.0).clip(-1, 1)


def har_rv(df, p, bpy):
    rv = lr(df[C]) ** 2
    fc = 0.35 * sma(rv, p["daily"]) + 0.35 * sma(rv, p["weekly"]) + 0.30 * sma(rv, p["monthly"])
    cur = sma(rv, 5)
    return pd.Series(-squash(((fc - cur) / cur.where(cur > 1e-14)).fillna(0.0), 0.5),
                     index=df.index)


def egarch_asym(df, p, bpy):
    w = p["window"]
    r = lr(df[C])
    dn, up = stdev(r.where(r < 0, 0.0), w), stdev(r.where(r > 0, 0.0), w)
    s = dn + up
    return pd.Series(-squash(((dn - up) / s.where(s > 1e-12)).fillna(0.0), 0.25), index=df.index)


def vol_mean_rev(df, p, bpy):
    vr = vol_regime(df, p["rank_window"], bpy)
    return -np.sign(zscore(df[C], 20)) * pd.Series(band_score(vr, 0.5, 0.95),
                                                   index=df.index).clip(0, 1)


def vol_breakout(df, p, bpy):
    rng = true_range(df)
    narrow = highest(rng, p["compress_window"])
    q25 = rng.rolling(p["lookback"], min_periods=p["lookback"]).quantile(0.25, interpolation="nearest")
    was_narrow = (narrow <= q25).shift(1).fillna(False)
    expanding = rng > sma(rng, 20) * 1.5
    return persist((was_narrow & expanding).astype(float) * np.sign(df[C] - df["open"]), p["hold"])


# ── Regime & Risk ─────────────────────────────────────────────────────────────

def dd_controlled(df, p, bpy):
    allowed = (1 + dd_from_peak(df[C]) / p["max_dd"]).clip(0, 1)
    return np.sign(ema(df[C], 50) - ema(df[C], 200)) * allowed


def max_dd_guard(df, p, bpy):
    cap = (1 + dd_from_peak(df[C]) / p["limit"]).clip(0, 1)
    return np.sign(ema(df[C], 20) - ema(df[C], 50)) * cap


def ulcer(df, p, bpy):
    dd = dd_from_peak(df[C]) * 100
    u = np.sqrt(sma(dd ** 2, p["window"]))
    return pd.Series(-squash(zscore(u, 120), 1.5), index=df.index)


def sortino(df, p, bpy):
    w = p["window"]
    r = lr(df[C])
    ds = stdev(r.where(r < 0, 0.0), w)
    return pd.Series(squash((sma(r, w) / ds.where(ds > 1e-12) * np.sqrt(bpy)).fillna(0.0), 1.5),
                     index=df.index)


def cornish_fisher(df, p, bpy):
    w = p["window"]
    r = lr(df[C])
    mu, sd = sma(r, w), stdev(r, w)
    s, k = roll_skew(r, w), roll_kurt(r, w)
    z = 1.645
    zcf = z + (z**2 - 1) * s / 6 + (z**3 - 3*z) * k / 24 - (2*z**3 - 5*z) * s**2 / 36
    v = mu - zcf * sd
    trend = np.sign(ema(df[C], 50) - ema(df[C], 200))
    return trend * (1 + pd.Series(squash(zscore(v, w), 1.5), index=df.index)).clip(0, 1)


def evt_tail(df, p, bpy):
    w, tf = p["window"], p["tail_frac"]
    r = lr(df[C])
    thr = percentile_nearest_rank(r, w, 5)
    exceed = sma((r < thr).astype(float), w)
    fatten = ((exceed - tf) / tf).clip(-1, 2)
    trend = np.sign(ema(df[C], 50) - ema(df[C], 200))
    return trend * (1 - fatten.clip(0, 1))


def momentum_crash(df, p, bpy):
    mom = pd.Series(squash(zscore(df[C].pct_change(126), 252), 1.5), index=df.index)
    bear = (dd_from_peak(df[C]) < -0.20).astype(float)
    vr = (rvol(df[C], 20, bpy) > rvol(df[C], 60, bpy)).astype(float)
    return mom * (1 - bear * vr)


def skew_premium(df, p, bpy):
    return pd.Series(-squash(zscore(roll_skew(lr(df[C]), p["window"]), 250), 1.5), index=df.index)


def dd_recovery(df, p, bpy):
    w = p["window"]
    dd = dd_from_peak(df[C])
    trough = lowest(dd, w)
    rec = ((dd - trough) / (-trough).where(trough < -0.01)).clip(0, 1).fillna(0.0)
    deep = (-trough / 0.15).clip(0, 1)
    return pd.Series(squash(rec * deep * 2.0, 0.8), index=df.index)


def vol_budget(df, p, bpy):
    v = rvol(df[C], p["window"], bpy)
    size = (p["budget"] / v.where(v > 1e-6)).clip(0, 1).fillna(0.0)
    return np.sign(ema(df[C], 20) - ema(df[C], 50)) * size


def bull_bear(df, p, bpy):
    dd = dd_from_peak(df[C])
    trough = df[C] / lowest(df[C], 252) - 1.0
    st = pd.Series(np.where(dd <= p["bear_threshold"], -1.0,
                            np.where(trough >= p["bull_threshold"], 1.0, np.nan)),
                   index=df.index).ffill().fillna(0.0)
    return st * 0.7


def vol_regime_switch(df, p, bpy):
    vr = vol_regime(df, p.get("rank_window", 252), bpy)
    z = pd.Series(squash(zscore(df[C], 20), 1.5), index=df.index)
    trend = np.sign(ema(df[C], 20) - ema(df[C], 50))
    return trend * (1 - vr).clip(0, 1) - z * vr.clip(0, 1)


def regime_leverage(df, p, bpy):
    calm = (1 - vol_regime(df, p.get("rank_window", 252), bpy)).clip(0, 1)
    q = trend_strength(df).clip(0, 1)
    healthy = (1 + dd_from_peak(df[C]) / 0.25).clip(0, 1)
    return np.sign(ema(df[C], 50) - ema(df[C], 200)) * (calm * q * healthy) ** (1 / 3)


def trend_fragility(df, p, bpy):
    accel = df[C].pct_change(10) - df[C].pct_change(40) / 4
    vf = -zscore(df["volume"], 40)
    frag = pd.Series(squash(zscore(accel, 60), 1.5), index=df.index).abs() * (1 + vf).clip(0, 2) / 2
    return -np.sign(accel) * frag.clip(0, 1)


def liquidity_stress(df, p, bpy):
    vs = vol_regime(df, p.get("rank_window", 252), bpy)
    rs = percentrank(atr(df, 14) / df[C], 120)
    vd = 1 - percentrank(df["volume"], 120)
    stress = (vs + rs + vd) / 3
    return np.sign(ema(df[C], 20) - ema(df[C], 50)) * (1 - stress).clip(0, 1)


# ── Microstructure ────────────────────────────────────────────────────────────

def ofi(df, p, bpy):
    w = p["window"]
    rng = df["high"] - df["low"]
    pressure = ((2 * (df[C] - df["low"]) / rng.where(rng > 1e-12)) - 1).fillna(0.0)
    return pd.Series(squash(zscore(rsum(pressure * df["volume"], w), 60), 1.5), index=df.index)


def tick_rule(df, p, bpy):
    tick = np.sign(df[C].diff()).replace(0, np.nan).ffill().fillna(0.0)
    return pd.Series(squash(sma(tick, p["window"]) * 2.0, 0.6), index=df.index)


def roll_spread(df, p, bpy):
    w = p["window"]
    r = df[C].pct_change()
    cov = sma(r * r.shift(1), w) - sma(r, w) * sma(r.shift(1), w)
    spread = 2 * np.sqrt((-cov).clip(lower=0))
    return pd.Series(-squash(zscore(spread, 120), 1.5), index=df.index)


def amihud(df, p, bpy):
    r = df[C].pct_change().abs()
    dv = df[C] * df["volume"]
    illiq = sma((r / dv).where(dv > 0, 0.0), p["window"])
    return pd.Series(-squash(zscore(illiq, 120), 1.5), index=df.index)


def kyle_lambda(df, p, bpy):
    w = p["window"]
    sv = np.sign(df[C].diff()) * df["volume"]
    cov = roll_cov(df[C].diff(), sv, w)
    vr = variance(sv, w)
    lam = (cov / vr.where(vr > 1e-12)).fillna(0.0)
    return pd.Series(-squash(zscore(lam, 120), 1.5), index=df.index) * np.sign(lr(df[C]))


def corwin_schultz(df, p, bpy):
    hl = np.log(df["high"] / df["low"]) ** 2
    beta = hl + hl.shift(1)
    h2 = pd.concat([df["high"], df["high"].shift(1)], axis=1).max(axis=1)
    l2 = pd.concat([df["low"], df["low"].shift(1)], axis=1).min(axis=1)
    gamma = np.log(h2 / l2) ** 2
    k = 3 - 2 * np.sqrt(2)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    spread = (2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))).clip(lower=0)
    return pd.Series(-squash(zscore(spread, 120), 1.5), index=df.index)


def vpin(df, p, bpy):
    w = p["window"]
    buy = df["volume"].where(df[C] > df["open"], 0.0)
    sell = df["volume"].where(df[C] < df["open"], 0.0)
    tot = rsum(buy + sell, w)
    imb = (rsum((buy - sell).abs(), w) / tot.where(tot > 0)).fillna(0.0)
    return pd.Series(-squash(zscore(imb, 120), 1.5), index=df.index)


def glosten_milgrom(df, p, bpy):
    d = np.sign(df[C].diff())
    conf = (zscore(df["volume"], 20) > 0).astype(float)
    return pd.Series(squash(sma(d, p["window"]) * 2.0, 0.6), index=df.index) * conf


def bid_ask_bounce(df, p, bpy):
    r = df[C].pct_change()
    ac = correlation(r, r.shift(1), p["window"])
    return pd.Series(-squash(zscore(r, 20), 1.5), index=df.index) * (-ac).clip(0, 1)


def volume_clock(df, p, bpy):
    w = p["window"]
    vt = rsum(df["volume"], w)
    mv = df[C].pct_change(w)
    eff = (mv.abs() / np.sqrt(vt.where(vt > 0))).fillna(0.0)
    return -np.sign(mv) * pd.Series(squash(zscore(eff, 120), 1.5), index=df.index).clip(0, 1)


def iceberg(df, p, bpy):
    w = p["window"]
    rk = percentrank(df["volume"], w)
    stealth = ((rk > 0.4) & (rk < 0.8)).astype(float)
    return pd.Series(squash(sma(stealth * np.sign(df[C].diff()), w) * 3.0, 0.5), index=df.index)


def realized_spread_rev(df, p, bpy):
    rev = -sma(df[C].pct_change(), p["horizon"])
    return pd.Series(squash(zscore(rev, 60), 1.5), index=df.index)


def liquidity_premium(df, p, bpy):
    stress = vol_regime(df, p.get("rank_window", 252), bpy)
    rev = pd.Series(-squash(zscore(df[C].pct_change(), p["window"]), 1.5), index=df.index)
    return rev * stress.clip(0, 1)


def closing_auction(df, p, bpy):
    rng = df["high"] - df["low"]
    cp = ((df[C] - df["low"]) / rng.where(rng > 1e-12)).fillna(0.5)
    heavy = (zscore(df["volume"], p["window"]) > 1.0).astype(float)
    return pd.Series(-band_score(cp, 0.0, 1.0), index=df.index) * heavy


# ── Statistical Arbitrage ─────────────────────────────────────────────────────

def ou_fit(df, p, bpy):
    w = p["window"]
    lag, delta = df[C].shift(1), df[C].diff()
    vr = variance(lag, w)
    theta = -(roll_cov(delta, lag, w) / vr.where(vr > 1e-12))
    mu = (sma(delta, w) / theta.where(theta.abs() > 1e-12)) + sma(lag, w)
    sd = stdev(delta, w)
    dev = ((df[C] - mu) / sd.where(sd > 1e-12)).fillna(0.0)
    return pd.Series(-squash(dev, 2.0), index=df.index).where(theta > 0, 0.0)


def variance_ratio(df, p, bpy):
    q, w = p["q"], p["window"]
    r = lr(df[C])
    v1, vq = variance(r, w), variance(rsum(r, q), w)
    vr = (vq / (q * v1).where(v1 > 1e-16)).fillna(1.0)
    z = pd.Series(squash(zscore(df[C], 20), 1.5), index=df.index)
    trending = (vr - 1.0).clip(-0.5, 0.5) * 2
    return z * trending.clip(0, 1) - z * (-trending).clip(0, 1)


def two_state_regime(df, p, bpy):
    vs, vl = stdev(lr(df[C]), p["short"]), stdev(lr(df[C]), p["long"])
    ratio = (vs / vl.where(vl > 1e-12)).fillna(1.0)
    z20 = zscore(df[C], 20)
    calm = (ratio < 0.9).astype(float)
    stressed = (ratio > 1.4).astype(float)
    return (-pd.Series(squash(z20, 1.5), index=df.index) * calm +
            pd.Series(squash(z20, 2.5), index=df.index) * stressed)


def adf_gated(df, p, bpy):
    w = p["window"]
    lag, delta = df[C].shift(1), df[C].diff()
    vr = variance(lag, w)
    gamma = roll_cov(delta, lag, w) / vr.where(vr > 1e-12)
    se = stdev(delta, w) / (np.sqrt(vr.where(vr > 1e-12)) * np.sqrt(w))
    t = (gamma / se.where(se > 1e-14)).fillna(0.0)
    return pd.Series(-squash(zscore(df[C], 20), 1.5), index=df.index) * (t < p["crit"]).astype(float)


def autocorr_sign(df, p, bpy):
    w = p["window"]
    r = df[C].pct_change()
    ac = correlation(r, r.shift(1), w)
    return pd.Series(squash(zscore(r, 20), 1.5), index=df.index) * (ac * 4).clip(-1, 1)


def bayesian_fair_value(df, p, bpy):
    pw, ow = p["prior_window"], p["obs_window"]
    pm, pv = sma(df[C], pw), variance(df[C], pw)
    om, ov = sma(df[C], ow), variance(df[C], ow)
    pp = (1 / pv.where(pv > 1e-12)).fillna(0.0)
    po = (1 / ov.where(ov > 1e-12)).fillna(0.0)
    denom = pp + po
    post = ((pm * pp + om * po) / denom.where(denom > 1e-18)).fillna(df[C])
    dev = ((df[C] - post) / np.sqrt(pv.where(pv > 1e-12))).fillna(0.0)
    return pd.Series(-squash(dev, 1.5), index=df.index)


def copula_tail(df, p, bpy):
    w = p["window"]
    u = percentrank(df[C].pct_change(), w)
    v = percentrank(df[C].pct_change(10), w)
    return pd.Series(squash((v - u) * 2.0, 0.7), index=df.index)


def turbulence(df, p, bpy):
    w = p["window"]
    r = lr(df[C])
    mu, sd = sma(r, w), stdev(r, w)
    d2 = ((r - mu) / sd.where(sd > 1e-12)) ** 2
    return pd.Series(-squash(zscore(df[C], 20), 1.5), index=df.index) * \
        (1 - percentrank(d2, w)).clip(0, 1)


def vol_conditional_spread(df, p, bpy):
    calm = (1 - vol_regime(df, p.get("rank_window", 252), bpy)).clip(0, 1)
    return pd.Series(-squash(zscore(df[C], p["window"]), 1.5), index=df.index) * calm


def hurst_regime(df, p, bpy):
    w = p["window"]
    r = lr(df[C])

    def _rs(win: np.ndarray) -> float:
        m = win.mean()
        cum = np.cumsum(win - m)
        rng = cum.max() - cum.min()
        s = win.std()
        return float(np.log(rng / s) / np.log(len(win))) if (rng > 1e-12 and s > 1e-12) else 0.5

    h = r.rolling(w, min_periods=w).apply(_rs, raw=True)
    z = pd.Series(squash(zscore(df[C], 20), 1.5), index=df.index)
    return z * ((h - 0.5) * 4).clip(-1, 1)


def kalman_state(df, p, bpy):
    scl = median(df[C].diff().abs(), 200)
    c = df[C].to_numpy(dtype=float)
    sc = scl.fillna(1.0).to_numpy()
    xh = np.full(len(c), np.nan)
    pp = np.full(len(c), np.nan)
    xh[0], pp[0] = c[0], 1.0
    for i in range(1, len(c)):
        s = sc[i] if sc[i] > 0 else 1.0
        q = p["process_var"] * s ** 2 * 10000.0
        rr = p["measure_var"] * s ** 2
        pm = pp[i - 1] + q
        k = pm / (pm + rr)
        xh[i] = xh[i - 1] + k * (c[i] - xh[i - 1])
        pp[i] = (1 - k) * pm
    st = pd.Series(xh, index=df.index)
    a = atr(df, 14)
    return pd.Series(-squash(((df[C] - st) / a.where(a > 1e-12)).fillna(0.0), 1.5), index=df.index)


# ── Factor / Macro ────────────────────────────────────────────────────────────

def low_vol_anomaly(df, p, bpy):
    rk = percentrank(rvol(df[C], p["window"], bpy), p["rank_window"])
    return pd.Series(-band_score(rk, 0.0, 1.0), index=df.index)


def technical_value(df, p, bpy):
    lm = sma(df[C], p["window"])
    return pd.Series(-squash(np.log(df[C] / lm), 0.25), index=df.index)


def kelly(df, p, bpy):
    w = p["window"]
    r = lr(df[C])
    v = variance(r, w)
    return pd.Series(squash(((sma(r, w) / v.where(v > 1e-14)) * p["fraction"]).fillna(0.0), 20.0),
                     index=df.index)


def max_sharpe(df, p, bpy):
    w = p["window"]
    r = lr(df[C])
    mu, sd = sma(r, w) * bpy, stdev(r, w) * np.sqrt(bpy)
    return pd.Series(squash((mu / sd.where(sd > 1e-9)).fillna(0.0), 1.0), index=df.index)


def risk_parity(df, p, bpy):
    v = rvol(df[C], p["window"], bpy)
    w = (p["target"] / v.where(v > 1e-6)).clip(0, 1.5).fillna(0.0)
    return (np.sign(ema(df[C], 50) - ema(df[C], 200)) * w / 1.5).clip(-1, 1)


def gap_drift(df, p, bpy):
    gap = (df["open"] - df[C].shift(1)) / df[C].shift(1)
    z = zscore(gap, 120)
    shock = np.sign(z) * (z.abs() > p["threshold_sd"]).astype(float)
    return persist(shock, p["hold"]) * 0.7


def faber(df, p, bpy):
    ma = sma(df[C], p["window"])
    above = (df[C] > ma).astype(float)
    margin = pd.Series(squash(((df[C] - ma) / ma.abs()).fillna(0.0), 0.05), index=df.index)
    return above * margin.clip(0, 1) - (1 - above) * margin.abs().clip(0, 1)


def absolute_momentum(df, p, bpy):
    lb = p["lookback"]
    return pd.Series(squash((df[C] - df[C].shift(lb)) / df[C].shift(lb), 0.15), index=df.index)


def vol_target_overlay(df, p, bpy):
    rz = rvol(df[C], p["window"], bpy)
    lev = (p["target"] / rz.where(rz > 1e-6)).clip(0, p["max_leverage"]).fillna(0.0)
    trend = np.sign(sma(df[C], 200).diff())
    return (trend * lev / p["max_leverage"]).clip(-1, 1)


def trend_carry(df, p, bpy):
    vol = stdev(lr(df[C]), 60)
    trend = pd.Series(squash((np.log(df[C] / df[C].shift(252)) /
                              (vol.where(vol > 1e-9) * np.sqrt(252))).fillna(0.0), 1.0),
                      index=df.index)
    carry = pd.Series(squash((sma(lr(df[C]), 63) / vol.where(vol > 1e-9)).fillna(0.0), 0.2),
                      index=df.index)
    return (0.6 * trend + 0.4 * carry).clip(-1, 1)


def cppi(df, p, bpy):
    peak = df[C].cummax()
    cushion = ((df[C] - peak * p["floor"]) / peak).clip(lower=0)
    return np.sign(sma(df[C], 50) - sma(df[C], 200)) * (cushion * p["multiplier"]).clip(0, 1)


def two_regime_alloc(df, p, bpy):
    stressed = ((vol_regime(df, p.get("rank_window", 252), bpy) > 0.7) |
                (dd_from_peak(df[C]) < -0.15)).astype(float)
    risk_on = np.sign(sma(df[C], 50) - sma(df[C], 200))
    risk_off = pd.Series(-squash(zscore(df[C], 20), 1.5), index=df.index) * 0.5
    return risk_on * (1 - stressed) + risk_off * stressed


# ── Seasonality ───────────────────────────────────────────────────────────────

def halloween(df, p, bpy):
    m = df.index.month
    return pd.Series(np.where((m >= 11) | (m <= 4), 0.45, -0.25), index=df.index)


def january_effect(df, p, bpy):
    m, d = df.index.month, df.index.day
    return pd.Series(np.where((m == 1) & (d <= 15), 0.5,
                              np.where((m == 12) & (d >= 20), 0.3, 0.0)), index=df.index)


def turn_of_month(df, p, bpy):
    dom = df.index.day
    dim = df.index.days_in_month
    near = ((dim - dom) <= p["days_before"]) | (dom <= p["days_after"])
    return pd.Series(np.where(near, 0.6, -0.15), index=df.index)


def expiry_week(df, p, bpy):
    dom = df.index.day
    inw = ((dom >= 15) & (dom <= 21)).astype(float)
    return pd.Series(-squash(zscore(df[C], 20), 1.5), index=df.index) * inw * 0.8


def quarter_end(df, p, bpy):
    m, dom, dim = df.index.month, df.index.day, df.index.days_in_month
    win = (np.isin(m, [3, 6, 9, 12]) & ((dim - dom) <= 3)).astype(float)
    return pd.Series(-squash(zscore(df[C].pct_change(63), 120), 1.5), index=df.index) * win


def overnight_intraday(df, p, bpy):
    onr = np.log(df["open"] / df[C].shift(1))
    idr = np.log(df[C] / df["open"])
    vol = stdev(lr(df[C]), 60)
    return pd.Series(squash(((sma(onr, 60) - sma(idr, 60)) / vol.where(vol > 1e-12)).fillna(0.0),
                            0.5), index=df.index)


def macro_seasonality(df, p, bpy):
    m = df.index.month
    seasonal = pd.Series(np.where((m >= 11) | (m <= 4), 0.5, -0.2), index=df.index)
    trend = np.sign(sma(df[C], 50) - sma(df[C], 200))
    return seasonal.where(np.sign(seasonal) == trend, seasonal * 0.25)


# ── Options / Crypto / Sentiment ──────────────────────────────────────────────

def vol_cone(df, p, bpy):
    rw = p["rank_window"]
    avg = (percentrank(rvol(df[C], 10, bpy), rw) + percentrank(rvol(df[C], 20, bpy), rw) +
           percentrank(rvol(df[C], 60, bpy), rw)) / 3
    return pd.Series(-band_score(avg, 0.0, 1.0), index=df.index) * np.sign(zscore(df[C], 20))


def implied_move(df, p, bpy):
    h = p["horizon"]
    expd = stdev(lr(df[C]), 60) * np.sqrt(h)
    act = df[C].pct_change(h).abs()
    ratio = (act / expd.where(expd > 1e-9)).fillna(1.0)
    return -np.sign(df[C].pct_change(h)) * pd.Series(squash(ratio - 1, 0.6),
                                                     index=df.index).clip(0, 1)


def vrp_proxy(df, p, bpy):
    realized = rvol(df[C], p["short"], bpy)
    implied = rvol(df[C], p["long"], bpy) * p["premium"]
    return pd.Series(squash(zscore(implied - realized, 120), 1.5), index=df.index)


def vol_curve_slope(df, p, bpy):
    n, f = rvol(df[C], p["near"], bpy), rvol(df[C], p["far"], bpy)
    return pd.Series(-squash(((n - f) / f.where(f > 1e-9)).fillna(0.0), 0.25), index=df.index)


def gamma_scalp(df, p, bpy):
    w = p["window"]
    pv = rsum(lr(df[C]).abs(), w)
    nm = np.log(df[C] / df[C].shift(w)).abs()
    chop = ((pv - nm) / pv.where(pv > 1e-12)).fillna(0.0)
    return pd.Series(squash(zscore(chop, 120), 1.5), index=df.index)


def vix_roll(df, p, bpy):
    n, f = rvol(df[C], 10, bpy), rvol(df[C], 60, bpy)
    return pd.Series(squash(((f - n) / f.where(f > 1e-9)).fillna(0.0), 0.25),
                     index=df.index).clip(-1, 1)


def crypto_tsmom(df, p, bpy):
    lb = p["lookback"]
    vol = stdev(lr(df[C]), 60) * np.sqrt(lb)
    return pd.Series(squash((np.log(df[C] / df[C].shift(lb)) / vol.where(vol > 1e-9)).fillna(0.0),
                            1.0), index=df.index)


def commodity_tsmom(df, p, bpy):
    return crypto_tsmom(df, p, bpy)


def crypto_vol_regime(df, p, bpy):
    rank = vol_regime(df, p.get("rank_window", 252), bpy)
    return np.sign(ema(df[C], 20) - ema(df[C], 50)) * (1 - rank).clip(0, 1)


def liquidation_cascade(df, p, bpy):
    a = atr(df, 14)
    violent = true_range(df) > a * p["range_mult"]
    heavy = zscore(df["volume"], 20) > p["vol_z"]
    rng = df["high"] - df["low"]
    lw = ((df[C] - df["low"]) / rng.where(rng > 1e-12)).fillna(0.5)
    uw = ((df["high"] - df[C]) / rng.where(rng > 1e-12)).fillna(0.5)
    cd = (violent & heavy & (lw > 0.6)).astype(float)
    cu = (violent & heavy & (uw > 0.6)).astype(float)
    return persist(cd - cu, p["hold"])


def crypto_weekend(df, p, bpy):
    we = pd.Series(np.isin(df.index.dayofweek, [5, 6]).astype(float), index=df.index)
    return pd.Series(-squash(zscore(df[C].pct_change(), 20), 1.5), index=df.index) * we


def volume_profile(df, p, bpy):
    w = p["window"]
    tp = (df["high"] + df["low"] + df[C]) / 3
    vv = rsum(df["volume"], w)
    poc = (rsum(tp * df["volume"], w) / vv.where(vv > 1e-12)).fillna(sma(tp, w))
    a = atr(df, 14)
    return pd.Series(-squash(((df[C] - poc) / a.where(a > 1e-12)).fillna(0.0), 1.5), index=df.index)


def capitulation(df, p, bpy):
    a = atr(df, 14)
    rng = df["high"] - df["low"]
    cp = ((df[C] - df["low"]) / rng.where(rng > 1e-12)).fillna(0.5)
    climax = zscore(df["volume"], 20) > p["vol_z"]
    wide = true_range(df) > a * 1.8
    buy = (climax & wide & (df[C] < df["open"]) & (cp > 0.55)).astype(float)
    sell = (climax & wide & (df[C] > df["open"]) & (cp < 0.45)).astype(float)
    return persist(buy - sell, p["hold"])


def fear_gauge(df, p, bpy):
    fear = vol_regime(df, 252, bpy)
    falling = (df[C].pct_change(5) < 0).astype(float)
    return (fear * falling * 2 - fear * (1 - falling) * 0.5).clip(-1, 1)


def duration_timing(df, p, bpy):
    slow = sma(df[C], 200)
    trend = pd.Series(squash(((sma(df[C], 50) - slow) / slow.abs()).fillna(0.0), 0.02),
                      index=df.index)
    calm = (1 - vol_regime(df, 252, bpy)).clip(0, 1)
    return trend * calm


# ── registry ──────────────────────────────────────────────────────────────────

CHECKS = {
    # Trend & Momentum
    "Donchian Channel Breakout": donchian_breakout,
    "EMA 50/200 Golden Cross": ema_cross,
    "MACD Histogram Momentum": macd_hist,
    "ADX Directional Movement": adx_dm,
    "Aroon Oscillator": aroon,
    "Keltner Channel Trend": keltner_trend,
    "Vortex Indicator": vortex,
    "Rolling Regression Slope (t-stat)": regression_slope,
    "Hull Moving Average Slope": hull_slope,
    "TRIX Triple-Smoothed Momentum": trix,
    "Chande Momentum Oscillator": cmo,
    "52-Week High Proximity": high52w,
    "Time-Series Momentum (12-1)": tsmom,
    "Trend Quality (R-squared Gated)": trend_quality,
    "Failed Breakout Reversal": failed_breakout,
    "Volume-Confirmed Range Breakout": volume_breakout,
    "Turtle Trading System 1": turtle,
    "Kaufman Adaptive Moving Average": kama,
    "Coppock Curve": coppock,
    "Dual Momentum (Absolute + Relative)": dual_momentum,
    "Guppy Multiple Moving Average": guppy,
    "Momentum Acceleration (2nd Derivative)": momentum_accel,
    "Volatility-Scaled Trend (CTA Core)": cta_core,
    "ATR-Normalised Trend Exposure": atr_trend_exposure,
    # Mean Reversion
    "Bollinger Band Mean Reversion": bollinger_rev,
    "RSI(2) Extreme Reversion": rsi2,
    "Price Z-Score Reversion": zscore_rev,
    "Stochastic Oscillator Reversion": stoch_rev,
    "Williams %R Reversion": williams_r,
    "Commodity Channel Index Reversion": cci_rev,
    "Money Flow Index Reversion": mfi_rev,
    "Ultimate Oscillator": ultimate_osc,
    "Keltner Channel Reversion": keltner_rev,
    "VWAP Reversion": vwap_rev,
    "Short-Term Reversal (1-Period)": short_reversal,
    "Long-Term Reversal (De Bondt-Thaler)": long_reversal,
    "Overnight Gap Fade": gap_fade,
    "Bollinger Squeeze Release": squeeze_release,
    "Average Daily Range Exhaustion": adr_exhaustion,
    "Range-Bound Channel Oscillator": range_oscillator,
    "Opening Range Reversal": opening_range_rev,
    "RSI Regular Divergence": rsi_divergence,
    "TD Sequential Setup Count": td_sequential,
    "Half-Life Gated Reversion": half_life_gated,
    "Fat-Tail Move Reversion": fat_tail_rev,
    # Volatility
    "Yang-Zhang Drift-Independent Volatility": yang_zhang,
    "Parkinson Range Volatility Divergence": parkinson_div,
    "Garman-Klass Volatility Efficiency": garman_klass,
    "Rogers-Satchell Drift-Robust Volatility": rogers_satchell,
    "Bipower Variation Jump Detection": bipower,
    "Merton Jump-Diffusion Discrepancy": merton_jump,
    "Realized Skewness Premium": realized_skew,
    "Volatility of Volatility": vol_of_vol,
    "Realized Volatility Term Structure": vol_term_structure,
    "Volatility Clustering Persistence": vol_clustering,
    "Volatility-Managed Portfolio": vol_managed,
    "HAR-RV Heterogeneous Autoregression": har_rv,
    "EGARCH Leverage Asymmetry": egarch_asym,
    "Volatility Mean Reversion": vol_mean_rev,
    "Volatility Expansion Breakout": vol_breakout,
    # Regime & Risk
    "Drawdown-Controlled Exposure": dd_controlled,
    "Maximum Drawdown Guard": max_dd_guard,
    "Ulcer Index Downside Risk": ulcer,
    "Sortino Downside Deviation": sortino,
    "Cornish-Fisher Modified VaR": cornish_fisher,
    "Extreme Value Theory Tail Estimate": evt_tail,
    "Momentum Crash Risk": momentum_crash,
    "Skewness Risk Premium": skew_premium,
    "Drawdown Recovery Momentum": dd_recovery,
    "Volatility Budget Allocation": vol_budget,
    "Bull-Bear Market Classifier": bull_bear,
    "Volatility Regime Switch": vol_regime_switch,
    "Regime-Conditional Leverage": regime_leverage,
    "Trend Fragility Index": trend_fragility,
    "Composite Liquidity Stress": liquidity_stress,
    # Microstructure
    "Order Flow Imbalance": ofi,
    "Tick Rule Signed Flow": tick_rule,
    "Roll Effective Spread Estimator": roll_spread,
    "Amihud Illiquidity Ratio": amihud,
    "Kyle's Lambda (Price Impact)": kyle_lambda,
    "Corwin-Schultz High-Low Spread": corwin_schultz,
    "VPIN Order Flow Toxicity": vpin,
    "Glosten-Milgrom Adverse Selection": glosten_milgrom,
    "Bid-Ask Bounce Reversal": bid_ask_bounce,
    "Volume Clock Information Arrival": volume_clock,
    "Volume Concentration (Iceberg Detection)": iceberg,
    "Realized Spread Price Reversal": realized_spread_rev,
    "Liquidity Provision Premium": liquidity_premium,
    "Closing Auction Pressure": closing_auction,
    # Statistical Arbitrage
    "Ornstein-Uhlenbeck Process Fit": ou_fit,
    "Lo-MacKinlay Variance Ratio": variance_ratio,
    "Two-State Gaussian Regime Filter": two_state_regime,
    "ADF Stationarity-Gated Reversion": adf_gated,
    "Return Autocorrelation Sign": autocorr_sign,
    "Bayesian Posterior Fair Value": bayesian_fair_value,
    "Copula Tail Dependence": copula_tail,
    "Financial Turbulence Index": turbulence,
    "Volatility-Conditional Spread Trade": vol_conditional_spread,
    "Hurst Exponent Regime Switch": hurst_regime,
    "Kalman Filter State Estimate": kalman_state,
    # Factor & Macro
    "Low Volatility Anomaly": low_vol_anomaly,
    "Technical Value (5-Year Mean Reversion)": technical_value,
    "Kelly Criterion Optimal Fraction": kelly,
    "Maximum Sharpe Tilt": max_sharpe,
    "Risk Parity Exposure": risk_parity,
    "Large Gap Continuation Drift": gap_drift,
    "Faber 10-Month Timing Model": faber,
    "Absolute Momentum Filter": absolute_momentum,
    "Volatility Target Overlay": vol_target_overlay,
    "Trend + Carry Composite": trend_carry,
    "Drawdown-Scaled Allocation": cppi,
    "Two-Regime Allocation Switch": two_regime_alloc,
    # Seasonality
    "Halloween Indicator (Sell in May)": halloween,
    "January Effect": january_effect,
    "Turn-of-the-Month Effect": turn_of_month,
    "Options Expiry Week Effect": expiry_week,
    "Quarter-End Rebalancing Flow": quarter_end,
    "Overnight vs Intraday Return Split": overnight_intraday,
    "Macro Seasonality Overlay": macro_seasonality,
    # Options / Crypto / Sentiment
    "Realized Volatility Cone": vol_cone,
    "Straddle-Implied Move vs Realized": implied_move,
    "Volatility Risk Premium Proxy": vrp_proxy,
    "Volatility Curve Slope Proxy": vol_curve_slope,
    "Gamma Scalping Profitability": gamma_scalp,
    "VIX Roll Short (Contango Harvest)": vix_roll,
    "Crypto Time-Series Momentum": crypto_tsmom,
    "Commodity Time-Series Momentum": commodity_tsmom,
    "Crypto Volatility Regime": crypto_vol_regime,
    "Liquidation Cascade Reversal": liquidation_cascade,
    "Crypto Weekend Liquidity Effect": crypto_weekend,
    "Volume Profile Value Area": volume_profile,
    "Capitulation Volume Climax": capitulation,
    "Volatility Fear Gauge": fear_gauge,
    "Duration Timing (Price-Based)": duration_timing,
}
