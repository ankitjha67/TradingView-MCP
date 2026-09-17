"""
Replications of catalogue papers the library did not previously cover.

These are the 47 strategies that `tools/find_model_gaps.py` found in the
paperswithbacktest replication catalogue with no counterpart among the existing
311 models.

Two honest statements about what these are.

**They are readings, not replications.** Each implements the mechanism its
paper describes, expressed against this engine's single-instrument bar API. It
is not a reproduction of the paper's own construction, and the ``research``
field says so. A machine-drafted batch was tried first and produced fluent code
with decorative citations — a study of long-run European real-estate allocation
implemented as a rolling z-score of returns — so these are written by hand and
each mechanism is chosen to match what the title actually claims.

**Twenty-three of them cannot run here, and say so.** A size effect needs a
cross-section of stocks; an annuity study needs mortality and liability data; a
portfolio optimisation needs a portfolio. Rather than approximate those from a
single price series — which is precisely the proxy-voting failure this library
was rebuilt to remove — they declare the feed they need and stand down, joining
the 119 models that already do. They are present, cited and inert until the
feed exists.

Every model here passed core/quant/candidate.py: contract, causality,
non-degeneracy, honest needs, evidence, and novelty against every other model
in the library. Two first drafts did not: a Kelly fraction reduced to hit rate
and payoff odds correlated 0.96 with the Sharpe tilt, and a 500-bar return
fade correlated 0.97 with De Bondt-Thaler. Both were renames, and both were
rewritten around the mechanism their paper actually describes — the
multi-outcome log-growth objective, and reversal of the price level that
begins only after continuation ends. tests/unit/quant/test_replications.py
pins those mechanisms.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import (
    BaseStrategy, DataNeed, Horizon, Regime, band_score, persist, squash)
from ..features import FeatureSet, _safe_div, rolling_rank, zscore

CAT_TREND = "Trend & Momentum"
CAT_MR = "Mean Reversion"
CAT_VOL = "Volatility"
CAT_REGIME = "Regime & Risk"
CAT_SEAS = "Seasonality & Calendar"
CAT_STAT = "Statistical Arbitrage"
CAT_MICRO = "Microstructure"
CAT_MACRO = "Macro & Allocation"
CAT_COMM = "Commodity & Carry"
CAT_RATES = "Rates & Credit"
CAT_FACTOR = "Factor & Smart Beta"
CAT_ML = "Machine Learning"
CAT_CRYPTO = "Crypto Native"

_SRC = "paperswithbacktest replication catalogue"


# ══ single-instrument: implementable from one bar series ══════════════════════

class MultiTimeframeTrendAgreement(BaseStrategy):
    name = "Multi-Timeframe Trend Agreement"
    category = CAT_TREND
    family = "mtf_agreement"
    research = ("Vojtko & Mesicek (2025), 'How to Design a Simple Multi-Timeframe "
                "Trend Strategy on Bitcoin'. Single-instrument reading; the paper's "
                f"own page reports Sharpe 0.81 over 16 years, against 3.39 in the {_SRC}.")
    description = ("Counts how many of three horizons agree on direction; conviction "
                   "is the depth of agreement, not the strength of any one trend.")
    horizon = Horizon.SWING
    min_bars = 260
    params = {"fast": 20, "mid": 60, "slow": 200}

    def score(self, f: FeatureSet) -> pd.Series:
        c = f.close
        votes = sum(np.sign(c - f.sma(self.params[k])) for k in ("fast", "mid", "slow"))
        # Three horizons agreeing is a different claim from one trending hard.
        return squash(votes / 3.0, 0.6)

    def diagnostics(self, f: FeatureSet) -> dict:
        c = float(f.close.iloc[-1])
        return {f"above_sma_{self.params[k]}": bool(c > float(f.sma(self.params[k]).iloc[-1]))
                for k in ("fast", "mid", "slow")}


class GoodCarryBadCarry(BaseStrategy):
    name = "Good Carry vs Bad Carry"
    category = CAT_COMM
    family = "carry_quality"
    research = ("Koijen, Moskowitz, Pedersen & Vrugt style carry decomposition, per "
                "'Good Carry, Bad Carry'. Single-instrument reading: carry is proxied "
                "by drift per unit of risk, and penalised when that risk is rising.")
    description = ("Separates carry earned in calm conditions from carry earned into "
                   "rising volatility — the second kind is compensation for a coming loss.")
    horizon = Horizon.SWING
    min_bars = 180
    params = {"drift": 60, "vol": 20, "vol_trend": 40}

    def score(self, f: FeatureSet) -> pd.Series:
        drift = f.close.pct_change(self.params["drift"])
        vol = f.realized_vol(self.params["vol"])
        carry = _safe_div(drift, vol.where(vol > 1e-9))
        # Bad carry: the same drift while volatility is climbing.
        vol_rising = zscore(vol, self.params["vol_trend"]).clip(-2, 2)
        quality = (1.0 - (vol_rising.clip(lower=0) / 2.0)).clip(0.0, 1.0)
        return squash(carry * quality, 1.2)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"drift_60b_pct": float(f.close.pct_change(60).iloc[-1] * 100),
                "realized_vol_pct": float(f.realized_vol(20).iloc[-1] * 100),
                "vol_zscore": float(zscore(f.realized_vol(20), 40).iloc[-1])}


class KellyMultiOutcomeFraction(BaseStrategy):
    name = "Kelly Fraction (Multiple Outcomes)"
    category = CAT_REGIME
    family = "kelly_sizing"
    research = ("Analytical Kelly for multiple outcomes. Reading: the trailing "
                "window's realised returns are the outcome distribution, and the "
                "fraction is the one that maximises expected log growth over it. "
                "That is the multi-outcome objective itself; its two-outcome "
                "reduction to hit rate and payoff odds collapses to a mean-variance "
                "ratio and says nothing a Sharpe tilt does not.")
    description = ("Growth-optimal fraction from maximising mean log wealth over the "
                   "realised outcome distribution, long or short; the worst outcome "
                   "in the window bounds it where a variance ratio would not.")
    horizon = Horizon.SWING
    min_bars = 300
    # The grid runs far past any fraction a sane book would hold so that it
    # is the worst outcome in the window, not the grid edge, that bounds
    # the answer. Capping at a few turns of leverage pins the fraction to
    # the cap and leaves only the sign of the mean, which is a momentum
    # filter under another name.
    params = {"window": 250, "max_leverage": 20.0, "grid": 81}

    def _growth(self, f: FeatureSet):
        """Mean log wealth per bar for every fraction on the grid, per bar."""
        w = self.params["window"]
        lev = self.params["max_leverage"]
        fracs = np.linspace(-lev, lev, self.params["grid"])
        r = f.ret.to_numpy(dtype=float)
        # Wealth after one outcome at each fraction. Wealth at or below zero is
        # ruin; the floor turns it into a log penalty large enough that one such
        # outcome in the window rules the fraction out, which is the point.
        wealth = 1.0 + np.outer(r, fracs)
        g = np.log(np.clip(wealth, 1e-3, None))
        table = pd.DataFrame(g, index=f.close.index)
        return fracs, table.rolling(w, min_periods=w // 2).mean()

    def score(self, f: FeatureSet) -> pd.Series:
        fracs, growth = self._growth(f)
        vals = growth.to_numpy()
        seen = np.isfinite(vals).any(axis=1)
        filled = np.where(np.isfinite(vals), vals, -np.inf)
        best = fracs[np.argmax(filled, axis=1)]
        # Growth at f=0 is exactly zero, so a maximum at or below zero means no
        # fraction beats not betting.
        kelly = np.where(filled.max(axis=1) > 1e-12, best, 0.0)
        kelly = np.where(seen, kelly, np.nan)
        # Full Kelly on daily equity outcomes sits around 2-8x; scale so
        # that range spreads across the middle of the response.
        return squash(pd.Series(kelly, index=f.close.index),
                      self.params["max_leverage"] / 4)

    def diagnostics(self, f: FeatureSet) -> dict:
        fracs, growth = self._growth(f)
        last = growth.iloc[-1].to_numpy()
        if not np.isfinite(last).any():
            return {}
        i = int(np.nanargmax(last))
        return {"kelly_fraction": float(fracs[i]),
                "log_growth_per_bar": float(last[i]),
                "worst_outcome": float(f.ret.tail(self.params["window"]).min())}


class FilterRuleEvolution(BaseStrategy):
    name = "Filter Rule with Confirmation Delay"
    category = CAT_TREND
    family = "filter_rule"
    research = ("Neely, Weller & Dittmar lineage, per 'Lessons from the Evolution of "
                "Foreign Exchange Trading Strategies'. The lesson is that naive filter "
                "rules decayed once crowded; this adds the confirmation delay that survived.")
    description = ("Breakout of a price filter band, taken only after the move holds "
                   "for a confirmation period.")
    horizon = Horizon.SWING
    min_bars = 200
    params = {"filter_pct": 0.02, "confirm": 3, "hold": 10}

    def score(self, f: FeatureSet) -> pd.Series:
        c = f.close
        ref = c.rolling(40, min_periods=20).mean()
        band = self.params["filter_pct"]
        raw = np.sign((c / ref - 1.0).where((c / ref - 1.0).abs() > band, 0.0))
        # The naive rule fires on the first touch; the survivor waits.
        held = raw.rolling(self.params["confirm"], min_periods=self.params["confirm"]).sum()
        confirmed = np.sign(held.where(held.abs() >= self.params["confirm"], 0.0))
        return persist(squash(confirmed, 0.9), self.params["hold"])


class CrashHeuristicRobustness(BaseStrategy):
    name = "Crash-Robust Heuristic Exposure"
    category = CAT_REGIME
    family = "crash_heuristic"
    research = ("'Are Heuristics Better than Theory if Market Crashes Are Possible' — "
                "simple rules beat optimisation when tails matter. Reading: hold "
                "exposure only while tail conditions are quiet.")
    description = ("A deliberately crude rule — full exposure in calm tails, none in "
                   "fat ones — on the finding that simplicity survives crashes better "
                   "than fitted optimisation.")
    horizon = Horizon.SWING
    min_bars = 200
    params = {"window": 90, "kurt_limit": 4.0}

    def score(self, f: FeatureSet) -> pd.Series:
        k = f.kurtosis(self.params["window"])
        dd = f.drawdown()
        calm = (k < self.params["kurt_limit"]) & (dd > -0.15)
        trend = np.sign(f.close - f.sma(100))
        return squash(trend * calm.astype(float), 0.7)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"excess_kurtosis": float(f.kurtosis(90).iloc[-1]),
                "drawdown_pct": float(f.drawdown().iloc[-1] * 100)}


class RegimeAwareConcentratedRisk(BaseStrategy):
    name = "Regime-Aware Concentration Risk"
    category = CAT_REGIME
    family = "concentration_regime"
    research = ("'Regime-Aware Risk Management in Concentrated Equity Portfolios: "
                "Evidence from the Magnificent Seven'. Reading: scale exposure by the "
                "stability of the volatility regime rather than its level.")
    description = ("Concentration is survivable while the volatility regime is stable; "
                   "exposure is cut when the regime itself starts moving.")
    horizon = Horizon.SWING
    min_bars = 200
    params = {"vol": 20, "stability": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        vol = f.realized_vol(self.params["vol"])
        # Volatility of volatility: the regime shifting, not the level.
        vov = vol.pct_change().rolling(self.params["stability"],
                                       min_periods=20).std(ddof=0)
        calm = 1.0 - rolling_rank(vov, 120)
        return squash(np.sign(f.close - f.ema(50)) * calm, 0.55)


class CryptoHodlFodlFactor(BaseStrategy):
    name = "Crypto Hodl/Fodl Factor Composite"
    category = CAT_CRYPTO
    family = "crypto_factor_composite"
    research = ("'Know When to Hodl Em, Know When to Fodl Em': factor structure in "
                "crypto. Reading: the paper's momentum and low-volatility legs, "
                "combined on a single series.")
    description = ("Holds when medium-horizon momentum is positive and volatility sits "
                   "below its own history; folds when either fails.")
    horizon = Horizon.SWING
    min_bars = 200
    params = {"mom": 60, "vol": 30}

    def score(self, f: FeatureSet) -> pd.Series:
        mom = zscore(f.close.pct_change(self.params["mom"]), 120)
        low_vol = 1.0 - rolling_rank(f.realized_vol(self.params["vol"]), 120)
        return squash(mom * (0.4 + 0.6 * low_vol), 1.4)


class WhitenedResidualSignal(BaseStrategy):
    name = "Whitened Return Residual"
    category = CAT_STAT
    family = "whitened_residual"
    research = ("'Statistical and Economic Benefits of Whitening Residuals in Bond "
                "Yields'. Reading: remove the autocorrelated component and trade what "
                "is left, which is the part not already priced.")
    description = ("Strips the AR(1) component from returns and trades the residual — "
                   "the innovation rather than the persistence.")
    horizon = Horizon.INTRADAY
    min_bars = 200
    params = {"window": 80}

    def score(self, f: FeatureSet) -> pd.Series:
        r = f.logret
        w = self.params["window"]
        lag = r.shift(1)
        cov = (r * lag).rolling(w, min_periods=w // 2).mean()
        var = (lag ** 2).rolling(w, min_periods=w // 2).mean()
        phi = _safe_div(cov, var.where(var > 1e-14)).clip(-0.95, 0.95)
        resid = r - phi * lag
        return -squash(zscore(resid, 40), 1.6)

    def diagnostics(self, f: FeatureSet) -> dict:
        r = f.logret
        lag = r.shift(1)
        cov = (r * lag).rolling(80, min_periods=40).mean()
        var = (lag ** 2).rolling(80, min_periods=40).mean()
        return {"ar1_phi": float(_safe_div(cov, var).iloc[-1])}


class BitcoinSeasonalTrendMR(BaseStrategy):
    name = "Seasonality, Trend and Reversion Blend"
    category = CAT_SEAS
    family = "seasonal_trend_blend"
    research = ("'Seasonality, Trend-following, and Mean reversion in Bitcoin' — the "
                "paper's point is that the three coexist and must be weighted by "
                "horizon rather than chosen between.")
    description = ("Blends a weekday effect, medium-horizon trend and short-horizon "
                   "reversion, each on the horizon where it was found to work.")
    horizon = Horizon.SWING
    min_bars = 200
    params = {"trend": 50, "revert": 5}

    def score(self, f: FeatureSet) -> pd.Series:
        idx = f.close.index
        weekday = (pd.Series(idx.dayofweek, index=idx)
                   if isinstance(idx, pd.DatetimeIndex) else pd.Series(0, index=idx))
        seasonal = ((weekday == 0).astype(float) - (weekday == 4).astype(float)) * 0.3
        trend = np.sign(f.close - f.sma(self.params["trend"])) * 0.4
        revert = -zscore(f.close.pct_change(self.params["revert"]), 40).clip(-2, 2) * 0.15
        return squash(seasonal + trend + revert, 0.8)


class LongRunRealEstateMomentum(BaseStrategy):
    name = "Long-Horizon Momentum with Drawdown Brake"
    category = CAT_MACRO
    family = "longrun_momentum"
    research = ("Fugazza, Guidolin & Nicodano (2006), 'Investing for the Long-Run in "
                "European Real Estate'. Reading: the long-horizon allocation case, "
                "with the drawdown condition that makes it survivable.")
    description = ("Twelve-month momentum, released only while the instrument is not "
                   "deep in drawdown — the long-run case fails precisely when held "
                   "through the deepest part.")
    horizon = Horizon.POSITION
    min_bars = 300
    params = {"lookback": 250, "dd_limit": -0.25}

    def score(self, f: FeatureSet) -> pd.Series:
        mom = f.close.pct_change(self.params["lookback"])
        brake = (f.drawdown() > self.params["dd_limit"]).astype(float)
        return squash(np.sign(mom) * brake * mom.abs().clip(0, 0.6) / 0.6, 0.8)


class RiskAwareYieldSearch(BaseStrategy):
    name = "Risk-Aware Yield Search"
    category = CAT_RATES
    family = "yield_search"
    research = ("'Dynamic Risk-Aware Yield Search: A Useful Tool for Fixed Income "
                "Investors'. Reading: reach for yield only where the risk taken to "
                "get it is falling, not rising.")
    description = ("Drift per unit of downside deviation, gated on that downside "
                   "measure improving rather than deteriorating.")
    horizon = Horizon.SWING
    min_bars = 200
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        r = f.logret
        down = r.where(r < 0, 0.0).rolling(w, min_periods=w // 2).std(ddof=0)
        drift = r.rolling(w, min_periods=w // 2).mean()
        yield_ = _safe_div(drift, down.where(down > 1e-12))
        improving = (down < down.shift(w // 3)).astype(float)
        return squash(yield_ * (0.3 + 0.7 * improving), 1.5)


class RiskPreferenceMomentum(BaseStrategy):
    name = "Skew-Conditioned Momentum"
    category = CAT_CRYPTO
    family = "skew_momentum"
    research = ("'Do Risk Preferences Drive Momentum in Cryptocurrencies?' — momentum "
                "attributed to lottery preference. Reading: condition momentum on "
                "realised skew, its observable footprint.")
    description = ("Momentum taken only where realised skew is not lottery-like; the "
                   "paper attributes the premium to preference for positive skew.")
    horizon = Horizon.SWING
    min_bars = 220
    params = {"mom": 40, "skew": 90}

    def score(self, f: FeatureSet) -> pd.Series:
        mom = np.sign(f.close.pct_change(self.params["mom"]))
        sk = f.skew(self.params["skew"])
        # Lottery-like (strongly positive skew) is where the premium is paid away.
        temper = (1.0 - rolling_rank(sk, 120)).clip(0.0, 1.0)
        return squash(mom * temper, 0.7)


class StalePricingLag(BaseStrategy):
    name = "Stale Pricing Autocorrelation"
    category = CAT_MICRO
    family = "stale_pricing"
    research = ("'Sitting Bucks: Stale Pricing in Fixed Income Funds'. Reading: stale "
                "marks show up as return autocorrelation, and the lag is tradeable "
                "until the mark catches up.")
    description = ("Measures return autocorrelation as a staleness proxy and leans "
                   "with the lag while it persists.")
    horizon = Horizon.INTRADAY
    min_bars = 180
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        r = f.logret
        w = self.params["window"]
        lag = r.shift(1)
        rho = (r * lag).rolling(w, min_periods=w // 2).mean()
        norm = (r.rolling(w, min_periods=w // 2).std(ddof=0) ** 2)
        ac = _safe_div(rho, norm.where(norm > 1e-14)).clip(-1, 1)
        # Positive autocorrelation means yesterday's move is still arriving.
        return squash(ac * np.sign(lag), 0.5)


class LongRunCommodityReversal(BaseStrategy):
    name = "Multi-Year Commodity Reversal"
    category = CAT_COMM
    family = "longrun_reversal"
    research = ("'Long-Run Reversal in Commodity Returns: Insights from Seven "
                "Centuries of Evidence'. Reading: what reverts is the price level, "
                "toward its long-run mean, and it does so only after the "
                "continuation phase has run its course. So the model fades the "
                "excursion from a multi-year anchor, and only once the trailing "
                "year is already moving back toward it.")
    description = ("Excursion of price from its multi-year mean, faded only after the "
                   "past year has begun to close it. No point-to-point past return "
                   "is used, which is what separates it from the 3-5 year "
                   "overreaction fade.")
    horizon = Horizon.POSITION
    min_bars = 640
    params = {"anchor": 750, "norm": 250, "turn": 250}

    def score(self, f: FeatureSet) -> pd.Series:
        a, nw, tw = (self.params[k] for k in ("anchor", "norm", "turn"))
        lp = np.log(f.close.where(f.close > 0))
        anchor = lp.rolling(a, min_periods=a // 2).mean()
        excursion = lp - anchor
        spread = excursion.rolling(nw, min_periods=nw // 2).std(ddof=0)
        stretch = excursion / spread.where(spread > 1e-9)
        # Reversal follows continuation; until the past year has turned back
        # toward the anchor there is nothing to fade yet.
        year_move = lp - lp.shift(tw)
        turned = (np.sign(year_move) == -np.sign(excursion)) & (excursion != 0)
        fade = -squash(stretch, 1.5)
        return fade.where(turned, 0.0).where(stretch.notna())


class BettingPatternStreakFade(BaseStrategy):
    name = "Post-Streak Overbetting Fade"
    category = CAT_MR
    family = "streak_overbet"
    research = ("'Rational Decision-Making Under Uncertainty: Observed Betting "
                "Patterns on a Biased Coin' — participants over-bet after runs. "
                "Reading: fade the extension that follows a streak.")
    description = ("Counts consecutive same-direction bars and fades the extension, "
                   "on the finding that bet size rises irrationally after a run.")
    horizon = Horizon.INTRADAY
    min_bars = 150
    params = {"max_streak": 5}

    def score(self, f: FeatureSet) -> pd.Series:
        sign = np.sign(f.logret).fillna(0.0)
        same = (sign == sign.shift(1)).astype(int)
        # Length of the current run, capped where over-betting is documented.
        streak = same.groupby((same == 0).cumsum()).cumsum().clip(0, self.params["max_streak"])
        return squash(-sign * streak / self.params["max_streak"], 0.7)


class LotteryPreferenceFade(BaseStrategy):
    name = "Lottery-Preference Payoff Fade"
    category = CAT_FACTOR
    family = "lottery_fade"
    research = ("'Can Financial Innovation Succeed by Catering to Behavioral "
                "Preferences? Evidence from a Callable Options Market'. Reading: "
                "products catering to lottery preference are overpriced; fade the "
                "lottery-like payoff profile.")
    description = ("Fades periods whose recent payoff shape is lottery-like — rare "
                   "large gains against frequent small losses.")
    horizon = Horizon.SWING
    min_bars = 200
    params = {"window": 90}

    def score(self, f: FeatureSet) -> pd.Series:
        r = f.logret
        w = self.params["window"]
        sk = f.skew(w)
        hit = (r > 0).rolling(w, min_periods=w // 2).mean()
        # Lottery: positive skew with a low hit rate.
        lottery = rolling_rank(sk, 120) * (1.0 - hit)
        return -squash(zscore(lottery, 60), 1.4)


class CryptoOverreactionReversal(BaseStrategy):
    name = "Overreaction Reversal (Extreme Bars)"
    category = CAT_MR
    family = "overreaction"
    research = ("'Price Overreactions in the Cryptocurrency Market'. Reading: the "
                "paper's event definition — a move beyond a rolling threshold — and "
                "the reversal that follows it.")
    description = ("Identifies bars beyond a rolling volatility threshold and takes "
                   "the documented next-period reversal.")
    horizon = Horizon.INTRADAY
    min_bars = 160
    params = {"threshold": 2.5, "window": 60, "hold": 3}

    def score(self, f: FeatureSet) -> pd.Series:
        z = zscore(f.logret, self.params["window"])
        extreme = z.abs() > self.params["threshold"]
        return persist(squash(-np.sign(z) * extreme.astype(float), 0.6),
                       self.params["hold"])


class ModelDisagreementCaution(BaseStrategy):
    name = "Model Disagreement Caution"
    category = CAT_ML
    family = "model_disagreement"
    research = ("'A Theory of Model Sophistication and Operational Risk' — more "
                "sophisticated models carry more operational risk. Reading: when "
                "estimators of the same quantity disagree, trust the reading less.")
    description = ("Compares three volatility estimators of the same series; wide "
                   "disagreement between them is treated as model risk and cuts "
                   "conviction rather than setting direction.")
    horizon = Horizon.SWING
    min_bars = 200
    params = {"window": 20}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        a, b, c = f.parkinson_vol(w), f.garman_klass_vol(w), f.rogers_satchell_vol(w)
        stack = pd.concat([a, b, c], axis=1)
        spread = _safe_div(stack.std(axis=1, ddof=0), stack.mean(axis=1).abs())
        agreement = (1.0 - rolling_rank(spread, 120)).clip(0.0, 1.0)
        return squash(np.sign(f.close - f.ema(40)) * agreement, 0.55)

    def diagnostics(self, f: FeatureSet) -> dict:
        w = self.params["window"]
        return {"parkinson": float(f.parkinson_vol(w).iloc[-1]),
                "garman_klass": float(f.garman_klass_vol(w).iloc[-1]),
                "rogers_satchell": float(f.rogers_satchell_vol(w).iloc[-1])}


class PricedTailRiskPremium(BaseStrategy):
    name = "Priced Tail Risk Premium"
    category = CAT_RATES
    family = "priced_tail_risk"
    research = ("'Priced risk in corporate bonds' — compensation attaches to tail "
                "exposure rather than variance. Reading: separate downside from total "
                "risk and require the compensation to be for the former.")
    description = ("Drift measured against downside deviation only, on the finding "
                   "that variance is not what is compensated.")
    horizon = Horizon.SWING
    min_bars = 200
    params = {"window": 80}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        r = f.logret
        total = r.rolling(w, min_periods=w // 2).std(ddof=0)
        down = r.where(r < 0, 0.0).rolling(w, min_periods=w // 2).std(ddof=0)
        # Where downside is a small share of total risk, the tail is cheap.
        share = _safe_div(down, total.where(total > 1e-12))
        cheap = (1.0 - rolling_rank(share, 120))
        drift = r.rolling(w, min_periods=w // 2).mean()
        return squash(np.sign(drift) * cheap, 0.6)


class TransactionalDemandProxy(BaseStrategy):
    name = "Transactional Demand Proxy"
    category = CAT_CRYPTO
    family = "transactional_demand"
    research = ("'Cryptocurrency as money: A trading strategy solution' — value as a "
                "medium of exchange rather than a store. Reading: turnover relative "
                "to volatility as an observable proxy for transactional use.")
    description = ("Rising turnover against steady volatility suggests use rather than "
                   "speculation; the paper ties that to subsequent strength.")
    horizon = Horizon.SWING
    min_bars = 180
    needs = (DataNeed.OHLC, DataNeed.VOLUME)
    params = {"window": 40}

    def score(self, f: FeatureSet) -> pd.Series:
        if not f.has_volume:
            return pd.Series(0.0, index=f.close.index)
        turnover = f.volume_z(self.params["window"])
        vol = zscore(f.realized_vol(20), 90)
        # Volume up without volatility up: use, not speculation.
        return squash(turnover - vol, 1.6)


class TermTransformationSlope(BaseStrategy):
    name = "Term Transformation Slope Proxy"
    category = CAT_RATES
    family = "term_slope"
    research = ("'Banks' exposure to interest rate risk, their earnings from term "
                "transformation, and the dynamics of the term structure'. Reading: "
                "the slope proxied by the gap between long- and short-horizon drift.")
    description = ("Long-horizon drift minus short-horizon drift as a term-structure "
                   "slope proxy — the shape banks earn from, not the level.")
    horizon = Horizon.SWING
    min_bars = 300
    params = {"short": 20, "long": 200}

    def score(self, f: FeatureSet) -> pd.Series:
        short_d = f.logret.rolling(self.params["short"], min_periods=10).mean()
        long_d = f.logret.rolling(self.params["long"], min_periods=60).mean()
        slope = long_d - short_d
        return squash(zscore(slope, 120), 1.3)


class ReturnClusteringRegime(BaseStrategy):
    name = "Return Clustering Regime Detector"
    category = CAT_REGIME
    family = "return_clustering"
    research = ("'Proof-of-What? Detecting original consensus algorithms in "
                "cryptocurrencies with a four-factor model'. Reading: the detection "
                "problem — distinguishing regimes from return structure alone.")
    description = ("Detects whether returns are clustering (persistent regime) or "
                   "dispersing, and takes direction only in the persistent state.")
    horizon = Horizon.SWING
    min_bars = 220
    params = {"window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        w = self.params["window"]
        absr = f.logret.abs()
        # Volatility clustering: today's magnitude predicting tomorrow's.
        clust = absr.rolling(w, min_periods=w // 2).corr(absr.shift(1)).clip(-1, 1)
        persistent = rolling_rank(clust, 120)
        return squash(np.sign(f.close - f.ema(60)) * persistent, 0.6)


class InterventionConditionedTrend(BaseStrategy):
    name = "Intervention-Conditioned Trend"
    category = CAT_TREND
    family = "intervention_trend"
    research = ("'The Temporal Pattern of Trading Rule Returns and Central Bank "
                "Intervention' — the finding is that rule profits are NOT generated "
                "by intervention. Reading: suppress the rule around intervention-like "
                "volatility spikes, where the profit is not.")
    description = ("A trend rule that stands aside during intervention-like volatility "
                   "spikes, on the finding that its returns do not come from them.")
    horizon = Horizon.SWING
    min_bars = 200
    params = {"spike_z": 2.0, "window": 60}

    def score(self, f: FeatureSet) -> pd.Series:
        spike = zscore(f.true_range, self.params["window"]).abs() > self.params["spike_z"]
        quiet = (~spike).astype(float)
        return squash(np.sign(f.close - f.sma(60)) * quiet, 0.65)


class IntrabarRangeReversion(BaseStrategy):
    name = "Intrabar Range Reversion"
    category = CAT_MICRO
    family = "intrabar_reversion"
    research = ("'Arbitrage in the Foreign Exchange Market: Turning on the "
                "Microscope' — deviations exist but are small and short-lived. "
                "Reading: close position within the bar's own range as the deviation.")
    description = ("Measures where the close sits inside the bar range and fades the "
                   "extremes — the short-lived deviation the microscope finds.")
    horizon = Horizon.INTRADAY
    min_bars = 150
    params = {"smooth": 5}

    def score(self, f: FeatureSet) -> pd.Series:
        rng = (f.high - f.low)
        pos = _safe_div(f.close - f.low, rng.where(rng > 1e-12)) - 0.5
        return -squash(pos.rolling(self.params["smooth"], min_periods=1).mean(), 0.35)


# ══ present, cited, and honestly unavailable ══════════════════════════════════
#
# Each of these needs a feed this engine does not carry. They declare it and
# stand down rather than approximating it from a single price series. That is
# the same contract the existing 119 unavailable models honour, and it is why
# the consensus line reads "N voting of M available of 311 in library" rather
# than claiming everything agrees.

class _Unavailable(BaseStrategy):
    """Shared shape: declares a feed, and returns nothing until it exists."""
    horizon = Horizon.POSITION
    min_bars = 60

    def score(self, f: FeatureSet) -> pd.Series:
        return pd.Series(0.0, index=f.close.index)


def _cross_sectional(cls_name, title, cite, desc, cat=CAT_FACTOR, fam=None):
    return type(cls_name, (_Unavailable,), {
        "name": title, "category": cat, "family": fam or cls_name.lower(),
        "research": cite, "description": desc,
        "needs": (DataNeed.OHLC, DataNeed.CROSS_SECTION),
    })


def _fundamental(cls_name, title, cite, desc, cat=CAT_MACRO, fam=None):
    return type(cls_name, (_Unavailable,), {
        "name": title, "category": cat, "family": fam or cls_name.lower(),
        "research": cite, "description": desc,
        "needs": (DataNeed.OHLC, DataNeed.FUNDAMENTALS),
    })


def _news_driven(cls_name, title, cite, desc, cat="Sentiment & Alt Data", fam=None):
    return type(cls_name, (_Unavailable,), {
        "name": title, "category": cat, "family": fam or cls_name.lower(),
        "research": cite, "description": desc,
        "needs": (DataNeed.OHLC, DataNeed.NEWS),
    })


# — need a cross-section of instruments —
GermanEquityDataQuality = _cross_sectional(
    "GermanEquityDataQuality", "Data-Quality Adjusted Cross-Section",
    "Important Characteristics, Weaknesses and Errors in German Equity Data from Thomson",
    "Cross-sectional returns after correcting known vendor data errors. Needs a peer "
    "universe and its data-quality flags; not derivable from one price series.")

BetaSizeCrossSection = _cross_sectional(
    "BetaSizeCrossSection", "Beta and Size Cross-Section (Europe)",
    "The Role of Beta and Size in the Cross-Section of European Stock Returns",
    "Sorts on beta and market capitalisation. Both are relative measures and need "
    "the universe they are relative to.")

MLImpliedRiskPremia = _cross_sectional(
    "MLImpliedRiskPremia", "Machine-Learning Implied Risk Premia",
    "Diverging roads: Theory-based vs. machine learning-implied stock risk premia",
    "Compares theory-based and ML-implied premia across a panel of stocks. Needs the "
    "panel.", cat=CAT_ML)

ValueSizeInstability = _cross_sectional(
    "ValueSizeInstability", "Value and Size Effect Instability",
    "Value and Size Effect: Now You See It, Now You Don't",
    "The point of the paper is that the cross-sectional premia appear and disappear "
    "by sub-period. Needs the cross-section to measure at all.")

MostDiversifiedPortfolio = _cross_sectional(
    "MostDiversifiedPortfolio", "Most Diversified Portfolio",
    "Properties of the Most Diversified Portfolio",
    "Maximises the diversification ratio across holdings. A portfolio construction, "
    "not a signal on one instrument.", cat=CAT_MACRO)

AbnormalReturnVariation = _cross_sectional(
    "AbnormalReturnVariation", "Systematic Abnormal Return Variation",
    "Systematic Abnormal Return Variation and Global Market Inefficiencies",
    "Measures abnormal return dispersion across a global universe as an inefficiency "
    "proxy. Dispersion needs more than one series.")

SizeEffectFactFiction = _cross_sectional(
    "SizeEffectFactFiction", "Size Effect After Controls",
    "Fact, Fiction, and the Size Effect",
    "Re-examines the size premium once quality and other controls are applied. Needs "
    "the cross-section and the control factors.")

EndToEndVarianceMinimization = _cross_sectional(
    "EndToEndVarianceMinimization", "End-to-End Variance Minimisation",
    "End-To-End Large Portfolio Optimization For Variance Minimization With Neural "
    "Networks Through Covariance Cleaning",
    "Cleans a large covariance matrix and optimises against it. Requires a covariance "
    "matrix, which requires many assets.", cat=CAT_ML)

VaRAdjustedSharpeOptimization = _cross_sectional(
    "VaRAdjustedSharpeOptimization", "VaR-Adjusted Sharpe Optimisation",
    "Robust Portfolio Optimization with Value-At-Risk Adjusted Sharpe Ratios",
    "Portfolio weights optimised on a VaR-adjusted objective. Portfolio-level by "
    "construction.", cat=CAT_MACRO)

CorporateBondFactorInvesting = _cross_sectional(
    "CorporateBondFactorInvesting", "Corporate Bond Factor Investing",
    "Out-performing corporate bonds indices with factor investing",
    "Factor sorts across a corporate bond universe against its index. Needs both.",
    cat=CAT_RATES)

FrontierGovernmentBonds = _cross_sectional(
    "FrontierGovernmentBonds", "Frontier and Emerging Government Bonds",
    "Frontier and Emerging Government Bond Markets",
    "Relative value across sovereign issuers. Needs the issuer cross-section.",
    cat=CAT_RATES)

HMMRegimeBondPortfolio = _cross_sectional(
    "HMMRegimeBondPortfolio", "HMM Regime Bond Portfolio",
    "Regime-based portfolio optimisation: A Hidden Markov Model approach for fixed "
    "income portfolios",
    "Allocates across fixed-income sleeves by inferred regime. The regime is "
    "estimable on one series; the allocation is not.", cat=CAT_RATES)

BlockchainRiskParity = _cross_sectional(
    "BlockchainRiskParity", "Blockchain Risk Parity Line",
    "The Blockchain Risk Parity Line: Moving From The Efficient Frontier To The Final "
    "Frontier Of Investments",
    "Risk-parity weights across crypto assets. Needs the asset set to weight.",
    cat=CAT_CRYPTO)

# — need data that is not a price series —
OptimalAnnuityRisk = _fundamental(
    "OptimalAnnuityRisk", "Optimal Annuity Risk Management",
    "Optimal Annuity Risk Management",
    "Optimises annuitisation against mortality and liability risk. Needs actuarial "
    "inputs; there is no price series that stands in for them.")

AnnuityDemandPuzzle = _fundamental(
    "AnnuityDemandPuzzle", "Annuity Demand Portfolio Application",
    "Explaining low annuity demand: an optimal portfolio application to Japan",
    "Household portfolio choice including annuities. Requires household balance-sheet "
    "and longevity data.")

InconsistentConsumption = _fundamental(
    "InconsistentConsumption", "Time-Inconsistent Consumption Allocation",
    "Inconsistent investment and consumption problems",
    "Allocation under time-inconsistent preferences with a consumption stream. Needs "
    "the consumption side.")

LaborIncomeHeuristics = _fundamental(
    "LaborIncomeHeuristics", "Portfolio Rules with Labour Income",
    "Heuristic Portfolio Rules with Labor Income",
    "Allocation conditioned on human capital. Labour income is not observable in "
    "market data.")

SovereignAuctionEffects = _fundamental(
    "SovereignAuctionEffects", "Sovereign Debt Auction Effects",
    "Price Effects of Sovereign Debt Auctions in the Euro-zone: The Role of the Crisis",
    "Trades the auction calendar. Needs the issuance schedule, which is not in the "
    "bar series.", cat=CAT_RATES)

RealTimeMacroBondPrediction = _fundamental(
    "RealTimeMacroBondPrediction", "Real-Time Macro Bond Prediction",
    "Are Bond Returns Predictable with Real-Time Macro Data?",
    "The paper's whole point is the real-time vintage of macro releases, including "
    "revisions. Needs the vintage data.", cat=CAT_RATES)

MediaToneViral = _news_driven(
    "MediaToneViral", "Media Tone Propagation",
    "Media Tone Goes Viral: Global Evidence from the Currency Market",
    "Trades the spread of news tone across markets. Needs a news feed with timestamps "
    "and coverage.")

MediaToneTimeSeries = _news_driven(
    "MediaToneTimeSeries", "Media Tone Time-Series and Cross-Section",
    "Is Media Tone just a Tone? Time-Series and Cross-Sectional Evidence from the "
    "Currency Market",
    "Separates the time-series from the cross-sectional component of news tone. Needs "
    "both a news feed and a currency cross-section.")

# — portfolio-level —
CoveredCallClosedEndFund = _cross_sectional(
    "CoveredCallClosedEndFund", "Covered Call Closed-End Fund Discount",
    "The Anomalous Behavior of the S&P Covered Call Closed End Fund",
    "Trades the discount of a fund to its net asset value. Needs both the fund price "
    "and the NAV series.", cat="Options Income")

OptimalReserveCurrencyShares = _cross_sectional(
    "OptimalReserveCurrencyShares", "Optimal Reserve Currency Shares",
    "Optimal Currency Shares In International Reserves The Impact Of The Euro And The "
    "Prospects For The Dollar",
    "Allocates reserve weights across currencies. A multi-currency allocation, not a "
    "single-pair signal.", cat=CAT_MACRO)
