"""
Rates, credit, commodities and options income.

Mirrors the `alphakit-strategies-rates`, `-commodity`, `-carry` and `-options`
families from the companion library (github.com/ankitjha67/alphakit).

Most rates and credit strategies need a yield series or a credit spread — those
are not derivable from an equity or crypto price, so they declare BENCHMARK and
stand down. The commodity and options-income rules that *can* be expressed on a
single tradeable series run everywhere, and say when they are approximating.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import BaseStrategy, DataNeed, Horizon, Regime, band_score, persist, squash
from ..features import FeatureSet, _safe_div, rolling_rank, zscore

RATES = "Rates & Credit"
COMMOD = "Commodity & Carry"
INCOME = "Options Income"


class _MacroFeedStrategy(BaseStrategy):
    """Base for rules requiring a yield, spread or macro series."""
    needs = (DataNeed.OHLC, DataNeed.BENCHMARK)
    horizon = Horizon.POSITION
    min_bars = 250
    _key = "macro_series"

    def score(self, f: FeatureSet) -> pd.Series:
        series = f.meta.get(self._key)
        if series is None:
            return pd.Series(np.nan, index=f.close.index)
        return squash(zscore(pd.Series(series, index=f.close.index), 120), 1.5)


# ── rates & credit ────────────────────────────────────────────────────────────

class BondCarryRolldown(_MacroFeedStrategy):
    name = "Bond Carry and Rolldown"
    category = RATES
    family = "bond_carry"
    research = "Koijen, Moskowitz, Pedersen & Vrugt (2018), 'Carry', JFE 127(2)"
    description = "Yield plus rolldown along the curve; the dominant return driver for a held bond position."
    _key = "yield_curve"


class G10BondCarry(_MacroFeedStrategy):
    name = "G10 Bond Carry"
    category = RATES
    family = "bond_carry"
    research = "Ilmanen (1995), 'Time-Varying Expected Returns in International Bond Markets', JF 50(2)"
    description = "Cross-country sovereign carry after hedging FX; needs a multi-country yield panel."
    needs = (DataNeed.OHLC, DataNeed.BENCHMARK, DataNeed.CROSS_SECTION)
    _key = "sovereign_yields"


class RealYieldMomentum(_MacroFeedStrategy):
    name = "Real Yield Momentum"
    category = RATES
    family = "real_rates"
    research = "Campbell, Shiller & Viceira (2009), 'Understanding Inflation-Indexed Bond Markets', Brookings Papers"
    description = "Momentum in inflation-adjusted yields; needs a TIPS or real-yield series."
    _key = "real_yield"


class CreditSpreadMomentum(_MacroFeedStrategy):
    name = "Credit Spread Momentum"
    category = RATES
    family = "credit"
    research = "Gilchrist & Zakrajšek (2012), 'Credit Spreads and Business Cycle Fluctuations', AER 102(4)"
    description = "Widening spreads lead equity weakness; the excess bond premium is the cleanest form."
    _key = "credit_spread"


class TermPremiumSignal(_MacroFeedStrategy):
    name = "Term Premium Signal"
    category = RATES
    family = "term_structure"
    research = "Adrian, Crump & Moench (2013), 'Pricing the Term Structure with Linear Regressions', JFE 110(1)"
    description = "The compensation for duration risk beyond expected short rates; needs an ACM term-premium series."
    _key = "term_premium"


class YieldCurveSlopeTrade(_MacroFeedStrategy):
    name = "Yield Curve Steepener/Flattener"
    category = RATES
    family = "term_structure"
    research = "Litterman & Scheinkman (1991), 'Common Factors Affecting Bond Returns', J. Fixed Income 1(1)"
    description = "Trades the level/slope/curvature decomposition of the yield curve."
    needs = (DataNeed.OHLC, DataNeed.BENCHMARK, DataNeed.CROSS_SECTION)
    _key = "yield_curve"


class BreakevenInflationTrade(_MacroFeedStrategy):
    name = "Breakeven Inflation Trade"
    category = RATES
    family = "inflation"
    research = "Fleckenstein, Longstaff & Lustig (2014), 'The TIPS-Treasury Bond Puzzle', JF 69(5)"
    description = "The nominal-versus-real yield gap as an inflation expectation; needs both curves."
    _key = "breakeven"


class CentralBankPolicySurprise(_MacroFeedStrategy):
    name = "Policy Rate Surprise"
    category = RATES
    family = "monetary"
    research = "Kuttner (2001), 'Monetary Policy Surprises and Interest Rates', J. Monetary Economics 47(3)"
    description = "Unexpected policy moves derived from futures repricing; needs a rate-futures feed."
    needs = (DataNeed.OHLC, DataNeed.BENCHMARK, DataNeed.NEWS)
    _key = "policy_surprise"


class FinancialConditionsIndex(_MacroFeedStrategy):
    name = "Financial Conditions Index"
    category = RATES
    family = "macro_composite"
    research = "Hatzius, Hooper, Mishkin, Schoenholtz & Watson (2010), NBER Working Paper 16150"
    description = "Composite of rates, spreads, equity and FX conditions; needs a macro data feed."
    _key = "financial_conditions"


class DurationTimingModel(BaseStrategy):
    name = "Duration Timing (Price-Based)"
    category = RATES
    family = "duration"
    research = "Ilmanen (1997), 'Forecasting U.S. Bond Returns', J. Fixed Income 7(1)"
    description = "Times duration exposure on the traded bond instrument's own trend and volatility."
    horizon = Horizon.POSITION
    min_bars = 250
    is_proxy = True
    proxy_note = ("Real duration timing regresses on yield levels, curve slope and momentum. With only the "
                  "instrument's price, this uses trend and vol as the timing input.")

    def score(self, f: FeatureSet) -> pd.Series:
        trend = squash((f.sma(50) - f.sma(200)) / f.sma(200).abs().where(f.sma(200).abs() > 1e-12), 0.02)
        calm = (1 - f.vol_regime).clip(0, 1)
        return trend * calm


# ── commodity & carry ─────────────────────────────────────────────────────────

class CommodityTermStructure(BaseStrategy):
    name = "Commodity Term Structure (Backwardation)"
    category = COMMOD
    family = "commodity_carry"
    research = "Erb & Harvey (2006), 'The Strategic and Tactical Value of Commodity Futures', FAJ 62(2)"
    description = "Backwardated curves earn a positive roll yield; contango bleeds. Needs two contract months."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    horizon = Horizon.POSITION
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        front, back = f.meta.get("front_close"), f.meta.get("back_close")
        if front is None or back is None:
            return pd.Series(np.nan, index=f.close.index)
        fr = pd.Series(front, index=f.close.index)
        bk = pd.Series(back, index=f.close.index).replace(0, np.nan)
        return squash(np.log(bk / fr) * -1, 0.02)


class CommodityMomentum(BaseStrategy):
    name = "Commodity Time-Series Momentum"
    category = COMMOD
    family = "commodity_trend"
    research = "Miffre & Rallis (2007), 'Momentum Strategies in Commodity Futures Markets', JBF 31(6)"
    description = "Momentum is strong and persistent in commodities, where trend-followers have long dominated."
    regimes = (Regime.TRENDING,)
    horizon = Horizon.POSITION
    min_bars = 280
    params = {"lookback": 252}

    def score(self, f: FeatureSet) -> pd.Series:
        lb = self.params["lookback"]
        vol = f.logret.rolling(60, min_periods=20).std(ddof=0) * np.sqrt(lb)
        return squash(np.log(f.close / f.close.shift(lb)) / vol.where(vol > 1e-9), 1.0)


class HedgingPressureSignal(BaseStrategy):
    name = "Hedging Pressure (COT)"
    category = COMMOD
    family = "positioning"
    research = "Basu & Miffre (2013), 'Capturing the Risk Premium of Commodity Futures', JBF 37(7)"
    description = "Commercial hedger positioning predicts commodity returns; needs CFTC Commitments of Traders data."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    horizon = Horizon.POSITION
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("cot_positioning") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class InventoryLevelSignal(BaseStrategy):
    name = "Commodity Inventory Signal"
    category = COMMOD
    family = "fundamental_commodity"
    research = "Gorton, Hayashi & Rouwenhorst (2013), 'The Fundamentals of Commodity Futures Returns', Review of Finance 17(1)"
    description = "Low inventories drive backwardation and higher expected returns; needs inventory data."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    horizon = Horizon.POSITION
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("inventory") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class SeasonalCommodityPattern(BaseStrategy):
    name = "Commodity Seasonal Pattern"
    category = COMMOD
    family = "commodity_seasonal"
    research = "Sørensen (2002), 'Modeling Seasonality in Agricultural Commodity Futures', J. Futures Markets 22(5)"
    description = "Agricultural and energy commodities carry strong production/consumption seasonality."
    horizon = Horizon.POSITION
    min_bars = 500

    def availability(self, f: FeatureSet):
        if not isinstance(f.df.index, pd.DatetimeIndex):
            return False, "requires a datetime index"
        return super().availability(f)

    def score(self, f: FeatureSet) -> pd.Series:
        month = pd.Series(f.df.index.month, index=f.close.index)
        edge = f.logret.groupby(month).transform(lambda x: x.shift(1).expanding(min_periods=8).mean())
        vol = f.logret.expanding(min_periods=60).std(ddof=0)
        return squash(edge / vol.where(vol > 1e-12), 0.4)


class GoldRealRateRelationship(BaseStrategy):
    name = "Gold vs Real Rates"
    category = COMMOD
    family = "macro_commodity"
    research = "Erb & Harvey (2013), 'The Golden Dilemma', FAJ 69(4)"
    description = "Gold is inversely related to real yields — its dominant macro driver. Needs a real-yield series."
    needs = (DataNeed.OHLC, DataNeed.BENCHMARK)
    horizon = Horizon.POSITION
    min_bars = 250

    def score(self, f: FeatureSet) -> pd.Series:
        real = f.meta.get("real_yield")
        if real is None:
            return pd.Series(np.nan, index=f.close.index)
        return -squash(zscore(pd.Series(real, index=f.close.index), 120), 1.5)


class CurrencyCarryTrade(BaseStrategy):
    name = "Currency Carry Trade"
    category = COMMOD
    family = "fx_carry"
    research = "Lustig, Roussanov & Verdelhan (2011), 'Common Risk Factors in Currency Markets', RFS 24(11)"
    description = "Long high-yield, short low-yield currencies; needs interest differentials across a currency panel."
    needs = (DataNeed.OHLC, DataNeed.BENCHMARK, DataNeed.CROSS_SECTION)
    horizon = Horizon.POSITION
    min_bars = 250

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("rate_differentials") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class PurchasingPowerParity(BaseStrategy):
    name = "PPP Currency Valuation"
    category = COMMOD
    family = "fx_value"
    research = "Rogoff (1996), 'The Purchasing Power Parity Puzzle', J. Economic Literature 34(2)"
    description = "Currencies revert to purchasing-power parity over multi-year horizons; needs CPI data."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    horizon = Horizon.POSITION
    min_bars = 500

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("cpi_ratio") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class RollYieldHarvest(BaseStrategy):
    name = "Roll Yield Harvest"
    category = COMMOD
    family = "commodity_carry"
    research = "Gorton & Rouwenhorst (2006), 'Facts and Fantasies about Commodity Futures', FAJ 62(2)"
    description = "Systematically captures roll yield along the futures curve; needs multiple contract months."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    horizon = Horizon.POSITION
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("curve_prices") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


# ── options income (proxy-expressible on the underlying) ──────────────────────

class CoveredCallOverlay(BaseStrategy):
    name = "Covered Call Overlay"
    category = INCOME
    family = "options_income"
    research = "Whaley (2002), 'Return and Risk of CBOE Buy Write Monthly Index', JD 10(2); CBOE BXM methodology"
    description = ("Long underlying, short an out-of-the-money call. Caps upside to harvest premium; historically "
                   "improves Sharpe while reducing total return in strong rallies.")
    horizon = Horizon.SWING
    min_bars = 200
    is_proxy = True
    proxy_note = ("Without a chain the premium cannot be priced. This expresses the *timing* rule the overlay "
                  "implies — favourable when implied-vol proxies are rich and the underlying is range-bound.")
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        # The overlay is attractive when vol is rich and the trend is not strong.
        vol_rich = f.vol_regime
        flat = 1 - f.trend_strength.clip(0, 1)
        attractive = (vol_rich * flat).clip(0, 1)
        # It remains a long-underlying position, so the score stays long-biased.
        return (0.3 + 0.5 * attractive) * np.sign(f.sma(50) - f.sma(200)).fillna(0).clip(0, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"vol_percentile": float(f.vol_regime.iloc[-1]),
                "trend_strength": float(f.trend_strength.iloc[-1]),
                "overlay_attractive": float((f.vol_regime * (1 - f.trend_strength)).clip(0, 1).iloc[-1])}


class CashSecuredPut(BaseStrategy):
    name = "Cash-Secured Put"
    category = INCOME
    family = "options_income"
    research = "CBOE PUT Index methodology; analysed in Ungar & Moran (2009), JOT 4(1)"
    description = "Short an out-of-the-money put against cash; synthetically equivalent to a covered call."
    horizon = Horizon.SWING
    min_bars = 200
    is_proxy = True
    proxy_note = "Expresses the entry-timing rule only; actual premium and assignment risk need a chain."

    def score(self, f: FeatureSet) -> pd.Series:
        # Best entered after a volatility spike into support, when put premium is rich.
        vol_spike = f.vol_regime
        oversold = -band_score(f.rsi(14), 0, 100).clip(-1, 0)
        return (vol_spike * oversold).clip(0, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"rsi": float(f.rsi(14).iloc[-1]), "vol_percentile": float(f.vol_regime.iloc[-1])}


class WheelStrategy(BaseStrategy):
    name = "Options Wheel"
    category = INCOME
    family = "options_income"
    research = "Systematic premium harvesting; return profile per Israelov & Nielsen (2015), JPM 41(4)"
    description = "Cycles cash-secured puts into covered calls on assignment; a continuous premium-harvest loop."
    horizon = Horizon.POSITION
    min_bars = 250
    is_proxy = True
    proxy_note = "Models the regime in which the wheel performs, not the option legs themselves."

    def score(self, f: FeatureSet) -> pd.Series:
        # The wheel performs in choppy, elevated-vol markets and suffers in sharp trends.
        choppy = 1 - f.trend_strength.clip(0, 1)
        vol_ok = f.vol_regime.clip(0, 1)
        no_crash = (1 + f.drawdown() / 0.25).clip(0, 1)
        return (choppy * vol_ok * no_crash).clip(0, 1) * 0.8


class ShortStrangleSystematic(BaseStrategy):
    name = "Systematic Short Strangle"
    category = INCOME
    family = "options_income"
    research = "Variance risk premium harvesting per Carr & Wu (2009), RFS 22(3)"
    description = "Sells both wings to harvest the variance premium; carries unbounded tail risk if left unhedged."
    horizon = Horizon.SWING
    min_bars = 250
    is_proxy = True
    proxy_note = "Scores the favourability of the short-vol regime; the actual position needs a chain and tail hedge."

    def score(self, f: FeatureSet) -> pd.Series:
        vol_rich = f.vol_regime
        ranging = 1 - f.trend_strength.clip(0, 1)
        # Explicitly disable in fat-tail regimes — this is where short strangles blow up.
        tail_safe = (1 - (f.kurtosis(60) / 6).clip(0, 1)).clip(0, 1)
        return (vol_rich * ranging * tail_safe).clip(0, 1) * 0.7

    def diagnostics(self, f: FeatureSet) -> dict:
        k = float(f.kurtosis(60).iloc[-1])
        return {"vol_percentile": float(f.vol_regime.iloc[-1]),
                "excess_kurtosis": k,
                "tail_risk": "elevated — short vol dangerous" if k > 3 else "normal"}


class IronCondorSystematic(BaseStrategy):
    name = "Systematic Iron Condor"
    category = INCOME
    family = "options_income"
    research = "Defined-risk premium selling; sizing framework per Israelov & Nielsen (2015), JPM 41(4)"
    description = "Defined-risk short strangle with protective wings; caps the tail the naked version carries."
    horizon = Horizon.SWING
    min_bars = 250
    is_proxy = True
    proxy_note = "Scores regime favourability only; strike selection and width require a live chain."

    def score(self, f: FeatureSet) -> pd.Series:
        ranging = 1 - f.trend_strength.clip(0, 1)
        vol_rich = f.vol_regime
        stable = (1 - rolling_rank(f.natr(14), 120)).clip(0, 1)
        return (ranging * vol_rich * stable).clip(0, 1) * 0.7


class VIXRollShort(BaseStrategy):
    name = "VIX Roll Short (Contango Harvest)"
    category = INCOME
    family = "vol_carry"
    research = "Simon & Campasano (2014), 'The VIX Futures Basis', JAI 16(3); Alexander & Korovilas (2012)"
    description = "Harvests VIX-futures contango; profitable most of the time and catastrophic in the tail."
    horizon = Horizon.SWING
    min_bars = 250
    is_proxy = True
    proxy_note = ("Real implementation shorts VIX futures. Without that curve this reads the realised-vol term "
                  "structure of the underlying as the contango/backwardation proxy.")

    def score(self, f: FeatureSet) -> pd.Series:
        near, far = f.realized_vol(10), f.realized_vol(60)
        basis = _safe_div(far - near, far.where(far > 1e-9))
        # Contango (far > near) pays; backwardation is the regime that destroys the trade.
        return squash(basis, 0.25).clip(-1, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        n, fr = float(f.realized_vol(10).iloc[-1]), float(f.realized_vol(60).iloc[-1])
        return {"near_vol_pct": n * 100, "far_vol_pct": fr * 100,
                "structure": "contango (carry positive)" if fr > n else "backwardation (STOP — tail regime)"}

    def explain(self, f: FeatureSet, v: float, d: dict) -> str:
        return (f"Volatility term structure is in {d.get('structure')} "
                f"(near {d.get('near_vol_pct', 0):.1f}% vs far {d.get('far_vol_pct', 0):.1f}%). "
                f"Conviction {abs(v):.2f}. Short-vol carry is profitable most months and "
                f"loses many years of gains in a single volatility spike.")


class ProtectivePutOverlay(BaseStrategy):
    name = "Protective Put Overlay"
    category = INCOME
    family = "tail_hedge"
    research = "Israelov (2019), 'Pathetic Protection: The Elusive Benefits of Protective Puts', JAI 21(3)"
    description = ("Long underlying plus a protective put. The cited research finds the cost usually exceeds the "
                   "benefit — included so the ensemble can price the hedge, not to recommend it.")
    horizon = Horizon.POSITION
    min_bars = 250
    is_proxy = True
    proxy_note = "Scores when tail protection is cheap relative to realised risk; premium pricing needs a chain."

    def score(self, f: FeatureSet) -> pd.Series:
        # Hedging is most valuable when vol is cheap but tail indicators are deteriorating.
        vol_cheap = 1 - f.vol_regime
        tail_risk = (f.kurtosis(60) / 6).clip(0, 1).fillna(0)
        skew_risk = (-f.skew(60) / 2).clip(0, 1).fillna(0)
        hedge_value = (vol_cheap * (tail_risk + skew_risk) / 2).clip(0, 1)
        # A hedged long is still long, reduced by the cost of protection.
        return np.sign(f.sma(50) - f.sma(200)).fillna(0).clip(0, 1) * (1 - hedge_value * 0.5)
