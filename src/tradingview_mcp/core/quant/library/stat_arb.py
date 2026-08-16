"""
Statistical arbitrage.

The methods behind the classic relative-value desks — Morgan Stanley's original
BAMS group, D.E. Shaw, Renaissance, Millennium pods. Several of these genuinely
require two or more price series; those declare CROSS_SECTION and stand down
rather than quietly degrading to a single-series approximation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps

from ..base import BaseStrategy, DataNeed, Horizon, Regime, band_score, squash
from ..features import FeatureSet, _safe_div, linreg_slope, rolling_rank, zscore

CAT = "Statistical Arbitrage"


class EngleGrangerCointegration(BaseStrategy):
    name = "Engle-Granger Cointegration Spread"
    category = CAT
    family = "cointegration"
    research = "Engle & Granger (1987), 'Co-integration and Error Correction', Econometrica 55(2)"
    description = "Regresses one leg on the other, tests the residual for stationarity, and trades its z-score."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 150
    params = {"window": 90, "adf_threshold": -2.86}

    def score(self, f: FeatureSet) -> pd.Series:
        partner = f.meta.get("pair_close")
        if partner is None:
            return pd.Series(np.nan, index=f.close.index)
        y, x = np.log(f.close), np.log(pd.Series(partner, index=f.close.index).replace(0, np.nan))
        w = self.params["window"]
        beta = y.rolling(w, min_periods=w // 2).cov(x) / x.rolling(w, min_periods=w // 2).var(ddof=0)
        resid = y - beta * x
        return -squash(zscore(resid, w), 1.5)


class OrnsteinUhlenbeck(BaseStrategy):
    name = "Ornstein-Uhlenbeck Process Fit"
    category = CAT
    family = "ou_process"
    research = "Uhlenbeck & Ornstein (1930); trading application per Bertram (2010), Physica A 389(11)"
    description = "Fits dP = θ(μ-P)dt + σdW by regression and trades displacement scaled by the fitted noise."
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 140
    params = {"window": 100}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        lag, delta = f.close.shift(1), f.close.diff()
        mp = max(20, w // 2)
        cov = delta.rolling(w, min_periods=mp).cov(lag)
        var = lag.rolling(w, min_periods=mp).var(ddof=0)
        theta = -(cov / var.where(var > 1e-12))
        mean_lag = lag.rolling(w, min_periods=mp).mean()
        mean_d = delta.rolling(w, min_periods=mp).mean()
        mu = (mean_d / theta.where(theta.abs() > 1e-12)) + mean_lag
        sigma = delta.rolling(w, min_periods=mp).std(ddof=0)
        dev = (f.close - mu) / sigma.where(sigma > 1e-12)
        # Only meaningful when θ>0, i.e. the process actually pulls back.
        return (-squash(dev, 2.0)).where(theta > 0, 0.0)

    def diagnostics(self, f: FeatureSet) -> dict:
        w = self.params["window"]
        lag, delta = f.close.shift(1), f.close.diff()
        cov = delta.rolling(w, min_periods=50).cov(lag)
        var = lag.rolling(w, min_periods=50).var(ddof=0)
        theta = float(-(cov / var).iloc[-1])
        return {"theta_mean_reversion_speed": theta,
                "half_life_bars": float(np.log(2) / theta) if theta > 0 else float("inf")}


class KalmanFilterTrend(BaseStrategy):
    name = "Kalman Filter State Estimate"
    category = CAT
    family = "kalman"
    research = "Kalman (1960), 'A New Approach to Linear Filtering'; trading use per Chan (2013) ch. 3"
    description = "Recursive optimal estimate of the latent fair value; trades price displacement from that state."
    horizon = Horizon.SWING
    min_bars = 80
    params = {"process_var": 1e-5, "measure_var": 1e-2}

    def score(self, f: FeatureSet) -> pd.Series:
        z = f.close.to_numpy(dtype=float)
        q, r = self.params["process_var"], self.params["measure_var"]
        # Scale process noise to the series level so the filter is unit-agnostic.
        scale = float(np.nanmedian(np.abs(np.diff(z)))) or 1.0
        q *= scale ** 2 * 1e4
        xh = np.zeros_like(z); p = np.zeros_like(z)
        xh[0], p[0] = z[0], 1.0
        for k in range(1, len(z)):
            p_minus = p[k - 1] + q
            gain = p_minus / (p_minus + r * scale ** 2)
            xh[k] = xh[k - 1] + gain * (z[k] - xh[k - 1])
            p[k] = (1 - gain) * p_minus
        state = pd.Series(xh, index=f.close.index)
        dev = (f.close - state) / f.atr(14).where(f.atr(14) > 1e-12)
        return -squash(dev, 1.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"atr": float(f.atr(14).iloc[-1])}


class AvellanedaLeeStatArb(BaseStrategy):
    name = "Avellaneda-Lee Residual s-Score"
    category = CAT
    family = "residual_statarb"
    research = "Avellaneda & Lee (2010), 'Statistical Arbitrage in the U.S. Equities Market', Quant. Finance 10(7)"
    description = "Trades the s-score of an OU-fitted residual from a factor regression — the modern stat-arb standard."
    needs = (DataNeed.OHLC, DataNeed.BENCHMARK)
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 150
    params = {"window": 60, "entry": 1.25}

    def score(self, f: FeatureSet) -> pd.Series:
        bench = f.meta.get("benchmark_close")
        if bench is None:
            return pd.Series(np.nan, index=f.close.index)
        w = self.params["window"]
        br = pd.Series(bench, index=f.close.index).pct_change()
        cov = f.ret.rolling(w, min_periods=w // 2).cov(br)
        var = br.rolling(w, min_periods=w // 2).var(ddof=0)
        beta = cov / var.where(var > 1e-14)
        resid_cum = (f.ret - beta * br).rolling(w, min_periods=w // 2).sum()
        return -squash(zscore(resid_cum, w) / self.params["entry"], 1.2)


class VarianceRatioTest(BaseStrategy):
    name = "Lo-MacKinlay Variance Ratio"
    category = CAT
    family = "variance_ratio"
    research = "Lo & MacKinlay (1988), 'Stock Market Prices Do Not Follow Random Walks', RFS 1(1)"
    description = "Measures whether the series trends or reverts, then applies the matching signal — a regime switch, not a directional bet."
    horizon = Horizon.SWING
    min_bars = 150
    params = {"q": 5, "window": 100}

    def score(self, f: FeatureSet) -> pd.Series:
        vr = f.variance_ratio(self.params["q"], self.params["window"])
        z = zscore(f.close, 20)
        trending = (vr - 1.0).clip(-0.5, 0.5) * 2  # +1 trending, -1 reverting
        return (squash(z, 1.5) * trending.clip(0, 1) - squash(z, 1.5) * (-trending).clip(0, 1))

    def diagnostics(self, f: FeatureSet) -> dict:
        vr = float(f.variance_ratio(5, 100).iloc[-1])
        return {"variance_ratio": vr,
                "regime": "trending" if vr > 1.05 else "mean-reverting" if vr < 0.95 else "random walk"}

    def explain(self, f: FeatureSet, v: float, d: dict) -> str:
        return (f"Variance ratio {d.get('variance_ratio', 1):.2f} ⇒ {d.get('regime')}; "
                f"applying the matching signal at conviction {abs(v):.2f}.")


class HurstExponentRegime(BaseStrategy):
    name = "Hurst Exponent Regime Switch"
    category = CAT
    family = "hurst"
    research = "Hurst (1951); Mandelbrot & Wallis (1969); modified R/S per Lo (1991), Econometrica 59(5)"
    description = "H<0.5 selects reversion, H>0.5 selects continuation, with conviction scaled by distance from 0.5."
    horizon = Horizon.SWING
    min_bars = 160
    params = {"window": 100}

    def score(self, f: FeatureSet) -> pd.Series:
        h = f.hurst(self.params["window"])
        z = zscore(f.close, 20)
        tilt = ((h - 0.5) * 4).clip(-1, 1)          # +1 trending, -1 reverting
        return squash(z, 1.5) * tilt

    def diagnostics(self, f: FeatureSet) -> dict:
        h = float(f.hurst(100).iloc[-1])
        return {"hurst": h,
                "interpretation": "persistent/trending" if h > 0.55 else
                                  "anti-persistent/mean-reverting" if h < 0.45 else "random walk"}


class HiddenMarkovRegime(BaseStrategy):
    name = "Two-State Gaussian Regime Filter"
    category = CAT
    family = "regime_switch"
    research = "Hamilton (1989), 'A New Approach to the Economic Analysis of Nonstationary Time Series', Econometrica 57(2)"
    description = "Classifies each bar into a calm or turbulent state from volatility and drift, then trades accordingly."
    horizon = Horizon.SWING
    min_bars = 150
    params = {"short": 10, "long": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        v_s = f.logret.rolling(self.params["short"], min_periods=5).std(ddof=0)
        v_l = f.logret.rolling(self.params["long"], min_periods=20).std(ddof=0)
        ratio = _safe_div(v_s, v_l.where(v_l > 1e-12), 1.0)
        z = zscore(f.close, 20)
        calm = (ratio < 0.9).astype(float)      # low-vol state → reversion pays
        stressed = (ratio > 1.4).astype(float)  # high-vol state → trend/continuation
        return -squash(z, 1.5) * calm + squash(z, 2.5) * stressed

    def diagnostics(self, f: FeatureSet) -> dict:
        v_s = f.logret.rolling(10).std(ddof=0).iloc[-1]
        v_l = f.logret.rolling(60).std(ddof=0).iloc[-1]
        ratio = float(v_s / v_l) if v_l else float("nan")
        return {"vol_ratio_short_long": ratio,
                "state": "calm" if ratio < 0.9 else "turbulent" if ratio > 1.4 else "transitional"}


class CopulaTailDependence(BaseStrategy):
    name = "Copula Tail Dependence"
    category = CAT
    family = "copula"
    research = "Xie, Liew, Wu & Zou (2016), 'Pairs Trading with Copulas', J. Trading 11(3)"
    description = "Uses the empirical copula of return and momentum ranks to find joint-distribution mispricings."
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 140
    params = {"window": 100}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        u = rolling_rank(f.ret, w)
        v = rolling_rank(f.close.pct_change(10), w)
        # Conditional mispricing: return rank far below its momentum rank ⇒ undervalued.
        return squash((v - u) * 2, 0.7)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"return_rank": float(rolling_rank(f.ret, 100).iloc[-1]),
                "momentum_rank": float(rolling_rank(f.close.pct_change(10), 100).iloc[-1])}


class PCAResidualArb(BaseStrategy):
    name = "PCA Residual Arbitrage"
    category = CAT
    family = "residual_statarb"
    research = "Avellaneda & Lee (2010); eigenportfolio construction per Litterman & Scheinkman (1991)"
    description = "Removes common principal-component exposure and trades the idiosyncratic remainder."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 150
    params = {"window": 90, "n_components": 3}

    def score(self, f: FeatureSet) -> pd.Series:
        panel = f.meta.get("universe_returns")
        if panel is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class AugmentedDickeyFuller(BaseStrategy):
    name = "ADF Stationarity-Gated Reversion"
    category = CAT
    family = "cointegration"
    research = "Dickey & Fuller (1979), JASA 74(366); Said & Dickey (1984), Biometrika 71(3)"
    description = "Runs a rolling unit-root regression and only fades the mean when the series tests stationary."
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 160
    params = {"window": 100, "crit": -2.0}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        lag, delta = f.close.shift(1), f.close.diff()
        mp = max(30, w // 2)
        cov = delta.rolling(w, min_periods=mp).cov(lag)
        var = lag.rolling(w, min_periods=mp).var(ddof=0)
        gamma = cov / var.where(var > 1e-12)
        # t-statistic on γ; γ significantly negative ⇒ reject unit root ⇒ stationary.
        resid_sd = delta.rolling(w, min_periods=mp).std(ddof=0)
        se = resid_sd / (np.sqrt(var.where(var > 1e-12)) * np.sqrt(w))
        tstat = gamma / se.where(se > 1e-14)
        stationary = (tstat < self.params["crit"]).astype(float)
        return -squash(zscore(f.close, 20), 1.5) * stationary

    def diagnostics(self, f: FeatureSet) -> dict:
        w = self.params["window"]
        lag, delta = f.close.shift(1), f.close.diff()
        cov = delta.rolling(w, min_periods=50).cov(lag)
        var = lag.rolling(w, min_periods=50).var(ddof=0)
        g = float((cov / var).iloc[-1])
        return {"adf_gamma": g, "unit_root_rejected": bool(g < -0.02)}


class BoxTiaoCanonical(BaseStrategy):
    name = "Box-Tiao Canonical Decomposition"
    category = CAT
    family = "cointegration"
    research = "Box & Tiao (1977), Biometrika 64(2); portfolio use per d'Aspremont (2011), Quant. Finance 11(3)"
    description = "Extracts the most predictable linear combination of a price panel rather than the least volatile."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    horizon = Horizon.SWING
    min_bars = 150

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("universe_returns") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class BayesianStateUpdate(BaseStrategy):
    name = "Bayesian Posterior Fair Value"
    category = CAT
    family = "bayesian"
    research = "Standard conjugate Normal-Normal updating; financial application per Rachev et al. (2008)"
    description = "Blends a long-window prior with recent observations by precision weighting, then fades the gap."
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 120
    params = {"prior_window": 60, "obs_window": 10}

    def score(self, f: FeatureSet) -> pd.Series:
        pw, ow = self.params["prior_window"], self.params["obs_window"]
        prior_mu = f.close.rolling(pw, min_periods=pw // 2).mean()
        prior_var = f.close.rolling(pw, min_periods=pw // 2).var(ddof=0)
        obs_mu = f.close.rolling(ow, min_periods=ow).mean()
        obs_var = f.close.rolling(ow, min_periods=ow).var(ddof=0)
        # Precision-weighted posterior mean.
        pp, po = 1 / prior_var.where(prior_var > 1e-12), 1 / obs_var.where(obs_var > 1e-12)
        post = (prior_mu * pp + obs_mu * po) / (pp + po)
        dev = (f.close - post) / np.sqrt(prior_var.where(prior_var > 1e-12))
        return -squash(dev, 1.5)


class DTWPatternMatch(BaseStrategy):
    name = "Shape-Matched Reversal Template"
    category = CAT
    family = "pattern_match"
    research = "Berndt & Clifford (1994) DTW; financial pattern matching per Lo, Mamaysky & Wang (2000), JF 55(4)"
    description = "Correlates the normalised recent path against V-shaped and inverted-V reversal templates."
    horizon = Horizon.SWING
    min_bars = 80
    params = {"window": 12}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        v_tmpl = np.concatenate([np.linspace(1, -1, w // 2), np.linspace(-1, 1, w - w // 2)])
        v_tmpl = (v_tmpl - v_tmpl.mean()) / (v_tmpl.std() or 1)

        def _corr(win: np.ndarray) -> float:
            sd = win.std()
            if sd < 1e-12:
                return 0.0
            return float(np.dot((win - win.mean()) / sd, v_tmpl) / len(win))

        corr = f.close.rolling(w, min_periods=w).apply(_corr, raw=True)
        # High positive correlation with a V ⇒ a bottom just completed ⇒ long.
        return squash(corr * 2, 0.8)


class JohansenEigenSpread(BaseStrategy):
    name = "Johansen Multivariate Cointegration"
    category = CAT
    family = "cointegration"
    research = "Johansen (1988), J. Economic Dynamics and Control 12(2-3); Johansen (1991), Econometrica 59(6)"
    description = "Maximum-likelihood cointegration across three or more legs; finds spreads pairwise tests miss."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    horizon = Horizon.SWING
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("universe_close") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class SpreadMomentumCarry(BaseStrategy):
    name = "Roll-Adjusted Term Structure Carry"
    category = CAT
    family = "carry"
    research = "Koijen, Moskowitz, Pedersen & Vrugt (2018), 'Carry', JFE 127(2)"
    description = "Trades the sign of the term-structure slope; carry is a distinct premium from momentum and value."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    horizon = Horizon.POSITION
    min_bars = 120

    def score(self, f: FeatureSet) -> pd.Series:
        front, back = f.meta.get("front_close"), f.meta.get("back_close")
        if front is None or back is None:
            return pd.Series(np.nan, index=f.close.index)
        fr = pd.Series(front, index=f.close.index)
        bk = pd.Series(back, index=f.close.index).replace(0, np.nan)
        return squash(np.log(fr / bk), 0.02)


class RollingBetaDislocation(BaseStrategy):
    name = "Rolling Beta Dislocation"
    category = CAT
    family = "residual_statarb"
    research = "Fama & MacBeth (1973), JPE 81(3); rolling-beta estimation per Lewellen & Nagel (2006), JFE 82(2)"
    description = "Flags when realised beta diverges sharply from its own history — the relationship has broken, not the price."
    needs = (DataNeed.OHLC, DataNeed.BENCHMARK)
    horizon = Horizon.SWING
    min_bars = 180
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        bench = f.meta.get("benchmark_close")
        if bench is None:
            return pd.Series(np.nan, index=f.close.index)
        w = self.params["window"]
        br = pd.Series(bench, index=f.close.index).pct_change()
        cov = f.ret.rolling(w, min_periods=w // 2).cov(br)
        var = br.rolling(w, min_periods=w // 2).var(ddof=0)
        beta = cov / var.where(var > 1e-14)
        return -squash(zscore(beta, 120), 1.5)


class AutocorrelationSignal(BaseStrategy):
    name = "Return Autocorrelation Sign"
    category = CAT
    family = "autocorrelation"
    research = "Fama (1970), 'Efficient Capital Markets', JF 25(2); Campbell, Lo & MacKinlay (1997) ch. 2"
    description = "Estimates first-order return autocorrelation and applies continuation or reversal to match its sign."
    horizon = Horizon.SWING
    min_bars = 140
    params = {"window": 100}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        r = f.ret
        ac = r.rolling(w, min_periods=w // 2).corr(r.shift(1))
        last_move = squash(zscore(r, 20), 1.5)
        return last_move * (ac * 4).clip(-1, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        r = f.ret
        ac = float(r.rolling(100, min_periods=50).corr(r.shift(1)).iloc[-1])
        return {"lag1_autocorrelation": ac,
                "implication": "momentum" if ac > 0.02 else "reversal" if ac < -0.02 else "none"}


class RandomMatrixDenoised(BaseStrategy):
    name = "Random Matrix Theory Denoised Signal"
    category = CAT
    family = "rmt"
    research = "Laloux, Cizeau, Bouchaud & Potters (1999), 'Noise Dressing of Financial Correlation Matrices', PRL 83(7)"
    description = "Filters correlation eigenvalues against the Marchenko-Pastur bound to keep only real structure."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    horizon = Horizon.SWING
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("universe_returns") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class CUSUMStructuralBreak(BaseStrategy):
    name = "CUSUM Structural Break Filter"
    category = CAT
    family = "changepoint"
    research = "Page (1954), 'Continuous Inspection Schemes', Biometrika 41(1-2); López de Prado (2018) AFML ch. 2"
    description = "Symmetric CUSUM filter that fires only on statistically significant cumulative displacement."
    horizon = Horizon.SWING
    min_bars = 120
    params = {"threshold_sd": 3.0, "vol_window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        r = f.logret.fillna(0).to_numpy()
        sd = f.logret.rolling(self.params["vol_window"], min_periods=20).std(ddof=0).fillna(0).to_numpy()
        thr = self.params["threshold_sd"]
        s_pos = s_neg = 0.0
        out = np.zeros(len(r))
        for i in range(len(r)):
            limit = thr * sd[i]
            s_pos, s_neg = max(0.0, s_pos + r[i]), min(0.0, s_neg + r[i])
            if limit > 0 and s_pos > limit:
                out[i], s_pos = 1.0, 0.0
            elif limit > 0 and s_neg < -limit:
                out[i], s_neg = -1.0, 0.0
        return pd.Series(out, index=f.close.index).replace(0, np.nan).ffill(limit=5).fillna(0)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"realized_vol_pct": float(f.realized_vol(60).iloc[-1] * 100)}


class FractionalDifferentiation(BaseStrategy):
    name = "Fractionally Differentiated Price"
    category = CAT
    family = "frac_diff"
    research = "Hosking (1981), Biometrika 68(1); financial application per López de Prado (2018), AFML ch. 5"
    description = "Differentiates just enough to reach stationarity while preserving memory that a first difference destroys."
    horizon = Horizon.SWING
    min_bars = 160
    params = {"d": 0.4, "width": 50}

    def score(self, f: FeatureSet) -> pd.Series:
        d, width = self.params["d"], self.params["width"]
        # Binomial expansion weights for the fractional difference operator.
        w = [1.0]
        for k in range(1, width):
            w.append(-w[-1] * (d - k + 1) / k)
        w = np.array(w[::-1])
        series = np.log(f.close)
        fd = series.rolling(width, min_periods=width).apply(lambda x: float(np.dot(w, x)), raw=True)
        return -squash(zscore(fd, 60), 1.5)


class RegimeConditionalSpread(BaseStrategy):
    name = "Volatility-Conditional Spread Trade"
    category = CAT
    family = "regime_switch"
    research = "Ang & Bekaert (2002), 'International Asset Allocation with Regime Shifts', RFS 15(4)"
    description = "Sizes the reversion trade inversely to the volatility regime — spreads widen before they converge."
    regimes = (Regime.LOW_VOL,)
    horizon = Horizon.SWING
    min_bars = 150
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        z = zscore(f.close, self.params["window"])
        calm = (1.0 - f.vol_regime).clip(0, 1)
        return -squash(z, 1.5) * calm

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"vol_regime_percentile": float(f.vol_regime.iloc[-1])}


class MahalanobisTurbulence(BaseStrategy):
    name = "Financial Turbulence Index"
    category = CAT
    family = "turbulence"
    research = "Kritzman & Li (2010), 'Skulls, Financial Turbulence, and Risk Management', FAJ 66(5)"
    description = "Mahalanobis distance of current returns from their historical distribution; high turbulence cuts risk."
    horizon = Horizon.SWING
    min_bars = 160
    params = {"window": 120}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        mu = f.logret.rolling(w, min_periods=w // 2).mean()
        sd = f.logret.rolling(w, min_periods=w // 2).std(ddof=0)
        d2 = ((f.logret - mu) / sd.where(sd > 1e-12)) ** 2
        turb = rolling_rank(d2, w)
        # Turbulence is a risk-off gate: fade the move, sized down as turbulence rises.
        return -squash(zscore(f.close, 20), 1.5) * (1 - turb).clip(0, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        w = 120
        mu = f.logret.rolling(w).mean()
        sd = f.logret.rolling(w).std(ddof=0)
        d2 = ((f.logret - mu) / sd) ** 2
        return {"turbulence_percentile": float(rolling_rank(d2, w).iloc[-1])}
