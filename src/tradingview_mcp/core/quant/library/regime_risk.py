"""
Regime detection and risk management.

Not directional models so much as the layer that decides how much of a
directional model to believe. This is where the risk desks at Bridgewater,
Man Group and the multi-manager platforms spend most of their effort, and it is
the layer most retail systems skip entirely.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import BaseStrategy, DataNeed, Horizon, Regime, band_score, squash
from ..features import FeatureSet, _safe_div, rolling_rank, zscore

CAT = "Regime & Risk"


class AbsorptionRatio(BaseStrategy):
    name = "Absorption Ratio Systemic Risk"
    category = CAT
    family = "systemic_risk"
    research = "Kritzman, Li, Page & Rigobon (2011), 'Principal Components as a Measure of Systemic Risk', JPM 37(4)"
    description = "Fraction of variance explained by the top principal components; a spike precedes fragility."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    horizon = Horizon.POSITION
    min_bars = 250

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("universe_returns") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class BullBearClassifier(BaseStrategy):
    name = "Bull-Bear Market Classifier"
    category = CAT
    family = "market_state"
    research = "Lunde & Timmermann (2004), 'Duration Dependence in Stock Prices', J. Business & Economic Statistics 22(3)"
    description = "Classifies the market state by drawdown depth from the running peak, with hysteresis to avoid whipsaw."
    horizon = Horizon.POSITION
    min_bars = 200
    params = {"bear_threshold": -0.20, "bull_threshold": 0.20}

    def score(self, f: FeatureSet) -> pd.Series:
        dd = f.drawdown()
        trough = f.close / f.close.rolling(252, min_periods=60).min() - 1
        state = np.where(dd <= self.params["bear_threshold"], -1.0,
                         np.where(trough >= self.params["bull_threshold"], 1.0, np.nan))
        return pd.Series(state, index=f.close.index).ffill().fillna(0) * 0.7

    def diagnostics(self, f: FeatureSet) -> dict:
        dd = float(f.drawdown().iloc[-1])
        return {"drawdown_from_peak_pct": dd * 100,
                "market_state": "bear" if dd <= -0.20 else "bull/neutral"}


class VolatilityRegimeSwitch(BaseStrategy):
    name = "Volatility Regime Switch"
    category = CAT
    family = "vol_regime"
    research = "Ang & Timmermann (2012), 'Regime Changes and Financial Markets', Annual Review of Financial Economics 4"
    description = "Selects between trend and reversion behaviour based on where volatility sits in its own distribution."
    horizon = Horizon.SWING
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        vr = f.vol_regime
        z = zscore(f.close, 20)
        trend = np.sign(f.ema(20) - f.ema(50)).fillna(0)
        # Low vol → trends persist; high vol → moves overshoot and revert.
        return trend * (1 - vr).clip(0, 1) - squash(z, 1.5) * vr.clip(0, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        vr = float(f.vol_regime.iloc[-1])
        return {"vol_percentile": vr,
                "active_mode": "trend-following (calm)" if vr < 0.5 else "mean-reversion (stressed)"}


class CorrelationRegimeBreak(BaseStrategy):
    name = "Correlation Regime Break"
    category = CAT
    family = "correlation"
    research = "Ang & Chen (2002), 'Asymmetric Correlations of Equity Portfolios', JFE 63(3)"
    description = "Correlations rise in crashes exactly when diversification is needed; a regime break cuts risk."
    needs = (DataNeed.OHLC, DataNeed.BENCHMARK)
    horizon = Horizon.POSITION
    min_bars = 200
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        b = f.meta.get("benchmark_close")
        if b is None:
            return pd.Series(np.nan, index=f.close.index)
        w = self.params["window"]
        br = pd.Series(b, index=f.close.index).pct_change()
        corr = f.ret.rolling(w, min_periods=w // 2).corr(br)
        return -squash(zscore(corr, 120), 1.5)


class ExtremeValueTailRisk(BaseStrategy):
    name = "Extreme Value Theory Tail Estimate"
    category = CAT
    family = "tail_risk"
    research = "Embrechts, Klüppelberg & Mikosch (1997), 'Modelling Extremal Events'; Hill (1975) tail index estimator"
    description = "Estimates the tail index from exceedances; a fattening tail means the ordinary risk model understates loss."
    horizon = Horizon.POSITION
    min_bars = 250
    params = {"window": 250, "tail_frac": 0.05}

    def score(self, f: FeatureSet) -> pd.Series:
        w, tf = self.params["window"], self.params["tail_frac"]
        thresh = f.logret.rolling(w, min_periods=w // 2).quantile(tf)
        exceed = (f.logret < thresh).astype(float).rolling(w, min_periods=w // 2).mean()
        # Exceedances arriving faster than the nominal rate ⇒ fattening tail ⇒ de-risk.
        fattening = ((exceed - tf) / tf).clip(-1, 2)
        trend = np.sign(f.ema(50) - f.ema(200)).fillna(0)
        return trend * (1 - fattening.clip(0, 1))

    def diagnostics(self, f: FeatureSet) -> dict:
        w, tf = 250, 0.05
        thresh = float(f.logret.rolling(w, min_periods=100).quantile(tf).iloc[-1])
        rate = float((f.logret < thresh).astype(float).rolling(w, min_periods=100).mean().iloc[-1])
        return {"tail_threshold_pct": thresh * 100, "observed_exceedance_rate": rate,
                "expected_rate": tf}


class CornishFisherVaR(BaseStrategy):
    name = "Cornish-Fisher Modified VaR"
    category = CAT
    family = "var"
    research = "Cornish & Fisher (1938); financial application per Favre & Galeano (2002), JAI 5(2)"
    description = "Adjusts VaR for skewness and kurtosis, correcting the normal assumption's understatement of tail loss."
    horizon = Horizon.POSITION
    min_bars = 200
    params = {"window": 120, "z": 1.645}

    def score(self, f: FeatureSet) -> pd.Series:
        w, z = self.params["window"], self.params["z"]
        mu = f.logret.rolling(w, min_periods=w // 2).mean()
        sd = f.logret.rolling(w, min_periods=w // 2).std(ddof=0)
        s = f.skew(w)
        k = f.kurtosis(w)
        # Cornish-Fisher expansion of the normal quantile.
        zcf = (z + (z ** 2 - 1) * s / 6 + (z ** 3 - 3 * z) * k / 24
               - (2 * z ** 3 - 5 * z) * s ** 2 / 36)
        var = mu - zcf * sd
        trend = np.sign(f.ema(50) - f.ema(200)).fillna(0)
        return trend * (1 + squash(zscore(var, w), 1.5)).clip(0, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        w = 120
        mu = float(f.logret.rolling(w, min_periods=60).mean().iloc[-1])
        sd = float(f.logret.rolling(w, min_periods=60).std(ddof=0).iloc[-1])
        s, k = float(f.skew(w).iloc[-1]), float(f.kurtosis(w).iloc[-1])
        z = 1.645
        zcf = z + (z**2 - 1) * s / 6 + (z**3 - 3*z) * k / 24 - (2*z**3 - 5*z) * s**2 / 36
        return {"skew": s, "excess_kurtosis": k, "normal_var_pct": (mu - z * sd) * 100,
                "modified_var_pct": (mu - zcf * sd) * 100}


class MaximumDrawdownGuard(BaseStrategy):
    name = "Maximum Drawdown Guard"
    category = CAT
    family = "drawdown"
    research = "Chekhlov, Uryasev & Zabarankin (2005), 'Drawdown Measure in Portfolio Optimization', IJTAF 8(1)"
    description = "Hard risk stop: exposure goes to zero as drawdown approaches the mandate limit."
    horizon = Horizon.POSITION
    min_bars = 150
    params = {"limit": 0.15, "recovery": 0.5}

    def score(self, f: FeatureSet) -> pd.Series:
        dd = f.drawdown()
        capacity = (1 + dd / self.params["limit"]).clip(0, 1)
        trend = np.sign(f.ema(20) - f.ema(50)).fillna(0)
        return trend * capacity

    def diagnostics(self, f: FeatureSet) -> dict:
        dd = float(f.drawdown().iloc[-1])
        return {"current_drawdown_pct": dd * 100, "limit_pct": self.params["limit"] * 100,
                "risk_capacity_remaining": float(max(0.0, 1 + dd / self.params["limit"]))}


class UlcerIndexRisk(BaseStrategy):
    name = "Ulcer Index Downside Risk"
    category = CAT
    family = "drawdown"
    research = "Martin & McCann (1989), 'The Investor's Guide to Fidelity Funds'"
    description = "Root-mean-square drawdown; penalises depth and duration together, unlike standard deviation."
    horizon = Horizon.POSITION
    min_bars = 150
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        dd = f.drawdown() * 100
        ulcer = np.sqrt((dd ** 2).rolling(self.params["window"], min_periods=20).mean())
        return -squash(zscore(ulcer, 120), 1.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        dd = f.drawdown() * 100
        return {"ulcer_index": float(np.sqrt((dd ** 2).rolling(60, min_periods=20).mean()).iloc[-1])}


class SortinoDownsideDeviation(BaseStrategy):
    name = "Sortino Downside Deviation"
    category = CAT
    family = "risk_adjusted"
    research = "Sortino & Price (1994), 'Performance Measurement in a Downside Risk Framework', JOI 3(3)"
    description = "Risk-adjusted return counting only downside deviation, since upside volatility is not a risk."
    horizon = Horizon.POSITION
    min_bars = 200
    params = {"window": 120}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        mu = f.logret.rolling(w, min_periods=w // 2).mean()
        downside = f.logret.where(f.logret < 0, 0.0).rolling(w, min_periods=w // 2).std(ddof=0)
        sortino = mu / downside.where(downside > 1e-12) * np.sqrt(f.bars_per_year)
        return squash(sortino, 1.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        w = 120
        mu = float(f.logret.rolling(w, min_periods=60).mean().iloc[-1])
        ds = float(f.logret.where(f.logret < 0, 0).rolling(w, min_periods=60).std(ddof=0).iloc[-1])
        return {"sortino_ratio": mu / ds * np.sqrt(f.bars_per_year) if ds > 1e-12 else 0.0}


class RegimeConditionalLeverage(BaseStrategy):
    name = "Regime-Conditional Leverage"
    category = CAT
    family = "vol_regime"
    research = "Ang & Bekaert (2004), 'How Regimes Affect Asset Allocation', FAJ 60(2)"
    description = "Scales gross exposure by the joint state of volatility, trend quality and drawdown."
    horizon = Horizon.POSITION
    min_bars = 250

    def score(self, f: FeatureSet) -> pd.Series:
        calm = (1 - f.vol_regime).clip(0, 1)
        quality = f.trend_strength.clip(0, 1)
        healthy = (1 + f.drawdown() / 0.25).clip(0, 1)
        exposure = (calm * quality * healthy) ** (1 / 3)
        return np.sign(f.ema(50) - f.ema(200)).fillna(0) * exposure

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"vol_percentile": float(f.vol_regime.iloc[-1]),
                "trend_strength": float(f.trend_strength.iloc[-1]),
                "drawdown_pct": float(f.drawdown().iloc[-1] * 100)}


class TrendFragilityIndex(BaseStrategy):
    name = "Trend Fragility Index"
    category = CAT
    family = "fragility"
    research = "Fragility framework per Taleb (2012), 'Antifragile'; convexity measurement per Taleb & Douady (2013), Quant. Finance 13(11)"
    description = "Detects trends becoming parabolic — accelerating on falling volume, historically a fragile configuration."
    horizon = Horizon.SWING
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        accel = f.close.pct_change(10) - f.close.pct_change(40) / 4
        vol_fade = -zscore(f.volume.fillna(f.volume.median()), 40) if f.has_volume else 0.0
        fragile = squash(zscore(accel, 60), 1.5).abs() * (1 + vol_fade).clip(0, 2) / 2
        return -np.sign(accel).fillna(0) * fragile.clip(0, 1)


class LiquidityStressIndex(BaseStrategy):
    name = "Composite Liquidity Stress"
    category = CAT
    family = "systemic_risk"
    research = "Composite stress framework per Kliesen, Owyang & Vermann (2012), Federal Reserve Bank of St. Louis Review 94(5)"
    description = "Blends volatility, range expansion and volume collapse into one stress reading that gates exposure."
    horizon = Horizon.SWING
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        vol_stress = f.vol_regime
        range_stress = rolling_rank(f.natr(14), 120)
        vol_dry = 1 - rolling_rank(f.volume.fillna(0), 120) if f.has_volume else 0.5
        stress = (vol_stress + range_stress + vol_dry) / 3
        trend = np.sign(f.ema(20) - f.ema(50)).fillna(0)
        return trend * (1 - stress).clip(0, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        vs, rs = float(f.vol_regime.iloc[-1]), float(rolling_rank(f.natr(14), 120).iloc[-1])
        vd = float(1 - rolling_rank(f.volume.fillna(0), 120).iloc[-1]) if f.has_volume else 0.5
        return {"vol_stress": vs, "range_stress": rs, "volume_dryness": vd,
                "composite_stress": (vs + rs + vd) / 3}


class YieldCurveSignal(BaseStrategy):
    name = "Yield Curve Recession Signal"
    category = CAT
    family = "macro"
    research = "Estrella & Mishkin (1998), 'Predicting U.S. Recessions', REStat 80(1)"
    description = "Term-spread inversion is the most reliable single recession predictor; needs a rates feed."
    needs = (DataNeed.OHLC, DataNeed.BENCHMARK)
    horizon = Horizon.POSITION
    min_bars = 250

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("term_spread") is None:
            return pd.Series(np.nan, index=f.close.index)
        spread = pd.Series(f.meta["term_spread"], index=f.close.index)
        return squash(spread, 1.0)


class MomentumCrashRisk(BaseStrategy):
    name = "Momentum Crash Risk"
    category = CAT
    family = "crash_risk"
    research = "Daniel & Moskowitz (2016), 'Momentum Crashes', JFE 122(2)"
    description = "Momentum crashes in panic rebounds; bear market plus rising volatility disables the momentum leg."
    horizon = Horizon.POSITION
    min_bars = 280

    def score(self, f: FeatureSet) -> pd.Series:
        mom = squash(zscore(f.close.pct_change(126), 252), 1.5)
        bear = (f.drawdown() < -0.20).astype(float)
        vol_rising = (f.realized_vol(20) > f.realized_vol(60)).astype(float)
        crash_risk = (bear * vol_rising).clip(0, 1)
        return mom * (1 - crash_risk)

    def diagnostics(self, f: FeatureSet) -> dict:
        dd = float(f.drawdown().iloc[-1])
        return {"drawdown_pct": dd * 100, "in_bear_market": bool(dd < -0.20),
                "vol_rising": bool(f.realized_vol(20).iloc[-1] > f.realized_vol(60).iloc[-1]),
                "momentum_disabled": bool(dd < -0.20 and f.realized_vol(20).iloc[-1] > f.realized_vol(60).iloc[-1])}


class SkewnessRiskPremium(BaseStrategy):
    name = "Skewness Risk Premium"
    category = CAT
    family = "higher_moments"
    research = "Harvey & Siddique (2000), 'Conditional Skewness in Asset Pricing Tests', JF 55(3)"
    description = "Assets with negative coskewness demand a premium; skew is a priced risk beyond variance."
    horizon = Horizon.POSITION
    min_bars = 250
    params = {"window": 120}

    def score(self, f: FeatureSet) -> pd.Series:
        s = f.skew(self.params["window"])
        return -squash(zscore(s, 250), 1.5)


class RecoveryRateSignal(BaseStrategy):
    name = "Drawdown Recovery Momentum"
    category = CAT
    family = "drawdown"
    research = "Recovery dynamics per Magdon-Ismail & Atiya (2004), 'Maximum Drawdown', Risk Magazine 17(10)"
    description = "Speed of recovery from a drawdown separates a genuine base from a dead-cat bounce."
    horizon = Horizon.SWING
    min_bars = 200
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        dd = f.drawdown()
        trough = dd.rolling(self.params["window"], min_periods=20).min()
        # Fraction of the drawdown already recovered.
        recovery = _safe_div(dd - trough, (-trough).where(trough < -0.01)).clip(0, 1)
        deep = (-trough / 0.15).clip(0, 1)
        return squash(recovery * deep * 2, 0.8)

    def diagnostics(self, f: FeatureSet) -> dict:
        dd = f.drawdown()
        tr = float(dd.rolling(60, min_periods=20).min().iloc[-1])
        cur = float(dd.iloc[-1])
        return {"trough_drawdown_pct": tr * 100, "current_drawdown_pct": cur * 100,
                "recovered_fraction": (cur - tr) / -tr if tr < -0.01 else 0.0}


class PositionConcentrationLimit(BaseStrategy):
    name = "Volatility Budget Allocation"
    category = CAT
    family = "budget"
    research = "Risk budgeting per Roncalli (2013), 'Introduction to Risk Parity and Budgeting'"
    description = "Allocates a fixed volatility budget, so position size falls exactly as risk per unit rises."
    horizon = Horizon.POSITION
    min_bars = 150
    params = {"budget": 0.10, "window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        vol = f.realized_vol(self.params["window"])
        size = (self.params["budget"] / vol.where(vol > 1e-6)).clip(0, 1)
        return np.sign(f.ema(20) - f.ema(50)).fillna(0) * size

    def diagnostics(self, f: FeatureSet) -> dict:
        v = float(f.realized_vol(20).iloc[-1])
        return {"realized_vol_pct": v * 100, "budget_pct": self.params["budget"] * 100,
                "allocation_fraction": float(min(self.params["budget"] / v, 1.0)) if v > 1e-6 else 0.0}
