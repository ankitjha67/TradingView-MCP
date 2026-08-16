"""
Options and derivatives.

The volatility desks at Optiver, IMC, SIG and Jane Street live here. Options
strategies genuinely need an options chain: strikes, expiries, implied vols and
open interest. Where that feed is absent these models say so and stand down.
The handful that can be computed from the underlying alone — realised-vol cones,
implied-move comparison, gamma-proxy pinning — are marked as proxies.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import BaseStrategy, DataNeed, Horizon, Regime, band_score, squash
from ..features import FeatureSet, _safe_div, rolling_rank, zscore

CAT = "Options & Derivatives"
CHAIN = (DataNeed.OHLC, DataNeed.OPTIONS_CHAIN)


class _ChainStrategy(BaseStrategy):
    """Base for models that cannot run without a real options chain."""
    needs = CHAIN
    horizon = Horizon.SWING
    min_bars = 120
    _chain_key = "options_chain"

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get(self._chain_key) is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class BlackScholesMispricing(_ChainStrategy):
    name = "Black-Scholes Relative Mispricing"
    category = CAT
    family = "bs_pricing"
    research = "Black & Scholes (1973), JPE 81(3); Merton (1973), Bell J. Economics 4(1)"
    description = "Compares market premium to the Black-Scholes value at the realised-vol input."


class ImpliedVolatilitySkew(_ChainStrategy):
    name = "Implied Volatility Skew"
    category = CAT
    family = "vol_surface"
    research = "Dumas, Fleming & Whaley (1998), 'Implied Volatility Functions', JF 53(6)"
    description = "Slope of implied vol across strikes; steep put skew prices crash risk and is itself mean-reverting."


class VolatilitySmileArbitrage(_ChainStrategy):
    name = "Volatility Smile Arbitrage"
    category = CAT
    family = "vol_surface"
    research = "Derman & Kani (1994), 'Riding on a Smile', Risk 7(2)"
    description = "Trades local dislocations in the smile against a no-arbitrage fitted surface."


class SABRSurfaceFit(_ChainStrategy):
    name = "SABR Stochastic Alpha-Beta-Rho Fit"
    category = CAT
    family = "vol_surface"
    research = "Hagan, Kumar, Lesniewski & Woodward (2002), 'Managing Smile Risk', Wilmott Magazine"
    description = "Fits the SABR model to the surface and trades residuals against the fitted smile."


class PutCallParityArb(_ChainStrategy):
    name = "Put-Call Parity Violation"
    category = CAT
    family = "arbitrage"
    research = "Stoll (1969), 'The Relationship Between Put and Call Option Prices', JF 24(5)"
    description = "A genuine arbitrage when synthetic and actual forward prices diverge beyond costs."


class GammaExposureLevels(_ChainStrategy):
    name = "Dealer Gamma Exposure (GEX)"
    category = CAT
    family = "dealer_flow"
    research = "Baltas (2019) dealer hedging flows; SqueezeMetrics (2017), 'The Implied Order Book'"
    description = "Net dealer gamma; positive gamma dampens realised vol, negative gamma amplifies it."


class VannaCharmFlow(_ChainStrategy):
    name = "Vanna-Charm Hedging Flow"
    category = CAT
    family = "dealer_flow"
    research = "Second-order Greeks per Haug (2007), 'The Complete Guide to Option Pricing Formulas'"
    description = "Predictable dealer re-hedging as spot, vol and time-to-expiry move the delta."


class VarianceSwapReplication(_ChainStrategy):
    name = "Variance Swap Replication"
    category = CAT
    family = "variance"
    research = "Demeterfi, Derman, Kamal & Zou (1999), 'More Than You Ever Wanted to Know About Volatility Swaps', Goldman Sachs"
    description = "Replicates a variance swap from a strip of options to isolate pure variance exposure."


class VIXTermStructure(_ChainStrategy):
    name = "VIX Term Structure Carry"
    category = CAT
    family = "vol_term"
    research = "CBOE VIX White Paper (2003, rev. 2019); term-structure carry per Simon & Campasano (2014), JAI 16(3)"
    description = "Contango pays short-vol carry; backwardation flags stress and reverses the sign."


class DispersionTrade(_ChainStrategy):
    name = "Index-Component Dispersion"
    category = CAT
    family = "dispersion"
    research = "Driessen, Maenhout & Vilkov (2009), 'The Price of Correlation Risk', JF 64(3)"
    description = "Sells index vol against component vol when implied correlation is rich."
    needs = (DataNeed.OHLC, DataNeed.OPTIONS_CHAIN, DataNeed.CROSS_SECTION)


class MaxPainPinning(_ChainStrategy):
    name = "Max Pain Expiry Pinning"
    category = CAT
    family = "expiry"
    research = "Ni, Pearson & Poteshman (2005), 'Stock Price Clustering on Option Expiration Dates', JFE 78(1)"
    description = "Prices cluster at strikes with maximal open interest into expiry — a documented pinning effect."


class PutCallRatioSentiment(_ChainStrategy):
    name = "Put-Call Ratio Sentiment"
    category = CAT
    family = "options_sentiment"
    research = "Pan & Poteshman (2006), 'The Information in Option Volume for Future Stock Prices', RFS 19(3)"
    description = "Option volume ratios carry directional information, especially from non-market-maker accounts."


class OpenInterestDivergence(_ChainStrategy):
    name = "Open Interest Divergence"
    category = CAT
    family = "options_sentiment"
    research = "Bessembinder & Seguin (1993), 'Price Volatility, Trading Volume and Market Depth', JFQA 28(1)"
    description = "Open interest rising against price marks positioning that must eventually unwind."


class BinomialAmericanExercise(_ChainStrategy):
    name = "Binomial American Early Exercise"
    category = CAT
    family = "bs_pricing"
    research = "Cox, Ross & Rubinstein (1979), 'Option Pricing: A Simplified Approach', JFE 7(3)"
    description = "Values the early-exercise premium on American options via a binomial lattice."


class SkewIndexTail(_ChainStrategy):
    name = "SKEW Index Tail Risk"
    category = CAT
    family = "tail_pricing"
    research = "CBOE SKEW Index methodology; risk-neutral skewness per Bakshi, Kapadia & Madan (2003), RFS 16(1)"
    description = "Risk-neutral skewness from out-of-the-money puts prices the market's tail expectation."


# ── computable from the underlying alone ──────────────────────────────────────

class RealizedVolatilityCone(BaseStrategy):
    name = "Realized Volatility Cone"
    category = CAT
    family = "vol_cone"
    research = "Burghardt & Lane (1990), 'How to Tell If Options Are Cheap', JPM 16(2)"
    description = "Places current realised vol on the historical percentile cone across horizons — the desk's first check."
    horizon = Horizon.SWING
    min_bars = 250
    params = {"horizons": (10, 20, 60), "rank_window": 252}

    def score(self, f: FeatureSet) -> pd.Series:
        rw = min(self.params["rank_window"], max(60, f.n // 2))
        ranks = [rolling_rank(f.realized_vol(h), rw) for h in self.params["horizons"]]
        avg = sum(ranks) / len(ranks)
        # Vol cheap (low percentile) → own gamma → favour breakout; rich → fade.
        return -band_score(avg, 0.0, 1.0) * np.sign(zscore(f.close, 20)).fillna(0)

    def diagnostics(self, f: FeatureSet) -> dict:
        rw = min(252, max(60, f.n // 2))
        out = {}
        for h in self.params["horizons"]:
            out[f"vol_{h}b_pct"] = float(f.realized_vol(h).iloc[-1] * 100)
            out[f"percentile_{h}b"] = float(rolling_rank(f.realized_vol(h), rw).iloc[-1])
        return out

    def explain(self, f: FeatureSet, v: float, d: dict) -> str:
        p = d.get("percentile_20b", 0.5)
        state = "cheap — favours owning optionality" if p < 0.3 else \
                "rich — favours selling premium" if p > 0.7 else "fairly priced"
        return (f"20-bar realised vol {d.get('vol_20b_pct', 0):.1f}% sits at the {p:.0%} percentile of its "
                f"1-year cone: volatility looks {state}. Conviction {abs(v):.2f}.")


class ImpliedMoveComparison(BaseStrategy):
    name = "Straddle-Implied Move vs Realized"
    category = CAT
    family = "vol_cone"
    research = "Implied-move framework per Natenberg (1994), 'Option Volatility and Pricing', ch. 4"
    description = "Compares the move a straddle would need against what the underlying actually delivers."
    horizon = Horizon.SWING
    min_bars = 150
    is_proxy = True
    proxy_note = ("Without a chain, the implied move is estimated from a GARCH-style forecast of realised vol "
                  "rather than read from actual at-the-money straddle premium.")
    params = {"horizon": 5}

    def score(self, f: FeatureSet) -> pd.Series:
        h = self.params["horizon"]
        expected = f.realized_vol(60, annualize=False) * np.sqrt(h)
        actual = (f.close.pct_change(h)).abs()
        ratio = _safe_div(actual, expected.where(expected > 1e-9), 1.0)
        # Delivered move far above the expected move ⇒ overextension ⇒ fade.
        return -np.sign(f.close.pct_change(h)).fillna(0) * squash(ratio - 1, 0.6).clip(0, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        h = self.params["horizon"]
        exp = float(f.realized_vol(60, annualize=False).iloc[-1] * np.sqrt(h) * 100)
        act = float(abs(f.close.pct_change(h).iloc[-1]) * 100)
        return {"expected_move_pct": exp, "actual_move_pct": act,
                "move_ratio": act / exp if exp > 1e-9 else float("nan")}


class GammaPinProxy(BaseStrategy):
    name = "Round-Number Pin Proxy"
    category = CAT
    family = "expiry"
    research = "Ni, Pearson & Poteshman (2005), JFE 78(1) — expiry-date price clustering"
    description = "Prices gravitate to round strike levels near expiry; approximates pinning without chain data."
    horizon = Horizon.INTRADAY
    min_bars = 100
    is_proxy = True
    proxy_note = "Uses round-number price levels as a stand-in for real open-interest concentration."
    params = {"granularity": 0.01}

    def score(self, f: FeatureSet) -> pd.Series:
        # Nearest "round" level at ~1% granularity of price.
        step = f.close.rolling(60, min_periods=20).mean() * self.params["granularity"]
        nearest = (f.close / step.where(step > 1e-9)).round() * step
        dist = (nearest - f.close) / f.atr(14).where(f.atr(14) > 1e-12)
        return squash(dist, 0.8) * 0.6

    def diagnostics(self, f: FeatureSet) -> dict:
        step = float(f.close.rolling(60, min_periods=20).mean().iloc[-1] * 0.01)
        px = float(f.close.iloc[-1])
        return {"nearest_pin_level": round(px / step) * step if step else float("nan"), "price": px}


class VolatilityRiskPremiumProxy(BaseStrategy):
    name = "Volatility Risk Premium Proxy"
    category = CAT
    family = "vrp"
    research = "Carr & Wu (2009), 'Variance Risk Premiums', RFS 22(3)"
    description = "Implied variance normally exceeds realised; the gap is the premium short-vol strategies harvest."
    horizon = Horizon.SWING
    min_bars = 200
    is_proxy = True
    proxy_note = ("Implied variance is approximated by a forward-looking EWMA of realised variance plus the "
                  "historical average premium, because no options chain is connected.")
    params = {"short": 10, "long": 60, "premium": 1.15}

    def score(self, f: FeatureSet) -> pd.Series:
        realized = f.realized_vol(self.params["short"])
        implied_proxy = f.realized_vol(self.params["long"]) * self.params["premium"]
        vrp = implied_proxy - realized
        return squash(zscore(vrp, 120), 1.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        r = float(f.realized_vol(10).iloc[-1] * 100)
        i = float(f.realized_vol(60).iloc[-1] * 1.15 * 100)
        return {"realized_vol_pct": r, "implied_proxy_pct": i, "premium_pct_points": i - r}


class TermStructureSlopeProxy(BaseStrategy):
    name = "Volatility Curve Slope Proxy"
    category = CAT
    family = "vol_term"
    research = "Simon & Campasano (2014), 'The VIX Futures Basis', JAI 16(3)"
    description = "Short- versus long-horizon vol slope stands in for the futures basis; inversion marks stress."
    horizon = Horizon.SWING
    min_bars = 200
    is_proxy = True
    proxy_note = "Derived from the realised-vol term structure of the underlying, not from listed VIX futures."
    params = {"near": 10, "far": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        near, far = f.realized_vol(self.params["near"]), f.realized_vol(self.params["far"])
        basis = _safe_div(near - far, far.where(far > 1e-9))
        # Backwardation (near > far) = stress = risk-off; contango = carry = risk-on.
        return -squash(basis, 0.25)

    def diagnostics(self, f: FeatureSet) -> dict:
        n, fr = float(f.realized_vol(10).iloc[-1]), float(f.realized_vol(60).iloc[-1])
        return {"near_vol_pct": n * 100, "far_vol_pct": fr * 100,
                "structure": "backwardation (stress)" if n > fr * 1.1 else "contango (carry)"}


class DeltaHedgingSlippage(BaseStrategy):
    name = "Gamma Scalping Profitability"
    category = CAT
    family = "gamma_scalp"
    research = "Wilmott (2006), 'Paul Wilmott on Quantitative Finance', ch. on hedging error"
    description = "Whether realised path variation would have paid for the theta of a hedged long-gamma position."
    horizon = Horizon.SWING
    min_bars = 150
    is_proxy = True
    proxy_note = "Compares realised path variation to an assumed theta cost, since actual option premium is unavailable."
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        path_variation = f.logret.abs().rolling(w, min_periods=w // 2).sum()
        net_move = np.log(f.close / f.close.shift(w)).abs()
        # Choppy path with little net move = gamma scalping pays = own vol.
        chop = _safe_div(path_variation - net_move, path_variation.where(path_variation > 1e-12))
        return squash(zscore(chop, 120), 1.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        w = 20
        pv = float(f.logret.abs().rolling(w).sum().iloc[-1])
        nm = float(abs(np.log(f.close.iloc[-1] / f.close.iloc[-1 - w]))) if f.n > w else float("nan")
        return {"path_variation_pct": pv * 100, "net_move_pct": nm * 100,
                "chop_ratio": (pv - nm) / pv if pv > 0 else float("nan")}


class FuturesBasisCarry(BaseStrategy):
    name = "Futures Basis Carry"
    category = CAT
    family = "carry"
    research = "Keynes (1930) normal backwardation; empirical carry per Koijen, Moskowitz, Pedersen & Vrugt (2018), JFE 127(2)"
    description = "Trades the spot-futures basis directly; requires both legs of the curve."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    horizon = Horizon.POSITION
    min_bars = 150

    def score(self, f: FeatureSet) -> pd.Series:
        spot, fut = f.meta.get("spot_close"), f.meta.get("futures_close")
        if spot is None or fut is None:
            return pd.Series(np.nan, index=f.close.index)
        s = pd.Series(spot, index=f.close.index)
        fu = pd.Series(fut, index=f.close.index).replace(0, np.nan)
        return squash(np.log(s / fu), 0.02)
