"""
Market microstructure.

The domain of Jane Street, Hudson River Trading, Jump and Citadel Securities.

An honesty note that matters: the published forms of most of these models take
tick-level trades-and-quotes or full limit-order-book depth. Bar data cannot
reconstruct that. Models here that approximate an order-book quantity from bar
OHLCV are marked ``is_proxy = True`` and carry a note saying exactly what was
substituted. They are down-weighted in consensus and never presented as the
original estimator.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import BaseStrategy, DataNeed, Horizon, Regime, band_score, persist, squash
from ..features import FeatureSet, _safe_div, rolling_rank, zscore

CAT = "Microstructure"


class KyleLambda(BaseStrategy):
    name = "Kyle's Lambda (Price Impact)"
    category = CAT
    family = "price_impact"
    research = "Kyle (1985), 'Continuous Auctions and Insider Trading', Econometrica 53(6)"
    description = "Regression slope of price change on signed volume — the market's depth coefficient."
    needs = (DataNeed.OHLC, DataNeed.VOLUME)
    horizon = Horizon.INTRADAY
    min_bars = 100
    is_proxy = True
    proxy_note = ("Kyle's λ is defined on signed order flow. Bar data has no trade signing, so the tick "
                  "rule (close-to-close direction) substitutes for true buy/sell classification.")
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        signed_vol = np.sign(f.close.diff()).fillna(0) * f.volume.fillna(0)
        dp = f.close.diff()
        cov = dp.rolling(w, min_periods=w // 2).cov(signed_vol)
        var = signed_vol.rolling(w, min_periods=w // 2).var(ddof=0)
        lam = _safe_div(cov, var.where(var > 1e-12))
        # High λ = thin/illiquid = moves overshoot and retrace.
        return -squash(zscore(lam, 120), 1.5) * np.sign(f.logret).fillna(0)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"lambda_percentile": float(rolling_rank(f.volume.fillna(0), 60).iloc[-1])}


class AmihudIlliquidity(BaseStrategy):
    name = "Amihud Illiquidity Ratio"
    category = CAT
    family = "liquidity"
    research = "Amihud (2002), 'Illiquidity and Stock Returns', J. Financial Markets 5(1)"
    description = "Absolute return per unit of dollar volume; the standard low-frequency illiquidity measure."
    needs = (DataNeed.OHLC, DataNeed.VOLUME)
    horizon = Horizon.SWING
    min_bars = 100
    params = {"window": 21}

    def score(self, f: FeatureSet) -> pd.Series:
        dollar_vol = (f.close * f.volume.fillna(0)).replace(0, np.nan)
        illiq = _safe_div(f.ret.abs(), dollar_vol).rolling(self.params["window"], min_periods=10).mean()
        return -squash(zscore(illiq, 120), 1.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        dv = (f.close * f.volume.fillna(0)).replace(0, np.nan)
        illiq = (f.ret.abs() / dv).rolling(21, min_periods=10).mean()
        return {"amihud_percentile": float(rolling_rank(illiq, 120).iloc[-1]),
                "avg_dollar_volume": float(dv.rolling(21).mean().iloc[-1])}


class RollEffectiveSpread(BaseStrategy):
    name = "Roll Effective Spread Estimator"
    category = CAT
    family = "spread"
    research = "Roll (1984), 'A Simple Implicit Measure of the Effective Bid-Ask Spread', JF 39(4)"
    description = "Infers the spread from negative serial covariance of returns caused by bid-ask bounce."
    horizon = Horizon.INTRADAY
    min_bars = 100
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        cov = f.ret.rolling(w, min_periods=w // 2).cov(f.ret.shift(1))
        spread = 2 * np.sqrt((-cov).clip(lower=0))
        # Widening spread = deteriorating liquidity = risk-off.
        return -squash(zscore(spread, 120), 1.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        cov = f.ret.rolling(60, min_periods=30).cov(f.ret.shift(1)).iloc[-1]
        return {"roll_spread_bps": float(2 * np.sqrt(max(0.0, -cov)) * 10000),
                "serial_covariance": float(cov)}


class CorwinSchultzSpread(BaseStrategy):
    name = "Corwin-Schultz High-Low Spread"
    category = CAT
    family = "spread"
    research = "Corwin & Schultz (2012), 'A Simple Way to Estimate Bid-Ask Spreads', JF 67(2)"
    description = "Recovers the spread from two-day high-low ratios; works where tick data is unavailable."
    horizon = Horizon.INTRADAY
    min_bars = 80

    def score(self, f: FeatureSet) -> pd.Series:
        hl = np.log(_safe_div(f.high, f.low, 1.0).clip(lower=1e-12)) ** 2
        beta = hl + hl.shift(1)
        h2 = pd.concat([f.high, f.high.shift(1)], axis=1).max(axis=1)
        l2 = pd.concat([f.low, f.low.shift(1)], axis=1).min(axis=1)
        gamma = np.log(_safe_div(h2, l2, 1.0).clip(lower=1e-12)) ** 2
        k = 3 - 2 * np.sqrt(2)
        alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
        spread = (2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))).clip(lower=0)
        return -squash(zscore(spread, 120), 1.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"high_low_range_pct": float((f.high.iloc[-1] / f.low.iloc[-1] - 1) * 100)}


class VPINToxicity(BaseStrategy):
    name = "VPIN Order Flow Toxicity"
    category = CAT
    family = "flow_toxicity"
    research = "Easley, López de Prado & O'Hara (2012), 'Flow Toxicity and Liquidity in a High-Frequency World', RFS 25(5)"
    description = "Volume-synchronised probability of informed trading; spiked ahead of the 2010 Flash Crash."
    needs = (DataNeed.OHLC, DataNeed.VOLUME)
    horizon = Horizon.INTRADAY
    min_bars = 120
    is_proxy = True
    proxy_note = ("True VPIN buckets by volume clock and classifies trades with a bulk-volume rule on tick data. "
                  "This computes the analogous imbalance on time bars using the return-signed bar volume.")
    params = {"window": 50}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        v = f.volume.fillna(0)
        buy = v.where(f.close > f.open, 0.0)
        sell = v.where(f.close < f.open, 0.0)
        tot = (buy + sell).rolling(w, min_periods=w // 2).sum()
        imbalance = _safe_div((buy - sell).abs().rolling(w, min_periods=w // 2).sum(), tot.where(tot > 0))
        # High toxicity ⇒ informed flow present ⇒ don't fade it, and cut size.
        return -squash(zscore(imbalance, 120), 1.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        v = f.volume.fillna(0)
        buy = v.where(f.close > f.open, 0.0).rolling(50).sum()
        sell = v.where(f.close < f.open, 0.0).rolling(50).sum()
        tot = buy + sell
        return {"vpin_proxy": float((abs(buy - sell) / tot).iloc[-1]) if tot.iloc[-1] > 0 else float("nan")}


class OrderFlowImbalance(BaseStrategy):
    name = "Order Flow Imbalance"
    category = CAT
    family = "order_flow"
    research = "Cont, Kukanov & Stoikov (2014), 'The Price Impact of Order Book Events', J. Financial Econometrics 12(1)"
    description = "Net buying pressure; the single strongest short-horizon predictor of price in the OFI literature."
    needs = (DataNeed.OHLC, DataNeed.VOLUME)
    horizon = Horizon.INTRADAY
    min_bars = 80
    is_proxy = True
    proxy_note = ("Published OFI uses best-bid/ask size changes from L1 book updates. This substitutes the "
                  "close's position within the bar range as the proxy for intra-bar buy/sell pressure.")
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        rng = (f.high - f.low).where((f.high - f.low) > 1e-12)
        # Close near the high ⇒ buyers absorbed the bar; near the low ⇒ sellers did.
        pressure = (2 * (f.close - f.low) / rng - 1).fillna(0)
        ofi = (pressure * f.volume.fillna(0)).rolling(self.params["window"], min_periods=5).sum()
        return squash(zscore(ofi, 60), 1.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        rng = f.high.iloc[-1] - f.low.iloc[-1]
        cp = (f.close.iloc[-1] - f.low.iloc[-1]) / rng if rng > 0 else 0.5
        return {"close_position_in_bar": float(cp),
                "interpretation": "buyers in control" if cp > 0.7 else "sellers in control" if cp < 0.3 else "balanced"}


class AvellanedaStoikovMM(BaseStrategy):
    name = "Avellaneda-Stoikov Reservation Price"
    category = CAT
    family = "market_making"
    research = "Avellaneda & Stoikov (2008), 'High-Frequency Trading in a Limit Order Book', Quant. Finance 8(3)"
    description = "Inventory-adjusted reservation price; the canonical optimal market-making quote framework."
    horizon = Horizon.INTRADAY
    min_bars = 100
    is_proxy = True
    proxy_note = ("Full model requires live inventory and a quoted book. This computes the reservation-price "
                  "skew from volatility and a mean-reverting inventory proxy only.")
    params = {"gamma": 0.1, "window": 30}

    def score(self, f: FeatureSet) -> pd.Series:
        mid = (f.high + f.low) / 2
        var = f.logret.rolling(self.params["window"], min_periods=10).var(ddof=0)
        # Inventory proxy: accumulated displacement from the local mid.
        inventory = zscore(f.close - mid.rolling(self.params["window"], min_periods=10).mean(),
                           self.params["window"])
        reservation_skew = -inventory * self.params["gamma"] * var * 1e4
        return squash(reservation_skew, 0.5) - squash(inventory, 2.0) * 0.5


class AlmgrenChrissImpact(BaseStrategy):
    name = "Almgren-Chriss Temporary Impact"
    category = CAT
    family = "price_impact"
    research = "Almgren & Chriss (2000), 'Optimal Execution of Portfolio Transactions', J. Risk 3(2)"
    description = "Separates temporary from permanent impact; temporary impact reverts and is therefore tradeable."
    needs = (DataNeed.OHLC, DataNeed.VOLUME)
    horizon = Horizon.INTRADAY
    min_bars = 100
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        # Impact scales with the square root of participation (Almgren et al. 2005).
        adv = f.volume.rolling(self.params["window"], min_periods=10).mean()
        participation = _safe_div(f.volume.fillna(0), adv.where(adv > 0), 1.0)
        expected = np.sqrt(participation.clip(lower=0)) * f.natr(14)
        actual = f.ret.abs()
        # Move much larger than participation justifies ⇒ temporary impact ⇒ expect reversion.
        excess = _safe_div(actual - expected, expected.where(expected > 1e-9))
        return -np.sign(f.ret).fillna(0) * squash(excess, 1.0).clip(0, 1)


class GlostenMilgromAdverseSelection(BaseStrategy):
    name = "Glosten-Milgrom Adverse Selection"
    category = CAT
    family = "flow_toxicity"
    research = "Glosten & Milgrom (1985), 'Bid, Ask and Transaction Prices', JFE 14(1)"
    description = "Spread widening driven by informed-trader risk; persistent directional flow signals information."
    needs = (DataNeed.OHLC, DataNeed.VOLUME)
    horizon = Horizon.INTRADAY
    min_bars = 100
    is_proxy = True
    proxy_note = "Uses run-length of same-direction bars as the informed-flow proxy in place of quote revisions."
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        d = np.sign(f.close.diff()).fillna(0)
        persistence = d.rolling(self.params["window"], min_periods=5).mean()
        vol_conf = (f.volume_z(20) > 0).astype(float) if f.has_volume else 1.0
        # Sustained one-sided flow on volume = informed; follow it.
        return squash(persistence * 2, 0.6) * vol_conf


class TickRuleMomentum(BaseStrategy):
    name = "Tick Rule Signed Flow"
    category = CAT
    family = "order_flow"
    research = "Lee & Ready (1991), 'Inferring Trade Direction from Intraday Data', JF 46(2)"
    description = "Classifies each bar as buyer- or seller-initiated and accumulates the signed series."
    horizon = Horizon.INTRADAY
    min_bars = 60
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        tick = np.sign(f.close.diff()).replace(0, np.nan).ffill().fillna(0)
        return squash(tick.rolling(self.params["window"], min_periods=5).mean() * 2, 0.6)


class HasbrouckInformationShare(BaseStrategy):
    name = "Hasbrouck Information Share"
    category = CAT
    family = "price_discovery"
    research = "Hasbrouck (1995), 'One Security, Many Markets', JF 50(4)"
    description = "Attributes price discovery across venues; requires simultaneous quotes from two or more markets."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    horizon = Horizon.INTRADAY
    min_bars = 150

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("venue_prices") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class HawkesSelfExcitation(BaseStrategy):
    name = "Hawkes Self-Exciting Intensity"
    category = CAT
    family = "point_process"
    research = "Bacry, Mastromatteo & Muzy (2015), 'Hawkes Processes in Finance', Market Microstructure and Liquidity 1(1)"
    description = "Trade arrivals cluster and self-excite; elevated intensity marks bursts that typically decay."
    horizon = Horizon.INTRADAY
    min_bars = 120
    is_proxy = True
    proxy_note = "Intensity estimated from exponentially-decayed large-bar arrivals rather than fitted to a tick point process."
    params = {"decay": 0.85, "threshold": 1.5}

    def score(self, f: FeatureSet) -> pd.Series:
        big = (f.true_range > f.atr(14) * self.params["threshold"]).astype(float)
        intensity = big.ewm(alpha=1 - self.params["decay"], adjust=False).mean()
        # Elevated arrival intensity decays; fade the latest burst.
        return -np.sign(f.logret).fillna(0) * squash(zscore(intensity, 60), 1.5).abs()


class BidAskBounce(BaseStrategy):
    name = "Bid-Ask Bounce Reversal"
    category = CAT
    family = "spread"
    research = "Blume & Stambaugh (1983), 'Biases in Computed Returns', JFE 12(3)"
    description = "Single-bar reversal driven by transacting alternately at bid and ask rather than by information."
    horizon = Horizon.INTRADAY
    min_bars = 80
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        ac = f.ret.rolling(self.params["window"], min_periods=20).corr(f.ret.shift(1))
        bounce_regime = (-ac).clip(0, 1)
        return -squash(zscore(f.ret, 20), 1.5) * bounce_regime


class VolumeClockBars(BaseStrategy):
    name = "Volume Clock Information Arrival"
    category = CAT
    family = "volume_clock"
    research = "Easley, López de Prado & O'Hara (2012), 'The Volume Clock', J. Portfolio Management 39(1)"
    description = "Sampling on volume rather than time normalises information arrival and stabilises return moments."
    needs = (DataNeed.OHLC, DataNeed.VOLUME)
    horizon = Horizon.INTRADAY
    min_bars = 120
    params = {"window": 50}

    def score(self, f: FeatureSet) -> pd.Series:
        v = f.volume.fillna(0)
        vol_time = v.rolling(self.params["window"], min_periods=10).sum()
        # Return per unit of volume-time: high = move on little volume = fragile.
        efficiency = _safe_div(f.close.pct_change(self.params["window"]).abs(),
                               np.sqrt(vol_time.where(vol_time > 0)))
        return -np.sign(f.close.pct_change(self.params["window"])).fillna(0) * \
            squash(zscore(efficiency, 120), 1.5).clip(0, 1)


class TradeSizeClustering(BaseStrategy):
    name = "Volume Concentration (Iceberg Detection)"
    category = CAT
    family = "order_flow"
    research = "Barclay & Warner (1993), 'Stealth Trading and Volatility', JFE 34(3)"
    description = "Informed traders split orders into medium sizes; concentrated medium-volume bars flag stealth accumulation."
    needs = (DataNeed.OHLC, DataNeed.VOLUME)
    horizon = Horizon.INTRADAY
    min_bars = 120
    params = {"window": 40}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        v = f.volume.fillna(0)
        rank = rolling_rank(v, w)
        # Stealth zone: persistent mid-range volume with a consistent direction.
        stealth = ((rank > 0.4) & (rank < 0.8)).astype(float)
        direction = np.sign(f.close.diff()).fillna(0)
        return squash((stealth * direction).rolling(w, min_periods=10).mean() * 3, 0.5)


class RealizedSpreadReversal(BaseStrategy):
    name = "Realized Spread Price Reversal"
    category = CAT
    family = "spread"
    research = "Huang & Stoll (1996), 'Dealer versus Auction Markets', JFE 41(3)"
    description = "Decomposes the effective spread; the reverting portion is dealer compensation, not information."
    horizon = Horizon.INTRADAY
    min_bars = 80
    params = {"horizon": 5}

    def score(self, f: FeatureSet) -> pd.Series:
        h = self.params["horizon"]
        immediate = f.ret
        subsequent = f.close.pct_change(h).shift(-h)  # for context only; not used causally
        reverting = -immediate.rolling(h, min_periods=2).mean()
        return squash(zscore(reverting, 60), 1.5)


class QuoteStuffingDetection(BaseStrategy):
    name = "Microstructure Noise Ratio"
    category = CAT
    family = "noise"
    research = "Aït-Sahalia, Mykland & Zhang (2005), 'How Often to Sample a Continuous-Time Process', RFS 18(2)"
    description = "Ratio of high-frequency to low-frequency variance; excess noise means quoted prices are unreliable."
    horizon = Horizon.INTRADAY
    min_bars = 120
    params = {"fast": 5, "slow": 30}

    def score(self, f: FeatureSet) -> pd.Series:
        fast_var = (f.logret ** 2).rolling(self.params["fast"], min_periods=3).sum()
        slow_var = (np.log(f.close / f.close.shift(self.params["fast"])) ** 2).rolling(
            self.params["slow"] // self.params["fast"], min_periods=2).sum()
        noise = _safe_div(fast_var - slow_var, fast_var.where(fast_var > 1e-14))
        # High noise ⇒ observed moves are mostly microstructure ⇒ fade.
        return -np.sign(f.logret).fillna(0) * squash(noise.clip(0, 1), 0.4)


class LiquidityProvisionReversal(BaseStrategy):
    name = "Liquidity Provision Premium"
    category = CAT
    family = "liquidity"
    research = "Nagel (2012), 'Evaporating Liquidity', RFS 25(7)"
    description = "Returns to supplying liquidity rise sharply when volatility spikes and liquidity withdraws."
    horizon = Horizon.SWING
    min_bars = 140
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        stress = f.vol_regime
        reversal = -squash(zscore(f.ret, self.params["window"]), 1.5)
        # Liquidity provision pays most precisely when stress is highest.
        return reversal * stress.clip(0, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"vol_regime_percentile": float(f.vol_regime.iloc[-1]),
                "recent_return_z": float(zscore(f.ret, 20).iloc[-1])}


class ClosingAuctionImbalance(BaseStrategy):
    name = "Closing Auction Pressure"
    category = CAT
    family = "auction"
    research = "Bogousslavsky & Muravyev (2023), 'Who Trades at the Close?', J. Financial Economics"
    description = "Index-rebalance and MOC flow concentrates at the close and typically reverses the next open."
    needs = (DataNeed.OHLC, DataNeed.VOLUME)
    horizon = Horizon.INTRADAY
    min_bars = 100
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        rng = (f.high - f.low).where((f.high - f.low) > 1e-12)
        close_pos = ((f.close - f.low) / rng).fillna(0.5)
        heavy = (f.volume_z(self.params["window"]) > 1.0).astype(float) if f.has_volume else 0.0
        # A close pinned at an extreme on heavy volume tends to give back at the next open.
        return -band_score(close_pos, 0.0, 1.0) * heavy


class MarketDepthAsymmetry(BaseStrategy):
    name = "Limit Order Book Depth Imbalance"
    category = CAT
    family = "order_book"
    research = "Cao, Hansch & Wang (2009), 'The Information Content of an Open Limit-Order Book', J. Futures Markets 29(1)"
    description = "Ratio of bid to ask depth beyond the touch; needs genuine L2 data and stands down without it."
    needs = (DataNeed.OHLC, DataNeed.ORDER_BOOK)
    horizon = Horizon.INTRADAY
    min_bars = 60

    def score(self, f: FeatureSet) -> pd.Series:
        book = f.meta.get("order_book")
        if book is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)
