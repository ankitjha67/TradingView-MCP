"""
Mean reversion and short-horizon reversal.

The counterpart to trend: short-horizon returns are negatively autocorrelated
(Jegadeesh 1990; Lehmann 1990), largely as compensation for supplying liquidity.
This is the bread and butter of high-turnover equity market-neutral desks.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import BaseStrategy, DataNeed, Horizon, Regime, band_score, persist, squash
from ..features import FeatureSet, rolling_rank, zscore

CAT = "Mean Reversion"


class BollingerReversion(BaseStrategy):
    name = "Bollinger Band Mean Reversion"
    category = CAT
    family = "bollinger"
    research = "Bollinger (2001), 'Bollinger on Bollinger Bands'"
    description = "Fades price at the standard-deviation envelope, scaled by how far outside the band it trades."
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 60
    params = {"period": 20, "k": 2.0}

    def score(self, f: FeatureSet) -> pd.Series:
        _, _, _, pct_b, _ = f.bollinger(self.params["period"], self.params["k"])
        return -band_score(pct_b, 0.0, 1.0)

    def diagnostics(self, f: FeatureSet) -> dict:
        up, mid, lo, pct_b, bw = f.bollinger(20, 2.0)
        return {"percent_b": float(pct_b.iloc[-1]), "bandwidth": float(bw.iloc[-1]),
                "upper": float(up.iloc[-1]), "lower": float(lo.iloc[-1])}

    def explain(self, f: FeatureSet, v: float, d: dict) -> str:
        b = d.get("percent_b", 0.5)
        where = "above the upper band" if b > 1 else "below the lower band" if b < 0 else "inside the bands"
        return (f"Price is {where} (%b={b:.2f}, bandwidth={d.get('bandwidth', 0):.3f}) → "
                f"{'fade long' if v > 0 else 'fade short' if v < 0 else 'no edge'} at {abs(v):.2f}.")


class RSI2Reversion(BaseStrategy):
    name = "RSI(2) Extreme Reversion"
    category = CAT
    family = "rsi_reversion"
    research = "Connors & Alvarez (2008), 'Short Term Trading Strategies That Work'"
    description = "Very short RSI above a long-trend filter — buys deep oversold dips inside an uptrend."
    regimes = (Regime.RANGING,)
    horizon = Horizon.INTRADAY
    min_bars = 220
    params = {"rsi_period": 2, "trend_period": 200}

    def score(self, f: FeatureSet) -> pd.Series:
        r = f.rsi(self.params["rsi_period"])
        trend = np.sign(f.close - f.sma(self.params["trend_period"]))
        raw = -band_score(r, 0.0, 100.0)
        # Only fade in the direction the long trend permits.
        return raw.where(np.sign(raw) == trend, raw * 0.25)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"rsi2": float(f.rsi(2).iloc[-1]), "sma200": float(f.sma(200).iloc[-1]),
                "above_sma200": bool(f.close.iloc[-1] > f.sma(200).iloc[-1])}


class ConnorsRSI(BaseStrategy):
    name = "Connors RSI Composite"
    category = CAT
    family = "rsi_reversion"
    research = "Connors, Alvarez & Radtke (2012), 'An Introduction to ConnorsRSI'"
    description = "Blends price RSI, a streak-length RSI and a percent-rank of returns into one reversion score."
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 80
    params = {"rsi_p": 3, "streak_p": 2, "rank_p": 100}

    def score(self, f: FeatureSet) -> pd.Series:
        d = np.sign(f.close.diff()).fillna(0).to_numpy()
        streak = np.zeros(len(d))
        for i in range(1, len(d)):
            streak[i] = streak[i - 1] + d[i] if d[i] != 0 and d[i] == np.sign(streak[i - 1]) else d[i]
        streak_s = pd.Series(streak, index=f.close.index)
        streak_rsi = 50 + 50 * np.tanh(streak_s / 3.0)
        rank = rolling_rank(f.ret, self.params["rank_p"]) * 100
        crsi = (f.rsi(self.params["rsi_p"]) + streak_rsi + rank) / 3.0
        return -band_score(crsi, 0.0, 100.0)


class StochasticReversion(BaseStrategy):
    name = "Stochastic Oscillator Reversion"
    category = CAT
    family = "stochastic"
    research = "Lane (1950s); formalised in Lane (1984), Technical Analysis of Stocks & Commodities"
    description = "Position of the close within its recent range; extremes mark exhaustion of the current swing."
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 60
    params = {"period": 14, "smooth": 3}

    def score(self, f: FeatureSet) -> pd.Series:
        k = f.stoch_k(self.params["period"]).rolling(self.params["smooth"], min_periods=1).mean()
        return -band_score(k, 0.0, 100.0)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"stoch_k": float(f.stoch_k(14).iloc[-1])}


class WilliamsRReversion(BaseStrategy):
    name = "Williams %R Reversion"
    category = CAT
    family = "stochastic"
    research = "Williams (1973), 'How I Made One Million Dollars Last Year Trading Commodities'"
    description = "Inverted range position; reads momentum failure at the edge of the recent range."
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 60
    params = {"period": 14}

    def score(self, f: FeatureSet) -> pd.Series:
        return -band_score(f.williams_r(self.params["period"]), -100.0, 0.0)


class CCIReversion(BaseStrategy):
    name = "Commodity Channel Index Reversion"
    category = CAT
    family = "cci"
    research = "Lambert (1980), 'Commodity Channel Index', Commodities magazine"
    description = "Deviation of typical price from its mean in units of mean absolute deviation."
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 60
    params = {"period": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        return -squash(f.cci(self.params["period"]) / 100.0, 1.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"cci": float(f.cci(20).iloc[-1])}


class ZScoreReversion(BaseStrategy):
    name = "Price Z-Score Reversion"
    category = CAT
    family = "zscore"
    research = "Chan (2013), 'Algorithmic Trading: Winning Strategies and Their Rationale', ch. 3"
    description = "Canonical mean-reversion signal: standardised distance of price from its rolling mean."
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 60
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        return -squash(zscore(f.close, self.params["window"]), 1.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"zscore": float(zscore(f.close, 20).iloc[-1]),
                "half_life_bars": float(f.half_life(100).iloc[-1])}


class HalfLifeGatedReversion(BaseStrategy):
    name = "Half-Life Gated Reversion"
    category = CAT
    family = "zscore"
    research = "Ornstein-Uhlenbeck half-life estimation per Chan (2013); OU process from Uhlenbeck & Ornstein (1930)"
    description = "Only fades the mean when the estimated OU half-life is short enough to revert within the holding period."
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 140
    params = {"window": 20, "hl_window": 100, "max_hl": 40}

    def score(self, f: FeatureSet) -> pd.Series:
        z = zscore(f.close, self.params["window"])
        hl = f.half_life(self.params["hl_window"])
        gate = (1.0 - (hl / self.params["max_hl"])).clip(0, 1).fillna(0)
        return -squash(z, 1.5) * gate

    def diagnostics(self, f: FeatureSet) -> dict:
        hl = float(f.half_life(100).iloc[-1])
        return {"half_life_bars": hl, "zscore": float(zscore(f.close, 20).iloc[-1]),
                "reverting": bool(np.isfinite(hl) and hl < 40)}

    def explain(self, f: FeatureSet, v: float, d: dict) -> str:
        hl = d.get("half_life_bars", float("nan"))
        verdict = (f"half-life {hl:.0f} bars — reversion tradeable" if np.isfinite(hl) and hl < 40
                   else "no measurable reversion; signal suppressed")
        return f"Z-score {d.get('zscore', 0):+.2f}, {verdict} → conviction {abs(v):.2f}."


class VWAPReversion(BaseStrategy):
    name = "VWAP Reversion"
    category = CAT
    family = "vwap"
    research = "Berkowitz, Logue & Noser (1988), 'The Total Cost of Transactions on the NYSE', JF 43(1)"
    description = "Fades displacement from volume-weighted average price, the standard institutional execution benchmark."
    needs = (DataNeed.OHLC, DataNeed.VOLUME)
    regimes = (Regime.RANGING,)
    horizon = Horizon.INTRADAY
    min_bars = 60
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        vwap = f.vwap(self.params["window"])
        dev = (f.close - vwap) / f.atr(14).where(f.atr(14) > 1e-12)
        return -squash(dev, 1.2)

    def diagnostics(self, f: FeatureSet) -> dict:
        v = float(f.vwap(20).iloc[-1])
        return {"vwap": v, "deviation_pct": float((f.close.iloc[-1] / v - 1) * 100)}


class ShortTermReversal(BaseStrategy):
    name = "Short-Term Reversal (1-Period)"
    category = CAT
    family = "reversal"
    research = "Jegadeesh (1990), JF 45(3); Lehmann (1990), QJE 105(1)"
    description = "Fades the most recent return — documented negative autocorrelation at the weekly and monthly horizon."
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 80
    params = {"lookback": 5}

    def score(self, f: FeatureSet) -> pd.Series:
        return -squash(zscore(f.close.pct_change(self.params["lookback"]), 60), 1.5)


class LongTermReversal(BaseStrategy):
    name = "Long-Term Reversal (De Bondt-Thaler)"
    category = CAT
    family = "reversal"
    research = "De Bondt & Thaler (1985), 'Does the Stock Market Overreact?', JF 40(3)"
    description = "Fades multi-year extremes — overreaction unwinds at the 3-5 year horizon."
    horizon = Horizon.POSITION
    min_bars = 500
    params = {"lookback": 504}

    def score(self, f: FeatureSet) -> pd.Series:
        return -squash(zscore(f.close.pct_change(self.params["lookback"]), 252), 1.5)


class OvernightGapFade(BaseStrategy):
    name = "Overnight Gap Fade"
    category = CAT
    family = "gap"
    research = "Lou, Polk & Skouras (2019), 'A Tug of War: Overnight vs Intraday Expected Returns', JFE 134(1)"
    description = "Fades the opening gap; overnight and intraday returns are systematically opposed."
    regimes = (Regime.RANGING,)
    horizon = Horizon.INTRADAY
    min_bars = 80
    params = {"z_window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        gap = (f.open - f.close.shift(1)) / f.close.shift(1)
        return -squash(zscore(gap, self.params["z_window"]), 1.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        g = float((f.open.iloc[-1] / f.close.iloc[-2] - 1) * 100) if f.n > 1 else float("nan")
        return {"gap_pct": g}


class OpeningRangeFade(BaseStrategy):
    name = "Opening Range Reversal"
    category = CAT
    family = "gap"
    research = "Crabel (1990), 'Day Trading with Short Term Price Patterns and Opening Range Breakout'"
    description = "Fades an extended move away from the session open when it stalls."
    regimes = (Regime.RANGING,)
    horizon = Horizon.INTRADAY
    min_bars = 60

    def score(self, f: FeatureSet) -> pd.Series:
        excursion = (f.close - f.open) / f.atr(14).where(f.atr(14) > 1e-12)
        stalling = (f.true_range < f.atr(14)).astype(float)
        return -squash(excursion, 1.5) * stalling


class RSIDivergence(BaseStrategy):
    name = "RSI Regular Divergence"
    category = CAT
    family = "divergence"
    research = "Wilder (1978); divergence framework per Murphy (1999), 'Technical Analysis of the Financial Markets'"
    description = "Price makes a new extreme that momentum does not confirm — the classic exhaustion tell."
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 90
    params = {"period": 14, "window": 20, "hold": 6}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        r = f.rsi(self.params["period"])
        px_hi = f.close >= f.close.rolling(w, min_periods=w).max()
        px_lo = f.close <= f.close.rolling(w, min_periods=w).min()
        rsi_lower_hi = r < r.rolling(w, min_periods=w).max()
        rsi_higher_lo = r > r.rolling(w, min_periods=w).min()
        bear = (px_hi & rsi_lower_hi).astype(float)
        bull = (px_lo & rsi_higher_lo).astype(float)
        return persist(bull - bear, self.params["hold"])

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"rsi": float(f.rsi(14).iloc[-1]),
                "at_20bar_high": bool(f.close.iloc[-1] >= f.close.tail(20).max()),
                "at_20bar_low": bool(f.close.iloc[-1] <= f.close.tail(20).min())}


class MFIReversion(BaseStrategy):
    name = "Money Flow Index Reversion"
    category = CAT
    family = "volume_osc"
    research = "Quong & Soudack (1989), 'Volume-Weighted RSI: Money Flow', Technical Analysis of Stocks & Commodities"
    description = "Volume-weighted RSI; distinguishes exhaustion backed by real flow from a drift on thin volume."
    needs = (DataNeed.OHLC, DataNeed.VOLUME)
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 60
    params = {"period": 14}

    def score(self, f: FeatureSet) -> pd.Series:
        return -band_score(f.mfi(self.params["period"]), 0.0, 100.0)


class UltimateOscillator(BaseStrategy):
    name = "Ultimate Oscillator"
    category = CAT
    family = "multi_period_osc"
    research = "Williams (1985), 'The Ultimate Oscillator', Technical Analysis of Stocks & Commodities"
    description = "Weighted blend of three lookbacks, built to avoid the false divergences of single-period oscillators."
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 80
    params = {"p1": 7, "p2": 14, "p3": 28}

    def score(self, f: FeatureSet) -> pd.Series:
        prev_close = f.close.shift(1)
        bp = f.close - pd.concat([f.low, prev_close], axis=1).min(axis=1)
        tr = f.true_range.where(f.true_range > 1e-12)
        avg = lambda p: bp.rolling(p, min_periods=p).sum() / tr.rolling(p, min_periods=p).sum()
        uo = 100 * (4 * avg(self.params["p1"]) + 2 * avg(self.params["p2"]) + avg(self.params["p3"])) / 7
        return -band_score(uo, 0.0, 100.0)


class KeltnerReversion(BaseStrategy):
    name = "Keltner Channel Reversion"
    category = CAT
    family = "channel_reversion"
    research = "Keltner (1960); ATR envelope variant per Chester Keltner / Linda Raschke"
    description = "Fades ATR-envelope excursions — an ATR band is less regime-sensitive than a stdev band."
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 60
    params = {"period": 20, "mult": 2.0}

    def score(self, f: FeatureSet) -> pd.Series:
        up, mid, lo = f.keltner(self.params["period"], 14, self.params["mult"])
        width = (up - lo).where((up - lo) > 1e-12)
        return -squash((f.close - mid) / width * 4, 1.2)


class TDSequentialProxy(BaseStrategy):
    name = "TD Sequential Setup Count"
    category = CAT
    family = "demark"
    research = "DeMark (1994), 'The New Science of Technical Analysis'"
    description = "Counts consecutive closes versus the close four bars prior; a completed 9-count marks exhaustion."
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 60
    params = {"lag": 4, "target": 9}

    def score(self, f: FeatureSet) -> pd.Series:
        lag, target = self.params["lag"], self.params["target"]
        up = (f.close > f.close.shift(lag)).to_numpy()
        dn = (f.close < f.close.shift(lag)).to_numpy()
        cu = cd = 0
        out = np.zeros(f.n)
        for i in range(f.n):
            cu = cu + 1 if up[i] else 0
            cd = cd + 1 if dn[i] else 0
            # A completed buy setup (9 consecutive lower closes) is a long signal.
            out[i] = min(cd, target) / target - min(cu, target) / target
        return pd.Series(out, index=f.close.index)

    def diagnostics(self, f: FeatureSet) -> dict:
        lag = self.params["lag"]
        up = (f.close > f.close.shift(lag)).tail(12).to_numpy()
        run = 0
        for v in reversed(up):
            if v:
                run += 1
            else:
                break
        return {"sell_setup_count": int(run)}


class PairsSpreadReversion(BaseStrategy):
    name = "Pairs Spread Reversion"
    category = CAT
    family = "pairs"
    research = "Gatev, Goetzmann & Rouwenhorst (2006), 'Pairs Trading', RFS 19(3)"
    description = "Z-score of the normalised spread against a matched partner; the canonical relative-value trade."
    needs = (DataNeed.OHLC, DataNeed.CROSS_SECTION)
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 120
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        partner = f.meta.get("pair_close")
        if partner is None:
            return pd.Series(np.nan, index=f.close.index)
        p = pd.Series(partner, index=f.close.index)
        spread = np.log(f.close) - np.log(p.replace(0, np.nan))
        return -squash(zscore(spread, self.params["window"]), 1.5)


class VolatilityCompressionReversion(BaseStrategy):
    name = "Bollinger Squeeze Release"
    category = CAT
    family = "squeeze"
    research = "Bollinger (2001) squeeze; Carter (2005), 'Mastering the Trade' TTM Squeeze"
    description = "Detects Bollinger bands compressing inside Keltner channels, then trades the expansion direction."
    horizon = Horizon.SWING
    min_bars = 90
    params = {"period": 20, "hold": 8}

    def score(self, f: FeatureSet) -> pd.Series:
        bb_up, _, bb_lo, _, _ = f.bollinger(self.params["period"], 2.0)
        kc_up, _, kc_lo = f.keltner(self.params["period"], 14, 1.5)
        squeezed = ((bb_up < kc_up) & (bb_lo > kc_lo))
        # fill_value, not .fillna: shifting a bool Series introduces NaN, which
        # promotes the column to object dtype, and .fillna on object dtype is
        # deprecated (it warns on every scan and changes behaviour in a future
        # pandas). Filling during the shift keeps it boolean throughout.
        released = squeezed.shift(1, fill_value=False) & ~squeezed
        direction = np.sign(f.close - f.sma(self.params["period"]))
        return persist(released.astype(float) * direction, self.params["hold"])

    def diagnostics(self, f: FeatureSet) -> dict:
        bb_up, _, bb_lo, _, bw = f.bollinger(20, 2.0)
        kc_up, _, kc_lo = f.keltner(20, 14, 1.5)
        return {"in_squeeze": bool(bb_up.iloc[-1] < kc_up.iloc[-1] and bb_lo.iloc[-1] > kc_lo.iloc[-1]),
                "bandwidth": float(bw.iloc[-1]),
                "bandwidth_percentile": float(rolling_rank(bw, 120).iloc[-1])}


class ADRExhaustion(BaseStrategy):
    name = "Average Daily Range Exhaustion"
    category = CAT
    family = "range_exhaustion"
    research = "Crabel (1990) range expansion; ATR framework per Wilder (1978)"
    description = "Fades a bar that has already travelled a multiple of its typical range — moves rarely extend indefinitely."
    regimes = (Regime.RANGING,)
    horizon = Horizon.INTRADAY
    min_bars = 60
    params = {"atr_period": 20, "threshold": 1.5}

    def score(self, f: FeatureSet) -> pd.Series:
        travelled = (f.close - f.open) / f.atr(self.params["atr_period"]).where(f.atr(self.params["atr_period"]) > 1e-12)
        excess = travelled.abs() - self.params["threshold"]
        return -np.sign(travelled) * excess.clip(0, 2) / 2.0

    def diagnostics(self, f: FeatureSet) -> dict:
        a = f.atr(20).iloc[-1]
        return {"bar_travel_in_atr": float((f.close.iloc[-1] - f.open.iloc[-1]) / a) if a else float("nan")}


class KurtosisTailReversion(BaseStrategy):
    name = "Fat-Tail Move Reversion"
    category = CAT
    family = "tail_reversion"
    research = "Mandelbrot (1963), 'The Variation of Certain Speculative Prices', J. Business 36(4)"
    description = "Fades returns in the extreme tail of their own distribution, where overreaction is most likely."
    regimes = (Regime.HIGH_VOL,)
    horizon = Horizon.SWING
    min_bars = 120
    params = {"window": 100, "tail_pct": 0.03}

    def score(self, f: FeatureSet) -> pd.Series:
        rank = rolling_rank(f.ret, self.params["window"])
        t = self.params["tail_pct"]
        return pd.Series(np.where(rank < t, 1.0, np.where(rank > 1 - t, -1.0, 0.0)),
                         index=f.close.index) * 0.85

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"return_percentile": float(rolling_rank(f.ret, 100).iloc[-1]),
                "excess_kurtosis": float(f.kurtosis(100).iloc[-1])}


class RangeBoundOscillator(BaseStrategy):
    name = "Range-Bound Channel Oscillator"
    category = CAT
    family = "channel_reversion"
    research = "Donchian channel framework applied to reversion per Kaufman (2013), 'Trading Systems and Methods'"
    description = "Fades the edges of a horizontal channel, gated on the market actually being range-bound."
    regimes = (Regime.RANGING,)
    horizon = Horizon.SWING
    min_bars = 90
    params = {"period": 30, "max_er": 0.35}

    def score(self, f: FeatureSet) -> pd.Series:
        up, mid, lo = f.donchian(self.params["period"])
        pos = (f.close - lo) / (up - lo).where((up - lo) > 1e-12)
        ranging = (1.0 - f.efficiency_ratio(self.params["period"]) / self.params["max_er"]).clip(0, 1)
        return -band_score(pos, 0.0, 1.0) * ranging
