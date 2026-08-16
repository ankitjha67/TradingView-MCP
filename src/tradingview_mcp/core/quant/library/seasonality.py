"""
Calendar and seasonality effects.

Small, persistent, well-documented anomalies. They are individually weak — which
is exactly why they belong in an ensemble rather than traded alone — and several
have decayed materially since publication. Where that is known, the docstring
says so instead of quietly presenting a dead effect as live.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import BaseStrategy, DataNeed, Horizon, Regime, squash
from ..features import FeatureSet, zscore

CAT = "Seasonality & Calendar"


class _CalendarStrategy(BaseStrategy):
    """Base for models that need a real DatetimeIndex."""
    horizon = Horizon.SWING
    min_bars = 150

    def availability(self, f: FeatureSet):
        if not isinstance(f.df.index, pd.DatetimeIndex):
            return False, "requires a datetime index"
        return super().availability(f)


class TurnOfMonthEffect(_CalendarStrategy):
    name = "Turn-of-the-Month Effect"
    category = CAT
    family = "monthly"
    research = "Ariel (1987), 'A Monthly Effect in Stock Returns', JFE 18(1); Lakonishok & Smidt (1988), RFS 1(4)"
    description = "Returns concentrate in the last and first few trading days of the month, driven by pension inflows."
    params = {"days_before": 2, "days_after": 3}

    def score(self, f: FeatureSet) -> pd.Series:
        dom = f.df.index.day
        days_in_month = f.df.index.days_in_month
        near_end = (days_in_month - dom) <= self.params["days_before"]
        near_start = dom <= self.params["days_after"]
        return pd.Series(np.where(near_end | near_start, 0.6, -0.15), index=f.close.index)

    def diagnostics(self, f: FeatureSet) -> dict:
        d = f.df.index[-1]
        return {"day_of_month": int(d.day), "days_in_month": int(d.days_in_month),
                "in_turn_of_month_window": bool(d.day <= 3 or (d.days_in_month - d.day) <= 2)}


class DayOfWeekEffect(_CalendarStrategy):
    name = "Day-of-Week Effect"
    category = CAT
    family = "weekly"
    research = "French (1980), 'Stock Returns and the Weekend Effect', JFE 8(1); Cross (1973), FAJ 29(6)"
    description = ("Monday returns were historically negative and Friday positive. The effect has weakened "
                   "substantially since the 1990s, so it is scored from the symbol's own realised history.")

    def score(self, f: FeatureSet) -> pd.Series:
        dow = pd.Series(f.df.index.dayofweek, index=f.close.index)
        # Learn each weekday's realised edge from an expanding window — no hard-coded prior.
        edge = f.logret.groupby(dow).transform(
            lambda x: x.shift(1).expanding(min_periods=10).mean())
        vol = f.logret.expanding(min_periods=20).std(ddof=0)
        return squash(edge / vol.where(vol > 1e-12), 0.4)

    def diagnostics(self, f: FeatureSet) -> dict:
        dow = pd.Series(f.df.index.dayofweek, index=f.close.index)
        today = int(f.df.index[-1].dayofweek)
        hist = f.logret[dow == today]
        names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return {"weekday": names[today], "historical_mean_return_bps": float(hist.mean() * 1e4),
                "observations": int(hist.notna().sum())}


class JanuaryEffect(_CalendarStrategy):
    name = "January Effect"
    category = CAT
    family = "monthly"
    research = "Rozeff & Kinney (1976), 'Capital Market Seasonality', JFE 3(4); Keim (1983), JFE 12(1)"
    description = ("Small caps outperformed in January, historically attributed to tax-loss-selling reversal. "
                   "Largely arbitraged away in large caps since the 1990s.")
    min_bars = 300

    def score(self, f: FeatureSet) -> pd.Series:
        month = f.df.index.month
        day = f.df.index.day
        return pd.Series(np.where((month == 1) & (day <= 15), 0.5,
                                  np.where((month == 12) & (day >= 20), 0.3, 0.0)),
                         index=f.close.index)


class HalloweenIndicator(_CalendarStrategy):
    name = "Halloween Indicator (Sell in May)"
    category = CAT
    family = "annual"
    research = "Bouman & Jacobsen (2002), 'The Halloween Indicator', AER 92(5); replicated in Jacobsen & Zhang (2013)"
    description = "November-April returns have historically exceeded May-October across most developed markets."
    horizon = Horizon.POSITION
    min_bars = 300

    def score(self, f: FeatureSet) -> pd.Series:
        month = f.df.index.month
        winter = np.isin(month, [11, 12, 1, 2, 3, 4])
        return pd.Series(np.where(winter, 0.45, -0.25), index=f.close.index)

    def diagnostics(self, f: FeatureSet) -> dict:
        m = int(f.df.index[-1].month)
        return {"month": m, "season": "Nov-Apr (favourable)" if m in (11, 12, 1, 2, 3, 4) else "May-Oct (weak)"}


class HolidayEffect(_CalendarStrategy):
    name = "Pre-Holiday Effect"
    category = CAT
    family = "holiday"
    research = "Lakonishok & Smidt (1988), 'Are Seasonal Anomalies Real?', RFS 1(4); Ariel (1990), JF 45(5)"
    description = "The trading day before a market holiday earns abnormally high returns; detected via calendar gaps."

    def score(self, f: FeatureSet) -> pd.Series:
        idx = f.df.index
        # A gap larger than the usual bar spacing implies a market closure ahead.
        gap_ahead = pd.Series(idx, index=f.close.index).diff().shift(-1)
        typical = gap_ahead.median()
        pre_holiday = (gap_ahead > typical * 2.5).astype(float)
        return pre_holiday * 0.55

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"bars": int(f.n), "index_frequency": str(pd.Series(f.df.index).diff().median())}


class MonthOfYearSeasonality(_CalendarStrategy):
    name = "Month-of-Year Seasonality"
    category = CAT
    family = "annual"
    research = "Heston & Sadka (2008), 'Seasonality in the Cross-Section of Stock Returns', JFE 87(2)"
    description = "Assets exhibit persistent same-calendar-month return patterns; learned from the symbol's own history."
    horizon = Horizon.POSITION
    min_bars = 400

    def score(self, f: FeatureSet) -> pd.Series:
        month = pd.Series(f.df.index.month, index=f.close.index)
        edge = f.logret.groupby(month).transform(lambda x: x.shift(1).expanding(min_periods=6).mean())
        vol = f.logret.expanding(min_periods=30).std(ddof=0)
        return squash(edge / vol.where(vol > 1e-12), 0.4)

    def diagnostics(self, f: FeatureSet) -> dict:
        month = pd.Series(f.df.index.month, index=f.close.index)
        cur = int(f.df.index[-1].month)
        hist = f.logret[month == cur]
        return {"month": cur, "historical_mean_return_bps": float(hist.mean() * 1e4),
                "observations": int(hist.notna().sum())}


class IntradayUShape(_CalendarStrategy):
    name = "Intraday U-Shape Volume Pattern"
    category = CAT
    family = "intraday"
    research = "Admati & Pfleiderer (1988), 'A Theory of Intraday Patterns', RFS 1(1); Jain & Joh (1988), JFQA 23(3)"
    description = "Volume and volatility are U-shaped through the session; the midday lull favours reversion."
    horizon = Horizon.INTRADAY
    min_bars = 200

    def availability(self, f: FeatureSet):
        if f.interval in ("1d", "1wk", "1mo"):
            return False, "requires intraday bars"
        return super().availability(f)

    def score(self, f: FeatureSet) -> pd.Series:
        hour = pd.Series(f.df.index.hour, index=f.close.index)
        hours = sorted(hour.unique())
        if len(hours) < 3:
            return pd.Series(np.nan, index=f.close.index)
        first, last = hours[0], hours[-1]
        midday = (~hour.isin([first, last])).astype(float)
        # Midday: low information arrival, reversion dominates. Open/close: trend.
        return -squash(zscore(f.ret, 20), 1.5) * midday + \
            squash(zscore(f.ret, 20), 2.0) * (1 - midday) * 0.5


class OvernightVsIntraday(_CalendarStrategy):
    name = "Overnight vs Intraday Return Split"
    category = CAT
    family = "intraday"
    research = "Lou, Polk & Skouras (2019), 'A Tug of War', JFE 134(1); Kelly & Clark (2011), JBF 35(5)"
    description = "Nearly all equity risk premium accrues overnight while intraday returns are flat or negative."
    horizon = Horizon.INTRADAY
    min_bars = 150

    def score(self, f: FeatureSet) -> pd.Series:
        overnight = np.log(f.open / f.close.shift(1))
        intraday = np.log(f.close / f.open)
        on_edge = overnight.rolling(60, min_periods=20).mean()
        id_edge = intraday.rolling(60, min_periods=20).mean()
        vol = f.logret.rolling(60, min_periods=20).std(ddof=0)
        return squash((on_edge - id_edge) / vol.where(vol > 1e-12), 0.5)

    def diagnostics(self, f: FeatureSet) -> dict:
        on = float(np.log(f.open / f.close.shift(1)).rolling(60, min_periods=20).mean().iloc[-1] * 1e4)
        idy = float(np.log(f.close / f.open).rolling(60, min_periods=20).mean().iloc[-1] * 1e4)
        return {"overnight_edge_bps": on, "intraday_edge_bps": idy}


class OptionsExpiryWeek(_CalendarStrategy):
    name = "Options Expiry Week Effect"
    category = CAT
    family = "expiry"
    research = "Stoll & Whaley (1987), 'Program Trading and Expiration-Day Effects', FAJ 43(2); Ni, Pearson & Poteshman (2005), JFE 78(1)"
    description = "Dealer hedging around monthly expiry dampens realised volatility and pins price into Friday."
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        idx = f.df.index
        dom, dow = idx.day, idx.dayofweek
        # Third Friday of the month = standard monthly equity/index expiry.
        expiry_week = pd.Series(((dom >= 15) & (dom <= 21)).astype(float), index=f.close.index)
        return -squash(zscore(f.close, 20), 1.5) * expiry_week * 0.8

    def diagnostics(self, f: FeatureSet) -> dict:
        d = f.df.index[-1]
        return {"day_of_month": int(d.day), "in_expiry_week": bool(15 <= d.day <= 21)}


class FOMCDrift(_CalendarStrategy):
    name = "FOMC Announcement Drift"
    category = CAT
    family = "macro_calendar"
    research = "Lucca & Moench (2015), 'The Pre-FOMC Announcement Drift', JF 70(1)"
    description = "Equities drift up in the 24 hours before scheduled FOMC announcements; needs a macro calendar."
    needs = (DataNeed.OHLC, DataNeed.NEWS)
    horizon = Horizon.SWING
    min_bars = 200

    def score(self, f: FeatureSet) -> pd.Series:
        if f.meta.get("macro_calendar") is None:
            return pd.Series(np.nan, index=f.close.index)
        return pd.Series(np.nan, index=f.close.index)


class QuarterEndRebalancing(_CalendarStrategy):
    name = "Quarter-End Rebalancing Flow"
    category = CAT
    family = "monthly"
    research = "Etula, Rinne, Suominen & Vaittinen (2020), 'Dash for Cash: Month-End Liquidity Needs', JFQA 55(4)"
    description = "Institutional rebalancing at quarter end creates predictable, mechanically-driven flow."
    min_bars = 250

    def score(self, f: FeatureSet) -> pd.Series:
        idx = f.df.index
        quarter_end_month = np.isin(idx.month, [3, 6, 9, 12])
        near_end = (idx.days_in_month - idx.day) <= 3
        window = pd.Series((quarter_end_month & near_end).astype(float), index=f.close.index)
        # Rebalancing pressure typically pushes against the quarter's move.
        return -squash(zscore(f.close.pct_change(63), 120), 1.5) * window

    def diagnostics(self, f: FeatureSet) -> dict:
        d = f.df.index[-1]
        return {"month": int(d.month), "days_to_month_end": int(d.days_in_month - d.day),
                "in_quarter_end_window": bool(d.month in (3, 6, 9, 12) and (d.days_in_month - d.day) <= 3)}


class SeasonalVolatilityPattern(_CalendarStrategy):
    name = "Seasonal Volatility Pattern"
    category = CAT
    family = "annual"
    research = "Seasonal volatility documented in Bouman & Jacobsen (2002), AER 92(5); September effect per Siegel (2014)"
    description = "Volatility peaks seasonally, notably September-October; positions scale down into those windows."
    horizon = Horizon.POSITION
    min_bars = 400

    def score(self, f: FeatureSet) -> pd.Series:
        month = pd.Series(f.df.index.month, index=f.close.index)
        seasonal_vol = f.realized_vol(20).groupby(month).transform(
            lambda x: x.shift(1).expanding(min_periods=6).mean())
        overall = f.realized_vol(20).expanding(min_periods=60).mean()
        elevated = (seasonal_vol / overall.where(overall > 1e-9)).fillna(1.0)
        trend = np.sign(f.ema(50) - f.ema(200)).fillna(0)
        return trend * (2 - elevated).clip(0, 1)


class TimeOfDayMomentum(_CalendarStrategy):
    name = "Time-of-Day Momentum"
    category = CAT
    family = "intraday"
    research = "Heston, Korajczyk & Sadka (2010), 'Intraday Patterns in the Cross-Section of Stock Returns', JF 65(4)"
    description = "Returns at a given time of day are positively autocorrelated across days at that same time."
    horizon = Horizon.INTRADAY
    min_bars = 250

    def availability(self, f: FeatureSet):
        if f.interval in ("1d", "1wk", "1mo"):
            return False, "requires intraday bars"
        return super().availability(f)

    def score(self, f: FeatureSet) -> pd.Series:
        slot = pd.Series(f.df.index.hour * 60 + f.df.index.minute, index=f.close.index)
        edge = f.logret.groupby(slot).transform(lambda x: x.shift(1).rolling(20, min_periods=5).mean())
        vol = f.logret.rolling(60, min_periods=20).std(ddof=0)
        return squash(edge / vol.where(vol > 1e-12), 0.5)


class WeekOfMonthPattern(_CalendarStrategy):
    name = "Week-of-Month Pattern"
    category = CAT
    family = "monthly"
    research = "Kohers & Patel (1999), 'A New Time-of-the-Month Anomaly', Applied Economics Letters 6(2)"
    description = "Return distribution differs systematically across weeks of the month; learned from own history."
    min_bars = 300

    def score(self, f: FeatureSet) -> pd.Series:
        week = pd.Series((f.df.index.day - 1) // 7, index=f.close.index)
        edge = f.logret.groupby(week).transform(lambda x: x.shift(1).expanding(min_periods=8).mean())
        vol = f.logret.expanding(min_periods=30).std(ddof=0)
        return squash(edge / vol.where(vol > 1e-12), 0.4)

    def diagnostics(self, f: FeatureSet) -> dict:
        d = f.df.index[-1]
        return {"week_of_month": int((d.day - 1) // 7) + 1}
