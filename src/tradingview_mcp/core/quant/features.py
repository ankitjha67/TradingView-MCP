"""
Shared feature engine.

Every strategy in the library reads from a single ``FeatureSet`` that is computed
once per (symbol, interval, dataframe) and reused across all models. This is the
difference between "200 models in 2 seconds" and "200 models in 4 minutes": the
previous implementation re-sliced a DataFrame and recomputed every indicator
inside a per-bar Python loop, once per strategy.

Everything here is vectorised over the whole frame. No look-ahead: every series
is causal (uses only information available at or before its own bar).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from functools import cached_property
from typing import Optional

import numpy as np
import pandas as pd

# Bars per year, used to annualise volatility and Sharpe by interval.
BARS_PER_YEAR = {
    "1m": 252 * 390, "2m": 252 * 195, "5m": 252 * 78, "15m": 252 * 26,
    "30m": 252 * 13, "1h": 252 * 7, "2h": 252 * 4, "4h": 252 * 2,
    "1d": 252, "1wk": 52, "1mo": 12,
}


def _safe_div(a, b, fill: float = 0.0):
    """Element-wise divide that never raises and never yields inf/NaN."""
    with np.errstate(divide="ignore", invalid="ignore"):
        out = a / b
    if isinstance(out, pd.Series):
        return out.replace([np.inf, -np.inf], np.nan).fillna(fill)
    out = np.asarray(out, dtype=float)
    out[~np.isfinite(out)] = fill
    return out


def zscore(series: pd.Series, window: int, min_periods: Optional[int] = None) -> pd.Series:
    """Rolling z-score. Zero-variance windows collapse to 0 rather than inf."""
    mp = min_periods if min_periods is not None else max(2, window // 2)
    mean = series.rolling(window, min_periods=mp).mean()
    std = series.rolling(window, min_periods=mp).std(ddof=0)
    return _safe_div(series - mean, std.where(std > 1e-12))


def rolling_rank(series: pd.Series, window: int) -> pd.Series:
    """Percentile rank of the current value within its trailing window (0..1)."""
    return series.rolling(window, min_periods=max(2, window // 2)).rank(pct=True)


def wilder_ema(series: pd.Series, period: int) -> pd.Series:
    """Wilder's smoothing (RMA) — the average used throughout Wilder (1978)."""
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def linreg_slope(series: pd.Series, window: int) -> pd.Series:
    """
    Rolling OLS slope against a 0..n-1 time index, computed in closed form.

    slope = cov(x, y) / var(x); with x fixed, var(x) is a constant, so this is a
    couple of rolling means instead of a regression per bar.
    """
    n = window
    x_mean = (n - 1) / 2.0
    var_x = (n * n - 1) / 12.0
    idx = np.arange(n, dtype=float) - x_mean

    def _slope(win: np.ndarray) -> float:
        return float(np.dot(win - win.mean(), idx) / (n * var_x))

    return series.rolling(n, min_periods=n).apply(_slope, raw=True)


