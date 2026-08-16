"""
Trend following and momentum.

The core of every managed-futures and CTA book (AQR, Man AHL, Winton, Aspect).
Time-series momentum is one of the most replicated effects in the literature —
Hurst, Ooi & Pedersen (2017) document it across 67 markets and 110 years.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import BaseStrategy, DataNeed, Horizon, Regime, band_score, persist, squash
from ..features import FeatureSet, linreg_slope, rolling_rank, zscore

CAT = "Trend & Momentum"


class TimeSeriesMomentum(BaseStrategy):
    name = "Time-Series Momentum (12-1)"
    category = CAT
    family = "tsmom"
    research = "Moskowitz, Ooi & Pedersen (2012), 'Time Series Momentum', JFE 104(2)"
    description = ("Sign of the trailing excess return over a 12-period lookback, skipping the "
                   "most recent period to avoid short-term reversal contamination.")
    regimes = (Regime.TRENDING,)
    horizon = Horizon.POSITION
    min_bars = 280
    params = {"lookback": 252, "skip": 21, "vol_window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        lb, skip = self.params["lookback"], self.params["skip"]
        past = np.log(f.close.shift(skip) / f.close.shift(skip + lb))
        vol = f.logret.rolling(self.params["vol_window"], min_periods=20).std(ddof=0) * np.sqrt(lb)
        return squash(past / vol.where(vol > 1e-9), 1.0)

    def diagnostics(self, f: FeatureSet) -> dict:
        lb, skip = self.params["lookback"], self.params["skip"]
        r = float(np.log(f.close.iloc[-1 - skip] / f.close.iloc[-1 - skip - lb])) if f.n > lb + skip else float("nan")
        return {"trailing_return_pct": r * 100, "annualized_vol_pct": float(f.realized_vol(60).iloc[-1] * 100)}

    def explain(self, f: FeatureSet, v: float, d: dict) -> str:
        return (f"12-1 momentum: trailing return {d.get('trailing_return_pct', float('nan')):.1f}% "
                f"risk-adjusted against {d.get('annualized_vol_pct', float('nan')):.1f}% annualised vol "
                f"→ {'long' if v > 0 else 'short' if v < 0 else 'flat'} conviction {abs(v):.2f}.")


class CrossSectionalMomentum(BaseStrategy):
    name = "Cross-Sectional Momentum (Jegadeesh-Titman)"
    category = CAT
    family = "xsmom"
    research = "Jegadeesh & Titman (1993), 'Returns to Buying Winners and Selling Losers', JF 48(1)"
    description = "Ranks a symbol's 6-month return against a universe and goes long winners, short losers."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    regimes = (Regime.TRENDING,)
    horizon = Horizon.POSITION
    min_bars = 150
    params = {"lookback": 126}

    def score(self, f: FeatureSet) -> pd.Series:
        # With a universe present the registry supplies peer returns in meta.
        peers = f.meta.get("peer_returns")
        own = f.close.pct_change(self.params["lookback"])
        if peers is None:
            return pd.Series(np.nan, index=f.close.index)
        return band_score(own.rank(pct=True) if not isinstance(peers, pd.Series)
                          else (own > peers).astype(float), 0.0, 1.0)


class DualMomentum(BaseStrategy):
    name = "Dual Momentum (Absolute + Relative)"
    category = CAT
    family = "tsmom"
    research = "Antonacci (2014), 'Dual Momentum Investing'"
    description = "Requires both a positive absolute trend and outperformance versus its own longer trend."
    regimes = (Regime.TRENDING,)
    horizon = Horizon.POSITION
    min_bars = 280
    params = {"abs_lb": 252, "rel_lb": 63}

    def score(self, f: FeatureSet) -> pd.Series:
        absolute = np.sign(f.close.pct_change(self.params["abs_lb"]))
        relative = squash(zscore(f.close.pct_change(self.params["rel_lb"]), 126), 1.5)
        # Both legs must agree; disagreement flattens the position.
        return (relative * (np.sign(relative) == absolute).astype(float)).fillna(0)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"absolute_12m_pct": float(f.close.pct_change(252).iloc[-1] * 100),
                "relative_3m_pct": float(f.close.pct_change(63).iloc[-1] * 100)}


class DonchianBreakout(BaseStrategy):
    name = "Donchian Channel Breakout"
    category = CAT
    family = "breakout"
    research = "Donchian (1960s); systematised by Dennis & Eckhardt's Turtle program (1983)"
    description = "Long on a new N-bar high, short on a new N-bar low, held until the opposite channel."
    regimes = (Regime.TRENDING,)
    horizon = Horizon.SWING
    min_bars = 80
    params = {"period": 20, "hold": 10}

    def score(self, f: FeatureSet) -> pd.Series:
        up, _, lo = f.donchian(self.params["period"])
        raw = np.where(f.close > up, 1.0, np.where(f.close < lo, -1.0, 0.0))
        return persist(pd.Series(raw, index=f.close.index), self.params["hold"])

    def diagnostics(self, f: FeatureSet) -> dict:
        up, mid, lo = f.donchian(self.params["period"])
        return {"upper": float(up.iloc[-1]), "lower": float(lo.iloc[-1]), "close": float(f.close.iloc[-1])}


class TurtleSystem(BaseStrategy):
    name = "Turtle Trading System 1"
    category = CAT
    family = "breakout"
    research = "Dennis & Eckhardt Turtle rules (1983); documented in Faith (2007), 'Way of the Turtle'"
    description = "20-bar entry breakout with a 10-bar opposite-channel exit — the original Turtle System 1."
    regimes = (Regime.TRENDING,)
    horizon = Horizon.SWING
    min_bars = 80
    params = {"entry": 20, "exit": 10}

    def score(self, f: FeatureSet) -> pd.Series:
        e_up, _, e_lo = f.donchian(self.params["entry"])
        x_up, _, x_lo = f.donchian(self.params["exit"])
        state, out = 0.0, np.zeros(f.n)
        c = f.close.to_numpy(); eu, el = e_up.to_numpy(), e_lo.to_numpy()
        xu, xl = x_up.to_numpy(), x_lo.to_numpy()
        for i in range(f.n):
            if state > 0 and c[i] < xl[i]:
                state = 0.0
            elif state < 0 and c[i] > xu[i]:
                state = 0.0
            if state == 0.0:
                if c[i] > eu[i]:
                    state = 1.0
                elif c[i] < el[i]:
                    state = -1.0
            out[i] = state
        return pd.Series(out, index=f.close.index)


class MovingAverageCrossover(BaseStrategy):
    name = "EMA 50/200 Golden Cross"
    category = CAT
    family = "ma_cross"
    research = "Brock, Lakonishok & LeBaron (1992), 'Simple Technical Trading Rules', JF 47(5)"
    description = "Classic long-horizon regime filter: fast EMA above slow EMA, scaled by separation."
    regimes = (Regime.TRENDING,)
    horizon = Horizon.POSITION
    min_bars = 220
    params = {"fast": 50, "slow": 200}

    def score(self, f: FeatureSet) -> pd.Series:
        fast, slow = f.ema(self.params["fast"]), f.ema(self.params["slow"])
        return squash((fast - slow) / slow.abs().where(slow.abs() > 1e-12), 0.03)

    def diagnostics(self, f: FeatureSet) -> dict:
        fast, slow = f.ema(50), f.ema(200)
        return {"ema50": float(fast.iloc[-1]), "ema200": float(slow.iloc[-1]),
                "separation_pct": float((fast.iloc[-1] / slow.iloc[-1] - 1) * 100)}


class MACDTrend(BaseStrategy):
    name = "MACD Histogram Momentum"
    category = CAT
    family = "macd"
    research = "Appel (1979), 'The Moving Average Convergence-Divergence Trading Method'"
    description = "MACD histogram normalised by ATR so conviction is comparable across volatility levels."
    horizon = Horizon.SWING
    min_bars = 60
    params = {"fast": 12, "slow": 26, "signal": 9}

    def score(self, f: FeatureSet) -> pd.Series:
        _, _, hist = f.macd(self.params["fast"], self.params["slow"], self.params["signal"])
        return squash(hist / f.atr(14).where(f.atr(14) > 1e-12), 0.6)

    def diagnostics(self, f: FeatureSet) -> dict:
        line, sig, hist = f.macd()
        return {"macd": float(line.iloc[-1]), "signal": float(sig.iloc[-1]), "histogram": float(hist.iloc[-1])}


class ADXTrendStrength(BaseStrategy):
    name = "ADX Directional Movement"
    category = CAT
    family = "adx"
    research = "Wilder (1978), 'New Concepts in Technical Trading Systems'"
    description = "Directional index spread gated by ADX, so it only takes a side when a trend actually exists."
    regimes = (Regime.TRENDING,)
    horizon = Horizon.SWING
    min_bars = 60
    params = {"period": 14, "adx_floor": 20.0}

    def score(self, f: FeatureSet) -> pd.Series:
        adx, pdi, mdi = f.adx(self.params["period"])
        gate = ((adx - self.params["adx_floor"]) / 20.0).clip(0, 1)
        return squash((pdi - mdi) / 25.0, 1.0) * gate

    def diagnostics(self, f: FeatureSet) -> dict:
        adx, pdi, mdi = f.adx(14)
        return {"adx": float(adx.iloc[-1]), "plus_di": float(pdi.iloc[-1]), "minus_di": float(mdi.iloc[-1])}

    def explain(self, f: FeatureSet, v: float, d: dict) -> str:
        adx = d.get("adx", float("nan"))
        regime = "strong trend" if adx > 25 else "developing trend" if adx > 20 else "no trend (signal suppressed)"
        return (f"ADX {adx:.1f} = {regime}; +DI {d.get('plus_di', 0):.1f} vs -DI {d.get('minus_di', 0):.1f} "
                f"→ conviction {abs(v):.2f}.")


class SupertrendFollower(BaseStrategy):
    name = "Supertrend (ATR Bands)"
    category = CAT
    family = "atr_trend"
    research = "Olivier Seban's Supertrend; ATR from Wilder (1978)"
    description = "Trailing ATR band that flips regime on close-through, a standard CTA stop-and-reverse."
    regimes = (Regime.TRENDING,)
    horizon = Horizon.SWING
    min_bars = 60
    params = {"period": 10, "multiplier": 3.0}

    def score(self, f: FeatureSet) -> pd.Series:
        atr = f.atr(self.params["period"]) * self.params["multiplier"]
        hl2 = (f.high + f.low) / 2
        ub, lb = (hl2 + atr).to_numpy(), (hl2 - atr).to_numpy()
        c = f.close.to_numpy()
        fu, fl = ub.copy(), lb.copy()
        trend = np.ones(f.n)
        for i in range(1, f.n):
            fu[i] = min(ub[i], fu[i - 1]) if c[i - 1] <= fu[i - 1] else ub[i]
            fl[i] = max(lb[i], fl[i - 1]) if c[i - 1] >= fl[i - 1] else lb[i]
            trend[i] = 1.0 if c[i] > fu[i - 1] else -1.0 if c[i] < fl[i - 1] else trend[i - 1]
        return pd.Series(trend, index=f.close.index) * f.trend_strength.clip(0.3, 1.0)


class IchimokuCloud(BaseStrategy):
    name = "Ichimoku Kinko Hyo"
    category = CAT
    family = "ichimoku"
    research = "Hosoda (Ichimoku Sanjin), published 1969"
    description = "Composite of conversion/base line cross, cloud position and lagging-span confirmation."
    regimes = (Regime.TRENDING,)
    horizon = Horizon.SWING
    min_bars = 120
    params = {"tenkan": 9, "kijun": 26, "senkou": 52}

    def score(self, f: FeatureSet) -> pd.Series:
        mid = lambda p: (f.high.rolling(p, min_periods=p).max() + f.low.rolling(p, min_periods=p).min()) / 2
        tenkan, kijun = mid(self.params["tenkan"]), mid(self.params["kijun"])
        span_a = ((tenkan + kijun) / 2).shift(self.params["kijun"])
        span_b = mid(self.params["senkou"]).shift(self.params["kijun"])
        above = ((f.close > span_a) & (f.close > span_b)).astype(float)
        below = ((f.close < span_a) & (f.close < span_b)).astype(float)
        return (0.5 * np.sign(tenkan - kijun) + 0.5 * (above - below)).clip(-1, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        mid = lambda p: (f.high.rolling(p).max() + f.low.rolling(p).min()) / 2
        return {"tenkan": float(mid(9).iloc[-1]), "kijun": float(mid(26).iloc[-1])}


class ParabolicSAR(BaseStrategy):
    name = "Parabolic SAR"
    category = CAT
    family = "atr_trend"
    research = "Wilder (1978), 'New Concepts in Technical Trading Systems'"
    description = "Accelerating stop-and-reverse; the acceleration factor tightens as the trend extends."
    regimes = (Regime.TRENDING,)
    horizon = Horizon.SWING
    min_bars = 60
    params = {"af_step": 0.02, "af_max": 0.2}

    def score(self, f: FeatureSet) -> pd.Series:
        h, l = f.high.to_numpy(), f.low.to_numpy()
        step, cap = self.params["af_step"], self.params["af_max"]
        sar = np.zeros(f.n); trend = np.ones(f.n)
        sar[0], ep, af = l[0], h[0], step
        for i in range(1, f.n):
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
        return pd.Series(trend, index=f.close.index) * 0.8


class KaufmanAdaptiveTrend(BaseStrategy):
    name = "Kaufman Adaptive Moving Average"
    category = CAT
    family = "adaptive_ma"
    research = "Kaufman (1995), 'Smarter Trading'"
    description = "Smoothing constant adapts to the efficiency ratio — fast in trends, inert in chop."
    horizon = Horizon.SWING
    min_bars = 80
    params = {"period": 10, "fast": 2, "slow": 30}

    def score(self, f: FeatureSet) -> pd.Series:
        kama = f.kama(self.params["period"], self.params["fast"], self.params["slow"])
        dev = (f.close - kama) / f.atr(14).where(f.atr(14) > 1e-12)
        return squash(dev, 1.5) * f.efficiency_ratio(self.params["period"]).clip(0, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"kama": float(f.kama(10).iloc[-1]), "efficiency_ratio": float(f.efficiency_ratio(10).iloc[-1])}


class HullMovingAverage(BaseStrategy):
    name = "Hull Moving Average Slope"
    category = CAT
    family = "adaptive_ma"
    research = "Hull (2005), 'How to reduce lag in a moving average'"
    description = "Weighted-composite MA that cuts lag; traded on the sign and steepness of its slope."
    horizon = Horizon.SWING
    min_bars = 80
    params = {"period": 21}

    def score(self, f: FeatureSet) -> pd.Series:
        hma = f.hull(self.params["period"])
        slope = hma.diff() / f.atr(14).where(f.atr(14) > 1e-12)
        return squash(slope, 0.3)


class VortexIndicator(BaseStrategy):
    name = "Vortex Indicator"
    category = CAT
    family = "vortex"
    research = "Botes & Siepman (2010), 'The Vortex Indicator', Technical Analysis of Stocks & Commodities"
    description = "Compares upward and downward directional movement built from opposite-extreme distances."
    regimes = (Regime.TRENDING,)
    horizon = Horizon.SWING
    min_bars = 60
    params = {"period": 14}

    def score(self, f: FeatureSet) -> pd.Series:
        p = self.params["period"]
        vm_plus = (f.high - f.low.shift(1)).abs().rolling(p, min_periods=p).sum()
        vm_minus = (f.low - f.high.shift(1)).abs().rolling(p, min_periods=p).sum()
        tr = f.true_range.rolling(p, min_periods=p).sum()
        vi_p, vi_m = vm_plus / tr.where(tr > 1e-12), vm_minus / tr.where(tr > 1e-12)
        return squash(vi_p - vi_m, 0.15)

    def diagnostics(self, f: FeatureSet) -> dict:
        p = 14
        tr = f.true_range.rolling(p).sum()
        return {"vi_plus": float(((f.high - f.low.shift(1)).abs().rolling(p).sum() / tr).iloc[-1]),
                "vi_minus": float(((f.low - f.high.shift(1)).abs().rolling(p).sum() / tr).iloc[-1])}


class AroonTrend(BaseStrategy):
    name = "Aroon Oscillator"
    category = CAT
    family = "aroon"
    research = "Chande (1995), 'A Time Price Oscillator', Technical Analysis of Stocks & Commodities"
    description = "Measures how recently the period high versus low occurred — a time-based trend gauge."
    horizon = Horizon.SWING
    min_bars = 60
    params = {"period": 25}

    def score(self, f: FeatureSet) -> pd.Series:
        p = self.params["period"]
        since_high = f.high.rolling(p + 1, min_periods=p + 1).apply(lambda x: p - int(np.argmax(x)), raw=True)
        since_low = f.low.rolling(p + 1, min_periods=p + 1).apply(lambda x: p - int(np.argmin(x)), raw=True)
        return ((100 * (p - since_high) / p) - (100 * (p - since_low) / p)) / 100.0


class LinearRegressionSlope(BaseStrategy):
    name = "Rolling Regression Slope (t-stat)"
    category = CAT
    family = "regression_trend"
    research = "Standard OLS trend estimation; t-stat filtering per Brock, Lakonishok & LeBaron (1992)"
    description = "OLS slope over a rolling window, scaled by residual noise so weak fits produce weak signals."
    regimes = (Regime.TRENDING,)
    horizon = Horizon.SWING
    min_bars = 90
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        slope = linreg_slope(np.log(f.close), w)
        noise = f.logret.rolling(w, min_periods=w // 2).std(ddof=0)
        return squash(slope / noise.where(noise > 1e-12) * np.sqrt(w), 2.0)

    def diagnostics(self, f: FeatureSet) -> dict:
        w = self.params["window"]
        s = linreg_slope(np.log(f.close), w).iloc[-1]
        return {"slope_per_bar_pct": float(s * 100), "r2_proxy": float(f.efficiency_ratio(w).iloc[-1])}


class TRIXOscillator(BaseStrategy):
    name = "TRIX Triple-Smoothed Momentum"
    category = CAT
    family = "trix"
    research = "Hutson (1983), 'TRIX — Triple Exponential Smoothing Oscillator'"
    description = "Rate of change of a triple-smoothed EMA; the smoothing strips out cycles shorter than the span."
    horizon = Horizon.SWING
    min_bars = 80
    params = {"period": 15, "signal": 9}

    def score(self, f: FeatureSet) -> pd.Series:
        e = np.log(f.close)
        for _ in range(3):
            e = e.ewm(span=self.params["period"], adjust=False).mean()
        trix = e.diff() * 10000
        sig = trix.ewm(span=self.params["signal"], adjust=False).mean()
        return squash(trix - sig, 5.0)


class CoppockCurve(BaseStrategy):
    name = "Coppock Curve"
    category = CAT
    family = "coppock"
    research = "Coppock (1962), Barron's — long-term momentum turn indicator"
    description = "Weighted MA of summed 14- and 11-period rates of change; a classic long-horizon bottom signal."
    horizon = Horizon.POSITION
    min_bars = 150
    params = {"roc1": 14, "roc2": 11, "wma": 10}

    def score(self, f: FeatureSet) -> pd.Series:
        roc = (f.close.pct_change(self.params["roc1"]) + f.close.pct_change(self.params["roc2"])) * 100
        w = np.arange(1, self.params["wma"] + 1, dtype=float)
        cc = roc.rolling(self.params["wma"], min_periods=self.params["wma"]).apply(
            lambda x: np.dot(x, w) / w.sum(), raw=True)
        return squash(cc, 8.0)


class ChandeMomentumOscillator(BaseStrategy):
    name = "Chande Momentum Oscillator"
    category = CAT
    family = "cmo"
    research = "Chande & Kroll (1994), 'The New Technical Trader'"
    description = "Unsmoothed momentum: net of up-moves and down-moves over their total, avoiding RSI's damping."
    horizon = Horizon.SWING
    min_bars = 60
    params = {"period": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        p = self.params["period"]
        d = f.close.diff()
        up = d.clip(lower=0).rolling(p, min_periods=p).sum()
        dn = (-d).clip(lower=0).rolling(p, min_periods=p).sum()
        tot = (up + dn).where((up + dn) > 1e-12)
        return ((up - dn) / tot).fillna(0)


class ElderTripleScreen(BaseStrategy):
    name = "Elder Triple Screen"
    category = CAT
    family = "multi_timeframe"
    research = "Elder (1993), 'Trading for a Living'"
    description = "Long-horizon trend sets the permitted side; a short-horizon oscillator times entry against it."
    horizon = Horizon.SWING
    min_bars = 120
    params = {"trend_span": 78, "osc_period": 13}

    def score(self, f: FeatureSet) -> pd.Series:
        trend = np.sign(f.ema(self.params["trend_span"]).diff())
        force = (f.close.diff() * f.volume.fillna(f.volume.median())).ewm(
            span=self.params["osc_period"], adjust=False).mean()
        pullback = -squash(zscore(force, 40), 1.5)
        # Only take pullback entries in the direction of the higher-timeframe trend.
        return (pullback.abs() * trend).where(np.sign(pullback) == trend, 0.0).fillna(0)


class GuppyMultipleMA(BaseStrategy):
    name = "Guppy Multiple Moving Average"
    category = CAT
    family = "ma_ribbon"
    research = "Guppy (1999), 'Trend Trading'"
    description = "Separation and alignment of short-term versus long-term EMA ribbons measures trend conviction."
    regimes = (Regime.TRENDING,)
    horizon = Horizon.SWING
    min_bars = 90
    params = {"short": (3, 5, 8, 10, 12, 15), "long": (30, 35, 40, 45, 50, 60)}

    def score(self, f: FeatureSet) -> pd.Series:
        short = sum(f.ema(p) for p in self.params["short"]) / len(self.params["short"])
        long = sum(f.ema(p) for p in self.params["long"]) / len(self.params["long"])
        return squash((short - long) / long.abs().where(long.abs() > 1e-12), 0.02)


class MomentumBreakoutVolConfirmed(BaseStrategy):
    name = "Volume-Confirmed Range Breakout"
    category = CAT
    family = "breakout"
    research = "Blume, Easley & O'Hara (1994), 'Market Statistics and Technical Analysis', JF 49(1)"
    description = "Breakouts on above-average volume; volume is the information signal that validates the move."
    needs = (DataNeed.OHLC, DataNeed.VOLUME)
    horizon = Horizon.SWING
    min_bars = 80
    params = {"period": 20, "vol_z": 1.0}

    def score(self, f: FeatureSet) -> pd.Series:
        up, _, lo = f.donchian(self.params["period"])
        conf = (f.volume_z(20) > self.params["vol_z"]).astype(float)
        raw = np.where(f.close > up, 1.0, np.where(f.close < lo, -1.0, 0.0))
        return persist(pd.Series(raw, index=f.close.index) * conf, 5)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"volume_zscore": float(f.volume_z(20).iloc[-1])}


class ATRChannelTrend(BaseStrategy):
    name = "Keltner Channel Trend"
    category = CAT
    family = "atr_trend"
    research = "Keltner (1960), 'How to Make Money in Commodities'; ATR variant per Linda Raschke"
    description = "EMA centre with ATR envelopes; trades sustained closes outside the channel."
    horizon = Horizon.SWING
    min_bars = 60
    params = {"period": 20, "atr_period": 14, "mult": 2.0}

    def score(self, f: FeatureSet) -> pd.Series:
        up, mid, lo = f.keltner(self.params["period"], self.params["atr_period"], self.params["mult"])
        width = (up - lo).where((up - lo) > 1e-12)
        return squash((f.close - mid) / width * 4, 1.2)


class RelativeStrengthTrend(BaseStrategy):
    name = "Relative Strength vs Benchmark"
    category = CAT
    family = "relative_strength"
    research = "Levy (1967), 'Relative Strength as a Criterion for Investment Selection', JF 22(4)"
    description = "Ratio of the symbol to its benchmark; a rising ratio is outperformance independent of market direction."
    needs = (DataNeed.OHLC, DataNeed.BENCHMARK)
    horizon = Horizon.POSITION
    min_bars = 150

    def score(self, f: FeatureSet) -> pd.Series:
        bench = f.meta.get("benchmark_close")
        if bench is None:
            return pd.Series(np.nan, index=f.close.index)
        ratio = f.close / pd.Series(bench, index=f.close.index).replace(0, np.nan)
        return squash(zscore(ratio, 63), 1.5)


class FrequencyDecomposedTrend(BaseStrategy):
    name = "Ehlers Instantaneous Trendline"
    category = CAT
    family = "cycle"
    research = "Ehlers (2001), 'Rocket Science for Traders'"
    description = "Signal-processing trendline that removes the dominant cycle instead of lagging it."
    horizon = Horizon.SWING
    min_bars = 80
    params = {"alpha": 0.07}

    def score(self, f: FeatureSet) -> pd.Series:
        a = self.params["alpha"]
        p = ((f.high + f.low) / 2).to_numpy()
        it = np.copy(p)
        for i in range(2, len(p)):
            it[i] = ((a - a * a / 4) * p[i] + 0.5 * a * a * p[i - 1] - (a - 0.75 * a * a) * p[i - 2]
                     + 2 * (1 - a) * it[i - 1] - (1 - a) ** 2 * it[i - 2])
        trend = pd.Series(it, index=f.close.index)
        return squash((f.close - trend) / f.atr(14).where(f.atr(14) > 1e-12), 1.5)


class FisherTransformTrend(BaseStrategy):
    name = "Ehlers Fisher Transform"
    category = CAT
    family = "cycle"
    research = "Ehlers (2002), 'Using the Fisher Transform', Technical Analysis of Stocks & Commodities"
    description = "Gaussianises the price distribution so turning points become sharp, statistically rare events."
    horizon = Horizon.SWING
    min_bars = 60
    params = {"period": 10}

    def score(self, f: FeatureSet) -> pd.Series:
        p = self.params["period"]
        mid = (f.high + f.low) / 2
        ll, hh = mid.rolling(p, min_periods=p).min(), mid.rolling(p, min_periods=p).max()
        rng = (hh - ll).where((hh - ll) > 1e-12)
        raw = (2 * ((mid - ll) / rng) - 1).clip(-0.999, 0.999).fillna(0)
        smooth = raw.ewm(alpha=0.33, adjust=False).mean().clip(-0.999, 0.999)
        fish = 0.5 * np.log((1 + smooth) / (1 - smooth))
        return squash(fish.ewm(alpha=0.5, adjust=False).mean(), 1.5)


class ResidualMomentum(BaseStrategy):
    name = "Residual (Beta-Neutral) Momentum"
    category = CAT
    family = "residual_mom"
    research = "Blitz, Huij & Martens (2011), 'Residual Momentum', J. Empirical Finance 18(3)"
    description = "Momentum in the market-orthogonal residual, which strips out beta-driven trend."
    needs = (DataNeed.OHLC, DataNeed.BENCHMARK)
    horizon = Horizon.POSITION
    min_bars = 180
    params = {"window": 126}

    def score(self, f: FeatureSet) -> pd.Series:
        bench = f.meta.get("benchmark_close")
        if bench is None:
            return pd.Series(np.nan, index=f.close.index)
        w = self.params["window"]
        br = pd.Series(bench, index=f.close.index).pct_change()
        cov = f.ret.rolling(w, min_periods=w // 2).cov(br)
        var = br.rolling(w, min_periods=w // 2).var(ddof=0)
        beta = cov / var.where(var > 1e-14)
        resid = f.ret - beta * br
        cum = resid.rolling(w, min_periods=w // 2).sum()
        sd = resid.rolling(w, min_periods=w // 2).std(ddof=0) * np.sqrt(w)
        return squash(cum / sd.where(sd > 1e-12), 1.0)


class FiftyTwoWeekHigh(BaseStrategy):
    name = "52-Week High Proximity"
    category = CAT
    family = "anchor"
    research = "George & Hwang (2004), 'The 52-Week High and Momentum Investing', JF 59(5)"
    description = "Nearness to the annual high; the anchoring bias makes proximity to it predict continuation."
    horizon = Horizon.POSITION
    min_bars = 260
    params = {"window": 252}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        hi = f.high.rolling(w, min_periods=w // 2).max()
        lo = f.low.rolling(w, min_periods=w // 2).min()
        pos = (f.close - lo) / (hi - lo).where((hi - lo) > 1e-12)
        return band_score(pos, 0.35, 0.98)

    def diagnostics(self, f: FeatureSet) -> dict:
        hi = f.high.rolling(252, min_periods=100).max().iloc[-1]
        return {"pct_below_52w_high": float((f.close.iloc[-1] / hi - 1) * 100), "high_52w": float(hi)}


class MomentumAcceleration(BaseStrategy):
    name = "Momentum Acceleration (2nd Derivative)"
    category = CAT
    family = "acceleration"
    research = "Extends Moskowitz, Ooi & Pedersen (2012) with a curvature term on the trend path"
    description = "Trades change in trend speed, which turns before the trend itself does."
    horizon = Horizon.SWING
    min_bars = 100
    params = {"fast": 21, "slow": 63}

    def score(self, f: FeatureSet) -> pd.Series:
        mom_f = f.close.pct_change(self.params["fast"])
        mom_s = f.close.pct_change(self.params["slow"])
        accel = mom_f - mom_s * (self.params["fast"] / self.params["slow"])
        return squash(zscore(accel, 63), 1.5)


class TrendQualityFilter(BaseStrategy):
    name = "Trend Quality (R-squared Gated)"
    category = CAT
    family = "regression_trend"
    research = "Kirkpatrick & Dahlquist (2010), 'Technical Analysis'; efficiency ratio per Kaufman (1995)"
    description = "Only trades the trend when the price path is efficient; suppresses signals in choppy tape."
    regimes = (Regime.TRENDING,)
    horizon = Horizon.SWING
    min_bars = 90
    params = {"window": 40, "min_er": 0.3}

    def score(self, f: FeatureSet) -> pd.Series:
        er = f.efficiency_ratio(self.params["window"])
        direction = np.sign(f.close - f.close.shift(self.params["window"]))
        gate = ((er - self.params["min_er"]) / (1 - self.params["min_er"])).clip(0, 1)
        return direction * gate

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"efficiency_ratio": float(f.efficiency_ratio(40).iloc[-1]),
                "trend_strength": float(f.trend_strength.iloc[-1])}


class VolatilityAdjustedTrend(BaseStrategy):
    name = "Volatility-Scaled Trend (CTA Core)"
    category = CAT
    family = "tsmom"
    research = "Baltas & Kosowski (2013), 'Momentum Strategies in Futures Markets and Trend-Following Funds'"
    description = "Blends three lookback horizons, each scaled by its own volatility — the standard CTA construction."
    regimes = (Regime.TRENDING,)
    horizon = Horizon.POSITION
    min_bars = 280
    params = {"lookbacks": (21, 63, 252)}

    def score(self, f: FeatureSet) -> pd.Series:
        vol = f.logret.rolling(60, min_periods=20).std(ddof=0)
        legs = []
        for lb in self.params["lookbacks"]:
            r = np.log(f.close / f.close.shift(lb))
            legs.append(squash(r / (vol.where(vol > 1e-9) * np.sqrt(lb)), 1.0))
        return sum(legs) / len(legs)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {f"return_{lb}b_pct": float(f.close.pct_change(lb).iloc[-1] * 100)
                for lb in self.params["lookbacks"] if f.n > lb}


class BreakoutFailureReversal(BaseStrategy):
    name = "Failed Breakout Reversal"
    category = CAT
    family = "breakout"
    research = "Kaufman (2013), 'Trading Systems and Methods', 5th ed. — false breakout patterns"
    description = "Fades a breakout that closes back inside the channel, a classic liquidity-sweep pattern."
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 80
    params = {"period": 20, "hold": 5}

    def score(self, f: FeatureSet) -> pd.Series:
        up, _, lo = f.donchian(self.params["period"])
        # Broke above yesterday, closed back below today → failed upside break.
        fail_up = ((f.high > up) & (f.close < up)).astype(float)
        fail_dn = ((f.low < lo) & (f.close > lo)).astype(float)
        return persist(fail_dn - fail_up, self.params["hold"])
