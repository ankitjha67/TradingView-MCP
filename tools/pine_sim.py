"""
Pine Script semantics, re-implemented in pandas.

This is the reference implementation the verifier compares against. It is written
from the **Pine documentation**, not from the engine's ``features.py`` — that
independence is the whole point. If both sides were derived from the same code, a
shared mistake would verify as a match.

Where Pine and pandas differ in convention, the Pine behaviour wins here:

* ``ta.sma(src, len)`` returns ``na`` until ``len`` bars exist. pandas would
  happily compute on a partial window; ``sma()`` below does not.
* ``ta.stdev(src, len, false)`` is the population standard deviation (ddof=0).
* ``ta.ema`` seeds from an SMA of the first ``len`` bars, then applies
  ``alpha = 2/(len+1)``. ``pandas.ewm(adjust=False)`` seeds from the first value
  instead — a warm-up-only difference, reproduced faithfully here.
* ``ta.rma`` (Wilder) uses ``alpha = 1/len`` and is what ``ta.atr`` and
  ``ta.rsi`` are built on.
* ``ta.percentrank(src, len)`` counts how many of the **previous** ``len`` values
  are below the current one — the current value is not in its own denominator,
  unlike ``Series.rank(pct=True)``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ── core rolling primitives ───────────────────────────────────────────────────

def sma(src: pd.Series, n: int) -> pd.Series:
    return src.rolling(n, min_periods=n).mean()


def stdev(src: pd.Series, n: int) -> pd.Series:
    """ta.stdev(..., biased=false) → population stdev."""
    return src.rolling(n, min_periods=n).std(ddof=0)


def variance(src: pd.Series, n: int) -> pd.Series:
    return src.rolling(n, min_periods=n).var(ddof=0)


def rsum(src: pd.Series, n: int) -> pd.Series:
    """math.sum(src, n)."""
    return src.rolling(n, min_periods=n).sum()


def highest(src: pd.Series, n: int) -> pd.Series:
    return src.rolling(n, min_periods=n).max()


def lowest(src: pd.Series, n: int) -> pd.Series:
    return src.rolling(n, min_periods=n).min()


def change(src: pd.Series, n: int = 1) -> pd.Series:
    return src.diff(n)


def correlation(x: pd.Series, y: pd.Series, n: int) -> pd.Series:
    return x.rolling(n, min_periods=n).corr(y)


def ema(src: pd.Series, n: int) -> pd.Series:
    """ta.ema: SMA-seeded, then alpha = 2/(n+1). NaN-safe."""
    a = 2.0 / (n + 1.0)
    v = src.to_numpy(dtype=float)
    out = np.full(len(v), np.nan)
    valid = np.flatnonzero(~np.isnan(v))
    if len(valid) < n:
        return pd.Series(out, index=src.index)
    # Seed at the n-th non-NaN observation; a leading NaN must not poison the
    # whole recursion, which is what a naive out[i-1] chain would do.
    start = valid[n - 1]
    out[start] = float(np.mean(v[valid[:n]]))
    for i in range(start + 1, len(v)):
        prev = out[i - 1]
        out[i] = prev if np.isnan(v[i]) else a * v[i] + (1 - a) * prev
    return pd.Series(out, index=src.index)


def rma(src: pd.Series, n: int) -> pd.Series:
    """Wilder smoothing: alpha = 1/n, SMA-seeded. Basis of ta.atr and ta.rsi."""
    a = 1.0 / n
    v = src.to_numpy(dtype=float)
    out = np.full(len(v), np.nan)
    valid = np.flatnonzero(~np.isnan(v))
    if len(valid) < n:
        return pd.Series(out, index=src.index)
    # Seed at the n-th non-NaN observation; a leading NaN must not poison the
    # whole recursion, which is what a naive out[i-1] chain would do.
    start = valid[n - 1]
    out[start] = float(np.mean(v[valid[:n]]))
    for i in range(start + 1, len(v)):
        prev = out[i - 1]
        out[i] = prev if np.isnan(v[i]) else a * v[i] + (1 - a) * prev
    return pd.Series(out, index=src.index)


def percentrank(src: pd.Series, n: int) -> pd.Series:
    """
    The emitted Pine ``prank()``: rank of the current value within its own window.

    Pine's raw ``ta.percentrank`` counts only prior values below the current one.
    ``prank`` adds the current observation to both count and denominator so it
    matches pandas ``rank(pct=True)``, and this reproduces that adjusted form.
    """
    def _pr(win: np.ndarray) -> float:
        cur, prior = win[-1], win[:-1]
        return (float((prior < cur).sum()) + 1.0) / n
    return src.rolling(n, min_periods=n).apply(_pr, raw=True)


def median(src: pd.Series, n: int) -> pd.Series:
    return src.rolling(n, min_periods=n).median()


def percentile_linear_interpolation(src: pd.Series, n: int, pct: float) -> pd.Series:
    """
    ta.percentile_linear_interpolation.

    The linear-interpolation variant is the one that matches pandas .quantile(),
    whose default interpolation is linear. ta.percentile_nearest_rank snaps to an
    observed value and drifts from the engine near the tail.
    """
    return src.rolling(n, min_periods=n).quantile(pct / 100.0, interpolation="linear")


# Kept under the old name so existing checks resolve.
percentile_nearest_rank = percentile_linear_interpolation


def linreg(src: pd.Series, n: int, offset: int = 0) -> pd.Series:
    """ta.linreg: value of the fitted line at `offset` bars back from the last."""
    idx = np.arange(n, dtype=float)
    xm = idx.mean()
    varx = ((idx - xm) ** 2).sum()

    def _lr(win: np.ndarray) -> float:
        ym = win.mean()
        slope = float(((idx - xm) * (win - ym)).sum() / varx)
        intercept = ym - slope * xm
        return intercept + slope * (n - 1 - offset)
    return src.rolling(n, min_periods=n).apply(_lr, raw=True)


# ── indicator primitives ──────────────────────────────────────────────────────

def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift(1)
    return pd.concat([df["high"] - df["low"],
                      (df["high"] - pc).abs(),
                      (df["low"] - pc).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return rma(true_range(df), n)


def rsi(src: pd.Series, n: int = 14) -> pd.Series:
    d = src.diff()
    up = rma(d.clip(lower=0), n)
    dn = rma((-d).clip(lower=0), n)
    rs = up / dn.where(dn > 0)
    return (100 - 100 / (1 + rs)).fillna(100.0).where(dn.notna())


def dmi(df: pd.DataFrame, n: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    """ta.dmi → (+DI, -DI, ADX)."""
    up_move = df["high"].diff()
    dn_move = -df["low"].diff()
    plus_dm = up_move.where((up_move > dn_move) & (up_move > 0), 0.0)
    minus_dm = dn_move.where((dn_move > up_move) & (dn_move > 0), 0.0)
    tr_n = rma(true_range(df), n)
    pdi = 100 * rma(plus_dm, n) / tr_n.where(tr_n > 0)
    mdi = 100 * rma(minus_dm, n) / tr_n.where(tr_n > 0)
    s = (pdi + mdi)
    dx = 100 * (pdi - mdi).abs() / s.where(s > 0)
    return pdi, mdi, rma(dx, n)


def stoch(close: pd.Series, high: pd.Series, low: pd.Series, n: int) -> pd.Series:
    ll, hh = lowest(low, n), highest(high, n)
    rng = hh - ll
    return 100 * (close - ll) / rng.where(rng > 0)


def cci(df: pd.DataFrame, n: int) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    m = sma(tp, n)
    md = (tp - m).abs().rolling(n, min_periods=n).mean()
    return (tp - m) / (0.015 * md).where(md > 0)


def mfi(df: pd.DataFrame, n: int) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    rmf = tp * df["volume"]
    up = rmf.where(tp.diff() > 0, 0.0).rolling(n, min_periods=n).sum()
    dn = rmf.where(tp.diff() < 0, 0.0).rolling(n, min_periods=n).sum()
    return 100 - 100 / (1 + up / dn.where(dn > 0))


def hma(src: pd.Series, n: int) -> pd.Series:
    def wma(s: pd.Series, k: int) -> pd.Series:
        w = np.arange(1, k + 1, dtype=float)
        return s.rolling(k, min_periods=k).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)
    return wma(2 * wma(src, max(1, n // 2)) - wma(src, n), max(1, int(np.sqrt(n))))


def wma(src: pd.Series, n: int) -> pd.Series:
    w = np.arange(1, n + 1, dtype=float)
    return src.rolling(n, min_periods=n).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)


# ── engine-shared helper equivalents (as defined in the emitted Pine) ─────────

def squash(x, s: float):
    """Pine squash(): tanh with the ±20 clamp."""
    z = np.clip(np.asarray(x, dtype=float) / s, -20, 20)
    return np.tanh(z)


def zscore(src: pd.Series, n: int) -> pd.Series:
    m, sd = sma(src, n), stdev(src, n)
    return ((src - m) / sd.where(sd > 1e-12)).fillna(0.0)


def zscore_skipna(src: pd.Series, n: int) -> pd.Series:
    """Pine zscoreSkipNa(): rolling z-score ignoring NaN, as pandas rolling does."""
    valid = src.notna().astype(float)
    fill = src.fillna(0.0)
    cnt = valid.rolling(n, min_periods=n).sum()
    m = fill.rolling(n, min_periods=n).sum() / cnt.where(cnt > 0)
    v = ((fill ** 2).rolling(n, min_periods=n).sum() / cnt.where(cnt > 0) - m ** 2).clip(lower=0)
    sd = np.sqrt(v)
    return ((src - m) / sd.where(sd > 1e-12)).fillna(0.0)


def band_score(x, lo: float, hi: float):
    return np.clip(2 * (np.asarray(x, dtype=float) - lo) / (hi - lo) - 1, -1, 1)


def lr(close: pd.Series) -> pd.Series:
    return np.log(close).diff()


def rvol(close: pd.Series, n: int, bpy: int) -> pd.Series:
    return stdev(lr(close), n) * np.sqrt(bpy)


def eff_ratio(close: pd.Series, p: int) -> pd.Series:
    return (close - close.shift(p)).abs() / rsum(close.diff().abs(), p).clip(lower=1e-12)


def trend_strength(df: pd.DataFrame) -> pd.Series:
    _, _, adx = dmi(df, 14)
    return (adx / 50).clip(0, 1) * 0.5 + eff_ratio(df["close"], 20).clip(0, 1) * 0.5


def vol_regime(df: pd.DataFrame, rank_len: int, bpy: int) -> pd.Series:
    return percentrank(rvol(df["close"], 20, bpy), rank_len)


def dd_from_peak(close: pd.Series) -> pd.Series:
    return close / close.cummax() - 1.0


def roll_skew(src: pd.Series, n: int) -> pd.Series:
    """
    Rolling skew via expanded central moments, bias-corrected as pandas does.

    Written this way because ``sma((src - m) ** 3, n)`` subtracts each bar's own
    rolling mean rather than the window's, which is a materially different (and
    wrong) quantity.
    """
    m = sma(src, n)
    e2, e3 = sma(src ** 2, n), sma(src ** 3, n)
    m2 = e2 - m ** 2
    m3 = e3 - 3 * m * e2 + 2 * m ** 3
    g1 = (m3 / (m2 ** 1.5).where(m2 > 1e-18)).fillna(0.0)
    return g1 * np.sqrt(n * (n - 1.0)) / (n - 2.0) if n > 2 else g1 * 0.0


def roll_kurt(src: pd.Series, n: int) -> pd.Series:
    """Rolling excess kurtosis via expanded central moments, bias-corrected."""
    m = sma(src, n)
    e2, e3, e4 = sma(src ** 2, n), sma(src ** 3, n), sma(src ** 4, n)
    m2 = e2 - m ** 2
    m4 = e4 - 4 * m * e3 + 6 * m ** 2 * e2 - 3 * m ** 4
    g2 = (m4 / (m2 ** 2).where(m2 > 1e-18) - 3.0).fillna(0.0)
    if n <= 3:
        return g2 * 0.0
    return ((n + 1.0) * g2 + 6.0) * (n - 1.0) / ((n - 2.0) * (n - 3.0))


def roll_cov(x: pd.Series, y: pd.Series, n: int) -> pd.Series:
    return sma(x * y, n) - sma(x, n) * sma(y, n)


def persist(raw: pd.Series, bars: int) -> pd.Series:
    """Pine persist(): hold a non-zero value for `bars` bars after it fires."""
    v = raw.fillna(0.0).to_numpy(dtype=float)
    out = np.zeros(len(v))
    held, age = 0.0, 0
    for i, r in enumerate(v):
        if r != 0.0:
            held, age = r, 0
        else:
            age += 1
            if age > bars:
                held = 0.0
        out[i] = held
    return pd.Series(out, index=raw.index)


BPY = {"1m": 98280, "5m": 19656, "15m": 6552, "30m": 3276,
       "1h": 1764, "4h": 504, "1d": 252, "1wk": 52, "1mo": 12}