@dataclass
class FeatureSet:
    """
    Causal indicator bundle for a single OHLCV series.

    Indicators are lazily computed via ``cached_property`` so a strategy that
    only needs RSI does not pay for the Yang-Zhang volatility estimator, but any
    indicator touched by two strategies is computed exactly once.
    """

    df: pd.DataFrame
    interval: str = "1d"
    symbol: str = ""
    meta: dict = field(default_factory=dict)

    # ── raw columns ───────────────────────────────────────────────────────────
    @cached_property
    def open(self) -> pd.Series: return self.df["open"].astype(float)

    @cached_property
    def high(self) -> pd.Series: return self.df["high"].astype(float)

    @cached_property
    def low(self) -> pd.Series: return self.df["low"].astype(float)

    @cached_property
    def close(self) -> pd.Series: return self.df["close"].astype(float)

    @cached_property
    def volume(self) -> pd.Series:
        if "volume" not in self.df.columns:
            return pd.Series(np.nan, index=self.df.index)
        return self.df["volume"].astype(float)

    @cached_property
    def has_volume(self) -> bool:
        v = self.volume
        return bool(v.notna().sum() > len(v) * 0.5 and v.fillna(0).sum() > 0)

    @cached_property
    def n(self) -> int: return len(self.df)

    @cached_property
    def bars_per_year(self) -> int: return BARS_PER_YEAR.get(self.interval, 252)

    # ── returns ───────────────────────────────────────────────────────────────
    @cached_property
    def ret(self) -> pd.Series: return self.close.pct_change()

    @cached_property
    def logret(self) -> pd.Series:
        return np.log(self.close / self.close.shift(1)).replace([np.inf, -np.inf], np.nan)

    @cached_property
    def typical(self) -> pd.Series: return (self.high + self.low + self.close) / 3.0

    @cached_property
    def hl_range(self) -> pd.Series: return self.high - self.low

    # ── moving averages ───────────────────────────────────────────────────────
    def sma(self, p: int) -> pd.Series:
        return self._memo(f"sma{p}", lambda: self.close.rolling(p, min_periods=p).mean())

    def ema(self, p: int) -> pd.Series:
        return self._memo(f"ema{p}", lambda: self.close.ewm(span=p, adjust=False, min_periods=p).mean())

    def std(self, p: int) -> pd.Series:
        return self._memo(f"std{p}", lambda: self.close.rolling(p, min_periods=p).std(ddof=0))

    def hull(self, p: int) -> pd.Series:
        """Hull (2005) moving average — low-lag weighted composite."""
        def _wma(s: pd.Series, n: int) -> pd.Series:
            w = np.arange(1, n + 1, dtype=float)
            return s.rolling(n, min_periods=n).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)
        return self._memo(f"hull{p}", lambda: _wma(
            2 * _wma(self.close, max(1, p // 2)) - _wma(self.close, p), max(1, int(np.sqrt(p)))))

    def kama(self, p: int = 10, fast: int = 2, slow: int = 30) -> pd.Series:
        """Kaufman Adaptive Moving Average — smoothing scales with efficiency ratio."""
        def _calc() -> pd.Series:
            er = self.efficiency_ratio(p)
            sc = (er * (2.0 / (fast + 1) - 2.0 / (slow + 1)) + 2.0 / (slow + 1)) ** 2
            c = self.close.to_numpy(dtype=float)
            s = sc.fillna(0.0).to_numpy(dtype=float)
            out = np.full(len(c), np.nan)
            seed = min(p, len(c) - 1)
            if seed < 1:
                return pd.Series(out, index=self.close.index)
            out[seed] = c[seed]
            for i in range(seed + 1, len(c)):
                out[i] = out[i - 1] + s[i] * (c[i] - out[i - 1])
            return pd.Series(out, index=self.close.index)
        return self._memo(f"kama{p}_{fast}_{slow}", _calc)

    def efficiency_ratio(self, p: int = 10) -> pd.Series:
        """Kaufman efficiency ratio: net move / total path. 1 = clean trend, 0 = chop."""
        def _calc() -> pd.Series:
            direction = (self.close - self.close.shift(p)).abs()
            volatility = self.close.diff().abs().rolling(p, min_periods=p).sum()
            return _safe_div(direction, volatility.where(volatility > 1e-12))
        return self._memo(f"er{p}", _calc)

    # ── volatility / range ────────────────────────────────────────────────────
    @cached_property
    def true_range(self) -> pd.Series:
        prev_close = self.close.shift(1)
        return pd.concat([
            self.high - self.low,
            (self.high - prev_close).abs(),
            (self.low - prev_close).abs(),
        ], axis=1).max(axis=1)

    def atr(self, p: int = 14) -> pd.Series:
        return self._memo(f"atr{p}", lambda: wilder_ema(self.true_range, p))

    def natr(self, p: int = 14) -> pd.Series:
        """ATR normalised by price — comparable across symbols and price levels."""
        return self._memo(f"natr{p}", lambda: _safe_div(self.atr(p), self.close))

    def realized_vol(self, p: int = 20, annualize: bool = True) -> pd.Series:
        def _calc() -> pd.Series:
            v = self.logret.rolling(p, min_periods=max(2, p // 2)).std(ddof=0)
            return v * np.sqrt(self.bars_per_year) if annualize else v
        return self._memo(f"rv{p}_{annualize}", _calc)

    def parkinson_vol(self, p: int = 20) -> pd.Series:
        """Parkinson (1980) high-low range estimator — ~5x more efficient than close-to-close."""
        def _calc() -> pd.Series:
            hl = np.log(_safe_div(self.high, self.low, 1.0).clip(lower=1e-12)) ** 2
            return np.sqrt(hl.rolling(p, min_periods=max(2, p // 2)).mean() / (4 * np.log(2))
                           ) * np.sqrt(self.bars_per_year)
        return self._memo(f"pk{p}", _calc)

    def garman_klass_vol(self, p: int = 20) -> pd.Series:
        """Garman-Klass (1980) OHLC estimator."""
        def _calc() -> pd.Series:
            hl = 0.5 * np.log(_safe_div(self.high, self.low, 1.0).clip(lower=1e-12)) ** 2
            co = (2 * np.log(2) - 1) * np.log(_safe_div(self.close, self.open, 1.0).clip(lower=1e-12)) ** 2
            return np.sqrt((hl - co).rolling(p, min_periods=max(2, p // 2)).mean().clip(lower=0)
                           ) * np.sqrt(self.bars_per_year)
        return self._memo(f"gk{p}", _calc)

    def rogers_satchell_vol(self, p: int = 20) -> pd.Series:
        """Rogers-Satchell (1991) — unlike Parkinson/GK, unbiased under nonzero drift."""
        def _calc() -> pd.Series:
            lg = lambda a, b: np.log(_safe_div(a, b, 1.0).clip(lower=1e-12))
            rs = lg(self.high, self.close) * lg(self.high, self.open) + \
                 lg(self.low, self.close) * lg(self.low, self.open)
            return np.sqrt(rs.rolling(p, min_periods=max(2, p // 2)).mean().clip(lower=0)
                           ) * np.sqrt(self.bars_per_year)
        return self._memo(f"rs{p}", _calc)

    def yang_zhang_vol(self, p: int = 20) -> pd.Series:
        """Yang-Zhang (2000) — drift-independent and handles overnight gaps."""
        def _calc() -> pd.Series:
            lg = lambda a, b: np.log(_safe_div(a, b, 1.0).clip(lower=1e-12))
            o = lg(self.open, self.close.shift(1))
            c = lg(self.close, self.open)
            mp = max(2, p // 2)
            vo = o.rolling(p, min_periods=mp).var(ddof=0)
            vc = c.rolling(p, min_periods=mp).var(ddof=0)
            lgv = lg(self.high, self.close) * lg(self.high, self.open) + \
                  lg(self.low, self.close) * lg(self.low, self.open)
            vrs = lgv.rolling(p, min_periods=mp).mean()
            k = 0.34 / (1.34 + (p + 1) / (p - 1)) if p > 1 else 0.34
            return np.sqrt((vo + k * vc + (1 - k) * vrs).clip(lower=0)) * np.sqrt(self.bars_per_year)
        return self._memo(f"yz{p}", _calc)

    # ── oscillators ───────────────────────────────────────────────────────────
    def rsi(self, p: int = 14) -> pd.Series:
        """Wilder (1978) RSI."""
        def _calc() -> pd.Series:
            d = self.close.diff()
            gain = wilder_ema(d.clip(lower=0), p)
            loss = wilder_ema((-d).clip(lower=0), p)
            rs = _safe_div(gain, loss.where(loss > 1e-12))
            out = 100 - 100 / (1 + rs)
            return out.where(loss > 1e-12, 100.0).where(gain > 1e-12, out)
        return self._memo(f"rsi{p}", _calc)

    def stoch_k(self, p: int = 14) -> pd.Series:
        def _calc() -> pd.Series:
            ll = self.low.rolling(p, min_periods=p).min()
            hh = self.high.rolling(p, min_periods=p).max()
            return 100 * _safe_div(self.close - ll, (hh - ll).where((hh - ll) > 1e-12), 0.5)
        return self._memo(f"stoch{p}", _calc)

    def williams_r(self, p: int = 14) -> pd.Series:
        return self._memo(f"wr{p}", lambda: self.stoch_k(p) - 100)

    def cci(self, p: int = 20) -> pd.Series:
        """Lambert's Commodity Channel Index."""
        def _calc() -> pd.Series:
            tp = self.typical
            ma = tp.rolling(p, min_periods=p).mean()
            md = (tp - ma).abs().rolling(p, min_periods=p).mean()
            return _safe_div(tp - ma, (0.015 * md).where(md > 1e-12))
        return self._memo(f"cci{p}", _calc)

    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9):
        """Returns (macd_line, signal_line, histogram)."""
        def _calc():
            line = self.ema(fast) - self.ema(slow)
            sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
            return line, sig, line - sig
        return self._memo(f"macd{fast}_{slow}_{signal}", _calc)

    def bollinger(self, p: int = 20, k: float = 2.0):
        """Returns (upper, mid, lower, %b, bandwidth)."""
        def _calc():
            mid = self.sma(p)
            sd = self.std(p)
            up, lo = mid + k * sd, mid - k * sd
            pct_b = _safe_div(self.close - lo, (up - lo).where((up - lo) > 1e-12), 0.5)
            bw = _safe_div(up - lo, mid)
            return up, mid, lo, pct_b, bw
        return self._memo(f"bb{p}_{k}", _calc)

    def keltner(self, p: int = 20, atr_p: int = 14, k: float = 2.0):
        def _calc():
            mid = self.ema(p)
            a = self.atr(atr_p)
            return mid + k * a, mid, mid - k * a
        return self._memo(f"kc{p}_{atr_p}_{k}", _calc)

    def donchian(self, p: int = 20):
        def _calc():
            # shift(1) so the channel never includes the current bar — no look-ahead.
            up = self.high.rolling(p, min_periods=p).max().shift(1)
            lo = self.low.rolling(p, min_periods=p).min().shift(1)
            return up, (up + lo) / 2, lo
        return self._memo(f"dc{p}", _calc)

    def adx(self, p: int = 14):
        """Wilder's ADX. Returns (adx, +DI, -DI)."""
        def _calc():
            up_move = self.high.diff()
            dn_move = -self.low.diff()
            plus_dm = up_move.where((up_move > dn_move) & (up_move > 0), 0.0)
            minus_dm = dn_move.where((dn_move > up_move) & (dn_move > 0), 0.0)
            atr = wilder_ema(self.true_range, p)
            pdi = 100 * _safe_div(wilder_ema(plus_dm, p), atr.where(atr > 1e-12))
            mdi = 100 * _safe_div(wilder_ema(minus_dm, p), atr.where(atr > 1e-12))
            dx = 100 * _safe_div((pdi - mdi).abs(), (pdi + mdi).where((pdi + mdi) > 1e-12))
            return wilder_ema(dx, p), pdi, mdi
        return self._memo(f"adx{p}", _calc)

    # ── volume ────────────────────────────────────────────────────────────────
    @cached_property
    def obv(self) -> pd.Series:
        """On-Balance Volume (Granville)."""
        return (np.sign(self.close.diff()).fillna(0) * self.volume.fillna(0)).cumsum()

    def vwap(self, p: int = 20) -> pd.Series:
        """Rolling VWAP. Falls back to typical-price SMA when volume is unavailable."""
        def _calc() -> pd.Series:
            if not self.has_volume:
                return self.typical.rolling(p, min_periods=p).mean()
            v = self.volume.fillna(0)
            pv = (self.typical * v).rolling(p, min_periods=p).sum()
            vv = v.rolling(p, min_periods=p).sum()
            return _safe_div(pv, vv.where(vv > 1e-12)).replace(0, np.nan).ffill()
        return self._memo(f"vwap{p}", _calc)

    def mfi(self, p: int = 14) -> pd.Series:
        """Money Flow Index — volume-weighted RSI."""
        def _calc() -> pd.Series:
            if not self.has_volume:
                return pd.Series(np.nan, index=self.close.index)
            rmf = self.typical * self.volume.fillna(0)
            up = rmf.where(self.typical.diff() > 0, 0.0).rolling(p, min_periods=p).sum()
            dn = rmf.where(self.typical.diff() < 0, 0.0).rolling(p, min_periods=p).sum()
            return 100 - 100 / (1 + _safe_div(up, dn.where(dn > 1e-12)))
        return self._memo(f"mfi{p}", _calc)

    def volume_z(self, p: int = 20) -> pd.Series:
        return self._memo(f"volz{p}", lambda: zscore(self.volume.fillna(0), p))

    # ── higher moments & structure ────────────────────────────────────────────
    def skew(self, p: int = 60) -> pd.Series:
        return self._memo(f"skew{p}", lambda: self.logret.rolling(p, min_periods=max(10, p // 2)).skew())

    def kurtosis(self, p: int = 60) -> pd.Series:
        return self._memo(f"kurt{p}", lambda: self.logret.rolling(p, min_periods=max(10, p // 2)).kurt())

    def hurst(self, p: int = 100) -> pd.Series:
        """
        Rolling Hurst exponent via rescaled range. H<0.5 mean-reverting,
        H≈0.5 random walk, H>0.5 trending (Mandelbrot; Lo 1991).
        """
        def _rs(win: np.ndarray) -> float:
            dev = np.cumsum(win - win.mean())
            r = dev.max() - dev.min()
            s = win.std()
            if s < 1e-12 or r < 1e-12:
                return 0.5
            return float(np.log(r / s) / np.log(len(win)))
        return self._memo(f"hurst{p}",
                          lambda: self.logret.rolling(p, min_periods=p).apply(_rs, raw=True))

    def variance_ratio(self, q: int = 5, p: int = 100) -> pd.Series:
        """
        Lo-MacKinlay (1988) variance ratio. VR>1 trending, VR<1 mean-reverting.
        Var(q-period return) / (q * Var(1-period return)).
        """
        def _calc() -> pd.Series:
            mp = max(20, p // 2)
            v1 = self.logret.rolling(p, min_periods=mp).var(ddof=0)
            vq = self.logret.rolling(q).sum().rolling(p, min_periods=mp).var(ddof=0)
            return _safe_div(vq, (q * v1).where(v1 > 1e-16), 1.0)
        return self._memo(f"vr{q}_{p}", _calc)

    def half_life(self, p: int = 100) -> pd.Series:
        """
        Ornstein-Uhlenbeck half-life of mean reversion, from the AR(1) coefficient
        of dP on lagged P. Short half-life => reversion trades are viable.
        """
        def _calc() -> pd.Series:
            lag = self.close.shift(1)
            delta = self.close - lag
            mp = max(20, p // 2)
            cov = delta.rolling(p, min_periods=mp).cov(lag)
            var = lag.rolling(p, min_periods=mp).var(ddof=0)
            beta = _safe_div(cov, var.where(var > 1e-12))
            hl = -np.log(2) / beta.where(beta < -1e-9)
            return hl.clip(upper=p * 4)
        return self._memo(f"hl{p}", _calc)

    def drawdown(self) -> pd.Series:
        return self._memo("dd", lambda: self.close / self.close.cummax() - 1.0)

    # ── regime ────────────────────────────────────────────────────────────────
    @cached_property
    def trend_strength(self) -> pd.Series:
        """0..1 trendiness: blend of ADX and Kaufman efficiency ratio."""
        adx, _, _ = self.adx(14)
        return ((adx / 50.0).clip(0, 1) * 0.5 + self.efficiency_ratio(20).clip(0, 1) * 0.5)

    @cached_property
    def vol_regime(self) -> pd.Series:
        """Percentile of current volatility within its trailing year (0..1)."""
        return rolling_rank(self.realized_vol(20), min(252, max(30, self.n // 2)))

    # ── memoisation ───────────────────────────────────────────────────────────
    def _memo(self, key: str, fn):
        cache = self.__dict__.setdefault("_cache", {})
        if key not in cache:
            cache[key] = fn()
        return cache[key]

    # ── introspection ─────────────────────────────────────────────────────────
    def fingerprint(self) -> str:
        """Stable id for this data window — used to cache computed feature sets."""
        tail = self.close.tail(3).to_numpy().tobytes()
        raw = f"{self.symbol}|{self.interval}|{self.n}".encode() + tail
        return hashlib.sha1(raw).hexdigest()[:16]


def build_features(df: pd.DataFrame, interval: str = "1d", symbol: str = "") -> FeatureSet:
    """
    Normalise an OHLCV frame and wrap it in a FeatureSet.

    Accepts capitalised or lowercase column names and either a DatetimeIndex or
    a 'date'/'timestamp' column. Rows with a missing close are dropped, because a
    NaN close silently poisons every downstream indicator.
    """
    if df is None or len(df) == 0:
        raise ValueError("build_features: empty dataframe")

    out = df.copy()
    out.columns = [str(c).strip().lower() for c in out.columns]

    for src, dst in (("adj close", "close"), ("adj_close", "close"), ("last", "close")):
        if dst not in out.columns and src in out.columns:
            out[dst] = out[src]

    if "close" not in out.columns:
        raise ValueError(f"build_features: no 'close' column in {list(out.columns)}")

    for col in ("open", "high", "low"):
        if col not in out.columns:
            out[col] = out["close"]
    if "volume" not in out.columns:
        out["volume"] = np.nan

    if not isinstance(out.index, pd.DatetimeIndex):
        for c in ("date", "datetime", "timestamp", "time"):
            if c in out.columns:
                out[c] = pd.to_datetime(out[c], errors="coerce", utc=True)
                out = out.dropna(subset=[c]).set_index(c)
                break

    out = out[~out.index.duplicated(keep="last")].sort_index()
    out = out.dropna(subset=["close"])
    # A high below the low means a corrupt bar; repair rather than propagate.
    out["high"] = out[["high", "low", "close", "open"]].max(axis=1)
    out["low"] = out[["high", "low", "close", "open"]].min(axis=1)

    return FeatureSet(df=out, interval=interval, symbol=symbol)
