"""
Volatility modelling and volatility arbitrage.

Volatility is the one quantity in finance that is genuinely forecastable, which
is why it anchors risk systems everywhere from Citadel's risk desk to a CTA's
position sizer. These models forecast it, trade its mean reversion, and trade
the premium embedded in it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import BaseStrategy, DataNeed, Horizon, Regime, band_score, persist, squash
from ..features import FeatureSet, _safe_div, rolling_rank, zscore

CAT = "Volatility"


class GARCHVolatilityForecast(BaseStrategy):
    name = "GARCH(1,1) Volatility Forecast"
    category = CAT
    family = "garch"
    research = "Bollerslev (1986), 'Generalized Autoregressive Conditional Heteroskedasticity', J. Econometrics 31(3)"
    description = ("Fits GARCH(1,1) by recursive filtering with standard parameters and trades the gap between "
                   "forecast and realised volatility.")
    horizon = Horizon.SWING
    min_bars = 150
    params = {"omega_scale": 0.05, "alpha": 0.08, "beta": 0.90}

    def _garch_var(self, f: FeatureSet) -> pd.Series:
        r = f.logret.fillna(0.0).to_numpy()
        long_run = float(np.nanvar(r)) or 1e-8
        a, b = self.params["alpha"], self.params["beta"]
        omega = long_run * (1 - a - b)
        v = np.empty(len(r)); v[0] = long_run
        for i in range(1, len(r)):
            v[i] = omega + a * r[i - 1] ** 2 + b * v[i - 1]
        return pd.Series(v, index=f.close.index)

    def score(self, f: FeatureSet) -> pd.Series:
        fc = np.sqrt(self._garch_var(f) * f.bars_per_year)
        realized = f.realized_vol(20)
        # Forecast above realised ⇒ vol expansion coming ⇒ reduce directional risk.
        gap = _safe_div(fc - realized, realized.where(realized > 1e-9))
        return -squash(gap, 0.35) * np.sign(zscore(f.close, 20)).fillna(0)

    def diagnostics(self, f: FeatureSet) -> dict:
        fc = float(np.sqrt(self._garch_var(f).iloc[-1] * f.bars_per_year))
        rv = float(f.realized_vol(20).iloc[-1])
        return {"garch_forecast_vol_pct": fc * 100, "realized_vol_pct": rv * 100,
                "persistence": self.params["alpha"] + self.params["beta"]}

    def explain(self, f: FeatureSet, v: float, d: dict) -> str:
        return (f"GARCH(1,1) forecasts {d.get('garch_forecast_vol_pct', 0):.1f}% annualised vol vs "
                f"{d.get('realized_vol_pct', 0):.1f}% realised (persistence α+β={d.get('persistence', 0):.2f}) "
                f"→ conviction {abs(v):.2f}.")


class EGARCHAsymmetry(BaseStrategy):
    name = "EGARCH Leverage Asymmetry"
    category = CAT
    family = "garch"
    research = "Nelson (1991), 'Conditional Heteroskedasticity in Asset Returns', Econometrica 59(2)"
    description = "Captures the leverage effect: negative returns raise future volatility more than positive ones."
    horizon = Horizon.SWING
    min_bars = 150
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        r = f.logret
        down = r.where(r < 0, 0.0).rolling(w, min_periods=w // 2).std(ddof=0)
        up = r.where(r > 0, 0.0).rolling(w, min_periods=w // 2).std(ddof=0)
        asym = _safe_div(down - up, (down + up).where((down + up) > 1e-12))
        # Strong downside asymmetry = fragile tape; lean defensive.
        return -squash(asym, 0.25)

    def diagnostics(self, f: FeatureSet) -> dict:
        r = f.logret
        d = float(r.where(r < 0, 0).rolling(60).std(ddof=0).iloc[-1])
        u = float(r.where(r > 0, 0).rolling(60).std(ddof=0).iloc[-1])
        return {"downside_vol": d, "upside_vol": u, "leverage_asymmetry": (d - u) / (d + u) if (d + u) else 0.0}


class GJRGarch(BaseStrategy):
    name = "GJR-GARCH Threshold Volatility"
    category = CAT
    family = "garch"
    research = "Glosten, Jagannathan & Runkle (1993), 'On the Relation between Expected Value and Volatility', JF 48(5)"
    description = "Adds an indicator term so negative shocks feed volatility through a separate, larger coefficient."
    horizon = Horizon.SWING
    min_bars = 150
    params = {"alpha": 0.03, "gamma": 0.10, "beta": 0.88}

    def score(self, f: FeatureSet) -> pd.Series:
        r = f.logret.fillna(0.0).to_numpy()
        lr = float(np.nanvar(r)) or 1e-8
        a, g, b = self.params["alpha"], self.params["gamma"], self.params["beta"]
        omega = lr * max(1e-6, 1 - a - g / 2 - b)
        v = np.empty(len(r)); v[0] = lr
        for i in range(1, len(r)):
            shock = r[i - 1] ** 2
            v[i] = omega + a * shock + g * shock * (r[i - 1] < 0) + b * v[i - 1]
        cond = pd.Series(np.sqrt(v * f.bars_per_year), index=f.close.index)
        return -squash(zscore(cond, 60), 1.5)


class HARRealizedVolatility(BaseStrategy):
    name = "HAR-RV Heterogeneous Autoregression"
    category = CAT
    family = "har_rv"
    research = "Corsi (2009), 'A Simple Approximate Long-Memory Model of Realized Volatility', J. Fin. Econometrics 7(2)"
    description = "Cascades daily, weekly and monthly realised volatility — the standard realised-vol benchmark."
    horizon = Horizon.SWING
    min_bars = 150
    params = {"daily": 1, "weekly": 5, "monthly": 22}

    def score(self, f: FeatureSet) -> pd.Series:
        rv = f.logret ** 2
        d = rv.rolling(self.params["daily"], min_periods=1).mean()
        w = rv.rolling(self.params["weekly"], min_periods=3).mean()
        m = rv.rolling(self.params["monthly"], min_periods=10).mean()
        forecast = 0.35 * d + 0.35 * w + 0.30 * m
        current = rv.rolling(5, min_periods=3).mean()
        gap = _safe_div(forecast - current, current.where(current > 1e-14))
        return -squash(gap, 0.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        rv = f.logret ** 2
        ann = np.sqrt(f.bars_per_year) * 100
        return {"rv_daily_pct": float(np.sqrt(rv.rolling(1).mean().iloc[-1]) * ann),
                "rv_weekly_pct": float(np.sqrt(rv.rolling(5).mean().iloc[-1]) * ann),
                "rv_monthly_pct": float(np.sqrt(rv.rolling(22).mean().iloc[-1]) * ann)}


class VolatilityRiskPremium(BaseStrategy):
    name = "Variance Risk Premium"
    category = CAT
    family = "vrp"
    research = "Bollerslev, Tauchen & Zhou (2009), 'Expected Stock Returns and Variance Risk Premium', RFS 22(11)"
    description = "The gap between implied and realised variance; harvesting it is the core short-vol carry trade."
    needs = (DataNeed.OHLC, DataNeed.OPTIONS_CHAIN)
    horizon = Horizon.SWING
    min_bars = 120

    def score(self, f: FeatureSet) -> pd.Series:
        iv = f.meta.get("implied_vol")
        if iv is None:
            return pd.Series(np.nan, index=f.close.index)
        implied = pd.Series(iv, index=f.close.index)
        return squash(implied - f.realized_vol(20), 0.05)


class VolatilityMeanReversion(BaseStrategy):
    name = "Volatility Mean Reversion"
    category = CAT
    family = "vol_reversion"
    research = "Fouque, Papanicolaou & Sircar (2000), 'Derivatives in Financial Markets with Stochastic Volatility'"
    description = "Volatility reverts far faster than price; extremes in realised vol mark the end of a move."
    horizon = Horizon.SWING
    min_bars = 150
    params = {"window": 20, "rank_window": 252}

    def score(self, f: FeatureSet) -> pd.Series:
        vol_rank = rolling_rank(f.realized_vol(self.params["window"]),
                                min(self.params["rank_window"], max(60, f.n // 2)))
        # Vol spike + price down = capitulation → long; vol trough = complacency → fade the drift.
        direction = -np.sign(zscore(f.close, 20)).fillna(0)
        return direction * band_score(vol_rank, 0.5, 0.95).clip(0, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"realized_vol_pct": float(f.realized_vol(20).iloc[-1] * 100),
                "vol_percentile": float(f.vol_regime.iloc[-1])}


class VolatilityTargeting(BaseStrategy):
    name = "Volatility-Managed Portfolio"
    category = CAT
    family = "vol_target"
    research = "Moreira & Muir (2017), 'Volatility-Managed Portfolios', JF 72(4)"
    description = "Scales exposure inversely to recent variance — raises risk-adjusted returns without forecasting direction."
    horizon = Horizon.POSITION
    min_bars = 150
    params = {"target_vol": 0.15, "window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        rv = f.realized_vol(self.params["window"])
        scale = (self.params["target_vol"] / rv.where(rv > 1e-6)).clip(0, 2.0)
        trend = np.sign(f.ema(50) - f.ema(200)).fillna(0)
        return (trend * scale / 2.0).clip(-1, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        rv = float(f.realized_vol(20).iloc[-1])
        return {"realized_vol_pct": rv * 100, "target_vol_pct": self.params["target_vol"] * 100,
                "leverage_multiple": float(min(self.params["target_vol"] / rv, 2.0)) if rv > 1e-6 else 0.0}


class ParkinsonRangeVol(BaseStrategy):
    name = "Parkinson Range Volatility Divergence"
    category = CAT
    family = "range_vol"
    research = "Parkinson (1980), 'The Extreme Value Method for Estimating the Variance', J. Business 53(1)"
    description = "Compares high-low range volatility to close-to-close; a wide gap signals intrabar churn without follow-through."
    horizon = Horizon.SWING
    min_bars = 100
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        pk, cc = f.parkinson_vol(self.params["window"]), f.realized_vol(self.params["window"])
        ratio = _safe_div(pk, cc.where(cc > 1e-9), 1.0)
        # Range >> close-to-close ⇒ intrabar reversion dominates ⇒ fade.
        return -squash(zscore(ratio, 60), 1.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"parkinson_vol_pct": float(f.parkinson_vol(20).iloc[-1] * 100),
                "close_to_close_vol_pct": float(f.realized_vol(20).iloc[-1] * 100)}


class GarmanKlassEfficiency(BaseStrategy):
    name = "Garman-Klass Volatility Efficiency"
    category = CAT
    family = "range_vol"
    research = "Garman & Klass (1980), 'On the Estimation of Security Price Volatilities', J. Business 53(1)"
    description = "OHLC estimator roughly 7x more efficient than close-to-close; detects mispriced short-term vol."
    horizon = Horizon.SWING
    min_bars = 100
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        gk = f.garman_klass_vol(self.params["window"])
        return -squash(zscore(gk, 60), 1.5) * np.sign(zscore(f.close, 20)).fillna(0)


class YangZhangDriftFree(BaseStrategy):
    name = "Yang-Zhang Drift-Independent Volatility"
    category = CAT
    family = "range_vol"
    research = "Yang & Zhang (2000), 'Drift-Independent Volatility Estimation', J. Business 73(3)"
    description = "The minimum-variance OHLC estimator; alone among them it handles overnight gaps and drift."
    horizon = Horizon.SWING
    min_bars = 100
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        yz = f.yang_zhang_vol(self.params["window"])
        return -squash(zscore(yz, 60), 1.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"yang_zhang_vol_pct": float(f.yang_zhang_vol(20).iloc[-1] * 100),
                "vol_percentile": float(rolling_rank(f.yang_zhang_vol(20), 120).iloc[-1])}


class RogersSatchellVol(BaseStrategy):
    name = "Rogers-Satchell Drift-Robust Volatility"
    category = CAT
    family = "range_vol"
    research = "Rogers & Satchell (1991), 'Estimating Variance from High, Low and Closing Prices', Ann. Appl. Prob. 1(4)"
    description = "Range estimator that stays unbiased under nonzero drift, unlike Parkinson and Garman-Klass."
    horizon = Horizon.SWING
    min_bars = 100
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        rs = f.rogers_satchell_vol(self.params["window"])
        cc = f.realized_vol(self.params["window"])
        return -squash(zscore(_safe_div(rs, cc.where(cc > 1e-9), 1.0), 60), 1.5)


class BipowerJumpDetection(BaseStrategy):
    name = "Bipower Variation Jump Detection"
    category = CAT
    family = "jumps"
    research = "Barndorff-Nielsen & Shephard (2004), 'Power and Bipower Variation', J. Fin. Econometrics 2(1)"
    description = "Separates continuous diffusion from discrete jumps; jumps mean-revert where diffusion trends."
    horizon = Horizon.SWING
    min_bars = 120
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        r = f.logret.abs()
        rv = (f.logret ** 2).rolling(w, min_periods=w // 2).sum()
        bv = (np.pi / 2) * (r * r.shift(1)).rolling(w, min_periods=w // 2).sum()
        jump_ratio = _safe_div(rv - bv, rv.where(rv > 1e-14)).clip(0, 1)
        # A large jump component ⇒ recent move is discontinuous ⇒ fade it.
        return -np.sign(f.logret).fillna(0) * jump_ratio

    def diagnostics(self, f: FeatureSet) -> dict:
        w = 20
        r = f.logret.abs()
        rv = float((f.logret ** 2).rolling(w).sum().iloc[-1])
        bv = float(((np.pi / 2) * (r * r.shift(1)).rolling(w).sum()).iloc[-1])
        return {"jump_component_share": max(0.0, (rv - bv) / rv) if rv > 0 else 0.0}


class MertonJumpDiffusion(BaseStrategy):
    name = "Merton Jump-Diffusion Discrepancy"
    category = CAT
    family = "jumps"
    research = "Merton (1976), 'Option Pricing When Underlying Stock Returns Are Discontinuous', JFE 3(1-2)"
    description = "Flags returns too large for the diffusion component alone, implying a jump that partly retraces."
    horizon = Horizon.SWING
    min_bars = 120
    params = {"window": 60, "threshold": 3.0}

    def score(self, f: FeatureSet) -> pd.Series:
        sd = f.logret.rolling(self.params["window"], min_periods=20).std(ddof=0)
        z = _safe_div(f.logret, sd.where(sd > 1e-12))
        excess = (z.abs() - self.params["threshold"]).clip(0, 3) / 3.0
        return -np.sign(z).fillna(0) * excess


class RealizedSkewness(BaseStrategy):
    name = "Realized Skewness Premium"
    category = CAT
    family = "higher_moments"
    research = "Amaya, Christoffersen, Jacobs & Vasquez (2015), 'Does Realized Skewness Predict Returns?', JFE 118(1)"
    description = "Negative realised skewness predicts higher subsequent returns — compensation for crash risk."
    horizon = Horizon.SWING
    min_bars = 120
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        return -squash(f.skew(self.params["window"]), 0.8)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"realized_skew": float(f.skew(60).iloc[-1]),
                "excess_kurtosis": float(f.kurtosis(60).iloc[-1])}


class VolatilityOfVolatility(BaseStrategy):
    name = "Volatility of Volatility"
    category = CAT
    family = "vol_of_vol"
    research = "Huang, Schlag, Shaliastovich & Thimme (2019), 'Volatility-of-Volatility Risk', JFQA 54(6)"
    description = "Instability in the volatility process itself is a distinct priced risk from volatility level."
    horizon = Horizon.SWING
    min_bars = 160
    params = {"vol_window": 20, "vov_window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        rv = f.realized_vol(self.params["vol_window"])
        vov = rv.rolling(self.params["vov_window"], min_periods=20).std(ddof=0)
        return -squash(zscore(vov, 120), 1.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        rv = f.realized_vol(20)
        return {"vol_of_vol": float(rv.rolling(60).std(ddof=0).iloc[-1] * 100)}


class VolatilityTermStructure(BaseStrategy):
    name = "Realized Volatility Term Structure"
    category = CAT
    family = "vol_term"
    research = "Term-structure framework per Christoffersen, Heston & Jacobs (2009), Management Science 55(12)"
    description = "Short- versus long-horizon volatility slope; inversion typically marks stress and precedes reversion."
    horizon = Horizon.SWING
    min_bars = 150
    params = {"short": 10, "long": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        s, l = f.realized_vol(self.params["short"]), f.realized_vol(self.params["long"])
        slope = _safe_div(s - l, l.where(l > 1e-9))
        return -squash(slope, 0.3)

    def diagnostics(self, f: FeatureSet) -> dict:
        s, l = float(f.realized_vol(10).iloc[-1]), float(f.realized_vol(60).iloc[-1])
        return {"short_vol_pct": s * 100, "long_vol_pct": l * 100,
                "structure": "inverted (stress)" if s > l * 1.15 else "normal"}


class VolatilityBreakout(BaseStrategy):
    name = "Volatility Expansion Breakout"
    category = CAT
    family = "vol_breakout"
    research = "Crabel (1990), 'Day Trading with Short Term Price Patterns'; NR7 / narrow-range compression"
    description = "Trades the direction of the first expansion out of a historically narrow range."
    horizon = Horizon.SWING
    min_bars = 100
    params = {"compress_window": 7, "lookback": 60, "hold": 6}

    def score(self, f: FeatureSet) -> pd.Series:
        rng = f.true_range
        narrow = rng.rolling(self.params["compress_window"], min_periods=self.params["compress_window"]).max()
        # fill_value on the shift rather than a later .fillna — shifting a bool
        # Series introduces NaN, promoting it to object dtype, and .fillna on
        # object dtype is deprecated and changes behaviour in a future pandas.
        was_narrow = (narrow <= rng.rolling(self.params["lookback"],
                                            min_periods=20).quantile(0.25)
                      ).shift(1, fill_value=False)
        expanding = rng > rng.rolling(20, min_periods=10).mean() * 1.5
        trigger = (was_narrow & expanding).astype(float)
        return persist(trigger * np.sign(f.close - f.open), self.params["hold"])

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"true_range": float(f.true_range.iloc[-1]), "atr14": float(f.atr(14).iloc[-1]),
                "range_percentile": float(rolling_rank(f.true_range, 60).iloc[-1])}


class VolatilityClustering(BaseStrategy):
    name = "Volatility Clustering Persistence"
    category = CAT
    family = "vol_cluster"
    research = "Mandelbrot (1963); formalised in Engle (1982), 'Autoregressive Conditional Heteroscedasticity', Econometrica 50(4)"
    description = "Volatility is autocorrelated even when returns are not; positions size down as clustering intensifies."
    horizon = Horizon.SWING
    min_bars = 140
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        absr = f.logret.abs()
        cluster = absr.rolling(self.params["window"], min_periods=20).corr(absr.shift(1))
        trend = np.sign(f.ema(20) - f.ema(50)).fillna(0)
        return trend * (1 - cluster.clip(0, 1)) * 0.7

    def diagnostics(self, f: FeatureSet) -> dict:
        absr = f.logret.abs()
        return {"vol_autocorrelation": float(absr.rolling(60).corr(absr.shift(1)).iloc[-1])}


class ATRPositionScaling(BaseStrategy):
    name = "ATR-Normalised Trend Exposure"
    category = CAT
    family = "vol_target"
    research = "Wilder (1978) ATR; risk-parity sizing per Qian (2005), 'Risk Parity Portfolios'"
    description = "Expresses trend conviction in ATR units so a quiet market and a violent one are treated alike."
    horizon = Horizon.SWING
    min_bars = 100
    params = {"trend_window": 50, "atr_period": 14}

    def score(self, f: FeatureSet) -> pd.Series:
        move = f.close - f.close.shift(self.params["trend_window"])
        atr = f.atr(self.params["atr_period"])
        return squash(_safe_div(move, atr.where(atr > 1e-12)) / np.sqrt(self.params["trend_window"]), 1.0)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"natr_pct": float(f.natr(14).iloc[-1] * 100),
                "move_in_atr": float((f.close.iloc[-1] - f.close.iloc[-51]) / f.atr(14).iloc[-1]) if f.n > 51 else float("nan")}


class VolatilitySeasonality(BaseStrategy):
    name = "Intraday Volatility Seasonality"
    category = CAT
    family = "vol_seasonal"
    research = "Andersen & Bollerslev (1997), 'Intraday Periodicity and Volatility Persistence', J. Empirical Finance 4(2-3)"
    description = "Volatility follows a strong intraday U-shape; deviations from the seasonal norm carry information."
    horizon = Horizon.INTRADAY
    min_bars = 200

    def availability(self, f: FeatureSet):
        if f.interval in ("1d", "1wk", "1mo"):
            return False, "requires intraday bars"
        return super().availability(f)

    def score(self, f: FeatureSet) -> pd.Series:
        if not isinstance(f.df.index, pd.DatetimeIndex):
            return pd.Series(np.nan, index=f.close.index)
        rng = f.true_range / f.close
        hour = f.df.index.hour
        seasonal = rng.groupby(hour).transform(lambda x: x.expanding(min_periods=5).mean())
        excess = _safe_div(rng - seasonal, seasonal.where(seasonal > 1e-12))
        return -np.sign(f.logret).fillna(0) * squash(excess, 0.5).abs()


class TailRiskHedge(BaseStrategy):
    name = "Conditional Tail Risk (CVaR)"
    category = CAT
    family = "tail_risk"
    research = "Rockafellar & Uryasev (2000), 'Optimization of Conditional Value-at-Risk', J. Risk 2(3)"
    description = "Expected loss beyond the VaR threshold; deteriorating CVaR cuts exposure before drawdown compounds."
    horizon = Horizon.SWING
    min_bars = 160
    params = {"window": 120, "alpha": 0.05}

    def score(self, f: FeatureSet) -> pd.Series:
        w, a = self.params["window"], self.params["alpha"]
        var = f.logret.rolling(w, min_periods=w // 2).quantile(a)
        cvar = f.logret.where(f.logret <= var).rolling(w, min_periods=5).mean()
        trend = np.sign(f.ema(20) - f.ema(50)).fillna(0)
        # Worse (more negative) CVaR than usual ⇒ scale down.
        risk_off = (1 + squash(zscore(cvar, w), 1.5)).clip(0, 1)
        return trend * risk_off

    def diagnostics(self, f: FeatureSet) -> dict:
        w, a = 120, 0.05
        var = float(f.logret.rolling(w, min_periods=40).quantile(a).iloc[-1])
        cv = float(f.logret.where(f.logret <= var).tail(w).mean())
        return {"var_95_pct": var * 100, "cvar_95_pct": cv * 100}


class DrawdownControl(BaseStrategy):
    name = "Drawdown-Controlled Exposure"
    category = CAT
    family = "drawdown"
    research = "Grossman & Zhou (1993), 'Optimal Investment Strategies for Controlling Drawdowns', Math. Finance 3(3)"
    description = "Cuts exposure as drawdown from the running peak deepens — the constraint most institutional mandates impose."
    horizon = Horizon.POSITION
    min_bars = 120
    params = {"max_dd": 0.20}

    def score(self, f: FeatureSet) -> pd.Series:
        dd = f.drawdown()
        allowed = (1 + dd / self.params["max_dd"]).clip(0, 1)
        trend = np.sign(f.ema(50) - f.ema(200)).fillna(0)
        return trend * allowed

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"current_drawdown_pct": float(f.drawdown().iloc[-1] * 100),
                "max_drawdown_pct": float(f.drawdown().min() * 100)}
