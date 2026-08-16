"""
Crypto-native models.

Two distinct groups. The on-chain metrics (MVRV, SOPR, NVT, hash ribbons) need a
blockchain data feed and stand down without one — they cannot be inferred from
price. The market-structure models (funding, basis, liquidation cascades,
dominance rotation) need exchange derivatives data; those that can be partially
read from price and volume are marked as proxies.

One deliberate omission worth naming: Stock-to-Flow is widely circulated but its
central claim failed out of sample after 2021, so it is not included as a signal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import BaseStrategy, DataNeed, Horizon, Regime, band_score, persist, squash
from ..features import FeatureSet, _safe_div, rolling_rank, zscore

CAT = "Crypto Native"


class _OnChainStrategy(BaseStrategy):
    """Base for models that require a blockchain data feed."""
    needs = (DataNeed.OHLC, DataNeed.ONCHAIN)
    horizon = Horizon.POSITION
    min_bars = 200
    _key = "onchain"

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get(self._key) is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class MVRVRatio(_OnChainStrategy):
    name = "MVRV Ratio"
    category = CAT
    family = "onchain_valuation"
    research = "Kalichkin & Coinmetrics (2018), 'Realized Capitalization'; MVRV per Puell & David (2018)"
    description = "Market value over realised value; above ~3.7 marks cycle tops, below 1 marks capitulation."


class SOPRSpentOutput(_OnChainStrategy):
    name = "Spent Output Profit Ratio"
    category = CAT
    family = "onchain_flow"
    research = "Shirakashi (2019), 'Spent Output Profit Ratio', Unchained Capital"
    description = "Whether coins moving on-chain are realising profit or loss; SOPR crossing 1 is a regime marker."


class NVTRatio(_OnChainStrategy):
    name = "NVT Ratio (Network Value to Transactions)"
    category = CAT
    family = "onchain_valuation"
    research = "Woo (2017), 'Introducing NVT Ratio'; NVT Signal per Kalichkin (2018)"
    description = "The crypto analogue of a P/E ratio: network value against on-chain transaction throughput."


class PuellMultiple(_OnChainStrategy):
    name = "Puell Multiple"
    category = CAT
    family = "onchain_supply"
    research = "Puell (2019), 'The Puell Multiple'"
    description = "Daily miner issuance value against its yearly average; captures supply-side pressure."


class HashRibbons(_OnChainStrategy):
    name = "Hash Ribbon Miner Capitulation"
    category = CAT
    family = "onchain_supply"
    research = "Edwards (2019), 'Hash Ribbons and Bitcoin Bottoms', Capriole Investments"
    description = "Hash-rate moving-average crossovers identify miner capitulation and subsequent recovery."


class ExchangeNetflow(_OnChainStrategy):
    name = "Exchange Netflow"
    category = CAT
    family = "onchain_flow"
    research = "CryptoQuant exchange flow methodology; academic treatment per Makarov & Schoar (2020), JFE 135(2)"
    description = "Coins moving onto exchanges signal selling intent; withdrawals signal accumulation."


class StablecoinSupplyRatio(_OnChainStrategy):
    name = "Stablecoin Supply Ratio"
    category = CAT
    family = "onchain_valuation"
    research = "Glassnode (2020), 'Stablecoin Supply Ratio' methodology"
    description = "Ratio of crypto market cap to stablecoin supply — a measure of available dry powder."


class RealizedCapHODLWaves(_OnChainStrategy):
    name = "HODL Waves Coin Age Distribution"
    category = CAT
    family = "onchain_supply"
    research = "Unchained Capital (2018), 'Bitcoin Data Science: HODL Waves'"
    description = "Age distribution of unspent outputs; old coins moving marks distribution by long-term holders."


class ThermocapMultiple(_OnChainStrategy):
    name = "Thermocap Multiple"
    category = CAT
    family = "onchain_valuation"
    research = "Nick Emblow / Coinmetrics (2019), 'Thermocap' security-spend valuation"
    description = "Market cap against cumulative miner revenue — a floor-valuation measure."


class MinerPositionIndex(_OnChainStrategy):
    name = "Miner Position Index"
    category = CAT
    family = "onchain_supply"
    research = "CryptoQuant MPI methodology (2020)"
    description = "Miner outflows against their one-year average; elevated readings precede supply overhangs."


# ── derivatives market structure ──────────────────────────────────────────────

class PerpetualFundingRate(BaseStrategy):
    name = "Perpetual Funding Rate Carry"
    category = CAT
    family = "funding"
    research = "Perpetual swap mechanism per BitMEX (2016); basis-trade analysis per Makarov & Schoar (2020), JFE 135(2)"
    description = "Extreme funding marks crowded positioning and is the single most reliable crypto contrarian signal."
    needs = (DataNeed.OHLC, DataNeed.ONCHAIN)
    horizon = Horizon.SWING
    min_bars = 120

    def score(self, f: FeatureSet) -> pd.Series:
        funding = f.meta.get("funding_rate")
        if funding is None:
            return pd.Series(np.nan, index=f.close.index)
        fr = pd.Series(funding, index=f.close.index)
        # Extremely positive funding = crowded longs = fade.
        return -squash(zscore(fr, 60), 1.5)


class CashAndCarryBasis(BaseStrategy):
    name = "Cash-and-Carry Basis Trade"
    category = CAT
    family = "funding"
    research = "Classic carry arbitrage; crypto application per Makarov & Schoar (2020), 'Trading and Arbitrage in Cryptocurrency Markets'"
    description = "Annualised premium of dated futures over spot; the core delta-neutral crypto yield trade."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    horizon = Horizon.POSITION
    min_bars = 120

    def score(self, f: FeatureSet) -> pd.Series:
        spot, fut = f.meta.get("spot_close"), f.meta.get("futures_close")
        if spot is None or fut is None:
            return pd.Series(np.nan, index=f.close.index)
        s = pd.Series(spot, index=f.close.index)
        fu = pd.Series(fut, index=f.close.index).replace(0, np.nan)
        return squash(np.log(fu / s), 0.03)


class OpenInterestPriceDivergence(BaseStrategy):
    name = "Open Interest Price Divergence"
    category = CAT
    family = "derivatives_positioning"
    research = "Bessembinder & Seguin (1993), JFQA 28(1); crypto application per Alexander & Heck (2020)"
    description = "Rising open interest against a flat price means leverage is building without conviction."
    needs = (DataNeed.OHLC, DataNeed.ONCHAIN)
    horizon = Horizon.SWING
    min_bars = 120

    def score(self, f: FeatureSet) -> pd.Series:
        oi = f.meta.get("open_interest")
        if oi is None:
            return pd.Series(np.nan, index=f.close.index)
        o = pd.Series(oi, index=f.close.index)
        return -squash(zscore(o.pct_change(5), 60) * np.sign(f.close.pct_change(5)), 1.5)


class LongShortRatioContrarian(BaseStrategy):
    name = "Long/Short Account Ratio"
    category = CAT
    family = "derivatives_positioning"
    research = "Retail positioning contrarian evidence per Kelley & Tetlock (2013), JF 68(3)"
    description = "Retail account positioning is a contrarian indicator at extremes; needs exchange positioning data."
    needs = (DataNeed.OHLC, DataNeed.ONCHAIN)
    horizon = Horizon.SWING
    min_bars = 120

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("long_short_ratio") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class LiquidationCascade(BaseStrategy):
    name = "Liquidation Cascade Reversal"
    category = CAT
    family = "liquidation"
    research = "Leverage-spiral mechanics per Brunnermeier & Pedersen (2009), 'Market Liquidity and Funding Liquidity', RFS 22(6)"
    description = "Forced deleveraging overshoots fundamental value and snaps back once the cascade exhausts."
    needs = (DataNeed.OHLC, DataNeed.VOLUME)
    horizon = Horizon.INTRADAY
    min_bars = 120
    is_proxy = True
    proxy_note = ("Real liquidation data comes from exchange liquidation feeds. This detects the price/volume "
                  "signature of a cascade — violent range expansion on extreme volume with a long wick.")
    params = {"vol_z": 2.0, "range_mult": 2.5, "hold": 6}

    def score(self, f: FeatureSet) -> pd.Series:
        violent = f.true_range > f.atr(14) * self.params["range_mult"]
        heavy = f.volume_z(20) > self.params["vol_z"]
        rng = (f.high - f.low).where((f.high - f.low) > 1e-12)
        # A long lower wick with a close well off the low = sellers exhausted.
        lower_wick = (f.close - f.low) / rng
        upper_wick = (f.high - f.close) / rng
        cascade_down = (violent & heavy & (lower_wick > 0.6)).astype(float)
        cascade_up = (violent & heavy & (upper_wick > 0.6)).astype(float)
        return persist(cascade_down - cascade_up, self.params["hold"])

    def diagnostics(self, f: FeatureSet) -> dict:
        rng = float(f.high.iloc[-1] - f.low.iloc[-1])
        return {"range_in_atr": float(f.true_range.iloc[-1] / f.atr(14).iloc[-1]),
                "volume_zscore": float(f.volume_z(20).iloc[-1]) if f.has_volume else float("nan"),
                "lower_wick_share": float((f.close.iloc[-1] - f.low.iloc[-1]) / rng) if rng > 0 else float("nan")}


class CrossExchangeSpread(BaseStrategy):
    name = "Cross-Exchange Price Spread"
    category = CAT
    family = "arbitrage"
    research = "Makarov & Schoar (2020), JFE 135(2) — persistent cross-exchange deviations in crypto"
    description = "Same asset priced differently across venues; needs simultaneous multi-venue quotes."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    horizon = Horizon.INTRADAY
    min_bars = 100

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("venue_prices") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class TriangularArbitrage(BaseStrategy):
    name = "Triangular Arbitrage"
    category = CAT
    family = "arbitrage"
    research = "Classic FX triangular arbitrage; crypto measurement per Makarov & Schoar (2020)"
    description = "Detects inconsistency across three pairs on one venue; needs all three legs simultaneously."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    horizon = Horizon.INTRADAY
    min_bars = 100

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("triangle_legs") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class BitcoinDominanceRotation(BaseStrategy):
    name = "Bitcoin Dominance Rotation"
    category = CAT
    family = "rotation"
    research = "Crypto market-cycle rotation; capital-flow framework per Liu & Tsyvinski (2021), RFS 34(6)"
    description = "Capital rotates between BTC and alts through the cycle; needs the dominance series."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    horizon = Horizon.POSITION
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        dom = f.meta.get("btc_dominance")
        if dom is None:
            return pd.Series(np.nan, index=f.close.index)
        return -squash(zscore(pd.Series(dom, index=f.close.index), 60), 1.5)


class CryptoMomentumFactor(BaseStrategy):
    name = "Crypto Time-Series Momentum"
    category = CAT
    family = "crypto_momentum"
    research = "Liu, Tsyvinski & Wu (2022), 'Common Risk Factors in Cryptocurrency', JF 77(2)"
    description = "Momentum is the dominant documented crypto factor, strongest at the 1-4 week horizon."
    horizon = Horizon.SWING
    min_bars = 120
    params = {"lookback": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        r = np.log(f.close / f.close.shift(self.params["lookback"]))
        vol = f.logret.rolling(60, min_periods=20).std(ddof=0) * np.sqrt(self.params["lookback"])
        return squash(r / vol.where(vol > 1e-9), 1.0)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"return_20b_pct": float(f.close.pct_change(20).iloc[-1] * 100),
                "annualized_vol_pct": float(f.realized_vol(60).iloc[-1] * 100)}


class WeekendEffectCrypto(BaseStrategy):
    name = "Crypto Weekend Liquidity Effect"
    category = CAT
    family = "crypto_seasonal"
    research = "Baur, Cahill, Godfrey & Liu (2019), 'Bitcoin Time-of-Day, Day-of-Week and Month-of-Year Effects', Finance Research Letters 31"
    description = "Crypto trades continuously but weekend liquidity thins, amplifying moves that partly revert Monday."
    horizon = Horizon.INTRADAY
    min_bars = 150

    def score(self, f: FeatureSet) -> pd.Series:
        if not isinstance(f.df.index, pd.DatetimeIndex):
            return pd.Series(np.nan, index=f.close.index)
        dow = f.df.index.dayofweek
        weekend = pd.Series(np.isin(dow, [5, 6]).astype(float), index=f.close.index)
        # Thin-liquidity weekend moves revert disproportionately.
        return -squash(zscore(f.ret, 20), 1.5) * weekend

    def diagnostics(self, f: FeatureSet) -> dict:
        if not isinstance(f.df.index, pd.DatetimeIndex):
            return {}
        return {"day_of_week": int(f.df.index[-1].dayofweek),
                "is_weekend": bool(f.df.index[-1].dayofweek in (5, 6))}


class RealizedVolatilityCrypto(BaseStrategy):
    name = "Crypto Volatility Regime"
    category = CAT
    family = "crypto_vol"
    research = "Katsiampa (2017), 'Volatility Estimation for Bitcoin', Economics Letters 158"
    description = "Crypto volatility clusters harder than equities; regime percentile drives exposure directly."
    horizon = Horizon.SWING
    min_bars = 200
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        rank = f.vol_regime
        trend = np.sign(f.ema(20) - f.ema(50)).fillna(0)
        # Trend-follow in calm regimes, cut hard in extreme-vol regimes.
        return trend * (1 - rank).clip(0, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"annualized_vol_pct": float(f.realized_vol(20).iloc[-1] * 100),
                "vol_percentile": float(f.vol_regime.iloc[-1])}


class AltcoinBetaRotation(BaseStrategy):
    name = "Altcoin Beta Amplification"
    category = CAT
    family = "rotation"
    research = "Liu, Tsyvinski & Wu (2022), JF 77(2) — cross-sectional crypto factor structure"
    description = "Alts amplify BTC moves with a lag; needs a BTC reference series to measure the relationship."
    needs = (DataNeed.OHLC, DataNeed.BENCHMARK)
    horizon = Horizon.SWING
    min_bars = 150
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        btc = f.meta.get("benchmark_close")
        if btc is None:
            return pd.Series(np.nan, index=f.close.index)
        w = self.params["window"]
        br = pd.Series(btc, index=f.close.index).pct_change()
        beta = f.ret.rolling(w, min_periods=w // 2).cov(br) / br.rolling(w, min_periods=w // 2).var(ddof=0)
        return squash(beta * br.rolling(3).mean() * 100, 1.0)


class VolumeProfileSupport(BaseStrategy):
    name = "Volume Profile Value Area"
    category = CAT
    family = "volume_profile"
    research = "Steidlmayer & Koy (1986), 'Markets and Market Logic' — Market Profile theory"
    description = "Price reverts toward the volume-weighted value area where the most business was transacted."
    needs = (DataNeed.OHLC, DataNeed.VOLUME)
    horizon = Horizon.SWING
    min_bars = 150
    params = {"window": 60, "bins": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        # Point of control ≈ volume-weighted price over the window.
        poc = f.vwap(w)
        dist = (f.close - poc) / f.atr(14).where(f.atr(14) > 1e-12)
        return -squash(dist, 1.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        poc = float(f.vwap(60).iloc[-1])
        return {"point_of_control": poc, "distance_pct": float((f.close.iloc[-1] / poc - 1) * 100)}
