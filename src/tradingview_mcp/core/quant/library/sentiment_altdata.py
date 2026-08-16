"""
Sentiment and alternative data.

Almost everything here genuinely needs an external feed — news wires, search
volume, short interest, insider filings, analyst revisions. That is the whole
point of alternative data: it is *alternative to price*. Deriving "sentiment"
from a moving average is not sentiment analysis, so these models declare their
feed and stand down without it rather than dressing up a price indicator.

The project already ships several real feeds (``news_service``,
``marketaux_service``, ``sentiment_service``). Wiring those into ``meta`` is what
activates the models below; until then they report honestly as unavailable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import BaseStrategy, DataNeed, Horizon, Regime, squash
from ..features import FeatureSet, rolling_rank, zscore

CAT = "Sentiment & Alt Data"


class _FeedStrategy(BaseStrategy):
    """Base for models requiring an external, non-price feed."""
    horizon = Horizon.SWING
    min_bars = 120
    _key = "sentiment"

    def score(self, f: FeatureSet) -> pd.Series:
        payload = f.meta.get(self._key)
        if payload is None:
            return pd.Series(np.nan, index=f.close.index)
        s = pd.Series(payload, index=f.close.index) if not isinstance(payload, pd.Series) else payload
        return squash(zscore(s.reindex(f.close.index), 60), 1.5)


class NewsSentimentTone(_FeedStrategy):
    name = "News Sentiment Tone"
    category = CAT
    family = "news"
    research = "Tetlock (2007), 'Giving Content to Investor Sentiment', JF 62(3)"
    description = "Negative media tone predicts short-horizon downward pressure followed by reversion."
    needs = (DataNeed.OHLC, DataNeed.NEWS)
    _key = "news_sentiment"


class NewsVolumeShock(_FeedStrategy):
    name = "News Volume Attention Shock"
    category = CAT
    family = "news"
    research = "Barber & Odean (2008), 'All That Glitters: Attention and News', RFS 21(2)"
    description = "Abnormal news volume drives retail attention-based buying that subsequently reverses."
    needs = (DataNeed.OHLC, DataNeed.NEWS)
    _key = "news_volume"


class EarningsCallTone(_FeedStrategy):
    name = "Earnings Call Linguistic Tone"
    category = CAT
    family = "text"
    research = "Loughran & McDonald (2011), 'When Is a Liability Not a Liability?', JF 66(1)"
    description = "Finance-specific sentiment lexicons applied to transcripts predict post-call drift."
    needs = (DataNeed.OHLC, DataNeed.NEWS, DataNeed.FUNDAMENTALS)
    _key = "call_tone"


class TenKRiskLanguage(_FeedStrategy):
    name = "Annual Report Risk Language"
    category = CAT
    family = "text"
    research = "Campbell, Chen, Dhaliwal, Lu & Steele (2014), 'The Information Content of Mandatory Risk Factor Disclosures', RAS 19"
    description = "Changes in risk-factor language year over year predict subsequent volatility."
    needs = (DataNeed.OHLC, DataNeed.NEWS, DataNeed.FUNDAMENTALS)
    _key = "filing_risk_language"


class GoogleTrendsAttention(_FeedStrategy):
    name = "Search Volume Attention"
    category = CAT
    family = "search"
    research = "Preis, Moat & Stanley (2013), 'Quantifying Trading Behavior Using Google Trends', Scientific Reports 3"
    description = "Rising search interest in financial terms preceded market declines in the published sample."
    needs = (DataNeed.OHLC, DataNeed.NEWS)
    _key = "search_volume"


class WikipediaPageViews(_FeedStrategy):
    name = "Wikipedia Page View Attention"
    category = CAT
    family = "search"
    research = "Moat, Curme, Avakian, Kenett, Stanley & Preis (2013), 'Quantifying Wikipedia Usage Patterns', Scientific Reports 3"
    description = "Page views on company articles proxy retail attention ahead of price moves."
    needs = (DataNeed.OHLC, DataNeed.NEWS)
    _key = "wiki_views"


class SocialMediaSentiment(_FeedStrategy):
    name = "Social Media Sentiment"
    category = CAT
    family = "social"
    research = "Bollen, Mao & Zeng (2011), 'Twitter Mood Predicts the Stock Market', J. Computational Science 2(1)"
    description = "Aggregate social mood carries short-horizon predictive content, strongest for retail-heavy names."
    needs = (DataNeed.OHLC, DataNeed.NEWS)
    _key = "social_sentiment"


class RetailOrderFlowSentiment(_FeedStrategy):
    name = "Retail Order Flow Imbalance"
    category = CAT
    family = "retail"
    research = "Boehmer, Jones, Zhang & Zhang (2021), 'Tracking Retail Investor Activity', JF 76(5)"
    description = "Retail order imbalance predicts returns positively at the weekly horizon, then reverses."
    needs = (DataNeed.OHLC, DataNeed.NEWS)
    _key = "retail_imbalance"


class ShortInterestSignal(_FeedStrategy):
    name = "Short Interest Ratio"
    category = CAT
    family = "positioning"
    research = "Asquith, Pathak & Ritter (2005), 'Short Interest, Institutional Ownership and Stock Returns', JFE 78(2)"
    description = "High short interest with low lending supply predicts underperformance; needs a short-interest feed."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    _key = "short_interest"


class InsiderTransactions(_FeedStrategy):
    name = "Insider Transaction Signal"
    category = CAT
    family = "positioning"
    research = "Lakonishok & Lee (2001), 'Are Insider Trades Informative?', RFS 14(1); Cohen, Malloy & Pomorski (2012), JF 67(3)"
    description = "Opportunistic insider purchases carry genuine information; routine trades do not."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    _key = "insider_net"


class AnalystRevisions(_FeedStrategy):
    name = "Analyst Revision Momentum"
    category = CAT
    family = "analyst"
    research = "Chan, Jegadeesh & Lakonishok (1996), 'Momentum Strategies', JF 51(5); Womack (1996), JF 51(1)"
    description = "Earnings-estimate revisions drift in the direction of the revision for several months."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    _key = "analyst_revisions"


class InstitutionalOwnershipChange(_FeedStrategy):
    name = "Institutional Ownership Change"
    category = CAT
    family = "positioning"
    research = "Gompers & Metrick (2001), 'Institutional Investors and Equity Prices', QJE 116(1)"
    description = "Changes in 13F institutional holdings predict returns, subject to a reporting lag."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    _key = "institutional_ownership"


class BakerWurglerSentiment(_FeedStrategy):
    name = "Market-Wide Sentiment Index"
    category = CAT
    family = "market_sentiment"
    research = "Baker & Wurgler (2006), 'Investor Sentiment and the Cross-Section of Stock Returns', JF 61(4)"
    description = "Composite market sentiment predicts the cross-section, most strongly for hard-to-value stocks."
    needs = (DataNeed.OHLC, DataNeed.NEWS)
    _key = "market_sentiment"


class SurveySentimentContrarian(_FeedStrategy):
    name = "Survey Sentiment Contrarian"
    category = CAT
    family = "market_sentiment"
    research = "Brown & Cliff (2005), 'Investor Sentiment and Asset Valuation', J. Business 78(2)"
    description = "Extreme bullishness in investor surveys is a contrarian indicator at multi-month horizons."
    needs = (DataNeed.OHLC, DataNeed.NEWS)
    _key = "survey_sentiment"

    def score(self, f: FeatureSet) -> pd.Series:
        base = super().score(f)
        return -base  # contrarian by construction


class CreditSpreadSignal(_FeedStrategy):
    name = "Credit Spread Risk Appetite"
    category = CAT
    family = "macro_sentiment"
    research = "Gilchrist & Zakrajšek (2012), 'Credit Spreads and Business Cycle Fluctuations', AER 102(4)"
    description = "Widening credit spreads lead equity weakness; the excess bond premium is the sharpest form."
    needs = (DataNeed.OHLC, DataNeed.BENCHMARK)
    _key = "credit_spread"

    def score(self, f: FeatureSet) -> pd.Series:
        return -super().score(f)  # wider spreads = risk-off


class SupplyChainAltData(_FeedStrategy):
    name = "Supply Chain Activity Signal"
    category = CAT
    family = "alt_data"
    research = "Cohen & Frazzini (2008), 'Economic Links and Predictable Returns', JF 63(4)"
    description = "Customer-firm performance predicts supplier returns with a lag; needs a supply-chain graph."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS, DataNeed.CROSS_SECTION)
    _key = "supply_chain"


class SatelliteFootfallData(_FeedStrategy):
    name = "Geolocation Footfall Signal"
    category = CAT
    family = "alt_data"
    research = "Katona, Painter, Patatoukas & Zeng (2018), 'On the Capital Market Consequences of Alternative Data'"
    description = "Parking-lot and foot-traffic counts anticipate retail revenue prints; needs a geolocation vendor."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    _key = "footfall"


class PatentInnovationSignal(_FeedStrategy):
    name = "Patent Innovation Signal"
    category = CAT
    family = "alt_data"
    research = "Kogan, Papanikolaou, Seru & Stoffman (2017), 'Technological Innovation, Resource Allocation and Growth', QJE 132(2)"
    description = "Market-value-weighted patent output predicts long-horizon returns; needs a patent database."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    horizon = Horizon.POSITION
    _key = "patents"


class JobPostingSignal(_FeedStrategy):
    name = "Hiring Activity Signal"
    category = CAT
    family = "alt_data"
    research = "Gutiérrez, Jegadeesh & Kim (2021), 'Job Postings and Firm Fundamentals'"
    description = "Job-posting growth leads revenue growth by one to two quarters; needs a postings feed."
    needs = (DataNeed.OHLC, DataNeed.FUNDAMENTALS)
    horizon = Horizon.POSITION
    _key = "job_postings"


# ── computable from price alone, and honest about what it is ───────────────────

class FearGreedPriceProxy(BaseStrategy):
    name = "Price-Based Fear & Greed Composite"
    category = CAT
    family = "market_sentiment"
    research = "Composite construction after CNN Business Fear & Greed methodology (price-derived components only)"
    description = ("Blends the four price-derived Fear & Greed components — momentum, strength, breadth proxy and "
                   "volatility — into a contrarian composite.")
    horizon = Horizon.SWING
    min_bars = 280
    is_proxy = True
    proxy_note = ("The published index also uses put/call ratios, junk-bond demand and safe-haven flows. This uses "
                  "only the price-derived components, so it is a partial reconstruction, not the index itself.")

    def score(self, f: FeatureSet) -> pd.Series:
        momentum = rolling_rank(f.close / f.sma(125) - 1, 252)
        strength = rolling_rank(f.close.pct_change(20), 252)
        vol_inv = 1 - f.vol_regime
        dd_health = (1 + f.drawdown() / 0.20).clip(0, 1)
        greed = (momentum.fillna(0.5) + strength.fillna(0.5) + vol_inv.fillna(0.5) + dd_health) / 4
        # Extreme greed → fade; extreme fear → buy.
        return -((greed - 0.5) * 2).clip(-1, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        momentum = float(rolling_rank(f.close / f.sma(125) - 1, 252).iloc[-1])
        strength = float(rolling_rank(f.close.pct_change(20), 252).iloc[-1])
        vol_inv = float(1 - f.vol_regime.iloc[-1])
        dd = float((1 + f.drawdown() / 0.20).clip(0, 1).iloc[-1])
        composite = (momentum + strength + vol_inv + dd) / 4
        label = ("extreme greed" if composite > 0.75 else "greed" if composite > 0.55
                 else "extreme fear" if composite < 0.25 else "fear" if composite < 0.45 else "neutral")
        return {"momentum_percentile": momentum, "strength_percentile": strength,
                "inverse_vol": vol_inv, "drawdown_health": dd,
                "composite_0_1": composite, "reading": label}

    def explain(self, f: FeatureSet, v: float, d: dict) -> str:
        return (f"Price-derived Fear & Greed composite reads {d.get('composite_0_1', 0.5):.2f} "
                f"({d.get('reading')}); contrarian stance at conviction {abs(v):.2f}. "
                f"Note: partial reconstruction — options and credit components are not connected.")


class VolatilityFearGauge(BaseStrategy):
    name = "Volatility Fear Gauge"
    category = CAT
    family = "market_sentiment"
    research = "Whaley (2000), 'The Investor Fear Gauge', JPM 26(3)"
    description = "Volatility spikes mark fear; extreme readings have historically been buy points, not sell points."
    horizon = Horizon.SWING
    min_bars = 250

    def score(self, f: FeatureSet) -> pd.Series:
        fear = f.vol_regime
        falling = (f.close.pct_change(5) < 0).astype(float)
        # Panic (high vol + falling price) is contrarian-bullish at extremes.
        return (fear * falling * 2 - fear * (1 - falling) * 0.5).clip(-1, 1)

    def diagnostics(self, f: FeatureSet) -> dict:
        return {"vol_percentile": float(f.vol_regime.iloc[-1]),
                "return_5b_pct": float(f.close.pct_change(5).iloc[-1] * 100),
                "state": "panic (contrarian buy zone)" if f.vol_regime.iloc[-1] > 0.8
                         and f.close.pct_change(5).iloc[-1] < 0 else "normal"}


class CapitulationVolumeSignal(BaseStrategy):
    name = "Capitulation Volume Climax"
    category = CAT
    family = "capitulation"
    research = "Selling-climax framework per Wyckoff (1931); volume-climax evidence per Gervais, Kaniel & Mingelgrin (2001), JF 56(3)"
    description = "Extreme volume on a wide down bar that closes strongly marks forced-seller exhaustion."
    needs = (DataNeed.OHLC, DataNeed.VOLUME)
    horizon = Horizon.SWING
    min_bars = 150
    params = {"vol_z": 2.0, "hold": 8}

    def score(self, f: FeatureSet) -> pd.Series:
        rng = (f.high - f.low).where((f.high - f.low) > 1e-12)
        close_pos = ((f.close - f.low) / rng).fillna(0.5)
        climax_vol = f.volume_z(20) > self.params["vol_z"]
        wide = f.true_range > f.atr(14) * 1.8
        down = f.close < f.open
        buy_climax = (climax_vol & wide & down & (close_pos > 0.55)).astype(float)
        sell_climax = (climax_vol & wide & (f.close > f.open) & (close_pos < 0.45)).astype(float)
        return (buy_climax - sell_climax).replace(0, np.nan).ffill(limit=self.params["hold"]).fillna(0)

    def diagnostics(self, f: FeatureSet) -> dict:
        rng = float(f.high.iloc[-1] - f.low.iloc[-1])
        return {"volume_zscore": float(f.volume_z(20).iloc[-1]),
                "range_in_atr": float(f.true_range.iloc[-1] / f.atr(14).iloc[-1]),
                "close_position": float((f.close.iloc[-1] - f.low.iloc[-1]) / rng) if rng > 0 else float("nan")}
