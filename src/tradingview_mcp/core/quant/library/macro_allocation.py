"""
Macro and cross-asset allocation.

Tactical and strategic allocation rules — the Bridgewater/GMO/Research Affiliates
end of the spectrum, plus the systematic TAA literature (Faber, Keller, Antonacci).

Family coverage here follows the layout of the companion **alphakit** library
(github.com/ankitjha67/alphakit), which organises the same territory as
`alphakit-strategies-macro`. Genuine cross-asset rules need a multi-asset panel:
you cannot run a permanent portfolio on one symbol. Those declare
CROSS_SECTION and stand down; the single-asset timing rules run everywhere.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import BaseStrategy, DataNeed, Horizon, Regime, band_score, squash
from ..features import FeatureSet, _safe_div, rolling_rank, zscore

CAT = "Macro & Allocation"


class _PanelStrategy(BaseStrategy):
    """Base for rules that need a multi-asset price panel."""
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    horizon = Horizon.POSITION
    min_bars = 250
    _key = "universe_close"

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get(self._key) is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class PermanentPortfolio(_PanelStrategy):
    name = "Permanent Portfolio"
    category = CAT
    family = "static_allocation"
    research = "Browne (1987), 'Harry Browne's Permanent Portfolio'; analysed in Faber (2015)"
    description = "Equal weights across equities, long bonds, gold and cash — one sleeve performs in each regime."


class AllWeatherRiskParity(_PanelStrategy):
    name = "All-Weather Risk Parity"
    category = CAT
    family = "risk_parity_panel"
    research = "Dalio/Bridgewater All Weather; formalised in Asness, Frazzini & Pedersen (2012), FAJ 68(1)"
    description = "Balances risk contribution across growth and inflation quadrants rather than capital."


class EqualRiskContribution(_PanelStrategy):
    name = "Equal Risk Contribution (ERC)"
    category = CAT
    family = "risk_parity_panel"
    research = "Maillard, Roncalli & Teiletche (2010), 'On the Properties of Equally-Weighted Risk Contributions', JPM 36(4)"
    description = "Solves for weights where every asset contributes identical marginal risk."


class MaximumDiversification(_PanelStrategy):
    name = "Maximum Diversification Portfolio"
    category = CAT
    family = "diversification"
    research = "Choueifaty & Coignard (2008), 'Toward Maximum Diversification', JPM 35(1)"
    description = "Maximises the ratio of weighted average volatility to portfolio volatility."


class MinimumVariancePortfolio(_PanelStrategy):
    name = "Minimum Variance Portfolio"
    category = CAT
    family = "diversification"
    research = "Clarke, de Silva & Thorley (2006), 'Minimum-Variance Portfolios in the U.S. Equity Market', JPM 33(1)"
    description = "The lowest-variance point on the efficient frontier; needs no return forecast."


class GlobalTacticalAssetAllocation(_PanelStrategy):
    name = "GTAA Cross-Asset Momentum"
    category = CAT
    family = "taa"
    research = "Faber (2007), 'A Quantitative Approach to Tactical Asset Allocation', JWM 9(4)"
    description = "Holds each asset only while it trades above its 10-month moving average."


class VigilantAssetAllocation(_PanelStrategy):
    name = "Vigilant Asset Allocation"
    category = CAT
    family = "taa"
    research = "Keller & Keuning (2017), 'Breadth Momentum and Vigilant Asset Allocation', SSRN 3002624"
    description = "Momentum-ranked offensive sleeve that flips fully defensive on any breadth breakdown."


class DefensiveAssetAllocation(_PanelStrategy):
    name = "Defensive Asset Allocation"
    category = CAT
    family = "taa"
    research = "Keller & Keuning (2018), 'Breadth Momentum and the Canary Universe', SSRN 3212862"
    description = "Uses a small canary universe to time the switch between offensive and defensive sleeves."


class AdaptiveAssetAllocation(_PanelStrategy):
    name = "Adaptive Asset Allocation"
    category = CAT
    family = "taa"
    research = "Butler, Philbrick, Gordillo & Varadi (2012), 'Adaptive Asset Allocation', SSRN 2328254"
    description = "Combines momentum ranking with minimum-variance weighting inside the selected set."


class YieldCurveRegimeAllocation(_PanelStrategy):
    name = "Yield Curve Regime Allocation"
    category = CAT
    family = "macro_regime"
    research = "Estrella & Mishkin (1998), REStat 80(1); allocation use per Ilmanen (2011), 'Expected Returns'"
    description = "Shifts allocation on the slope and level of the curve; inversion drives de-risking."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION, DataNeed.BENCHMARK)


class InflationRegimeAllocation(_PanelStrategy):
    name = "Inflation Regime Allocation"
    category = CAT
    family = "macro_regime"
    research = "Neville, Draaisma, Funnell, Harvey & van Hemert (2021), 'The Best Strategies for Inflationary Times', JPM 47(8)"
    description = "Rotates toward commodities and real assets as inflation surprises turn positive."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION, DataNeed.BENCHMARK)


class GrowthInflationQuadrant(_PanelStrategy):
    name = "Growth-Inflation Quadrant Rotation"
    category = CAT
    family = "macro_regime"
    research = "Four-quadrant framework per Dalio (2015); empirical support in Ilmanen (2011), 'Expected Returns' ch. 27"
    description = "Classifies the macro environment into four quadrants and holds the historically best sleeve."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION, DataNeed.BENCHMARK)


class CrossAssetCarry(_PanelStrategy):
    name = "Cross-Asset Carry"
    category = CAT
    family = "carry_panel"
    research = "Koijen, Moskowitz, Pedersen & Vrugt (2018), 'Carry', JFE 127(2)"
    description = "Buys high-carry and sells low-carry assets across equities, bonds, FX and commodities."


class BetaRotationDefensive(_PanelStrategy):
    name = "Defensive Beta Rotation"
    category = CAT
    family = "rotation"
    research = "Blitz & van Vliet (2007), 'The Volatility Effect', JPM 34(1)"
    description = "Rotates between high- and low-beta sleeves based on the prevailing volatility regime."


# ── single-asset timing rules that genuinely run on one series ────────────────

class FaberTimingModel(BaseStrategy):
    name = "Faber 10-Month Timing Model"
    category = CAT
    family = "taa"
    research = "Faber (2007), 'A Quantitative Approach to Tactical Asset Allocation', JWM 9(4)"
    description = ("Hold while price is above its 10-month (≈200-day) moving average, otherwise move to cash. "
                   "The single most-replicated tactical rule in the literature.")
    regimes = (Regime.TRENDING,)
    horizon = Horizon.POSITION
    min_bars = 230
    params = {"window": 200}

    def score(self, f: FeatureSet) -> pd.Series:
        ma = f.sma(self.params["window"])
        above = (f.close > ma).astype(float)
        # Conviction scales with distance above the line, not just the binary state.
        margin = squash((f.close - ma) / ma.abs().where(ma.abs() > 1e-12), 0.05)
        return above * margin.clip(0, 1) - (1 - above) * margin.abs().clip(0, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        ma = float(f.sma(200).iloc[-1])
        px = float(f.close.iloc[-1])
        return {"sma200": ma, "price": px, "distance_pct": (px / ma - 1) * 100,
                "state": "invested" if px > ma else "cash"}

    def explain(self, f: FeatureSet, v: float, d: dict) -> str:
        return (f"Price {d.get('price', 0):,.2f} is {d.get('distance_pct', 0):+.1f}% "
                f"vs its 200-day average ({d.get('sma200', 0):,.2f}) — Faber model says "
                f"{d.get('state')}. Conviction {abs(v):.2f}.")


class AbsoluteMomentumFilter(BaseStrategy):
    name = "Absolute Momentum Filter"
    category = CAT
    family = "taa"
    research = "Antonacci (2014), 'Absolute Momentum: A Simple Rule-Based Strategy', SSRN 2244633"
    description = "Holds only while trailing 12-month return is positive; a pure crash filter."
    horizon = Horizon.POSITION
    min_bars = 280
    params = {"lookback": 252}

    def score(self, f: FeatureSet) -> pd.Series:
        r = f.close.pct_change(self.params["lookback"])
        return squash(r, 0.15)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"trailing_12m_return_pct": float(f.close.pct_change(252).iloc[-1] * 100)}


class VolatilityTargetOverlay(BaseStrategy):
    name = "Volatility Target Overlay"
    category = CAT
    family = "vol_overlay"
    research = "Harvey, Hoyle, Korgaonkar, Rattray, Sargaison & van Hemert (2018), 'The Impact of Volatility Targeting', JPM 45(1)"
    description = "Scales exposure to hold realised volatility at a constant target; improves Sharpe and cuts tails."
    horizon = Horizon.POSITION
    min_bars = 180
    params = {"target": 0.10, "window": 60, "max_leverage": 1.5}

    def score(self, f: FeatureSet) -> pd.Series:
        rv = f.realized_vol(self.params["window"])
        lever = (self.params["target"] / rv.where(rv > 1e-6)).clip(0, self.params["max_leverage"])
        trend = np.sign(f.sma(200).diff()).fillna(0)
        return (trend * lever / self.params["max_leverage"]).clip(-1, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        rv = float(f.realized_vol(60).iloc[-1])
        return {"realized_vol_pct": rv * 100, "target_vol_pct": self.params["target"] * 100,
                "implied_leverage": float(min(self.params["target"] / rv, 1.5)) if rv > 1e-6 else 0.0}


class TrendPlusCarryComposite(BaseStrategy):
    name = "Trend + Carry Composite"
    category = CAT
    family = "multi_signal"
    research = "Baltas & Kosowski (2013), SSRN 2140091; carry leg per Koijen et al. (2018), JFE 127(2)"
    description = "Blends trend and a term-structure carry proxy — the two legs of most macro programmes."
    horizon = Horizon.POSITION
    min_bars = 280

    def score(self, f: FeatureSet) -> pd.Series:
        vol = f.logret.rolling(60, min_periods=20).std(ddof=0)
        trend = squash(np.log(f.close / f.close.shift(252)) / (vol.where(vol > 1e-9) * np.sqrt(252)), 1.0)
        # Carry proxy: drift over the recent window relative to its own volatility.
        carry = squash(f.logret.rolling(63, min_periods=30).mean() / vol.where(vol > 1e-9), 0.2)
        return (0.6 * trend + 0.4 * carry).clip(-1, 1)


class DrawdownRecoveryAllocation(BaseStrategy):
    name = "Drawdown-Scaled Allocation"
    category = CAT
    family = "vol_overlay"
    research = "Grossman & Zhou (1993), Math. Finance 3(3); CPPI framework per Black & Perold (1992), JEDC 16(3)"
    description = "Constant-proportion portfolio insurance: exposure scales with the cushion above the floor."
    horizon = Horizon.POSITION
    min_bars = 200
    params = {"floor": 0.85, "multiplier": 3.0}

    def score(self, f: FeatureSet) -> pd.Series:
        peak = f.close.cummax()
        cushion = ((f.close - peak * self.params["floor"]) / peak).clip(lower=0)
        exposure = (cushion * self.params["multiplier"]).clip(0, 1)
        trend = np.sign(f.sma(50) - f.sma(200)).fillna(0)
        return trend * exposure

    def diagnostics(self, f: FeatureSet) -> dict:
        peak = float(f.close.cummax().iloc[-1])
        px = float(f.close.iloc[-1])
        cushion = max(0.0, (px - peak * 0.85) / peak)
        return {"peak": peak, "floor": peak * 0.85, "cushion_pct": cushion * 100,
                "exposure": min(1.0, cushion * 3.0)}


class SeasonalMacroOverlay(BaseStrategy):
    name = "Macro Seasonality Overlay"
    category = CAT
    family = "macro_seasonal"
    research = "Bouman & Jacobsen (2002), AER 92(5); Keloharju, Linnainmaa & Nyberg (2016), JF 71(4)"
    description = "Combines the seasonal calendar tilt with a trend filter so seasonality never fights the trend."
    horizon = Horizon.POSITION
    min_bars = 300

    def availability(self, f: FeatureSet):
        if not isinstance(f.df.index, pd.DatetimeIndex):
            return False, "requires a datetime index"
        return super().availability(f)

    def score(self, f: FeatureSet) -> pd.Series:
        month = f.df.index.month
        seasonal = pd.Series(np.where(np.isin(month, [11, 12, 1, 2, 3, 4]), 0.5, -0.2),
                             index=f.close.index)
        trend = np.sign(f.sma(50) - f.sma(200)).fillna(0)
        # Only express the seasonal tilt when the trend does not contradict it.
        return seasonal.where(np.sign(seasonal) == trend, seasonal * 0.25)


class RegimeSwitchingAllocation(BaseStrategy):
    name = "Two-Regime Allocation Switch"
    category = CAT
    family = "macro_regime"
    research = "Ang & Bekaert (2004), 'How Regimes Affect Asset Allocation', FAJ 60(2)"
    description = "Switches between a risk-on trend rule and a risk-off defensive rule based on the volatility state."
    horizon = Horizon.POSITION
    min_bars = 280

    def score(self, f: FeatureSet) -> pd.Series:
        stressed = ((f.vol_regime > 0.7) | (f.drawdown() < -0.15)).astype(float)
        risk_on = np.sign(f.sma(50) - f.sma(200)).fillna(0)
        risk_off = -squash(zscore(f.close, 20), 1.5) * 0.5
        return risk_on * (1 - stressed) + risk_off * stressed

    def diagnostics(self, f: FeatureSet) -> dict:
        vr = float(f.vol_regime.iloc[-1])
        dd = float(f.drawdown().iloc[-1])
        return {"vol_percentile": vr, "drawdown_pct": dd * 100,
                "active_regime": "risk-off" if (vr > 0.7 or dd < -0.15) else "risk-on"}
