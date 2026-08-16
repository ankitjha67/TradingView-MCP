"""
Factor investing and smart beta.

The academic backbone of AQR, Dimensional, Robeco and the systematic-equity pods
at the multi-managers. Factors are cross-sectional by construction: value means
cheap *relative to peers*. Models needing a universe or fundamentals declare it
and stand down on a single symbol rather than inventing a substitute.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import BaseStrategy, DataNeed, Horizon, Regime, band_score, squash
from ..features import FeatureSet, _safe_div, rolling_rank, zscore

CAT = "Factor & Smart Beta"


class MarketBeta(BaseStrategy):
    name = "CAPM Market Beta"
    category = CAT
    family = "beta"
    research = "Sharpe (1964), JF 19(3); Lintner (1965), REStat 47(1)"
    description = "Rolling beta to the benchmark; the first-order decomposition of any equity return."
    needs = (DataNeed.OHLC, DataNeed.BENCHMARK)
    horizon = Horizon.POSITION
    min_bars = 150
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        b = f.meta.get("benchmark_close")
        if b is None:
            return pd.Series(np.nan, index=f.close.index)
        w = self.params["window"]
        br = pd.Series(b, index=f.close.index).pct_change()
        beta = f.ret.rolling(w, min_periods=w // 2).cov(br) / br.rolling(w, min_periods=w // 2).var(ddof=0)
        return squash(np.sign(br.rolling(20).mean()) * beta, 1.5)


class BettingAgainstBeta(BaseStrategy):
    name = "Betting Against Beta"
    category = CAT
    family = "beta"
    research = "Frazzini & Pedersen (2014), 'Betting Against Beta', JFE 111(1)"
    description = "Leverage-constrained investors bid up high-beta assets, so low beta earns higher risk-adjusted returns."
    needs = (DataNeed.OHLC, DataNeed.BENCHMARK, DataNeed.CROSS_SECTION)
    horizon = Horizon.POSITION
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("benchmark_close") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class LowVolatilityAnomaly(BaseStrategy):
    name = "Low Volatility Anomaly"
    category = CAT
    family = "low_vol"
    research = "Ang, Hodrick, Xing & Zhang (2006), 'The Cross-Section of Volatility and Expected Returns', JF 61(1)"
    description = "Low-volatility assets have historically out-returned high-volatility ones, inverting the CAPM prediction."
    horizon = Horizon.POSITION
    min_bars = 280
    params = {"window": 60, "rank_window": 252}

    def score(self, f: FeatureSet) -> pd.Series:
        vol_rank = rolling_rank(f.realized_vol(self.params["window"]),
                                min(self.params["rank_window"], max(60, f.n // 2)))
        return -band_score(vol_rank, 0.0, 1.0)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"realized_vol_pct": float(f.realized_vol(60).iloc[-1] * 100),
                "vol_percentile": float(f.vol_regime.iloc[-1])}


class IdiosyncraticVolatility(BaseStrategy):
    name = "Idiosyncratic Volatility Puzzle"
    category = CAT
    family = "low_vol"
    research = "Ang, Hodrick, Xing & Zhang (2009), 'High Idiosyncratic Volatility and Low Returns', JFE 91(1)"
    description = "Residual volatility after removing market beta predicts low returns — an anomaly relative to theory."
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
        beta = f.ret.rolling(w, min_periods=w // 2).cov(br) / br.rolling(w, min_periods=w // 2).var(ddof=0)
        ivol = (f.ret - beta * br).rolling(w, min_periods=w // 2).std(ddof=0)
        return -squash(zscore(ivol, 120), 1.5)


class DownsideBeta(BaseStrategy):
    name = "Downside Beta Premium"
    category = CAT
    family = "beta"
    research = "Ang, Chen & Xing (2006), 'Downside Risk', RFS 19(4)"
    description = "Beta measured only in down markets is priced separately from ordinary beta."
    needs = (DataNeed.OHLC, DataNeed.BENCHMARK)
    horizon = Horizon.POSITION
    min_bars = 200
    params = {"window": 120}

    def score(self, f: FeatureSet) -> pd.Series:
        b = f.meta.get("benchmark_close")
        if b is None:
            return pd.Series(np.nan, index=f.close.index)
        w = self.params["window"]
        br = pd.Series(b, index=f.close.index).pct_change()
        down = br < 0
        db = f.ret.where(down).rolling(w, min_periods=20).cov(br.where(down)) / \
            br.where(down).rolling(w, min_periods=20).var(ddof=0)
        return -squash(zscore(db, w), 1.5)


class ValueBookToMarket(BaseStrategy):
    name = "Value (Book-to-Market)"
    category = CAT
    family = "value"
    research = "Fama & French (1993), 'Common Risk Factors in the Returns on Stocks and Bonds', JFE 33(1)"
    description = "The canonical value factor; requires book equity from fundamentals."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    horizon = Horizon.POSITION
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("book_value") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class PriceToLongRunMean(BaseStrategy):
    name = "Technical Value (5-Year Mean Reversion)"
    category = CAT
    family = "value"
    research = "Asness, Moskowitz & Pedersen (2013), 'Value and Momentum Everywhere', JF 68(3) — 5-year reversal definition"
    description = "The price-only value proxy AMP use for assets with no book value: level versus its 5-year average."
    horizon = Horizon.POSITION
    min_bars = 500
    params = {"window": 1260}

    def score(self, f: FeatureSet) -> pd.Series:
        w = min(self.params["window"], max(250, f.n - 10))
        long_mean = f.close.rolling(w, min_periods=w // 3).mean()
        return -squash(np.log(f.close / long_mean), 0.25)

    def diagnostics(self, f: FeatureSet) -> dict:
        w = min(1260, max(250, f.n - 10))
        lm = float(f.close.rolling(w, min_periods=w // 3).mean().iloc[-1])
        return {"long_run_mean": lm, "premium_to_mean_pct": float((f.close.iloc[-1] / lm - 1) * 100)}


class QualityMinusJunk(BaseStrategy):
    name = "Quality Minus Junk"
    category = CAT
    family = "quality"
    research = "Asness, Frazzini & Pedersen (2019), 'Quality Minus Junk', Review of Accounting Studies 24"
    description = "Profitable, growing, safe, well-managed firms outperform; needs fundamentals."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    horizon = Horizon.POSITION
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("fundamentals") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class ReturnStability(BaseStrategy):
    name = "Return Stability (Technical Quality)"
    category = CAT
    family = "quality"
    research = "Price-based quality proxy following the 'safety' leg of Asness, Frazzini & Pedersen (2019)"
    description = "Consistency of returns — low drawdown, high hit rate, stable volatility — as a price-only quality read."
    horizon = Horizon.POSITION
    min_bars = 200
    params = {"window": 120}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        hit = (f.logret > 0).rolling(w, min_periods=w // 2).mean()
        vol_stab = 1 - rolling_rank(f.realized_vol(20).rolling(w, min_periods=w // 2).std(ddof=0), w)
        dd = 1 + f.drawdown().rolling(w, min_periods=w // 2).min()
        return band_score((hit + vol_stab.fillna(0.5) + dd.clip(0, 1)) / 3, 0.35, 0.65)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"hit_rate": float((f.logret > 0).rolling(120, min_periods=60).mean().iloc[-1]),
                "max_drawdown_120b_pct": float(f.drawdown().rolling(120, min_periods=60).min().iloc[-1] * 100)}


class GrossProfitability(BaseStrategy):
    name = "Gross Profitability"
    category = CAT
    family = "profitability"
    research = "Novy-Marx (2013), 'The Other Side of Value', JFE 108(1)"
    description = "Gross profits over assets predicts returns as strongly as book-to-market; needs fundamentals."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    horizon = Horizon.POSITION
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("fundamentals") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class PiotroskiFScore(BaseStrategy):
    name = "Piotroski F-Score"
    category = CAT
    family = "quality"
    research = "Piotroski (2000), 'Value Investing: The Use of Historical Financial Statement Information', J. Accounting Research 38"
    description = "Nine binary accounting tests separating strong from weak value names; needs financial statements."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    horizon = Horizon.POSITION
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("fundamentals") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class AltmanZScore(BaseStrategy):
    name = "Altman Z-Score Distress"
    category = CAT
    family = "distress"
    research = "Altman (1968), 'Financial Ratios, Discriminant Analysis and the Prediction of Corporate Bankruptcy', JF 23(4)"
    description = "Bankruptcy-risk discriminant; distressed names carry a distinct return profile. Needs fundamentals."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    horizon = Horizon.POSITION
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("fundamentals") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class AccrualsAnomaly(BaseStrategy):
    name = "Accruals Anomaly"
    category = CAT
    family = "accounting"
    research = "Sloan (1996), 'Do Stock Prices Fully Reflect Information in Accruals and Cash Flows?', Accounting Review 71(3)"
    description = "Earnings driven by accruals rather than cash flow revert; needs cash-flow statements."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    horizon = Horizon.POSITION
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("fundamentals") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class AssetGrowthAnomaly(BaseStrategy):
    name = "Asset Growth Anomaly"
    category = CAT
    family = "investment"
    research = "Cooper, Gulen & Schill (2008), 'Asset Growth and the Cross-Section of Stock Returns', JF 63(4)"
    description = "Firms expanding their balance sheet fastest subsequently underperform; needs fundamentals."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    horizon = Horizon.POSITION
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("fundamentals") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class PostEarningsDrift(BaseStrategy):
    name = "Post-Earnings Announcement Drift"
    category = CAT
    family = "pead"
    research = "Ball & Brown (1968), J. Accounting Research 6(2); Bernard & Thomas (1989), J. Accounting Research 27"
    description = "Prices underreact to earnings surprises and drift for weeks; needs an earnings calendar."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    horizon = Horizon.SWING
    min_bars = 150

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("earnings_dates") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class PriceGapDrift(BaseStrategy):
    name = "Large Gap Continuation Drift"
    category = CAT
    family = "pead"
    research = "Price-only PEAD proxy following the underreaction mechanism in Bernard & Thomas (1989)"
    description = "Large unexplained gaps proxy for news shocks, which drift in the gap direction rather than fully revert."
    horizon = Horizon.SWING
    min_bars = 120
    is_proxy = True
    proxy_note = "Uses outsized overnight gaps as a stand-in for scheduled earnings surprises, which need a calendar feed."
    params = {"threshold_sd": 2.5, "hold": 15}

    def score(self, f: FeatureSet) -> pd.Series:
        gap = (f.open - f.close.shift(1)) / f.close.shift(1)
        z = zscore(gap, 120)
        shock = np.sign(z) * (z.abs() > self.params["threshold_sd"]).astype(float)
        return shock.replace(0, np.nan).ffill(limit=self.params["hold"]).fillna(0) * 0.7

    def diagnostics(self, f: FeatureSet) -> dict:
        gap = (f.open - f.close.shift(1)) / f.close.shift(1)
        return {"latest_gap_pct": float(gap.iloc[-1] * 100), "gap_zscore": float(zscore(gap, 120).iloc[-1])}


class SizeEffect(BaseStrategy):
    name = "Size Effect (SMB)"
    category = CAT
    family = "size"
    research = "Banz (1981), 'The Relationship Between Return and Market Value of Common Stocks', JFE 9(1)"
    description = "Small capitalisations earn a premium over large; requires market-cap data across a universe."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS, DataNeed.CROSS_SECTION)
    horizon = Horizon.POSITION
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        return pd.Series(np.nan, index=f.close.index)


class LiquidityFactor(BaseStrategy):
    name = "Liquidity Risk Factor"
    category = CAT
    family = "liquidity_factor"
    research = "Pástor & Stambaugh (2003), 'Liquidity Risk and Expected Stock Returns', JPE 111(3)"
    description = "Sensitivity to market-wide liquidity shocks is priced; approximated here by turnover-adjusted reversal."
    needs = (DataNeed.OHLC, DataNeed.VOLUME)
    horizon = Horizon.POSITION
    min_bars = 200
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        signed_vol = np.sign(f.ret) * f.volume.fillna(0)
        # Pástor-Stambaugh gamma: reversal per unit of signed volume.
        gamma = f.ret.shift(-1).rolling(w, min_periods=w // 2).corr(signed_vol)
        return -squash(zscore(gamma.shift(1), w), 1.5)


class NetShareIssuance(BaseStrategy):
    name = "Net Share Issuance"
    category = CAT
    family = "issuance"
    research = "Pontiff & Woodgate (2008), 'Share Issuance and Cross-Sectional Returns', JF 63(2)"
    description = "Firms issuing shares underperform, those buying back outperform; needs share-count history."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    horizon = Horizon.POSITION
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        return pd.Series(np.nan, index=f.close.index)


class CarhartFourFactor(BaseStrategy):
    name = "Carhart Four-Factor Alpha"
    category = CAT
    family = "multifactor"
    research = "Carhart (1997), 'On Persistence in Mutual Fund Performance', JF 52(1)"
    description = "Alpha after market, size, value and momentum; needs factor return series."
    needs = (DataNeed.OHLC, DataNeed.BENCHMARK, DataNeed.CROSS_SECTION)
    horizon = Horizon.POSITION
    min_bars = 250

    def score(self, f: FeatureSet) -> pd.Series:
        return pd.Series(np.nan, index=f.close.index)


class RiskParityAllocation(BaseStrategy):
    name = "Risk Parity Exposure"
    category = CAT
    family = "risk_parity"
    research = "Qian (2005), 'Risk Parity Portfolios'; Maillard, Roncalli & Teiletche (2010), JPM 36(4)"
    description = "Equalises risk contribution rather than capital; on a single asset this is inverse-volatility sizing."
    horizon = Horizon.POSITION
    min_bars = 150
    params = {"window": 60, "target": 0.12}

    def score(self, f: FeatureSet) -> pd.Series:
        vol = f.realized_vol(self.params["window"])
        weight = (self.params["target"] / vol.where(vol > 1e-6)).clip(0, 1.5)
        trend = np.sign(f.ema(50) - f.ema(200)).fillna(0)
        return (trend * weight / 1.5).clip(-1, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        v = float(f.realized_vol(60).iloc[-1])
        return {"realized_vol_pct": v * 100,
                "risk_parity_weight": float(min(self.params["target"] / v, 1.5)) if v > 1e-6 else 0.0}


class HierarchicalRiskParity(BaseStrategy):
    name = "Hierarchical Risk Parity"
    category = CAT
    family = "risk_parity"
    research = "López de Prado (2016), 'Building Diversified Portfolios that Outperform Out of Sample', JPM 42(4)"
    description = "Clusters the correlation matrix before allocating, avoiding the instability of matrix inversion."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    horizon = Horizon.POSITION
    min_bars = 250

    def score(self, f: FeatureSet) -> pd.Series:
        return pd.Series(np.nan, index=f.close.index)


class BlackLittermanView(BaseStrategy):
    name = "Black-Litterman Blended View"
    category = CAT
    family = "allocation"
    research = "Black & Litterman (1992), 'Global Portfolio Optimization', FAJ 48(5)"
    description = "Blends an equilibrium prior with active views by confidence weighting; here trend is the view."
    horizon = Horizon.POSITION
    min_bars = 200
    params = {"view_confidence": 0.5, "window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        # Equilibrium prior: the long-run drift. View: current trend, weighted by its own reliability.
        prior = squash(f.logret.rolling(252, min_periods=100).mean() * 252, 0.1)
        view = squash(zscore(f.close.pct_change(self.params["window"]), 120), 1.5)
        conf = f.efficiency_ratio(self.params["window"]).clip(0, 1) * self.params["view_confidence"]
        return prior * (1 - conf) + view * conf


class KellyCriterionSizing(BaseStrategy):
    name = "Kelly Criterion Optimal Fraction"
    category = CAT
    family = "allocation"
    research = "Kelly (1956), Bell System Technical Journal 35(4); Thorp (2006), 'The Kelly Criterion in Blackjack, Sports Betting and the Stock Market'"
    description = "Growth-optimal fraction from estimated edge over variance, capped at half-Kelly for estimation error."
    horizon = Horizon.POSITION
    min_bars = 200
    params = {"window": 120, "fraction": 0.5}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        mu = f.logret.rolling(w, min_periods=w // 2).mean()
        var = f.logret.rolling(w, min_periods=w // 2).var(ddof=0)
        kelly = (mu / var.where(var > 1e-14)) * self.params["fraction"]
        return squash(kelly, 20.0)

    def diagnostics(self, f: FeatureSet) -> dict:
        w = 120
        mu = float(f.logret.rolling(w, min_periods=60).mean().iloc[-1])
        var = float(f.logret.rolling(w, min_periods=60).var(ddof=0).iloc[-1])
        return {"edge_per_bar_bps": mu * 1e4, "variance": var,
                "half_kelly_fraction": float(mu / var * 0.5) if var > 1e-14 else 0.0}


class MaxSharpeTilt(BaseStrategy):
    name = "Maximum Sharpe Tilt"
    category = CAT
    family = "allocation"
    research = "Markowitz (1952), 'Portfolio Selection', JF 7(1); Sharpe (1966), J. Business 39(1)"
    description = "Tilts toward the asset when its own trailing Sharpe is in the upper part of its historical range."
    horizon = Horizon.POSITION
    min_bars = 250
    params = {"window": 120}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        mu = f.logret.rolling(w, min_periods=w // 2).mean() * f.bars_per_year
        sd = f.logret.rolling(w, min_periods=w // 2).std(ddof=0) * np.sqrt(f.bars_per_year)
        sharpe = mu / sd.where(sd > 1e-9)
        return squash(sharpe, 1.0)

    def diagnostics(self, f: FeatureSet) -> dict:
        w = 120
        mu = f.logret.rolling(w, min_periods=60).mean().iloc[-1] * f.bars_per_year
        sd = f.logret.rolling(w, min_periods=60).std(ddof=0).iloc[-1] * np.sqrt(f.bars_per_year)
        return {"annualized_return_pct": float(mu * 100), "annualized_vol_pct": float(sd * 100),
                "sharpe_ratio": float(mu / sd) if sd > 1e-9 else 0.0}


class TrendFactorTiming(BaseStrategy):
    name = "Factor Momentum Timing"
    category = CAT
    family = "factor_timing"
    research = "Gupta & Kelly (2019), 'Factor Momentum Everywhere', JPM 45(3)"
    description = "Factors themselves trend; recent factor performance predicts near-term factor returns."
    horizon = Horizon.POSITION
    min_bars = 250
    params = {"window": 126}

    def score(self, f: FeatureSet) -> pd.Series:
        # Proxy the value/momentum tilt by the relative performance of each leg's own signal path.
        mom_leg = squash(zscore(f.close.pct_change(126), 252), 1.5)
        val_leg = -squash(np.log(f.close / f.close.rolling(504, min_periods=200).mean()), 0.25)
        mom_perf = (mom_leg.shift(1) * f.logret).rolling(self.params["window"], min_periods=60).mean()
        val_perf = (val_leg.shift(1) * f.logret).rolling(self.params["window"], min_periods=60).mean()
        total = mom_perf.clip(lower=0) + val_perf.clip(lower=0)
        return ((mom_leg * mom_perf.clip(lower=0) + val_leg * val_perf.clip(lower=0))
                / total.where(total > 1e-12)).fillna(0).clip(-1, 1)


class DefensiveEquityTilt(BaseStrategy):
    name = "Defensive Equity Tilt"
    category = CAT
    family = "low_vol"
    research = "Frazzini & Pedersen (2014); Blitz & van Vliet (2007), 'The Volatility Effect', JPM 34(1)"
    description = "Combines low volatility, low drawdown and low beta into one defensive composite."
    horizon = Horizon.POSITION
    min_bars = 280

    def score(self, f: FeatureSet) -> pd.Series:
        low_vol = 1 - f.vol_regime
        shallow_dd = (1 + f.drawdown().rolling(120, min_periods=60).min()).clip(0, 1)
        smooth = 1 - rolling_rank(f.logret.abs().rolling(20, min_periods=10).mean(), 252)
        return band_score((low_vol + shallow_dd + smooth) / 3, 0.35, 0.7)


class SeasonalFactorRotation(BaseStrategy):
    name = "Momentum-Reversal Horizon Rotation"
    category = CAT
    family = "factor_timing"
    research = "Asness, Moskowitz & Pedersen (2013), JF 68(3) — momentum and value as negatively correlated siblings"
    description = "Rotates between short-horizon reversal and medium-horizon momentum based on which is currently paying."
    horizon = Horizon.SWING
    min_bars = 250
    params = {"eval_window": 120}

    def score(self, f: FeatureSet) -> pd.Series:
        rev = -squash(zscore(f.close.pct_change(5), 60), 1.5)
        mom = squash(zscore(f.close.pct_change(63), 120), 1.5)
        w = self.params["eval_window"]
        rev_pnl = (rev.shift(1) * f.logret).rolling(w, min_periods=40).mean()
        mom_pnl = (mom.shift(1) * f.logret).rolling(w, min_periods=40).mean()
        return pd.Series(np.where(rev_pnl > mom_pnl, rev, mom), index=f.close.index)

    def diagnostics(self, f: FeatureSet) -> dict:
        rev = -squash(zscore(f.close.pct_change(5), 60), 1.5)
        mom = squash(zscore(f.close.pct_change(63), 120), 1.5)
        rp = float((rev.shift(1) * f.logret).rolling(120, min_periods=40).mean().iloc[-1])
        mp = float((mom.shift(1) * f.logret).rolling(120, min_periods=40).mean().iloc[-1])
        return {"reversal_edge_bps": rp * 1e4, "momentum_edge_bps": mp * 1e4,
                "active_leg": "reversal" if rp > mp else "momentum"}
