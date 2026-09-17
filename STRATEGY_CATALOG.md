# Strategy Catalog

_Generated 2026-09-17 by `tools/generate_catalog.py`. Do not edit by hand — re-run the generator._

## Summary

| | |
|---|---|
| **Total models** | 358 |
| **Categories** | 16 |
| **Independent families** | 233 |
| **Runnable on price/volume alone** | 216 |
| **Require an external feed** | 142 |
| **Proxy implementations** | 22 |

### How to read this

**Family** is the honest unit of diversification. Two models in the same family are variations on one idea, not two independent opinions — the consensus engine splits a single vote between them. 358 models across 233 families means roughly 233 genuinely distinct views.

**Needs** is what the model requires to run honestly. A model needing an options chain or a peer universe reports as *unavailable* when that feed is absent instead of silently substituting a price indicator and voting anyway.

**Proxy** marks a model that approximates its published method using substituted data — for example estimating order-flow imbalance from bar volume because tick data is not available. Proxies are labelled everywhere they appear and are weighted at 40% of a full vote in the consensus.

---

## Models by category

| Category | Models | Families | Price-only | Needs feed | Proxies |
|---|---:|---:|---:|---:|---:|
| Trend & Momentum | 35 | 25 | 32 | 3 | 0 |
| Factor & Smart Beta | 34 | 22 | 13 | 21 | 1 |
| Macro & Allocation | 29 | 18 | 8 | 21 | 0 |
| Crypto Native | 27 | 16 | 8 | 19 | 1 |
| Mean Reversion | 25 | 19 | 24 | 1 | 0 |
| Sentiment & Alt Data | 24 | 13 | 3 | 21 | 1 |
| Statistical Arbitrage | 23 | 17 | 15 | 8 | 0 |
| Machine Learning | 22 | 16 | 19 | 3 | 0 |
| Microstructure | 22 | 14 | 20 | 2 | 6 |
| Options & Derivatives | 22 | 14 | 6 | 16 | 5 |
| Volatility | 22 | 15 | 21 | 1 | 0 |
| Regime & Risk | 21 | 17 | 18 | 3 | 0 |
| Rates & Credit | 18 | 16 | 4 | 14 | 1 |
| Seasonality & Calendar | 15 | 8 | 14 | 1 | 0 |
| Commodity & Carry | 11 | 10 | 4 | 7 | 0 |
| Options Income | 8 | 4 | 7 | 1 | 7 |

---

## Trend & Momentum

_35 models · 25 families_

1. **52-Week High Proximity**
   - Nearness to the annual high; the anchoring bias makes proximity to it predict continuation.
   - *Research:* George & Hwang (2004), 'The 52-Week High and Momentum Investing', JF 59(5)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 260 · *Family:* `anchor`

2. **ADX Directional Movement**
   - Directional index spread gated by ADX, so it only takes a side when a trend actually exists.
   - *Research:* Wilder (1978), 'New Concepts in Technical Trading Systems'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 60 · *Family:* `adx`

3. **Aroon Oscillator**
   - Measures how recently the period high versus low occurred — a time-based trend gauge.
   - *Research:* Chande (1995), 'A Time Price Oscillator', Technical Analysis of Stocks & Commodities
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 60 · *Family:* `aroon`

4. **Chande Momentum Oscillator**
   - Unsmoothed momentum: net of up-moves and down-moves over their total, avoiding RSI's damping.
   - *Research:* Chande & Kroll (1994), 'The New Technical Trader'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 60 · *Family:* `cmo`

5. **Coppock Curve**
   - Weighted MA of summed 14- and 11-period rates of change; a classic long-horizon bottom signal.
   - *Research:* Coppock (1962), Barron's — long-term momentum turn indicator
   - *Needs:* price only · *Horizon:* position · *Min bars:* 150 · *Family:* `coppock`

6. **Cross-Sectional Momentum (Jegadeesh-Titman)**
   - Ranks a symbol's 6-month return against a universe and goes long winners, short losers.
   - *Research:* Jegadeesh & Titman (1993), 'Returns to Buying Winners and Selling Losers', JF 48(1)
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 150 · *Family:* `xsmom`

7. **Donchian Channel Breakout**
   - Long on a new N-bar high, short on a new N-bar low, held until the opposite channel.
   - *Research:* Donchian (1960s); systematised by Dennis & Eckhardt's Turtle program (1983)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 80 · *Family:* `breakout`

8. **Dual Momentum (Absolute + Relative)**
   - Requires both a positive absolute trend and outperformance versus its own longer trend.
   - *Research:* Antonacci (2014), 'Dual Momentum Investing'
   - *Needs:* price only · *Horizon:* position · *Min bars:* 280 · *Family:* `tsmom`

9. **EMA 50/200 Golden Cross**
   - Classic long-horizon regime filter: fast EMA above slow EMA, scaled by separation.
   - *Research:* Brock, Lakonishok & LeBaron (1992), 'Simple Technical Trading Rules', JF 47(5)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 220 · *Family:* `ma_cross`

10. **Ehlers Fisher Transform**
   - Gaussianises the price distribution so turning points become sharp, statistically rare events.
   - *Research:* Ehlers (2002), 'Using the Fisher Transform', Technical Analysis of Stocks & Commodities
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 60 · *Family:* `cycle`

11. **Ehlers Instantaneous Trendline**
   - Signal-processing trendline that removes the dominant cycle instead of lagging it.
   - *Research:* Ehlers (2001), 'Rocket Science for Traders'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 80 · *Family:* `cycle`

12. **Elder Triple Screen**
   - Long-horizon trend sets the permitted side; a short-horizon oscillator times entry against it.
   - *Research:* Elder (1993), 'Trading for a Living'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 120 · *Family:* `multi_timeframe`

13. **Failed Breakout Reversal**
   - Fades a breakout that closes back inside the channel, a classic liquidity-sweep pattern.
   - *Research:* Kaufman (2013), 'Trading Systems and Methods', 5th ed. — false breakout patterns
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 80 · *Family:* `breakout`

14. **Filter Rule with Confirmation Delay**
   - Breakout of a price filter band, taken only after the move holds for a confirmation period.
   - *Research:* Neely, Weller & Dittmar lineage, per 'Lessons from the Evolution of Foreign Exchange Trading Strategies'. The lesson is that naive filter rules decayed once crowded; this adds the confirmation delay that survived.
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `filter_rule`

15. **Guppy Multiple Moving Average**
   - Separation and alignment of short-term versus long-term EMA ribbons measures trend conviction.
   - *Research:* Guppy (1999), 'Trend Trading'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 90 · *Family:* `ma_ribbon`

16. **Hull Moving Average Slope**
   - Weighted-composite MA that cuts lag; traded on the sign and steepness of its slope.
   - *Research:* Hull (2005), 'How to reduce lag in a moving average'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 80 · *Family:* `adaptive_ma`

17. **Ichimoku Kinko Hyo**
   - Composite of conversion/base line cross, cloud position and lagging-span confirmation.
   - *Research:* Hosoda (Ichimoku Sanjin), published 1969
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 120 · *Family:* `ichimoku`

18. **Intervention-Conditioned Trend**
   - A trend rule that stands aside during intervention-like volatility spikes, on the finding that its returns do not come from them.
   - *Research:* 'The Temporal Pattern of Trading Rule Returns and Central Bank Intervention' — the finding is that rule profits are NOT generated by intervention. Reading: suppress the rule around intervention-like volatility spikes, where the profit is not.
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `intervention_trend`

19. **Kaufman Adaptive Moving Average**
   - Smoothing constant adapts to the efficiency ratio — fast in trends, inert in chop.
   - *Research:* Kaufman (1995), 'Smarter Trading'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 80 · *Family:* `adaptive_ma`

20. **Keltner Channel Trend**
   - EMA centre with ATR envelopes; trades sustained closes outside the channel.
   - *Research:* Keltner (1960), 'How to Make Money in Commodities'; ATR variant per Linda Raschke
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 60 · *Family:* `atr_trend`

21. **MACD Histogram Momentum**
   - MACD histogram normalised by ATR so conviction is comparable across volatility levels.
   - *Research:* Appel (1979), 'The Moving Average Convergence-Divergence Trading Method'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 60 · *Family:* `macd`

22. **Momentum Acceleration (2nd Derivative)**
   - Trades change in trend speed, which turns before the trend itself does.
   - *Research:* Extends Moskowitz, Ooi & Pedersen (2012) with a curvature term on the trend path
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 100 · *Family:* `acceleration`

23. **Multi-Timeframe Trend Agreement**
   - Counts how many of three horizons agree on direction; conviction is the depth of agreement, not the strength of any one trend.
   - *Research:* Vojtko & Mesicek (2025), 'How to Design a Simple Multi-Timeframe Trend Strategy on Bitcoin'. Single-instrument reading; the paper's own page reports Sharpe 0.81 over 16 years, against 3.39 in the paperswithbacktest replication catalogue.
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 260 · *Family:* `mtf_agreement`

24. **Parabolic SAR**
   - Accelerating stop-and-reverse; the acceleration factor tightens as the trend extends.
   - *Research:* Wilder (1978), 'New Concepts in Technical Trading Systems'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 60 · *Family:* `atr_trend`

25. **Relative Strength vs Benchmark**
   - Ratio of the symbol to its benchmark; a rising ratio is outperformance independent of market direction.
   - *Research:* Levy (1967), 'Relative Strength as a Criterion for Investment Selection', JF 22(4)
   - *Needs:* price only, benchmark series · *Horizon:* position · *Min bars:* 150 · *Family:* `relative_strength`

26. **Residual (Beta-Neutral) Momentum**
   - Momentum in the market-orthogonal residual, which strips out beta-driven trend.
   - *Research:* Blitz, Huij & Martens (2011), 'Residual Momentum', J. Empirical Finance 18(3)
   - *Needs:* price only, benchmark series · *Horizon:* position · *Min bars:* 180 · *Family:* `residual_mom`

27. **Rolling Regression Slope (t-stat)**
   - OLS slope over a rolling window, scaled by residual noise so weak fits produce weak signals.
   - *Research:* Standard OLS trend estimation; t-stat filtering per Brock, Lakonishok & LeBaron (1992)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 90 · *Family:* `regression_trend`

28. **Supertrend (ATR Bands)**
   - Trailing ATR band that flips regime on close-through, a standard CTA stop-and-reverse.
   - *Research:* Olivier Seban's Supertrend; ATR from Wilder (1978)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 60 · *Family:* `atr_trend`

29. **TRIX Triple-Smoothed Momentum**
   - Rate of change of a triple-smoothed EMA; the smoothing strips out cycles shorter than the span.
   - *Research:* Hutson (1983), 'TRIX — Triple Exponential Smoothing Oscillator'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 80 · *Family:* `trix`

30. **Time-Series Momentum (12-1)**
   - Sign of the trailing excess return over a 12-period lookback, skipping the most recent period to avoid short-term reversal contamination.
   - *Research:* Moskowitz, Ooi & Pedersen (2012), 'Time Series Momentum', JFE 104(2)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 280 · *Family:* `tsmom`

31. **Trend Quality (R-squared Gated)**
   - Only trades the trend when the price path is efficient; suppresses signals in choppy tape.
   - *Research:* Kirkpatrick & Dahlquist (2010), 'Technical Analysis'; efficiency ratio per Kaufman (1995)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 90 · *Family:* `regression_trend`

32. **Turtle Trading System 1**
   - 20-bar entry breakout with a 10-bar opposite-channel exit — the original Turtle System 1.
   - *Research:* Dennis & Eckhardt Turtle rules (1983); documented in Faith (2007), 'Way of the Turtle'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 80 · *Family:* `breakout`

33. **Volatility-Scaled Trend (CTA Core)**
   - Blends three lookback horizons, each scaled by its own volatility — the standard CTA construction.
   - *Research:* Baltas & Kosowski (2013), 'Momentum Strategies in Futures Markets and Trend-Following Funds'
   - *Needs:* price only · *Horizon:* position · *Min bars:* 280 · *Family:* `tsmom`

34. **Volume-Confirmed Range Breakout**
   - Breakouts on above-average volume; volume is the information signal that validates the move.
   - *Research:* Blume, Easley & O'Hara (1994), 'Market Statistics and Technical Analysis', JF 49(1)
   - *Needs:* price only, volume · *Horizon:* swing · *Min bars:* 80 · *Family:* `breakout`

35. **Vortex Indicator**
   - Compares upward and downward directional movement built from opposite-extreme distances.
   - *Research:* Botes & Siepman (2010), 'The Vortex Indicator', Technical Analysis of Stocks & Commodities
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 60 · *Family:* `vortex`

---

## Factor & Smart Beta

_34 models · 22 families_

1. **Accruals Anomaly**
   - Earnings driven by accruals rather than cash flow revert; needs cash-flow statements.
   - *Research:* Sloan (1996), 'Do Stock Prices Fully Reflect Information in Accruals and Cash Flows?', Accounting Review 71(3)
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 200 · *Family:* `accounting`

2. **Altman Z-Score Distress**
   - Bankruptcy-risk discriminant; distressed names carry a distinct return profile. Needs fundamentals.
   - *Research:* Altman (1968), 'Financial Ratios, Discriminant Analysis and the Prediction of Corporate Bankruptcy', JF 23(4)
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 200 · *Family:* `distress`

3. **Asset Growth Anomaly**
   - Firms expanding their balance sheet fastest subsequently underperform; needs fundamentals.
   - *Research:* Cooper, Gulen & Schill (2008), 'Asset Growth and the Cross-Section of Stock Returns', JF 63(4)
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 200 · *Family:* `investment`

4. **Beta and Size Cross-Section (Europe)**
   - Sorts on beta and market capitalisation. Both are relative measures and need the universe they are relative to.
   - *Research:* The Role of Beta and Size in the Cross-Section of European Stock Returns
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 60 · *Family:* `betasizecrosssection`

5. **Betting Against Beta**
   - Leverage-constrained investors bid up high-beta assets, so low beta earns higher risk-adjusted returns.
   - *Research:* Frazzini & Pedersen (2014), 'Betting Against Beta', JFE 111(1)
   - *Needs:* price only, benchmark series, peer universe · *Horizon:* position · *Min bars:* 200 · *Family:* `beta`

6. **Black-Litterman Blended View**
   - Blends an equilibrium prior with active views by confidence weighting; here trend is the view.
   - *Research:* Black & Litterman (1992), 'Global Portfolio Optimization', FAJ 48(5)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 200 · *Family:* `allocation`

7. **CAPM Market Beta**
   - Rolling beta to the benchmark; the first-order decomposition of any equity return.
   - *Research:* Sharpe (1964), JF 19(3); Lintner (1965), REStat 47(1)
   - *Needs:* price only, benchmark series · *Horizon:* position · *Min bars:* 150 · *Family:* `beta`

8. **Carhart Four-Factor Alpha**
   - Alpha after market, size, value and momentum; needs factor return series.
   - *Research:* Carhart (1997), 'On Persistence in Mutual Fund Performance', JF 52(1)
   - *Needs:* price only, benchmark series, peer universe · *Horizon:* position · *Min bars:* 250 · *Family:* `multifactor`

9. **Data-Quality Adjusted Cross-Section**
   - Cross-sectional returns after correcting known vendor data errors. Needs a peer universe and its data-quality flags; not derivable from one price series.
   - *Research:* Important Characteristics, Weaknesses and Errors in German Equity Data from Thomson
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 60 · *Family:* `germanequitydataquality`

10. **Defensive Equity Tilt**
   - Combines low volatility, low drawdown and low beta into one defensive composite.
   - *Research:* Frazzini & Pedersen (2014); Blitz & van Vliet (2007), 'The Volatility Effect', JPM 34(1)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 280 · *Family:* `low_vol`

11. **Downside Beta Premium**
   - Beta measured only in down markets is priced separately from ordinary beta.
   - *Research:* Ang, Chen & Xing (2006), 'Downside Risk', RFS 19(4)
   - *Needs:* price only, benchmark series · *Horizon:* position · *Min bars:* 200 · *Family:* `beta`

12. **Factor Momentum Timing**
   - Factors themselves trend; recent factor performance predicts near-term factor returns.
   - *Research:* Gupta & Kelly (2019), 'Factor Momentum Everywhere', JPM 45(3)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 250 · *Family:* `factor_timing`

13. **Gross Profitability**
   - Gross profits over assets predicts returns as strongly as book-to-market; needs fundamentals.
   - *Research:* Novy-Marx (2013), 'The Other Side of Value', JFE 108(1)
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 200 · *Family:* `profitability`

14. **Hierarchical Risk Parity**
   - Clusters the correlation matrix before allocating, avoiding the instability of matrix inversion.
   - *Research:* López de Prado (2016), 'Building Diversified Portfolios that Outperform Out of Sample', JPM 42(4)
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 250 · *Family:* `risk_parity`

15. **Idiosyncratic Volatility Puzzle**
   - Residual volatility after removing market beta predicts low returns — an anomaly relative to theory.
   - *Research:* Ang, Hodrick, Xing & Zhang (2009), 'High Idiosyncratic Volatility and Low Returns', JFE 91(1)
   - *Needs:* price only, benchmark series · *Horizon:* position · *Min bars:* 200 · *Family:* `low_vol`

16. **Kelly Criterion Optimal Fraction**
   - Growth-optimal fraction from estimated edge over variance, capped at half-Kelly for estimation error.
   - *Research:* Kelly (1956), Bell System Technical Journal 35(4); Thorp (2006), 'The Kelly Criterion in Blackjack, Sports Betting and the Stock Market'
   - *Needs:* price only · *Horizon:* position · *Min bars:* 200 · *Family:* `allocation`

17. **Large Gap Continuation Drift** — **PROXY**
   - Large unexplained gaps proxy for news shocks, which drift in the gap direction rather than fully revert.
   - *Research:* Price-only PEAD proxy following the underreaction mechanism in Bernard & Thomas (1989)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 120 · *Family:* `pead`
   - *Proxy note:* Uses outsized overnight gaps as a stand-in for scheduled earnings surprises, which need a calendar feed.

18. **Liquidity Risk Factor**
   - Sensitivity to market-wide liquidity shocks is priced; approximated here by turnover-adjusted reversal.
   - *Research:* Pástor & Stambaugh (2003), 'Liquidity Risk and Expected Stock Returns', JPE 111(3)
   - *Needs:* price only, volume · *Horizon:* position · *Min bars:* 200 · *Family:* `liquidity_factor`

19. **Lottery-Preference Payoff Fade**
   - Fades periods whose recent payoff shape is lottery-like — rare large gains against frequent small losses.
   - *Research:* 'Can Financial Innovation Succeed by Catering to Behavioral Preferences? Evidence from a Callable Options Market'. Reading: products catering to lottery preference are overpriced; fade the lottery-like payoff profile.
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `lottery_fade`

20. **Low Volatility Anomaly**
   - Low-volatility assets have historically out-returned high-volatility ones, inverting the CAPM prediction.
   - *Research:* Ang, Hodrick, Xing & Zhang (2006), 'The Cross-Section of Volatility and Expected Returns', JF 61(1)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 280 · *Family:* `low_vol`

21. **Maximum Sharpe Tilt**
   - Tilts toward the asset when its own trailing Sharpe is in the upper part of its historical range.
   - *Research:* Markowitz (1952), 'Portfolio Selection', JF 7(1); Sharpe (1966), J. Business 39(1)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 250 · *Family:* `allocation`

22. **Momentum-Reversal Horizon Rotation**
   - Rotates between short-horizon reversal and medium-horizon momentum based on which is currently paying.
   - *Research:* Asness, Moskowitz & Pedersen (2013), JF 68(3) — momentum and value as negatively correlated siblings
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 250 · *Family:* `factor_timing`

23. **Net Share Issuance**
   - Firms issuing shares underperform, those buying back outperform; needs share-count history.
   - *Research:* Pontiff & Woodgate (2008), 'Share Issuance and Cross-Sectional Returns', JF 63(2)
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 200 · *Family:* `issuance`

24. **Piotroski F-Score**
   - Nine binary accounting tests separating strong from weak value names; needs financial statements.
   - *Research:* Piotroski (2000), 'Value Investing: The Use of Historical Financial Statement Information', J. Accounting Research 38
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 200 · *Family:* `quality`

25. **Post-Earnings Announcement Drift**
   - Prices underreact to earnings surprises and drift for weeks; needs an earnings calendar.
   - *Research:* Ball & Brown (1968), J. Accounting Research 6(2); Bernard & Thomas (1989), J. Accounting Research 27
   - *Needs:* price only, fundamentals · *Horizon:* swing · *Min bars:* 150 · *Family:* `pead`

26. **Quality Minus Junk**
   - Profitable, growing, safe, well-managed firms outperform; needs fundamentals.
   - *Research:* Asness, Frazzini & Pedersen (2019), 'Quality Minus Junk', Review of Accounting Studies 24
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 200 · *Family:* `quality`

27. **Return Stability (Technical Quality)**
   - Consistency of returns — low drawdown, high hit rate, stable volatility — as a price-only quality read.
   - *Research:* Price-based quality proxy following the 'safety' leg of Asness, Frazzini & Pedersen (2019)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 200 · *Family:* `quality`

28. **Risk Parity Exposure**
   - Equalises risk contribution rather than capital; on a single asset this is inverse-volatility sizing.
   - *Research:* Qian (2005), 'Risk Parity Portfolios'; Maillard, Roncalli & Teiletche (2010), JPM 36(4)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 150 · *Family:* `risk_parity`

29. **Size Effect (SMB)**
   - Small capitalisations earn a premium over large; requires market-cap data across a universe.
   - *Research:* Banz (1981), 'The Relationship Between Return and Market Value of Common Stocks', JFE 9(1)
   - *Needs:* price only, fundamentals, peer universe · *Horizon:* position · *Min bars:* 200 · *Family:* `size`

30. **Size Effect After Controls**
   - Re-examines the size premium once quality and other controls are applied. Needs the cross-section and the control factors.
   - *Research:* Fact, Fiction, and the Size Effect
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 60 · *Family:* `sizeeffectfactfiction`

31. **Systematic Abnormal Return Variation**
   - Measures abnormal return dispersion across a global universe as an inefficiency proxy. Dispersion needs more than one series.
   - *Research:* Systematic Abnormal Return Variation and Global Market Inefficiencies
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 60 · *Family:* `abnormalreturnvariation`

32. **Technical Value (5-Year Mean Reversion)**
   - The price-only value proxy AMP use for assets with no book value: level versus its 5-year average.
   - *Research:* Asness, Moskowitz & Pedersen (2013), 'Value and Momentum Everywhere', JF 68(3) — 5-year reversal definition
   - *Needs:* price only · *Horizon:* position · *Min bars:* 500 · *Family:* `value`

33. **Value (Book-to-Market)**
   - The canonical value factor; requires book equity from fundamentals.
   - *Research:* Fama & French (1993), 'Common Risk Factors in the Returns on Stocks and Bonds', JFE 33(1)
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 200 · *Family:* `value`

34. **Value and Size Effect Instability**
   - The point of the paper is that the cross-sectional premia appear and disappear by sub-period. Needs the cross-section to measure at all.
   - *Research:* Value and Size Effect: Now You See It, Now You Don't
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 60 · *Family:* `valuesizeinstability`

---

## Macro & Allocation

_29 models · 18 families_

1. **Absolute Momentum Filter**
   - Holds only while trailing 12-month return is positive; a pure crash filter.
   - *Research:* Antonacci (2014), 'Absolute Momentum: A Simple Rule-Based Strategy', SSRN 2244633
   - *Needs:* price only · *Horizon:* position · *Min bars:* 280 · *Family:* `taa`

2. **Adaptive Asset Allocation**
   - Combines momentum ranking with minimum-variance weighting inside the selected set.
   - *Research:* Butler, Philbrick, Gordillo & Varadi (2012), 'Adaptive Asset Allocation', SSRN 2328254
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 250 · *Family:* `taa`

3. **All-Weather Risk Parity**
   - Balances risk contribution across growth and inflation quadrants rather than capital.
   - *Research:* Dalio/Bridgewater All Weather; formalised in Asness, Frazzini & Pedersen (2012), FAJ 68(1)
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 250 · *Family:* `risk_parity_panel`

4. **Annuity Demand Portfolio Application**
   - Household portfolio choice including annuities. Requires household balance-sheet and longevity data.
   - *Research:* Explaining low annuity demand: an optimal portfolio application to Japan
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 60 · *Family:* `annuitydemandpuzzle`

5. **Cross-Asset Carry**
   - Buys high-carry and sells low-carry assets across equities, bonds, FX and commodities.
   - *Research:* Koijen, Moskowitz, Pedersen & Vrugt (2018), 'Carry', JFE 127(2)
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 250 · *Family:* `carry_panel`

6. **Defensive Asset Allocation**
   - Uses a small canary universe to time the switch between offensive and defensive sleeves.
   - *Research:* Keller & Keuning (2018), 'Breadth Momentum and the Canary Universe', SSRN 3212862
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 250 · *Family:* `taa`

7. **Defensive Beta Rotation**
   - Rotates between high- and low-beta sleeves based on the prevailing volatility regime.
   - *Research:* Blitz & van Vliet (2007), 'The Volatility Effect', JPM 34(1)
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 250 · *Family:* `rotation`

8. **Drawdown-Scaled Allocation**
   - Constant-proportion portfolio insurance: exposure scales with the cushion above the floor.
   - *Research:* Grossman & Zhou (1993), Math. Finance 3(3); CPPI framework per Black & Perold (1992), JEDC 16(3)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 200 · *Family:* `vol_overlay`

9. **Equal Risk Contribution (ERC)**
   - Solves for weights where every asset contributes identical marginal risk.
   - *Research:* Maillard, Roncalli & Teiletche (2010), 'On the Properties of Equally-Weighted Risk Contributions', JPM 36(4)
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 250 · *Family:* `risk_parity_panel`

10. **Faber 10-Month Timing Model**
   - Hold while price is above its 10-month (≈200-day) moving average, otherwise move to cash. The single most-replicated tactical rule in the literature.
   - *Research:* Faber (2007), 'A Quantitative Approach to Tactical Asset Allocation', JWM 9(4)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 230 · *Family:* `taa`

11. **GTAA Cross-Asset Momentum**
   - Holds each asset only while it trades above its 10-month moving average.
   - *Research:* Faber (2007), 'A Quantitative Approach to Tactical Asset Allocation', JWM 9(4)
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 250 · *Family:* `taa`

12. **Growth-Inflation Quadrant Rotation**
   - Classifies the macro environment into four quadrants and holds the historically best sleeve.
   - *Research:* Four-quadrant framework per Dalio (2015); empirical support in Ilmanen (2011), 'Expected Returns' ch. 27
   - *Needs:* price only, peer universe, benchmark series · *Horizon:* position · *Min bars:* 250 · *Family:* `macro_regime`

13. **Inflation Regime Allocation**
   - Rotates toward commodities and real assets as inflation surprises turn positive.
   - *Research:* Neville, Draaisma, Funnell, Harvey & van Hemert (2021), 'The Best Strategies for Inflationary Times', JPM 47(8)
   - *Needs:* price only, peer universe, benchmark series · *Horizon:* position · *Min bars:* 250 · *Family:* `macro_regime`

14. **Long-Horizon Momentum with Drawdown Brake**
   - Twelve-month momentum, released only while the instrument is not deep in drawdown — the long-run case fails precisely when held through the deepest part.
   - *Research:* Fugazza, Guidolin & Nicodano (2006), 'Investing for the Long-Run in European Real Estate'. Reading: the long-horizon allocation case, with the drawdown condition that makes it survivable.
   - *Needs:* price only · *Horizon:* position · *Min bars:* 300 · *Family:* `longrun_momentum`

15. **Macro Seasonality Overlay**
   - Combines the seasonal calendar tilt with a trend filter so seasonality never fights the trend.
   - *Research:* Bouman & Jacobsen (2002), AER 92(5); Keloharju, Linnainmaa & Nyberg (2016), JF 71(4)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 300 · *Family:* `macro_seasonal`

16. **Maximum Diversification Portfolio**
   - Maximises the ratio of weighted average volatility to portfolio volatility.
   - *Research:* Choueifaty & Coignard (2008), 'Toward Maximum Diversification', JPM 35(1)
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 250 · *Family:* `diversification`

17. **Minimum Variance Portfolio**
   - The lowest-variance point on the efficient frontier; needs no return forecast.
   - *Research:* Clarke, de Silva & Thorley (2006), 'Minimum-Variance Portfolios in the U.S. Equity Market', JPM 33(1)
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 250 · *Family:* `diversification`

18. **Most Diversified Portfolio**
   - Maximises the diversification ratio across holdings. A portfolio construction, not a signal on one instrument.
   - *Research:* Properties of the Most Diversified Portfolio
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 60 · *Family:* `mostdiversifiedportfolio`

19. **Optimal Annuity Risk Management**
   - Optimises annuitisation against mortality and liability risk. Needs actuarial inputs; there is no price series that stands in for them.
   - *Research:* Optimal Annuity Risk Management
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 60 · *Family:* `optimalannuityrisk`

20. **Optimal Reserve Currency Shares**
   - Allocates reserve weights across currencies. A multi-currency allocation, not a single-pair signal.
   - *Research:* Optimal Currency Shares In International Reserves The Impact Of The Euro And The Prospects For The Dollar
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 60 · *Family:* `optimalreservecurrencyshares`

21. **Permanent Portfolio**
   - Equal weights across equities, long bonds, gold and cash — one sleeve performs in each regime.
   - *Research:* Browne (1987), 'Harry Browne's Permanent Portfolio'; analysed in Faber (2015)
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 250 · *Family:* `static_allocation`

22. **Portfolio Rules with Labour Income**
   - Allocation conditioned on human capital. Labour income is not observable in market data.
   - *Research:* Heuristic Portfolio Rules with Labor Income
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 60 · *Family:* `laborincomeheuristics`

23. **Time-Inconsistent Consumption Allocation**
   - Allocation under time-inconsistent preferences with a consumption stream. Needs the consumption side.
   - *Research:* Inconsistent investment and consumption problems
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 60 · *Family:* `inconsistentconsumption`

24. **Trend + Carry Composite**
   - Blends trend and a term-structure carry proxy — the two legs of most macro programmes.
   - *Research:* Baltas & Kosowski (2013), SSRN 2140091; carry leg per Koijen et al. (2018), JFE 127(2)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 280 · *Family:* `multi_signal`

25. **Two-Regime Allocation Switch**
   - Switches between a risk-on trend rule and a risk-off defensive rule based on the volatility state.
   - *Research:* Ang & Bekaert (2004), 'How Regimes Affect Asset Allocation', FAJ 60(2)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 280 · *Family:* `macro_regime`

26. **VaR-Adjusted Sharpe Optimisation**
   - Portfolio weights optimised on a VaR-adjusted objective. Portfolio-level by construction.
   - *Research:* Robust Portfolio Optimization with Value-At-Risk Adjusted Sharpe Ratios
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 60 · *Family:* `varadjustedsharpeoptimization`

27. **Vigilant Asset Allocation**
   - Momentum-ranked offensive sleeve that flips fully defensive on any breadth breakdown.
   - *Research:* Keller & Keuning (2017), 'Breadth Momentum and Vigilant Asset Allocation', SSRN 3002624
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 250 · *Family:* `taa`

28. **Volatility Target Overlay**
   - Scales exposure to hold realised volatility at a constant target; improves Sharpe and cuts tails.
   - *Research:* Harvey, Hoyle, Korgaonkar, Rattray, Sargaison & van Hemert (2018), 'The Impact of Volatility Targeting', JPM 45(1)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 180 · *Family:* `vol_overlay`

29. **Yield Curve Regime Allocation**
   - Shifts allocation on the slope and level of the curve; inversion drives de-risking.
   - *Research:* Estrella & Mishkin (1998), REStat 80(1); allocation use per Ilmanen (2011), 'Expected Returns'
   - *Needs:* price only, peer universe, benchmark series · *Horizon:* position · *Min bars:* 250 · *Family:* `macro_regime`

---

## Crypto Native

_27 models · 16 families_

1. **Altcoin Beta Amplification**
   - Alts amplify BTC moves with a lag; needs a BTC reference series to measure the relationship.
   - *Research:* Liu, Tsyvinski & Wu (2022), JF 77(2) — cross-sectional crypto factor structure
   - *Needs:* price only, benchmark series · *Horizon:* swing · *Min bars:* 150 · *Family:* `rotation`

2. **Bitcoin Dominance Rotation**
   - Capital rotates between BTC and alts through the cycle; needs the dominance series.
   - *Research:* Crypto market-cycle rotation; capital-flow framework per Liu & Tsyvinski (2021), RFS 34(6)
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 200 · *Family:* `rotation`

3. **Blockchain Risk Parity Line**
   - Risk-parity weights across crypto assets. Needs the asset set to weight.
   - *Research:* The Blockchain Risk Parity Line: Moving From The Efficient Frontier To The Final Frontier Of Investments
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 60 · *Family:* `blockchainriskparity`

4. **Cash-and-Carry Basis Trade**
   - Annualised premium of dated futures over spot; the core delta-neutral crypto yield trade.
   - *Research:* Classic carry arbitrage; crypto application per Makarov & Schoar (2020), 'Trading and Arbitrage in Cryptocurrency Markets'
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 120 · *Family:* `funding`

5. **Cross-Exchange Price Spread**
   - Same asset priced differently across venues; needs simultaneous multi-venue quotes.
   - *Research:* Makarov & Schoar (2020), JFE 135(2) — persistent cross-exchange deviations in crypto
   - *Needs:* price only, peer universe · *Horizon:* intraday · *Min bars:* 100 · *Family:* `arbitrage`

6. **Crypto Hodl/Fodl Factor Composite**
   - Holds when medium-horizon momentum is positive and volatility sits below its own history; folds when either fails.
   - *Research:* 'Know When to Hodl Em, Know When to Fodl Em': factor structure in crypto. Reading: the paper's momentum and low-volatility legs, combined on a single series.
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `crypto_factor_composite`

7. **Crypto Time-Series Momentum**
   - Momentum is the dominant documented crypto factor, strongest at the 1-4 week horizon.
   - *Research:* Liu, Tsyvinski & Wu (2022), 'Common Risk Factors in Cryptocurrency', JF 77(2)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 120 · *Family:* `crypto_momentum`

8. **Crypto Volatility Regime**
   - Crypto volatility clusters harder than equities; regime percentile drives exposure directly.
   - *Research:* Katsiampa (2017), 'Volatility Estimation for Bitcoin', Economics Letters 158
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `crypto_vol`

9. **Crypto Weekend Liquidity Effect**
   - Crypto trades continuously but weekend liquidity thins, amplifying moves that partly revert Monday.
   - *Research:* Baur, Cahill, Godfrey & Liu (2019), 'Bitcoin Time-of-Day, Day-of-Week and Month-of-Year Effects', Finance Research Letters 31
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 150 · *Family:* `crypto_seasonal`

10. **Exchange Netflow**
   - Coins moving onto exchanges signal selling intent; withdrawals signal accumulation.
   - *Research:* CryptoQuant exchange flow methodology; academic treatment per Makarov & Schoar (2020), JFE 135(2)
   - *Needs:* price only, on-chain / exchange · *Horizon:* position · *Min bars:* 200 · *Family:* `onchain_flow`

11. **HODL Waves Coin Age Distribution**
   - Age distribution of unspent outputs; old coins moving marks distribution by long-term holders.
   - *Research:* Unchained Capital (2018), 'Bitcoin Data Science: HODL Waves'
   - *Needs:* price only, on-chain / exchange · *Horizon:* position · *Min bars:* 200 · *Family:* `onchain_supply`

12. **Hash Ribbon Miner Capitulation**
   - Hash-rate moving-average crossovers identify miner capitulation and subsequent recovery.
   - *Research:* Edwards (2019), 'Hash Ribbons and Bitcoin Bottoms', Capriole Investments
   - *Needs:* price only, on-chain / exchange · *Horizon:* position · *Min bars:* 200 · *Family:* `onchain_supply`

13. **Liquidation Cascade Reversal** — **PROXY**
   - Forced deleveraging overshoots fundamental value and snaps back once the cascade exhausts.
   - *Research:* Leverage-spiral mechanics per Brunnermeier & Pedersen (2009), 'Market Liquidity and Funding Liquidity', RFS 22(6)
   - *Needs:* price only, volume · *Horizon:* intraday · *Min bars:* 120 · *Family:* `liquidation`
   - *Proxy note:* Real liquidation data comes from exchange liquidation feeds. This detects the price/volume signature of a cascade — violent range expansion on extreme volume with a long wick.

14. **Long/Short Account Ratio**
   - Retail account positioning is a contrarian indicator at extremes; needs exchange positioning data.
   - *Research:* Retail positioning contrarian evidence per Kelley & Tetlock (2013), JF 68(3)
   - *Needs:* price only, on-chain / exchange · *Horizon:* swing · *Min bars:* 120 · *Family:* `derivatives_positioning`

15. **MVRV Ratio**
   - Market value over realised value; above ~3.7 marks cycle tops, below 1 marks capitulation.
   - *Research:* Kalichkin & Coinmetrics (2018), 'Realized Capitalization'; MVRV per Puell & David (2018)
   - *Needs:* price only, on-chain / exchange · *Horizon:* position · *Min bars:* 200 · *Family:* `onchain_valuation`

16. **Miner Position Index**
   - Miner outflows against their one-year average; elevated readings precede supply overhangs.
   - *Research:* CryptoQuant MPI methodology (2020)
   - *Needs:* price only, on-chain / exchange · *Horizon:* position · *Min bars:* 200 · *Family:* `onchain_supply`

17. **NVT Ratio (Network Value to Transactions)**
   - The crypto analogue of a P/E ratio: network value against on-chain transaction throughput.
   - *Research:* Woo (2017), 'Introducing NVT Ratio'; NVT Signal per Kalichkin (2018)
   - *Needs:* price only, on-chain / exchange · *Horizon:* position · *Min bars:* 200 · *Family:* `onchain_valuation`

18. **Open Interest Price Divergence**
   - Rising open interest against a flat price means leverage is building without conviction.
   - *Research:* Bessembinder & Seguin (1993), JFQA 28(1); crypto application per Alexander & Heck (2020)
   - *Needs:* price only, on-chain / exchange · *Horizon:* swing · *Min bars:* 120 · *Family:* `derivatives_positioning`

19. **Perpetual Funding Rate Carry**
   - Extreme funding marks crowded positioning and is the single most reliable crypto contrarian signal.
   - *Research:* Perpetual swap mechanism per BitMEX (2016); basis-trade analysis per Makarov & Schoar (2020), JFE 135(2)
   - *Needs:* price only, on-chain / exchange · *Horizon:* swing · *Min bars:* 120 · *Family:* `funding`

20. **Puell Multiple**
   - Daily miner issuance value against its yearly average; captures supply-side pressure.
   - *Research:* Puell (2019), 'The Puell Multiple'
   - *Needs:* price only, on-chain / exchange · *Horizon:* position · *Min bars:* 200 · *Family:* `onchain_supply`

21. **Skew-Conditioned Momentum**
   - Momentum taken only where realised skew is not lottery-like; the paper attributes the premium to preference for positive skew.
   - *Research:* 'Do Risk Preferences Drive Momentum in Cryptocurrencies?' — momentum attributed to lottery preference. Reading: condition momentum on realised skew, its observable footprint.
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 220 · *Family:* `skew_momentum`

22. **Spent Output Profit Ratio**
   - Whether coins moving on-chain are realising profit or loss; SOPR crossing 1 is a regime marker.
   - *Research:* Shirakashi (2019), 'Spent Output Profit Ratio', Unchained Capital
   - *Needs:* price only, on-chain / exchange · *Horizon:* position · *Min bars:* 200 · *Family:* `onchain_flow`

23. **Stablecoin Supply Ratio**
   - Ratio of crypto market cap to stablecoin supply — a measure of available dry powder.
   - *Research:* Glassnode (2020), 'Stablecoin Supply Ratio' methodology
   - *Needs:* price only, on-chain / exchange · *Horizon:* position · *Min bars:* 200 · *Family:* `onchain_valuation`

24. **Thermocap Multiple**
   - Market cap against cumulative miner revenue — a floor-valuation measure.
   - *Research:* Nick Emblow / Coinmetrics (2019), 'Thermocap' security-spend valuation
   - *Needs:* price only, on-chain / exchange · *Horizon:* position · *Min bars:* 200 · *Family:* `onchain_valuation`

25. **Transactional Demand Proxy**
   - Rising turnover against steady volatility suggests use rather than speculation; the paper ties that to subsequent strength.
   - *Research:* 'Cryptocurrency as money: A trading strategy solution' — value as a medium of exchange rather than a store. Reading: turnover relative to volatility as an observable proxy for transactional use.
   - *Needs:* price only, volume · *Horizon:* swing · *Min bars:* 180 · *Family:* `transactional_demand`

26. **Triangular Arbitrage**
   - Detects inconsistency across three pairs on one venue; needs all three legs simultaneously.
   - *Research:* Classic FX triangular arbitrage; crypto measurement per Makarov & Schoar (2020)
   - *Needs:* price only, peer universe · *Horizon:* intraday · *Min bars:* 100 · *Family:* `arbitrage`

27. **Volume Profile Value Area**
   - Price reverts toward the volume-weighted value area where the most business was transacted.
   - *Research:* Steidlmayer & Koy (1986), 'Markets and Market Logic' — Market Profile theory
   - *Needs:* price only, volume · *Horizon:* swing · *Min bars:* 150 · *Family:* `volume_profile`

---

## Mean Reversion

_25 models · 19 families_

1. **Average Daily Range Exhaustion**
   - Fades a bar that has already travelled a multiple of its typical range — moves rarely extend indefinitely.
   - *Research:* Crabel (1990) range expansion; ATR framework per Wilder (1978)
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 60 · *Family:* `range_exhaustion`

2. **Bollinger Band Mean Reversion**
   - Fades price at the standard-deviation envelope, scaled by how far outside the band it trades.
   - *Research:* Bollinger (2001), 'Bollinger on Bollinger Bands'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 60 · *Family:* `bollinger`

3. **Bollinger Squeeze Release**
   - Detects Bollinger bands compressing inside Keltner channels, then trades the expansion direction.
   - *Research:* Bollinger (2001) squeeze; Carter (2005), 'Mastering the Trade' TTM Squeeze
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 90 · *Family:* `squeeze`

4. **Commodity Channel Index Reversion**
   - Deviation of typical price from its mean in units of mean absolute deviation.
   - *Research:* Lambert (1980), 'Commodity Channel Index', Commodities magazine
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 60 · *Family:* `cci`

5. **Connors RSI Composite**
   - Blends price RSI, a streak-length RSI and a percent-rank of returns into one reversion score.
   - *Research:* Connors, Alvarez & Radtke (2012), 'An Introduction to ConnorsRSI'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 80 · *Family:* `rsi_reversion`

6. **Fat-Tail Move Reversion**
   - Fades returns in the extreme tail of their own distribution, where overreaction is most likely.
   - *Research:* Mandelbrot (1963), 'The Variation of Certain Speculative Prices', J. Business 36(4)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 120 · *Family:* `tail_reversion`

7. **Half-Life Gated Reversion**
   - Only fades the mean when the estimated OU half-life is short enough to revert within the holding period.
   - *Research:* Ornstein-Uhlenbeck half-life estimation per Chan (2013); OU process from Uhlenbeck & Ornstein (1930)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 140 · *Family:* `zscore`

8. **Keltner Channel Reversion**
   - Fades ATR-envelope excursions — an ATR band is less regime-sensitive than a stdev band.
   - *Research:* Keltner (1960); ATR envelope variant per Chester Keltner / Linda Raschke
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 60 · *Family:* `channel_reversion`

9. **Long-Term Reversal (De Bondt-Thaler)**
   - Fades multi-year extremes — overreaction unwinds at the 3-5 year horizon.
   - *Research:* De Bondt & Thaler (1985), 'Does the Stock Market Overreact?', JF 40(3)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 500 · *Family:* `reversal`

10. **Money Flow Index Reversion**
   - Volume-weighted RSI; distinguishes exhaustion backed by real flow from a drift on thin volume.
   - *Research:* Quong & Soudack (1989), 'Volume-Weighted RSI: Money Flow', Technical Analysis of Stocks & Commodities
   - *Needs:* price only, volume · *Horizon:* swing · *Min bars:* 60 · *Family:* `volume_osc`

11. **Opening Range Reversal**
   - Fades an extended move away from the session open when it stalls.
   - *Research:* Crabel (1990), 'Day Trading with Short Term Price Patterns and Opening Range Breakout'
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 60 · *Family:* `gap`

12. **Overnight Gap Fade**
   - Fades the opening gap; overnight and intraday returns are systematically opposed.
   - *Research:* Lou, Polk & Skouras (2019), 'A Tug of War: Overnight vs Intraday Expected Returns', JFE 134(1)
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 80 · *Family:* `gap`

13. **Overreaction Reversal (Extreme Bars)**
   - Identifies bars beyond a rolling volatility threshold and takes the documented next-period reversal.
   - *Research:* 'Price Overreactions in the Cryptocurrency Market'. Reading: the paper's event definition — a move beyond a rolling threshold — and the reversal that follows it.
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 160 · *Family:* `overreaction`

14. **Pairs Spread Reversion**
   - Z-score of the normalised spread against a matched partner; the canonical relative-value trade.
   - *Research:* Gatev, Goetzmann & Rouwenhorst (2006), 'Pairs Trading', RFS 19(3)
   - *Needs:* price only, peer universe · *Horizon:* swing · *Min bars:* 120 · *Family:* `pairs`

15. **Post-Streak Overbetting Fade**
   - Counts consecutive same-direction bars and fades the extension, on the finding that bet size rises irrationally after a run.
   - *Research:* 'Rational Decision-Making Under Uncertainty: Observed Betting Patterns on a Biased Coin' — participants over-bet after runs. Reading: fade the extension that follows a streak.
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 150 · *Family:* `streak_overbet`

16. **Price Z-Score Reversion**
   - Canonical mean-reversion signal: standardised distance of price from its rolling mean.
   - *Research:* Chan (2013), 'Algorithmic Trading: Winning Strategies and Their Rationale', ch. 3
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 60 · *Family:* `zscore`

17. **RSI Regular Divergence**
   - Price makes a new extreme that momentum does not confirm — the classic exhaustion tell.
   - *Research:* Wilder (1978); divergence framework per Murphy (1999), 'Technical Analysis of the Financial Markets'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 90 · *Family:* `divergence`

18. **RSI(2) Extreme Reversion**
   - Very short RSI above a long-trend filter — buys deep oversold dips inside an uptrend.
   - *Research:* Connors & Alvarez (2008), 'Short Term Trading Strategies That Work'
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 220 · *Family:* `rsi_reversion`

19. **Range-Bound Channel Oscillator**
   - Fades the edges of a horizontal channel, gated on the market actually being range-bound.
   - *Research:* Donchian channel framework applied to reversion per Kaufman (2013), 'Trading Systems and Methods'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 90 · *Family:* `channel_reversion`

20. **Short-Term Reversal (1-Period)**
   - Fades the most recent return — documented negative autocorrelation at the weekly and monthly horizon.
   - *Research:* Jegadeesh (1990), JF 45(3); Lehmann (1990), QJE 105(1)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 80 · *Family:* `reversal`

21. **Stochastic Oscillator Reversion**
   - Position of the close within its recent range; extremes mark exhaustion of the current swing.
   - *Research:* Lane (1950s); formalised in Lane (1984), Technical Analysis of Stocks & Commodities
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 60 · *Family:* `stochastic`

22. **TD Sequential Setup Count**
   - Counts consecutive closes versus the close four bars prior; a completed 9-count marks exhaustion.
   - *Research:* DeMark (1994), 'The New Science of Technical Analysis'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 60 · *Family:* `demark`

23. **Ultimate Oscillator**
   - Weighted blend of three lookbacks, built to avoid the false divergences of single-period oscillators.
   - *Research:* Williams (1985), 'The Ultimate Oscillator', Technical Analysis of Stocks & Commodities
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 80 · *Family:* `multi_period_osc`

24. **VWAP Reversion**
   - Fades displacement from volume-weighted average price, the standard institutional execution benchmark.
   - *Research:* Berkowitz, Logue & Noser (1988), 'The Total Cost of Transactions on the NYSE', JF 43(1)
   - *Needs:* price only, volume · *Horizon:* intraday · *Min bars:* 60 · *Family:* `vwap`

25. **Williams %R Reversion**
   - Inverted range position; reads momentum failure at the edge of the recent range.
   - *Research:* Williams (1973), 'How I Made One Million Dollars Last Year Trading Commodities'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 60 · *Family:* `stochastic`

---

## Sentiment & Alt Data

_24 models · 13 families_

1. **Analyst Revision Momentum**
   - Earnings-estimate revisions drift in the direction of the revision for several months.
   - *Research:* Chan, Jegadeesh & Lakonishok (1996), 'Momentum Strategies', JF 51(5); Womack (1996), JF 51(1)
   - *Needs:* price only, fundamentals · *Horizon:* swing · *Min bars:* 120 · *Family:* `analyst`

2. **Annual Report Risk Language**
   - Changes in risk-factor language year over year predict subsequent volatility.
   - *Research:* Campbell, Chen, Dhaliwal, Lu & Steele (2014), 'The Information Content of Mandatory Risk Factor Disclosures', RAS 19
   - *Needs:* price only, news / alt-data, fundamentals · *Horizon:* swing · *Min bars:* 120 · *Family:* `text`

3. **Capitulation Volume Climax**
   - Extreme volume on a wide down bar that closes strongly marks forced-seller exhaustion.
   - *Research:* Selling-climax framework per Wyckoff (1931); volume-climax evidence per Gervais, Kaniel & Mingelgrin (2001), JF 56(3)
   - *Needs:* price only, volume · *Horizon:* swing · *Min bars:* 150 · *Family:* `capitulation`

4. **Credit Spread Risk Appetite**
   - Widening credit spreads lead equity weakness; the excess bond premium is the sharpest form.
   - *Research:* Gilchrist & Zakrajšek (2012), 'Credit Spreads and Business Cycle Fluctuations', AER 102(4)
   - *Needs:* price only, benchmark series · *Horizon:* swing · *Min bars:* 120 · *Family:* `macro_sentiment`

5. **Earnings Call Linguistic Tone**
   - Finance-specific sentiment lexicons applied to transcripts predict post-call drift.
   - *Research:* Loughran & McDonald (2011), 'When Is a Liability Not a Liability?', JF 66(1)
   - *Needs:* price only, news / alt-data, fundamentals · *Horizon:* swing · *Min bars:* 120 · *Family:* `text`

6. **Geolocation Footfall Signal**
   - Parking-lot and foot-traffic counts anticipate retail revenue prints; needs a geolocation vendor.
   - *Research:* Katona, Painter, Patatoukas & Zeng (2018), 'On the Capital Market Consequences of Alternative Data'
   - *Needs:* price only, fundamentals · *Horizon:* swing · *Min bars:* 120 · *Family:* `alt_data`

7. **Hiring Activity Signal**
   - Job-posting growth leads revenue growth by one to two quarters; needs a postings feed.
   - *Research:* Gutiérrez, Jegadeesh & Kim (2021), 'Job Postings and Firm Fundamentals'
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 120 · *Family:* `alt_data`

8. **Insider Transaction Signal**
   - Opportunistic insider purchases carry genuine information; routine trades do not.
   - *Research:* Lakonishok & Lee (2001), 'Are Insider Trades Informative?', RFS 14(1); Cohen, Malloy & Pomorski (2012), JF 67(3)
   - *Needs:* price only, fundamentals · *Horizon:* swing · *Min bars:* 120 · *Family:* `positioning`

9. **Institutional Ownership Change**
   - Changes in 13F institutional holdings predict returns, subject to a reporting lag.
   - *Research:* Gompers & Metrick (2001), 'Institutional Investors and Equity Prices', QJE 116(1)
   - *Needs:* price only, fundamentals · *Horizon:* swing · *Min bars:* 120 · *Family:* `positioning`

10. **Market-Wide Sentiment Index**
   - Composite market sentiment predicts the cross-section, most strongly for hard-to-value stocks.
   - *Research:* Baker & Wurgler (2006), 'Investor Sentiment and the Cross-Section of Stock Returns', JF 61(4)
   - *Needs:* price only, news / alt-data · *Horizon:* swing · *Min bars:* 120 · *Family:* `market_sentiment`

11. **Media Tone Propagation**
   - Trades the spread of news tone across markets. Needs a news feed with timestamps and coverage.
   - *Research:* Media Tone Goes Viral: Global Evidence from the Currency Market
   - *Needs:* price only, news / alt-data · *Horizon:* position · *Min bars:* 60 · *Family:* `mediatoneviral`

12. **Media Tone Time-Series and Cross-Section**
   - Separates the time-series from the cross-sectional component of news tone. Needs both a news feed and a currency cross-section.
   - *Research:* Is Media Tone just a Tone? Time-Series and Cross-Sectional Evidence from the Currency Market
   - *Needs:* price only, news / alt-data · *Horizon:* position · *Min bars:* 60 · *Family:* `mediatonetimeseries`

13. **News Sentiment Tone**
   - Negative media tone predicts short-horizon downward pressure followed by reversion.
   - *Research:* Tetlock (2007), 'Giving Content to Investor Sentiment', JF 62(3)
   - *Needs:* price only, news / alt-data · *Horizon:* swing · *Min bars:* 120 · *Family:* `news`

14. **News Volume Attention Shock**
   - Abnormal news volume drives retail attention-based buying that subsequently reverses.
   - *Research:* Barber & Odean (2008), 'All That Glitters: Attention and News', RFS 21(2)
   - *Needs:* price only, news / alt-data · *Horizon:* swing · *Min bars:* 120 · *Family:* `news`

15. **Patent Innovation Signal**
   - Market-value-weighted patent output predicts long-horizon returns; needs a patent database.
   - *Research:* Kogan, Papanikolaou, Seru & Stoffman (2017), 'Technological Innovation, Resource Allocation and Growth', QJE 132(2)
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 120 · *Family:* `alt_data`

16. **Price-Based Fear & Greed Composite** — **PROXY**
   - Blends the four price-derived Fear & Greed components — momentum, strength, breadth proxy and volatility — into a contrarian composite.
   - *Research:* Composite construction after CNN Business Fear & Greed methodology (price-derived components only)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 280 · *Family:* `market_sentiment`
   - *Proxy note:* The published index also uses put/call ratios, junk-bond demand and safe-haven flows. This uses only the price-derived components, so it is a partial reconstruction, not the index itself.

17. **Retail Order Flow Imbalance**
   - Retail order imbalance predicts returns positively at the weekly horizon, then reverses.
   - *Research:* Boehmer, Jones, Zhang & Zhang (2021), 'Tracking Retail Investor Activity', JF 76(5)
   - *Needs:* price only, news / alt-data · *Horizon:* swing · *Min bars:* 120 · *Family:* `retail`

18. **Search Volume Attention**
   - Rising search interest in financial terms preceded market declines in the published sample.
   - *Research:* Preis, Moat & Stanley (2013), 'Quantifying Trading Behavior Using Google Trends', Scientific Reports 3
   - *Needs:* price only, news / alt-data · *Horizon:* swing · *Min bars:* 120 · *Family:* `search`

19. **Short Interest Ratio**
   - High short interest with low lending supply predicts underperformance; needs a short-interest feed.
   - *Research:* Asquith, Pathak & Ritter (2005), 'Short Interest, Institutional Ownership and Stock Returns', JFE 78(2)
   - *Needs:* price only, fundamentals · *Horizon:* swing · *Min bars:* 120 · *Family:* `positioning`

20. **Social Media Sentiment**
   - Aggregate social mood carries short-horizon predictive content, strongest for retail-heavy names.
   - *Research:* Bollen, Mao & Zeng (2011), 'Twitter Mood Predicts the Stock Market', J. Computational Science 2(1)
   - *Needs:* price only, news / alt-data · *Horizon:* swing · *Min bars:* 120 · *Family:* `social`

21. **Supply Chain Activity Signal**
   - Customer-firm performance predicts supplier returns with a lag; needs a supply-chain graph.
   - *Research:* Cohen & Frazzini (2008), 'Economic Links and Predictable Returns', JF 63(4)
   - *Needs:* price only, fundamentals, peer universe · *Horizon:* swing · *Min bars:* 120 · *Family:* `alt_data`

22. **Survey Sentiment Contrarian**
   - Extreme bullishness in investor surveys is a contrarian indicator at multi-month horizons.
   - *Research:* Brown & Cliff (2005), 'Investor Sentiment and Asset Valuation', J. Business 78(2)
   - *Needs:* price only, news / alt-data · *Horizon:* swing · *Min bars:* 120 · *Family:* `market_sentiment`

23. **Volatility Fear Gauge**
   - Volatility spikes mark fear; extreme readings have historically been buy points, not sell points.
   - *Research:* Whaley (2000), 'The Investor Fear Gauge', JPM 26(3)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 250 · *Family:* `market_sentiment`

24. **Wikipedia Page View Attention**
   - Page views on company articles proxy retail attention ahead of price moves.
   - *Research:* Moat, Curme, Avakian, Kenett, Stanley & Preis (2013), 'Quantifying Wikipedia Usage Patterns', Scientific Reports 3
   - *Needs:* price only, news / alt-data · *Horizon:* swing · *Min bars:* 120 · *Family:* `search`

---

## Statistical Arbitrage

_23 models · 17 families_

1. **ADF Stationarity-Gated Reversion**
   - Runs a rolling unit-root regression and only fades the mean when the series tests stationary.
   - *Research:* Dickey & Fuller (1979), JASA 74(366); Said & Dickey (1984), Biometrika 71(3)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 160 · *Family:* `cointegration`

2. **Avellaneda-Lee Residual s-Score**
   - Trades the s-score of an OU-fitted residual from a factor regression — the modern stat-arb standard.
   - *Research:* Avellaneda & Lee (2010), 'Statistical Arbitrage in the U.S. Equities Market', Quant. Finance 10(7)
   - *Needs:* price only, benchmark series · *Horizon:* swing · *Min bars:* 150 · *Family:* `residual_statarb`

3. **Bayesian Posterior Fair Value**
   - Blends a long-window prior with recent observations by precision weighting, then fades the gap.
   - *Research:* Standard conjugate Normal-Normal updating; financial application per Rachev et al. (2008)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 120 · *Family:* `bayesian`

4. **Box-Tiao Canonical Decomposition**
   - Extracts the most predictable linear combination of a price panel rather than the least volatile.
   - *Research:* Box & Tiao (1977), Biometrika 64(2); portfolio use per d'Aspremont (2011), Quant. Finance 11(3)
   - *Needs:* price only, peer universe · *Horizon:* swing · *Min bars:* 150 · *Family:* `cointegration`

5. **CUSUM Structural Break Filter**
   - Symmetric CUSUM filter that fires only on statistically significant cumulative displacement.
   - *Research:* Page (1954), 'Continuous Inspection Schemes', Biometrika 41(1-2); López de Prado (2018) AFML ch. 2
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 120 · *Family:* `changepoint`

6. **Copula Tail Dependence**
   - Uses the empirical copula of return and momentum ranks to find joint-distribution mispricings.
   - *Research:* Xie, Liew, Wu & Zou (2016), 'Pairs Trading with Copulas', J. Trading 11(3)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 140 · *Family:* `copula`

7. **Engle-Granger Cointegration Spread**
   - Regresses one leg on the other, tests the residual for stationarity, and trades its z-score.
   - *Research:* Engle & Granger (1987), 'Co-integration and Error Correction', Econometrica 55(2)
   - *Needs:* price only, peer universe · *Horizon:* swing · *Min bars:* 150 · *Family:* `cointegration`

8. **Financial Turbulence Index**
   - Mahalanobis distance of current returns from their historical distribution; high turbulence cuts risk.
   - *Research:* Kritzman & Li (2010), 'Skulls, Financial Turbulence, and Risk Management', FAJ 66(5)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 160 · *Family:* `turbulence`

9. **Fractionally Differentiated Price**
   - Differentiates just enough to reach stationarity while preserving memory that a first difference destroys.
   - *Research:* Hosking (1981), Biometrika 68(1); financial application per López de Prado (2018), AFML ch. 5
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 160 · *Family:* `frac_diff`

10. **Hurst Exponent Regime Switch**
   - H<0.5 selects reversion, H>0.5 selects continuation, with conviction scaled by distance from 0.5.
   - *Research:* Hurst (1951); Mandelbrot & Wallis (1969); modified R/S per Lo (1991), Econometrica 59(5)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 160 · *Family:* `hurst`

11. **Johansen Multivariate Cointegration**
   - Maximum-likelihood cointegration across three or more legs; finds spreads pairwise tests miss.
   - *Research:* Johansen (1988), J. Economic Dynamics and Control 12(2-3); Johansen (1991), Econometrica 59(6)
   - *Needs:* price only, peer universe · *Horizon:* swing · *Min bars:* 200 · *Family:* `cointegration`

12. **Kalman Filter State Estimate**
   - Recursive optimal estimate of the latent fair value; trades price displacement from that state.
   - *Research:* Kalman (1960), 'A New Approach to Linear Filtering'; trading use per Chan (2013) ch. 3
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 80 · *Family:* `kalman`

13. **Lo-MacKinlay Variance Ratio**
   - Measures whether the series trends or reverts, then applies the matching signal — a regime switch, not a directional bet.
   - *Research:* Lo & MacKinlay (1988), 'Stock Market Prices Do Not Follow Random Walks', RFS 1(1)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 150 · *Family:* `variance_ratio`

14. **Ornstein-Uhlenbeck Process Fit**
   - Fits dP = θ(μ-P)dt + σdW by regression and trades displacement scaled by the fitted noise.
   - *Research:* Uhlenbeck & Ornstein (1930); trading application per Bertram (2010), Physica A 389(11)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 140 · *Family:* `ou_process`

15. **PCA Residual Arbitrage**
   - Removes common principal-component exposure and trades the idiosyncratic remainder.
   - *Research:* Avellaneda & Lee (2010); eigenportfolio construction per Litterman & Scheinkman (1991)
   - *Needs:* price only, peer universe · *Horizon:* swing · *Min bars:* 150 · *Family:* `residual_statarb`

16. **Random Matrix Theory Denoised Signal**
   - Filters correlation eigenvalues against the Marchenko-Pastur bound to keep only real structure.
   - *Research:* Laloux, Cizeau, Bouchaud & Potters (1999), 'Noise Dressing of Financial Correlation Matrices', PRL 83(7)
   - *Needs:* price only, peer universe · *Horizon:* swing · *Min bars:* 200 · *Family:* `rmt`

17. **Return Autocorrelation Sign**
   - Estimates first-order return autocorrelation and applies continuation or reversal to match its sign.
   - *Research:* Fama (1970), 'Efficient Capital Markets', JF 25(2); Campbell, Lo & MacKinlay (1997) ch. 2
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 140 · *Family:* `autocorrelation`

18. **Roll-Adjusted Term Structure Carry**
   - Trades the sign of the term-structure slope; carry is a distinct premium from momentum and value.
   - *Research:* Koijen, Moskowitz, Pedersen & Vrugt (2018), 'Carry', JFE 127(2)
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 120 · *Family:* `carry`

19. **Rolling Beta Dislocation**
   - Flags when realised beta diverges sharply from its own history — the relationship has broken, not the price.
   - *Research:* Fama & MacBeth (1973), JPE 81(3); rolling-beta estimation per Lewellen & Nagel (2006), JFE 82(2)
   - *Needs:* price only, benchmark series · *Horizon:* swing · *Min bars:* 180 · *Family:* `residual_statarb`

20. **Shape-Matched Reversal Template**
   - Correlates the normalised recent path against V-shaped and inverted-V reversal templates.
   - *Research:* Berndt & Clifford (1994) DTW; financial pattern matching per Lo, Mamaysky & Wang (2000), JF 55(4)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 80 · *Family:* `pattern_match`

21. **Two-State Gaussian Regime Filter**
   - Classifies each bar into a calm or turbulent state from volatility and drift, then trades accordingly.
   - *Research:* Hamilton (1989), 'A New Approach to the Economic Analysis of Nonstationary Time Series', Econometrica 57(2)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 150 · *Family:* `regime_switch`

22. **Volatility-Conditional Spread Trade**
   - Sizes the reversion trade inversely to the volatility regime — spreads widen before they converge.
   - *Research:* Ang & Bekaert (2002), 'International Asset Allocation with Regime Shifts', RFS 15(4)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 150 · *Family:* `regime_switch`

23. **Whitened Return Residual**
   - Strips the AR(1) component from returns and trades the residual — the innovation rather than the persistence.
   - *Research:* 'Statistical and Economic Benefits of Whitening Residuals in Bond Yields'. Reading: remove the autocorrelated component and trade what is left, which is the part not already priced.
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 200 · *Family:* `whitened_residual`

---

## Machine Learning

_22 models · 16 families_

1. **Bagged Signal Ensemble**
   - Averages parameter-perturbed copies of one signal so the reading is not an artefact of one lookback.
   - *Research:* Breiman (1996), 'Bagging Predictors', Machine Learning 24(2); sequential bootstrap per López de Prado (2018) ch. 4
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `tree_ensemble`

2. **Bayesian Online Change Point Detection**
   - Tracks run-length posterior over the regime; a collapse means the old statistics no longer apply.
   - *Research:* Adams & MacKay (2007), 'Bayesian Online Changepoint Detection', arXiv:0710.3742
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 160 · *Family:* `changepoint`

3. **Bayesian Uncertainty-Weighted Signal**
   - Ensemble disagreement stands in for posterior variance; conviction falls when the models disagree.
   - *Research:* Blundell, Cornebise, Kavukcuoglu & Wierstra (2015), 'Weight Uncertainty in Neural Networks', ICML
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 180 · *Family:* `bayesian_ml`

4. **Convolutional Order Book Classifier**
   - CNN over limit-order-book snapshots; requires L2 depth and stands down without it.
   - *Research:* Zhang, Zohren & Roberts (2019), 'DeepLOB', IEEE Trans. Signal Processing 67(11)
   - *Needs:* price only, L2 order book · *Horizon:* intraday · *Min bars:* 200 · *Family:* `deep_learning`

5. **Direct Reinforcement Policy**
   - Learns position directly by ascending the differential Sharpe ratio, with no intermediate forecast.
   - *Research:* Moody & Saffell (2001), 'Learning to Trade via Direct Reinforcement', IEEE Trans. Neural Networks 12(4)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `reinforcement`

6. **Elastic Net Feature Selection**
   - L1+L2 penalty via coordinate descent; the L1 term drops features that carry no signal.
   - *Research:* Zou & Hastie (2005), 'Regularization and Variable Selection via the Elastic Net', JRSS-B 67(2)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 220 · *Family:* `linear_learner`

7. **End-to-End Variance Minimisation**
   - Cleans a large covariance matrix and optimises against it. Requires a covariance matrix, which requires many assets.
   - *Research:* End-To-End Large Portfolio Optimization For Variance Minimization With Neural Networks Through Covariance Cleaning
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 60 · *Family:* `endtoendvarianceminimization`

8. **Evolved Rule Combination**
   - Weights a fixed rule population by trailing realised performance — selection without re-derivation.
   - *Research:* Allen & Karjalainen (1999), 'Using Genetic Algorithms to Find Technical Trading Rules', JFE 51(2)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `evolutionary`

9. **Gaussian Process Posterior Mean**
   - Kernel-weighted forecast where the posterior variance sizes the position — uncertain means small.
   - *Research:* Rasmussen & Williams (2006), 'Gaussian Processes for Machine Learning'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 160 · *Family:* `bayesian_ml`

10. **Gradient Boosted Stumps**
   - Sequentially fits stumps to the residual, so each learner corrects the previous ensemble's errors.
   - *Research:* Friedman (2001), 'Greedy Function Approximation', Annals of Statistics 29(5); Chen & Guestrin (2016) XGBoost
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 220 · *Family:* `tree_ensemble`

11. **Isolation Forest Anomaly Score**
   - Scores how easily the current bar is isolated across features; anomalies revert more often than they persist.
   - *Research:* Liu, Ting & Zhou (2008), 'Isolation Forest', IEEE ICDM
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 160 · *Family:* `anomaly`

12. **K-Means Market Regime Clustering**
   - Assigns each bar to a volatility/trend cluster and applies the behaviour historically best in that cluster.
   - *Research:* MacQueen (1967); financial regime application per Ahmed, Chen & Zhang (2020)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `clustering`

13. **K-Nearest Neighbour Historical Analog**
   - Finds the closest historical matches to the current pattern and averages what followed them.
   - *Research:* Cover & Hart (1967), IEEE Trans. Information Theory 13(1); financial analogs per Farmer & Sidorowich (1987)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 250 · *Family:* `instance_based`

14. **Linear SVM Decision Boundary**
   - Online hinge-loss classifier trained by sub-gradient descent; margin distance becomes conviction.
   - *Research:* Cortes & Vapnik (1995), 'Support-Vector Networks', Machine Learning 20(3)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 220 · *Family:* `linear_learner`

15. **Machine-Learning Implied Risk Premia**
   - Compares theory-based and ML-implied premia across a panel of stocks. Needs the panel.
   - *Research:* Diverging roads: Theory-based vs. machine learning-implied stock risk premia
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 60 · *Family:* `mlimpliedriskpremia`

16. **Model Disagreement Caution**
   - Compares three volatility estimators of the same series; wide disagreement between them is treated as model risk and cuts conviction rather than setting direction.
   - *Research:* 'A Theory of Model Sophistication and Operational Risk' — more sophisticated models carry more operational risk. Reading: when estimators of the same quantity disagree, trust the reading less.
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `model_disagreement`

17. **Mutual Information Feature Gate**
   - Keeps only features carrying measurable information about forward returns, unlike linear correlation.
   - *Research:* Kraskov, Stögbauer & Grassberger (2004), 'Estimating Mutual Information', Phys. Rev. E 69(6)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 220 · *Family:* `information_theory`

18. **Online Ridge Regression**
   - Recursive least squares with L2 shrinkage, refit every bar on data available up to that bar.
   - *Research:* Hoerl & Kennard (1970), Technometrics 12(1); online form per Cesa-Bianchi & Lugosi (2006)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `linear_learner`

19. **Random Forest Ensemble Vote**
   - Bagged decision stumps over the feature block; each stump splits one feature at its rolling median.
   - *Research:* Breiman (2001), 'Random Forests', Machine Learning 45(1)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `tree_ensemble`

20. **Recurrent Momentum Filter**
   - Leaky-integrator recurrence over normalised returns — the gated-memory mechanism without offline training.
   - *Research:* Hochreiter & Schmidhuber (1997) LSTM; financial application per Fischer & Krauss (2018), EJOR 270(2)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 160 · *Family:* `recurrent`

21. **Shannon Entropy Predictability Filter**
   - Low entropy in the return-sign sequence means structure is present and worth trading.
   - *Research:* Shannon (1948); market application per Molgedey & Ebeling (2000), Physica A 287(3-4)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 160 · *Family:* `information_theory`

22. **Triple-Barrier Meta-Labeling**
   - A secondary model that decides whether to act on the primary signal, sizing bets by hit probability.
   - *Research:* López de Prado (2018), 'Advances in Financial Machine Learning', ch. 3
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `meta_labeling`

---

## Microstructure

_22 models · 14 families_

1. **Almgren-Chriss Temporary Impact**
   - Separates temporary from permanent impact; temporary impact reverts and is therefore tradeable.
   - *Research:* Almgren & Chriss (2000), 'Optimal Execution of Portfolio Transactions', J. Risk 3(2)
   - *Needs:* price only, volume · *Horizon:* intraday · *Min bars:* 100 · *Family:* `price_impact`

2. **Amihud Illiquidity Ratio**
   - Absolute return per unit of dollar volume; the standard low-frequency illiquidity measure.
   - *Research:* Amihud (2002), 'Illiquidity and Stock Returns', J. Financial Markets 5(1)
   - *Needs:* price only, volume · *Horizon:* swing · *Min bars:* 100 · *Family:* `liquidity`

3. **Avellaneda-Stoikov Reservation Price** — **PROXY**
   - Inventory-adjusted reservation price; the canonical optimal market-making quote framework.
   - *Research:* Avellaneda & Stoikov (2008), 'High-Frequency Trading in a Limit Order Book', Quant. Finance 8(3)
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 100 · *Family:* `market_making`
   - *Proxy note:* Full model requires live inventory and a quoted book. This computes the reservation-price skew from volatility and a mean-reverting inventory proxy only.

4. **Bid-Ask Bounce Reversal**
   - Single-bar reversal driven by transacting alternately at bid and ask rather than by information.
   - *Research:* Blume & Stambaugh (1983), 'Biases in Computed Returns', JFE 12(3)
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 80 · *Family:* `spread`

5. **Closing Auction Pressure**
   - Index-rebalance and MOC flow concentrates at the close and typically reverses the next open.
   - *Research:* Bogousslavsky & Muravyev (2023), 'Who Trades at the Close?', J. Financial Economics
   - *Needs:* price only, volume · *Horizon:* intraday · *Min bars:* 100 · *Family:* `auction`

6. **Corwin-Schultz High-Low Spread**
   - Recovers the spread from two-day high-low ratios; works where tick data is unavailable.
   - *Research:* Corwin & Schultz (2012), 'A Simple Way to Estimate Bid-Ask Spreads', JF 67(2)
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 80 · *Family:* `spread`

7. **Glosten-Milgrom Adverse Selection** — **PROXY**
   - Spread widening driven by informed-trader risk; persistent directional flow signals information.
   - *Research:* Glosten & Milgrom (1985), 'Bid, Ask and Transaction Prices', JFE 14(1)
   - *Needs:* price only, volume · *Horizon:* intraday · *Min bars:* 100 · *Family:* `flow_toxicity`
   - *Proxy note:* Uses run-length of same-direction bars as the informed-flow proxy in place of quote revisions.

8. **Hasbrouck Information Share**
   - Attributes price discovery across venues; requires simultaneous quotes from two or more markets.
   - *Research:* Hasbrouck (1995), 'One Security, Many Markets', JF 50(4)
   - *Needs:* price only, peer universe · *Horizon:* intraday · *Min bars:* 150 · *Family:* `price_discovery`

9. **Hawkes Self-Exciting Intensity** — **PROXY**
   - Trade arrivals cluster and self-excite; elevated intensity marks bursts that typically decay.
   - *Research:* Bacry, Mastromatteo & Muzy (2015), 'Hawkes Processes in Finance', Market Microstructure and Liquidity 1(1)
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 120 · *Family:* `point_process`
   - *Proxy note:* Intensity estimated from exponentially-decayed large-bar arrivals rather than fitted to a tick point process.

10. **Intrabar Range Reversion**
   - Measures where the close sits inside the bar range and fades the extremes — the short-lived deviation the microscope finds.
   - *Research:* 'Arbitrage in the Foreign Exchange Market: Turning on the Microscope' — deviations exist but are small and short-lived. Reading: close position within the bar's own range as the deviation.
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 150 · *Family:* `intrabar_reversion`

11. **Kyle's Lambda (Price Impact)** — **PROXY**
   - Regression slope of price change on signed volume — the market's depth coefficient.
   - *Research:* Kyle (1985), 'Continuous Auctions and Insider Trading', Econometrica 53(6)
   - *Needs:* price only, volume · *Horizon:* intraday · *Min bars:* 100 · *Family:* `price_impact`
   - *Proxy note:* Kyle's λ is defined on signed order flow. Bar data has no trade signing, so the tick rule (close-to-close direction) substitutes for true buy/sell classification.

12. **Limit Order Book Depth Imbalance**
   - Ratio of bid to ask depth beyond the touch; needs genuine L2 data and stands down without it.
   - *Research:* Cao, Hansch & Wang (2009), 'The Information Content of an Open Limit-Order Book', J. Futures Markets 29(1)
   - *Needs:* price only, L2 order book · *Horizon:* intraday · *Min bars:* 60 · *Family:* `order_book`

13. **Liquidity Provision Premium**
   - Returns to supplying liquidity rise sharply when volatility spikes and liquidity withdraws.
   - *Research:* Nagel (2012), 'Evaporating Liquidity', RFS 25(7)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 140 · *Family:* `liquidity`

14. **Microstructure Noise Ratio**
   - Ratio of high-frequency to low-frequency variance; excess noise means quoted prices are unreliable.
   - *Research:* Aït-Sahalia, Mykland & Zhang (2005), 'How Often to Sample a Continuous-Time Process', RFS 18(2)
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 120 · *Family:* `noise`

15. **Order Flow Imbalance** — **PROXY**
   - Net buying pressure; the single strongest short-horizon predictor of price in the OFI literature.
   - *Research:* Cont, Kukanov & Stoikov (2014), 'The Price Impact of Order Book Events', J. Financial Econometrics 12(1)
   - *Needs:* price only, volume · *Horizon:* intraday · *Min bars:* 80 · *Family:* `order_flow`
   - *Proxy note:* Published OFI uses best-bid/ask size changes from L1 book updates. This substitutes the close's position within the bar range as the proxy for intra-bar buy/sell pressure.

16. **Realized Spread Price Reversal**
   - Decomposes the effective spread; the reverting portion is dealer compensation, not information.
   - *Research:* Huang & Stoll (1996), 'Dealer versus Auction Markets', JFE 41(3)
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 80 · *Family:* `spread`

17. **Roll Effective Spread Estimator**
   - Infers the spread from negative serial covariance of returns caused by bid-ask bounce.
   - *Research:* Roll (1984), 'A Simple Implicit Measure of the Effective Bid-Ask Spread', JF 39(4)
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 100 · *Family:* `spread`

18. **Stale Pricing Autocorrelation**
   - Measures return autocorrelation as a staleness proxy and leans with the lag while it persists.
   - *Research:* 'Sitting Bucks: Stale Pricing in Fixed Income Funds'. Reading: stale marks show up as return autocorrelation, and the lag is tradeable until the mark catches up.
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 180 · *Family:* `stale_pricing`

19. **Tick Rule Signed Flow**
   - Classifies each bar as buyer- or seller-initiated and accumulates the signed series.
   - *Research:* Lee & Ready (1991), 'Inferring Trade Direction from Intraday Data', JF 46(2)
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 60 · *Family:* `order_flow`

20. **VPIN Order Flow Toxicity** — **PROXY**
   - Volume-synchronised probability of informed trading; spiked ahead of the 2010 Flash Crash.
   - *Research:* Easley, López de Prado & O'Hara (2012), 'Flow Toxicity and Liquidity in a High-Frequency World', RFS 25(5)
   - *Needs:* price only, volume · *Horizon:* intraday · *Min bars:* 120 · *Family:* `flow_toxicity`
   - *Proxy note:* True VPIN buckets by volume clock and classifies trades with a bulk-volume rule on tick data. This computes the analogous imbalance on time bars using the return-signed bar volume.

21. **Volume Clock Information Arrival**
   - Sampling on volume rather than time normalises information arrival and stabilises return moments.
   - *Research:* Easley, López de Prado & O'Hara (2012), 'The Volume Clock', J. Portfolio Management 39(1)
   - *Needs:* price only, volume · *Horizon:* intraday · *Min bars:* 120 · *Family:* `volume_clock`

22. **Volume Concentration (Iceberg Detection)**
   - Informed traders split orders into medium sizes; concentrated medium-volume bars flag stealth accumulation.
   - *Research:* Barclay & Warner (1993), 'Stealth Trading and Volatility', JFE 34(3)
   - *Needs:* price only, volume · *Horizon:* intraday · *Min bars:* 120 · *Family:* `order_flow`

---

## Options & Derivatives

_22 models · 14 families_

1. **Binomial American Early Exercise**
   - Values the early-exercise premium on American options via a binomial lattice.
   - *Research:* Cox, Ross & Rubinstein (1979), 'Option Pricing: A Simplified Approach', JFE 7(3)
   - *Needs:* price only, options chain · *Horizon:* swing · *Min bars:* 120 · *Family:* `bs_pricing`

2. **Black-Scholes Relative Mispricing**
   - Compares market premium to the Black-Scholes value at the realised-vol input.
   - *Research:* Black & Scholes (1973), JPE 81(3); Merton (1973), Bell J. Economics 4(1)
   - *Needs:* price only, options chain · *Horizon:* swing · *Min bars:* 120 · *Family:* `bs_pricing`

3. **Dealer Gamma Exposure (GEX)**
   - Net dealer gamma; positive gamma dampens realised vol, negative gamma amplifies it.
   - *Research:* Baltas (2019) dealer hedging flows; SqueezeMetrics (2017), 'The Implied Order Book'
   - *Needs:* price only, options chain · *Horizon:* swing · *Min bars:* 120 · *Family:* `dealer_flow`

4. **Futures Basis Carry**
   - Trades the spot-futures basis directly; requires both legs of the curve.
   - *Research:* Keynes (1930) normal backwardation; empirical carry per Koijen, Moskowitz, Pedersen & Vrugt (2018), JFE 127(2)
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 150 · *Family:* `carry`

5. **Gamma Scalping Profitability** — **PROXY**
   - Whether realised path variation would have paid for the theta of a hedged long-gamma position.
   - *Research:* Wilmott (2006), 'Paul Wilmott on Quantitative Finance', ch. on hedging error
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 150 · *Family:* `gamma_scalp`
   - *Proxy note:* Compares realised path variation to an assumed theta cost, since actual option premium is unavailable.

6. **Implied Volatility Skew**
   - Slope of implied vol across strikes; steep put skew prices crash risk and is itself mean-reverting.
   - *Research:* Dumas, Fleming & Whaley (1998), 'Implied Volatility Functions', JF 53(6)
   - *Needs:* price only, options chain · *Horizon:* swing · *Min bars:* 120 · *Family:* `vol_surface`

7. **Index-Component Dispersion**
   - Sells index vol against component vol when implied correlation is rich.
   - *Research:* Driessen, Maenhout & Vilkov (2009), 'The Price of Correlation Risk', JF 64(3)
   - *Needs:* price only, options chain, peer universe · *Horizon:* swing · *Min bars:* 120 · *Family:* `dispersion`

8. **Max Pain Expiry Pinning**
   - Prices cluster at strikes with maximal open interest into expiry — a documented pinning effect.
   - *Research:* Ni, Pearson & Poteshman (2005), 'Stock Price Clustering on Option Expiration Dates', JFE 78(1)
   - *Needs:* price only, options chain · *Horizon:* swing · *Min bars:* 120 · *Family:* `expiry`

9. **Open Interest Divergence**
   - Open interest rising against price marks positioning that must eventually unwind.
   - *Research:* Bessembinder & Seguin (1993), 'Price Volatility, Trading Volume and Market Depth', JFQA 28(1)
   - *Needs:* price only, options chain · *Horizon:* swing · *Min bars:* 120 · *Family:* `options_sentiment`

10. **Put-Call Parity Violation**
   - A genuine arbitrage when synthetic and actual forward prices diverge beyond costs.
   - *Research:* Stoll (1969), 'The Relationship Between Put and Call Option Prices', JF 24(5)
   - *Needs:* price only, options chain · *Horizon:* swing · *Min bars:* 120 · *Family:* `arbitrage`

11. **Put-Call Ratio Sentiment**
   - Option volume ratios carry directional information, especially from non-market-maker accounts.
   - *Research:* Pan & Poteshman (2006), 'The Information in Option Volume for Future Stock Prices', RFS 19(3)
   - *Needs:* price only, options chain · *Horizon:* swing · *Min bars:* 120 · *Family:* `options_sentiment`

12. **Realized Volatility Cone**
   - Places current realised vol on the historical percentile cone across horizons — the desk's first check.
   - *Research:* Burghardt & Lane (1990), 'How to Tell If Options Are Cheap', JPM 16(2)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 250 · *Family:* `vol_cone`

13. **Round-Number Pin Proxy** — **PROXY**
   - Prices gravitate to round strike levels near expiry; approximates pinning without chain data.
   - *Research:* Ni, Pearson & Poteshman (2005), JFE 78(1) — expiry-date price clustering
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 100 · *Family:* `expiry`
   - *Proxy note:* Uses round-number price levels as a stand-in for real open-interest concentration.

14. **SABR Stochastic Alpha-Beta-Rho Fit**
   - Fits the SABR model to the surface and trades residuals against the fitted smile.
   - *Research:* Hagan, Kumar, Lesniewski & Woodward (2002), 'Managing Smile Risk', Wilmott Magazine
   - *Needs:* price only, options chain · *Horizon:* swing · *Min bars:* 120 · *Family:* `vol_surface`

15. **SKEW Index Tail Risk**
   - Risk-neutral skewness from out-of-the-money puts prices the market's tail expectation.
   - *Research:* CBOE SKEW Index methodology; risk-neutral skewness per Bakshi, Kapadia & Madan (2003), RFS 16(1)
   - *Needs:* price only, options chain · *Horizon:* swing · *Min bars:* 120 · *Family:* `tail_pricing`

16. **Straddle-Implied Move vs Realized** — **PROXY**
   - Compares the move a straddle would need against what the underlying actually delivers.
   - *Research:* Implied-move framework per Natenberg (1994), 'Option Volatility and Pricing', ch. 4
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 150 · *Family:* `vol_cone`
   - *Proxy note:* Without a chain, the implied move is estimated from a GARCH-style forecast of realised vol rather than read from actual at-the-money straddle premium.

17. **VIX Term Structure Carry**
   - Contango pays short-vol carry; backwardation flags stress and reverses the sign.
   - *Research:* CBOE VIX White Paper (2003, rev. 2019); term-structure carry per Simon & Campasano (2014), JAI 16(3)
   - *Needs:* price only, options chain · *Horizon:* swing · *Min bars:* 120 · *Family:* `vol_term`

18. **Vanna-Charm Hedging Flow**
   - Predictable dealer re-hedging as spot, vol and time-to-expiry move the delta.
   - *Research:* Second-order Greeks per Haug (2007), 'The Complete Guide to Option Pricing Formulas'
   - *Needs:* price only, options chain · *Horizon:* swing · *Min bars:* 120 · *Family:* `dealer_flow`

19. **Variance Swap Replication**
   - Replicates a variance swap from a strip of options to isolate pure variance exposure.
   - *Research:* Demeterfi, Derman, Kamal & Zou (1999), 'More Than You Ever Wanted to Know About Volatility Swaps', Goldman Sachs
   - *Needs:* price only, options chain · *Horizon:* swing · *Min bars:* 120 · *Family:* `variance`

20. **Volatility Curve Slope Proxy** — **PROXY**
   - Short- versus long-horizon vol slope stands in for the futures basis; inversion marks stress.
   - *Research:* Simon & Campasano (2014), 'The VIX Futures Basis', JAI 16(3)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `vol_term`
   - *Proxy note:* Derived from the realised-vol term structure of the underlying, not from listed VIX futures.

21. **Volatility Risk Premium Proxy** — **PROXY**
   - Implied variance normally exceeds realised; the gap is the premium short-vol strategies harvest.
   - *Research:* Carr & Wu (2009), 'Variance Risk Premiums', RFS 22(3)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `vrp`
   - *Proxy note:* Implied variance is approximated by a forward-looking EWMA of realised variance plus the historical average premium, because no options chain is connected.

22. **Volatility Smile Arbitrage**
   - Trades local dislocations in the smile against a no-arbitrage fitted surface.
   - *Research:* Derman & Kani (1994), 'Riding on a Smile', Risk 7(2)
   - *Needs:* price only, options chain · *Horizon:* swing · *Min bars:* 120 · *Family:* `vol_surface`

---

## Volatility

_22 models · 15 families_

1. **ATR-Normalised Trend Exposure**
   - Expresses trend conviction in ATR units so a quiet market and a violent one are treated alike.
   - *Research:* Wilder (1978) ATR; risk-parity sizing per Qian (2005), 'Risk Parity Portfolios'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 100 · *Family:* `vol_target`

2. **Bipower Variation Jump Detection**
   - Separates continuous diffusion from discrete jumps; jumps mean-revert where diffusion trends.
   - *Research:* Barndorff-Nielsen & Shephard (2004), 'Power and Bipower Variation', J. Fin. Econometrics 2(1)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 120 · *Family:* `jumps`

3. **Conditional Tail Risk (CVaR)**
   - Expected loss beyond the VaR threshold; deteriorating CVaR cuts exposure before drawdown compounds.
   - *Research:* Rockafellar & Uryasev (2000), 'Optimization of Conditional Value-at-Risk', J. Risk 2(3)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 160 · *Family:* `tail_risk`

4. **Drawdown-Controlled Exposure**
   - Cuts exposure as drawdown from the running peak deepens — the constraint most institutional mandates impose.
   - *Research:* Grossman & Zhou (1993), 'Optimal Investment Strategies for Controlling Drawdowns', Math. Finance 3(3)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 120 · *Family:* `drawdown`

5. **EGARCH Leverage Asymmetry**
   - Captures the leverage effect: negative returns raise future volatility more than positive ones.
   - *Research:* Nelson (1991), 'Conditional Heteroskedasticity in Asset Returns', Econometrica 59(2)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 150 · *Family:* `garch`

6. **GARCH(1,1) Volatility Forecast**
   - Fits GARCH(1,1) by recursive filtering with standard parameters and trades the gap between forecast and realised volatility.
   - *Research:* Bollerslev (1986), 'Generalized Autoregressive Conditional Heteroskedasticity', J. Econometrics 31(3)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 150 · *Family:* `garch`

7. **GJR-GARCH Threshold Volatility**
   - Adds an indicator term so negative shocks feed volatility through a separate, larger coefficient.
   - *Research:* Glosten, Jagannathan & Runkle (1993), 'On the Relation between Expected Value and Volatility', JF 48(5)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 150 · *Family:* `garch`

8. **Garman-Klass Volatility Efficiency**
   - OHLC estimator roughly 7x more efficient than close-to-close; detects mispriced short-term vol.
   - *Research:* Garman & Klass (1980), 'On the Estimation of Security Price Volatilities', J. Business 53(1)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 100 · *Family:* `range_vol`

9. **HAR-RV Heterogeneous Autoregression**
   - Cascades daily, weekly and monthly realised volatility — the standard realised-vol benchmark.
   - *Research:* Corsi (2009), 'A Simple Approximate Long-Memory Model of Realized Volatility', J. Fin. Econometrics 7(2)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 150 · *Family:* `har_rv`

10. **Intraday Volatility Seasonality**
   - Volatility follows a strong intraday U-shape; deviations from the seasonal norm carry information.
   - *Research:* Andersen & Bollerslev (1997), 'Intraday Periodicity and Volatility Persistence', J. Empirical Finance 4(2-3)
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 200 · *Family:* `vol_seasonal`

11. **Merton Jump-Diffusion Discrepancy**
   - Flags returns too large for the diffusion component alone, implying a jump that partly retraces.
   - *Research:* Merton (1976), 'Option Pricing When Underlying Stock Returns Are Discontinuous', JFE 3(1-2)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 120 · *Family:* `jumps`

12. **Parkinson Range Volatility Divergence**
   - Compares high-low range volatility to close-to-close; a wide gap signals intrabar churn without follow-through.
   - *Research:* Parkinson (1980), 'The Extreme Value Method for Estimating the Variance', J. Business 53(1)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 100 · *Family:* `range_vol`

13. **Realized Skewness Premium**
   - Negative realised skewness predicts higher subsequent returns — compensation for crash risk.
   - *Research:* Amaya, Christoffersen, Jacobs & Vasquez (2015), 'Does Realized Skewness Predict Returns?', JFE 118(1)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 120 · *Family:* `higher_moments`

14. **Realized Volatility Term Structure**
   - Short- versus long-horizon volatility slope; inversion typically marks stress and precedes reversion.
   - *Research:* Term-structure framework per Christoffersen, Heston & Jacobs (2009), Management Science 55(12)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 150 · *Family:* `vol_term`

15. **Rogers-Satchell Drift-Robust Volatility**
   - Range estimator that stays unbiased under nonzero drift, unlike Parkinson and Garman-Klass.
   - *Research:* Rogers & Satchell (1991), 'Estimating Variance from High, Low and Closing Prices', Ann. Appl. Prob. 1(4)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 100 · *Family:* `range_vol`

16. **Variance Risk Premium**
   - The gap between implied and realised variance; harvesting it is the core short-vol carry trade.
   - *Research:* Bollerslev, Tauchen & Zhou (2009), 'Expected Stock Returns and Variance Risk Premium', RFS 22(11)
   - *Needs:* price only, options chain · *Horizon:* swing · *Min bars:* 120 · *Family:* `vrp`

17. **Volatility Clustering Persistence**
   - Volatility is autocorrelated even when returns are not; positions size down as clustering intensifies.
   - *Research:* Mandelbrot (1963); formalised in Engle (1982), 'Autoregressive Conditional Heteroscedasticity', Econometrica 50(4)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 140 · *Family:* `vol_cluster`

18. **Volatility Expansion Breakout**
   - Trades the direction of the first expansion out of a historically narrow range.
   - *Research:* Crabel (1990), 'Day Trading with Short Term Price Patterns'; NR7 / narrow-range compression
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 100 · *Family:* `vol_breakout`

19. **Volatility Mean Reversion**
   - Volatility reverts far faster than price; extremes in realised vol mark the end of a move.
   - *Research:* Fouque, Papanicolaou & Sircar (2000), 'Derivatives in Financial Markets with Stochastic Volatility'
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 150 · *Family:* `vol_reversion`

20. **Volatility of Volatility**
   - Instability in the volatility process itself is a distinct priced risk from volatility level.
   - *Research:* Huang, Schlag, Shaliastovich & Thimme (2019), 'Volatility-of-Volatility Risk', JFQA 54(6)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 160 · *Family:* `vol_of_vol`

21. **Volatility-Managed Portfolio**
   - Scales exposure inversely to recent variance — raises risk-adjusted returns without forecasting direction.
   - *Research:* Moreira & Muir (2017), 'Volatility-Managed Portfolios', JF 72(4)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 150 · *Family:* `vol_target`

22. **Yang-Zhang Drift-Independent Volatility**
   - The minimum-variance OHLC estimator; alone among them it handles overnight gaps and drift.
   - *Research:* Yang & Zhang (2000), 'Drift-Independent Volatility Estimation', J. Business 73(3)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 100 · *Family:* `range_vol`

---

## Regime & Risk

_21 models · 17 families_

1. **Absorption Ratio Systemic Risk**
   - Fraction of variance explained by the top principal components; a spike precedes fragility.
   - *Research:* Kritzman, Li, Page & Rigobon (2011), 'Principal Components as a Measure of Systemic Risk', JPM 37(4)
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 250 · *Family:* `systemic_risk`

2. **Bull-Bear Market Classifier**
   - Classifies the market state by drawdown depth from the running peak, with hysteresis to avoid whipsaw.
   - *Research:* Lunde & Timmermann (2004), 'Duration Dependence in Stock Prices', J. Business & Economic Statistics 22(3)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 200 · *Family:* `market_state`

3. **Composite Liquidity Stress**
   - Blends volatility, range expansion and volume collapse into one stress reading that gates exposure.
   - *Research:* Composite stress framework per Kliesen, Owyang & Vermann (2012), Federal Reserve Bank of St. Louis Review 94(5)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `systemic_risk`

4. **Cornish-Fisher Modified VaR**
   - Adjusts VaR for skewness and kurtosis, correcting the normal assumption's understatement of tail loss.
   - *Research:* Cornish & Fisher (1938); financial application per Favre & Galeano (2002), JAI 5(2)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 200 · *Family:* `var`

5. **Correlation Regime Break**
   - Correlations rise in crashes exactly when diversification is needed; a regime break cuts risk.
   - *Research:* Ang & Chen (2002), 'Asymmetric Correlations of Equity Portfolios', JFE 63(3)
   - *Needs:* price only, benchmark series · *Horizon:* position · *Min bars:* 200 · *Family:* `correlation`

6. **Crash-Robust Heuristic Exposure**
   - A deliberately crude rule — full exposure in calm tails, none in fat ones — on the finding that simplicity survives crashes better than fitted optimisation.
   - *Research:* 'Are Heuristics Better than Theory if Market Crashes Are Possible' — simple rules beat optimisation when tails matter. Reading: hold exposure only while tail conditions are quiet.
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `crash_heuristic`

7. **Drawdown Recovery Momentum**
   - Speed of recovery from a drawdown separates a genuine base from a dead-cat bounce.
   - *Research:* Recovery dynamics per Magdon-Ismail & Atiya (2004), 'Maximum Drawdown', Risk Magazine 17(10)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `drawdown`

8. **Extreme Value Theory Tail Estimate**
   - Estimates the tail index from exceedances; a fattening tail means the ordinary risk model understates loss.
   - *Research:* Embrechts, Klüppelberg & Mikosch (1997), 'Modelling Extremal Events'; Hill (1975) tail index estimator
   - *Needs:* price only · *Horizon:* position · *Min bars:* 250 · *Family:* `tail_risk`

9. **Kelly Fraction (Multiple Outcomes)**
   - Growth-optimal fraction from maximising mean log wealth over the realised outcome distribution, long or short; the worst outcome in the window bounds it where a variance ratio would not.
   - *Research:* Analytical Kelly for multiple outcomes. Reading: the trailing window's realised returns are the outcome distribution, and the fraction is the one that maximises expected log growth over it. That is the multi-outcome objective itself; its two-outcome reduction to hit rate and payoff odds collapses to a mean-variance ratio and says nothing a Sharpe tilt does not.
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 300 · *Family:* `kelly_sizing`

10. **Maximum Drawdown Guard**
   - Hard risk stop: exposure goes to zero as drawdown approaches the mandate limit.
   - *Research:* Chekhlov, Uryasev & Zabarankin (2005), 'Drawdown Measure in Portfolio Optimization', IJTAF 8(1)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 150 · *Family:* `drawdown`

11. **Momentum Crash Risk**
   - Momentum crashes in panic rebounds; bear market plus rising volatility disables the momentum leg.
   - *Research:* Daniel & Moskowitz (2016), 'Momentum Crashes', JFE 122(2)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 280 · *Family:* `crash_risk`

12. **Regime-Aware Concentration Risk**
   - Concentration is survivable while the volatility regime is stable; exposure is cut when the regime itself starts moving.
   - *Research:* 'Regime-Aware Risk Management in Concentrated Equity Portfolios: Evidence from the Magnificent Seven'. Reading: scale exposure by the stability of the volatility regime rather than its level.
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `concentration_regime`

13. **Regime-Conditional Leverage**
   - Scales gross exposure by the joint state of volatility, trend quality and drawdown.
   - *Research:* Ang & Bekaert (2004), 'How Regimes Affect Asset Allocation', FAJ 60(2)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 250 · *Family:* `vol_regime`

14. **Return Clustering Regime Detector**
   - Detects whether returns are clustering (persistent regime) or dispersing, and takes direction only in the persistent state.
   - *Research:* 'Proof-of-What? Detecting original consensus algorithms in cryptocurrencies with a four-factor model'. Reading: the detection problem — distinguishing regimes from return structure alone.
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 220 · *Family:* `return_clustering`

15. **Skewness Risk Premium**
   - Assets with negative coskewness demand a premium; skew is a priced risk beyond variance.
   - *Research:* Harvey & Siddique (2000), 'Conditional Skewness in Asset Pricing Tests', JF 55(3)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 250 · *Family:* `higher_moments`

16. **Sortino Downside Deviation**
   - Risk-adjusted return counting only downside deviation, since upside volatility is not a risk.
   - *Research:* Sortino & Price (1994), 'Performance Measurement in a Downside Risk Framework', JOI 3(3)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 200 · *Family:* `risk_adjusted`

17. **Trend Fragility Index**
   - Detects trends becoming parabolic — accelerating on falling volume, historically a fragile configuration.
   - *Research:* Fragility framework per Taleb (2012), 'Antifragile'; convexity measurement per Taleb & Douady (2013), Quant. Finance 13(11)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `fragility`

18. **Ulcer Index Downside Risk**
   - Root-mean-square drawdown; penalises depth and duration together, unlike standard deviation.
   - *Research:* Martin & McCann (1989), 'The Investor's Guide to Fidelity Funds'
   - *Needs:* price only · *Horizon:* position · *Min bars:* 150 · *Family:* `drawdown`

19. **Volatility Budget Allocation**
   - Allocates a fixed volatility budget, so position size falls exactly as risk per unit rises.
   - *Research:* Risk budgeting per Roncalli (2013), 'Introduction to Risk Parity and Budgeting'
   - *Needs:* price only · *Horizon:* position · *Min bars:* 150 · *Family:* `budget`

20. **Volatility Regime Switch**
   - Selects between trend and reversion behaviour based on where volatility sits in its own distribution.
   - *Research:* Ang & Timmermann (2012), 'Regime Changes and Financial Markets', Annual Review of Financial Economics 4
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `vol_regime`

21. **Yield Curve Recession Signal**
   - Term-spread inversion is the most reliable single recession predictor; needs a rates feed.
   - *Research:* Estrella & Mishkin (1998), 'Predicting U.S. Recessions', REStat 80(1)
   - *Needs:* price only, benchmark series · *Horizon:* position · *Min bars:* 250 · *Family:* `macro`

---

## Rates & Credit

_18 models · 16 families_

1. **Bond Carry and Rolldown**
   - Yield plus rolldown along the curve; the dominant return driver for a held bond position.
   - *Research:* Koijen, Moskowitz, Pedersen & Vrugt (2018), 'Carry', JFE 127(2)
   - *Needs:* price only, benchmark series · *Horizon:* position · *Min bars:* 250 · *Family:* `bond_carry`

2. **Breakeven Inflation Trade**
   - The nominal-versus-real yield gap as an inflation expectation; needs both curves.
   - *Research:* Fleckenstein, Longstaff & Lustig (2014), 'The TIPS-Treasury Bond Puzzle', JF 69(5)
   - *Needs:* price only, benchmark series · *Horizon:* position · *Min bars:* 250 · *Family:* `inflation`

3. **Corporate Bond Factor Investing**
   - Factor sorts across a corporate bond universe against its index. Needs both.
   - *Research:* Out-performing corporate bonds indices with factor investing
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 60 · *Family:* `corporatebondfactorinvesting`

4. **Credit Spread Momentum**
   - Widening spreads lead equity weakness; the excess bond premium is the cleanest form.
   - *Research:* Gilchrist & Zakrajšek (2012), 'Credit Spreads and Business Cycle Fluctuations', AER 102(4)
   - *Needs:* price only, benchmark series · *Horizon:* position · *Min bars:* 250 · *Family:* `credit`

5. **Duration Timing (Price-Based)** — **PROXY**
   - Times duration exposure on the traded bond instrument's own trend and volatility.
   - *Research:* Ilmanen (1997), 'Forecasting U.S. Bond Returns', J. Fixed Income 7(1)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 250 · *Family:* `duration`
   - *Proxy note:* Real duration timing regresses on yield levels, curve slope and momentum. With only the instrument's price, this uses trend and vol as the timing input.

6. **Financial Conditions Index**
   - Composite of rates, spreads, equity and FX conditions; needs a macro data feed.
   - *Research:* Hatzius, Hooper, Mishkin, Schoenholtz & Watson (2010), NBER Working Paper 16150
   - *Needs:* price only, benchmark series · *Horizon:* position · *Min bars:* 250 · *Family:* `macro_composite`

7. **Frontier and Emerging Government Bonds**
   - Relative value across sovereign issuers. Needs the issuer cross-section.
   - *Research:* Frontier and Emerging Government Bond Markets
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 60 · *Family:* `frontiergovernmentbonds`

8. **G10 Bond Carry**
   - Cross-country sovereign carry after hedging FX; needs a multi-country yield panel.
   - *Research:* Ilmanen (1995), 'Time-Varying Expected Returns in International Bond Markets', JF 50(2)
   - *Needs:* price only, benchmark series, peer universe · *Horizon:* position · *Min bars:* 250 · *Family:* `bond_carry`

9. **HMM Regime Bond Portfolio**
   - Allocates across fixed-income sleeves by inferred regime. The regime is estimable on one series; the allocation is not.
   - *Research:* Regime-based portfolio optimisation: A Hidden Markov Model approach for fixed income portfolios
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 60 · *Family:* `hmmregimebondportfolio`

10. **Policy Rate Surprise**
   - Unexpected policy moves derived from futures repricing; needs a rate-futures feed.
   - *Research:* Kuttner (2001), 'Monetary Policy Surprises and Interest Rates', J. Monetary Economics 47(3)
   - *Needs:* price only, benchmark series, news / alt-data · *Horizon:* position · *Min bars:* 250 · *Family:* `monetary`

11. **Priced Tail Risk Premium**
   - Drift measured against downside deviation only, on the finding that variance is not what is compensated.
   - *Research:* 'Priced risk in corporate bonds' — compensation attaches to tail exposure rather than variance. Reading: separate downside from total risk and require the compensation to be for the former.
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `priced_tail_risk`

12. **Real Yield Momentum**
   - Momentum in inflation-adjusted yields; needs a TIPS or real-yield series.
   - *Research:* Campbell, Shiller & Viceira (2009), 'Understanding Inflation-Indexed Bond Markets', Brookings Papers
   - *Needs:* price only, benchmark series · *Horizon:* position · *Min bars:* 250 · *Family:* `real_rates`

13. **Real-Time Macro Bond Prediction**
   - The paper's whole point is the real-time vintage of macro releases, including revisions. Needs the vintage data.
   - *Research:* Are Bond Returns Predictable with Real-Time Macro Data?
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 60 · *Family:* `realtimemacrobondprediction`

14. **Risk-Aware Yield Search**
   - Drift per unit of downside deviation, gated on that downside measure improving rather than deteriorating.
   - *Research:* 'Dynamic Risk-Aware Yield Search: A Useful Tool for Fixed Income Investors'. Reading: reach for yield only where the risk taken to get it is falling, not rising.
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `yield_search`

15. **Sovereign Debt Auction Effects**
   - Trades the auction calendar. Needs the issuance schedule, which is not in the bar series.
   - *Research:* Price Effects of Sovereign Debt Auctions in the Euro-zone: The Role of the Crisis
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 60 · *Family:* `sovereignauctioneffects`

16. **Term Premium Signal**
   - The compensation for duration risk beyond expected short rates; needs an ACM term-premium series.
   - *Research:* Adrian, Crump & Moench (2013), 'Pricing the Term Structure with Linear Regressions', JFE 110(1)
   - *Needs:* price only, benchmark series · *Horizon:* position · *Min bars:* 250 · *Family:* `term_structure`

17. **Term Transformation Slope Proxy**
   - Long-horizon drift minus short-horizon drift as a term-structure slope proxy — the shape banks earn from, not the level.
   - *Research:* 'Banks' exposure to interest rate risk, their earnings from term transformation, and the dynamics of the term structure'. Reading: the slope proxied by the gap between long- and short-horizon drift.
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 300 · *Family:* `term_slope`

18. **Yield Curve Steepener/Flattener**
   - Trades the level/slope/curvature decomposition of the yield curve.
   - *Research:* Litterman & Scheinkman (1991), 'Common Factors Affecting Bond Returns', J. Fixed Income 1(1)
   - *Needs:* price only, benchmark series, peer universe · *Horizon:* position · *Min bars:* 250 · *Family:* `term_structure`

---

## Seasonality & Calendar

_15 models · 8 families_

1. **Day-of-Week Effect**
   - Monday returns were historically negative and Friday positive. The effect has weakened substantially since the 1990s, so it is scored from the symbol's own realised history.
   - *Research:* French (1980), 'Stock Returns and the Weekend Effect', JFE 8(1); Cross (1973), FAJ 29(6)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 150 · *Family:* `weekly`

2. **FOMC Announcement Drift**
   - Equities drift up in the 24 hours before scheduled FOMC announcements; needs a macro calendar.
   - *Research:* Lucca & Moench (2015), 'The Pre-FOMC Announcement Drift', JF 70(1)
   - *Needs:* price only, news / alt-data · *Horizon:* swing · *Min bars:* 200 · *Family:* `macro_calendar`

3. **Halloween Indicator (Sell in May)**
   - November-April returns have historically exceeded May-October across most developed markets.
   - *Research:* Bouman & Jacobsen (2002), 'The Halloween Indicator', AER 92(5); replicated in Jacobsen & Zhang (2013)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 300 · *Family:* `annual`

4. **Intraday U-Shape Volume Pattern**
   - Volume and volatility are U-shaped through the session; the midday lull favours reversion.
   - *Research:* Admati & Pfleiderer (1988), 'A Theory of Intraday Patterns', RFS 1(1); Jain & Joh (1988), JFQA 23(3)
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 200 · *Family:* `intraday`

5. **January Effect**
   - Small caps outperformed in January, historically attributed to tax-loss-selling reversal. Largely arbitraged away in large caps since the 1990s.
   - *Research:* Rozeff & Kinney (1976), 'Capital Market Seasonality', JFE 3(4); Keim (1983), JFE 12(1)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 300 · *Family:* `monthly`

6. **Month-of-Year Seasonality**
   - Assets exhibit persistent same-calendar-month return patterns; learned from the symbol's own history.
   - *Research:* Heston & Sadka (2008), 'Seasonality in the Cross-Section of Stock Returns', JFE 87(2)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 400 · *Family:* `annual`

7. **Options Expiry Week Effect**
   - Dealer hedging around monthly expiry dampens realised volatility and pins price into Friday.
   - *Research:* Stoll & Whaley (1987), 'Program Trading and Expiration-Day Effects', FAJ 43(2); Ni, Pearson & Poteshman (2005), JFE 78(1)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `expiry`

8. **Overnight vs Intraday Return Split**
   - Nearly all equity risk premium accrues overnight while intraday returns are flat or negative.
   - *Research:* Lou, Polk & Skouras (2019), 'A Tug of War', JFE 134(1); Kelly & Clark (2011), JBF 35(5)
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 150 · *Family:* `intraday`

9. **Pre-Holiday Effect**
   - The trading day before a market holiday earns abnormally high returns; detected via calendar gaps.
   - *Research:* Lakonishok & Smidt (1988), 'Are Seasonal Anomalies Real?', RFS 1(4); Ariel (1990), JF 45(5)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 150 · *Family:* `holiday`

10. **Quarter-End Rebalancing Flow**
   - Institutional rebalancing at quarter end creates predictable, mechanically-driven flow.
   - *Research:* Etula, Rinne, Suominen & Vaittinen (2020), 'Dash for Cash: Month-End Liquidity Needs', JFQA 55(4)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 250 · *Family:* `monthly`

11. **Seasonal Volatility Pattern**
   - Volatility peaks seasonally, notably September-October; positions scale down into those windows.
   - *Research:* Seasonal volatility documented in Bouman & Jacobsen (2002), AER 92(5); September effect per Siegel (2014)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 400 · *Family:* `annual`

12. **Seasonality, Trend and Reversion Blend**
   - Blends a weekday effect, medium-horizon trend and short-horizon reversion, each on the horizon where it was found to work.
   - *Research:* 'Seasonality, Trend-following, and Mean reversion in Bitcoin' — the paper's point is that the three coexist and must be weighted by horizon rather than chosen between.
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `seasonal_trend_blend`

13. **Time-of-Day Momentum**
   - Returns at a given time of day are positively autocorrelated across days at that same time.
   - *Research:* Heston, Korajczyk & Sadka (2010), 'Intraday Patterns in the Cross-Section of Stock Returns', JF 65(4)
   - *Needs:* price only · *Horizon:* intraday · *Min bars:* 250 · *Family:* `intraday`

14. **Turn-of-the-Month Effect**
   - Returns concentrate in the last and first few trading days of the month, driven by pension inflows.
   - *Research:* Ariel (1987), 'A Monthly Effect in Stock Returns', JFE 18(1); Lakonishok & Smidt (1988), RFS 1(4)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 150 · *Family:* `monthly`

15. **Week-of-Month Pattern**
   - Return distribution differs systematically across weeks of the month; learned from own history.
   - *Research:* Kohers & Patel (1999), 'A New Time-of-the-Month Anomaly', Applied Economics Letters 6(2)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 300 · *Family:* `monthly`

---

## Commodity & Carry

_11 models · 10 families_

1. **Commodity Inventory Signal**
   - Low inventories drive backwardation and higher expected returns; needs inventory data.
   - *Research:* Gorton, Hayashi & Rouwenhorst (2013), 'The Fundamentals of Commodity Futures Returns', Review of Finance 17(1)
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 200 · *Family:* `fundamental_commodity`

2. **Commodity Seasonal Pattern**
   - Agricultural and energy commodities carry strong production/consumption seasonality.
   - *Research:* Sørensen (2002), 'Modeling Seasonality in Agricultural Commodity Futures', J. Futures Markets 22(5)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 500 · *Family:* `commodity_seasonal`

3. **Commodity Term Structure (Backwardation)**
   - Backwardated curves earn a positive roll yield; contango bleeds. Needs two contract months.
   - *Research:* Erb & Harvey (2006), 'The Strategic and Tactical Value of Commodity Futures', FAJ 62(2)
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 200 · *Family:* `commodity_carry`

4. **Commodity Time-Series Momentum**
   - Momentum is strong and persistent in commodities, where trend-followers have long dominated.
   - *Research:* Miffre & Rallis (2007), 'Momentum Strategies in Commodity Futures Markets', JBF 31(6)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 280 · *Family:* `commodity_trend`

5. **Currency Carry Trade**
   - Long high-yield, short low-yield currencies; needs interest differentials across a currency panel.
   - *Research:* Lustig, Roussanov & Verdelhan (2011), 'Common Risk Factors in Currency Markets', RFS 24(11)
   - *Needs:* price only, benchmark series, peer universe · *Horizon:* position · *Min bars:* 250 · *Family:* `fx_carry`

6. **Gold vs Real Rates**
   - Gold is inversely related to real yields — its dominant macro driver. Needs a real-yield series.
   - *Research:* Erb & Harvey (2013), 'The Golden Dilemma', FAJ 69(4)
   - *Needs:* price only, benchmark series · *Horizon:* position · *Min bars:* 250 · *Family:* `macro_commodity`

7. **Good Carry vs Bad Carry**
   - Separates carry earned in calm conditions from carry earned into rising volatility — the second kind is compensation for a coming loss.
   - *Research:* Koijen, Moskowitz, Pedersen & Vrugt style carry decomposition, per 'Good Carry, Bad Carry'. Single-instrument reading: carry is proxied by drift per unit of risk, and penalised when that risk is rising.
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 180 · *Family:* `carry_quality`

8. **Hedging Pressure (COT)**
   - Commercial hedger positioning predicts commodity returns; needs CFTC Commitments of Traders data.
   - *Research:* Basu & Miffre (2013), 'Capturing the Risk Premium of Commodity Futures', JBF 37(7)
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 200 · *Family:* `positioning`

9. **Multi-Year Commodity Reversal**
   - Excursion of price from its multi-year mean, faded only after the past year has begun to close it. No point-to-point past return is used, which is what separates it from the 3-5 year overreaction fade.
   - *Research:* 'Long-Run Reversal in Commodity Returns: Insights from Seven Centuries of Evidence'. Reading: what reverts is the price level, toward its long-run mean, and it does so only after the continuation phase has run its course. So the model fades the excursion from a multi-year anchor, and only once the trailing year is already moving back toward it.
   - *Needs:* price only · *Horizon:* position · *Min bars:* 640 · *Family:* `longrun_reversal`

10. **PPP Currency Valuation**
   - Currencies revert to purchasing-power parity over multi-year horizons; needs CPI data.
   - *Research:* Rogoff (1996), 'The Purchasing Power Parity Puzzle', J. Economic Literature 34(2)
   - *Needs:* price only, fundamentals · *Horizon:* position · *Min bars:* 500 · *Family:* `fx_value`

11. **Roll Yield Harvest**
   - Systematically captures roll yield along the futures curve; needs multiple contract months.
   - *Research:* Gorton & Rouwenhorst (2006), 'Facts and Fantasies about Commodity Futures', FAJ 62(2)
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 200 · *Family:* `commodity_carry`

---

## Options Income

_8 models · 4 families_

1. **Cash-Secured Put** — **PROXY**
   - Short an out-of-the-money put against cash; synthetically equivalent to a covered call.
   - *Research:* CBOE PUT Index methodology; analysed in Ungar & Moran (2009), JOT 4(1)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `options_income`
   - *Proxy note:* Expresses the entry-timing rule only; actual premium and assignment risk need a chain.

2. **Covered Call Closed-End Fund Discount**
   - Trades the discount of a fund to its net asset value. Needs both the fund price and the NAV series.
   - *Research:* The Anomalous Behavior of the S&P Covered Call Closed End Fund
   - *Needs:* price only, peer universe · *Horizon:* position · *Min bars:* 60 · *Family:* `coveredcallclosedendfund`

3. **Covered Call Overlay** — **PROXY**
   - Long underlying, short an out-of-the-money call. Caps upside to harvest premium; historically improves Sharpe while reducing total return in strong rallies.
   - *Research:* Whaley (2002), 'Return and Risk of CBOE Buy Write Monthly Index', JD 10(2); CBOE BXM methodology
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 200 · *Family:* `options_income`
   - *Proxy note:* Without a chain the premium cannot be priced. This expresses the *timing* rule the overlay implies — favourable when implied-vol proxies are rich and the underlying is range-bound.

4. **Options Wheel** — **PROXY**
   - Cycles cash-secured puts into covered calls on assignment; a continuous premium-harvest loop.
   - *Research:* Systematic premium harvesting; return profile per Israelov & Nielsen (2015), JPM 41(4)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 250 · *Family:* `options_income`
   - *Proxy note:* Models the regime in which the wheel performs, not the option legs themselves.

5. **Protective Put Overlay** — **PROXY**
   - Long underlying plus a protective put. The cited research finds the cost usually exceeds the benefit — included so the ensemble can price the hedge, not to recommend it.
   - *Research:* Israelov (2019), 'Pathetic Protection: The Elusive Benefits of Protective Puts', JAI 21(3)
   - *Needs:* price only · *Horizon:* position · *Min bars:* 250 · *Family:* `tail_hedge`
   - *Proxy note:* Scores when tail protection is cheap relative to realised risk; premium pricing needs a chain.

6. **Systematic Iron Condor** — **PROXY**
   - Defined-risk short strangle with protective wings; caps the tail the naked version carries.
   - *Research:* Defined-risk premium selling; sizing framework per Israelov & Nielsen (2015), JPM 41(4)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 250 · *Family:* `options_income`
   - *Proxy note:* Scores regime favourability only; strike selection and width require a live chain.

7. **Systematic Short Strangle** — **PROXY**
   - Sells both wings to harvest the variance premium; carries unbounded tail risk if left unhedged.
   - *Research:* Variance risk premium harvesting per Carr & Wu (2009), RFS 22(3)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 250 · *Family:* `options_income`
   - *Proxy note:* Scores the favourability of the short-vol regime; the actual position needs a chain and tail hedge.

8. **VIX Roll Short (Contango Harvest)** — **PROXY**
   - Harvests VIX-futures contango; profitable most of the time and catastrophic in the tail.
   - *Research:* Simon & Campasano (2014), 'The VIX Futures Basis', JAI 16(3); Alexander & Korovilas (2012)
   - *Needs:* price only · *Horizon:* swing · *Min bars:* 250 · *Family:* `vol_carry`
   - *Proxy note:* Real implementation shorts VIX futures. Without that curve this reads the realised-vol term structure of the underlying as the contango/backwardation proxy.

---

## Models requiring an external data feed

142 models need something beyond the symbol's own price history. They are implemented and registered, and activate automatically once the corresponding feed is wired into `FeatureSet.meta`. Until then they report as unavailable rather than voting on a substitute.

| Feed | Models | What it unlocks |
|---|---:|---|
| `cross_section` | 55 | Cross-sectional factors, pairs trading, portfolio allocation, dispersion |
| `benchmark` | 27 | Beta, residual momentum, relative strength, correlation regime |
| `fundamentals` | 29 | Value, quality, accruals, insider and short-interest signals |
| `options_chain` | 16 | Implied vol surface, skew, gamma exposure, variance premium |
| `order_book` | 2 | True order-flow imbalance, L2 depth, DeepLOB |
| `onchain` | 13 | MVRV, SOPR, NVT, funding rates, exchange flows |
| `news` | 14 | News tone, search attention, social sentiment, macro calendar |

---

## Proxy implementations

These 22 models approximate their published method. Each states what was substituted. They are down-weighted to 40% of a full vote.

- **Avellaneda-Stoikov Reservation Price** (Microstructure) — Full model requires live inventory and a quoted book. This computes the reservation-price skew from volatility and a mean-reverting inventory proxy only.
- **Cash-Secured Put** (Options Income) — Expresses the entry-timing rule only; actual premium and assignment risk need a chain.
- **Covered Call Overlay** (Options Income) — Without a chain the premium cannot be priced. This expresses the *timing* rule the overlay implies — favourable when implied-vol proxies are rich and the underlying is range-bound.
- **Duration Timing (Price-Based)** (Rates & Credit) — Real duration timing regresses on yield levels, curve slope and momentum. With only the instrument's price, this uses trend and vol as the timing input.
- **Gamma Scalping Profitability** (Options & Derivatives) — Compares realised path variation to an assumed theta cost, since actual option premium is unavailable.
- **Glosten-Milgrom Adverse Selection** (Microstructure) — Uses run-length of same-direction bars as the informed-flow proxy in place of quote revisions.
- **Hawkes Self-Exciting Intensity** (Microstructure) — Intensity estimated from exponentially-decayed large-bar arrivals rather than fitted to a tick point process.
- **Kyle's Lambda (Price Impact)** (Microstructure) — Kyle's λ is defined on signed order flow. Bar data has no trade signing, so the tick rule (close-to-close direction) substitutes for true buy/sell classification.
- **Large Gap Continuation Drift** (Factor & Smart Beta) — Uses outsized overnight gaps as a stand-in for scheduled earnings surprises, which need a calendar feed.
- **Liquidation Cascade Reversal** (Crypto Native) — Real liquidation data comes from exchange liquidation feeds. This detects the price/volume signature of a cascade — violent range expansion on extreme volume with a long wick.
- **Options Wheel** (Options Income) — Models the regime in which the wheel performs, not the option legs themselves.
- **Order Flow Imbalance** (Microstructure) — Published OFI uses best-bid/ask size changes from L1 book updates. This substitutes the close's position within the bar range as the proxy for intra-bar buy/sell pressure.
- **Price-Based Fear & Greed Composite** (Sentiment & Alt Data) — The published index also uses put/call ratios, junk-bond demand and safe-haven flows. This uses only the price-derived components, so it is a partial reconstruction, not the index itself.
- **Protective Put Overlay** (Options Income) — Scores when tail protection is cheap relative to realised risk; premium pricing needs a chain.
- **Round-Number Pin Proxy** (Options & Derivatives) — Uses round-number price levels as a stand-in for real open-interest concentration.
- **Straddle-Implied Move vs Realized** (Options & Derivatives) — Without a chain, the implied move is estimated from a GARCH-style forecast of realised vol rather than read from actual at-the-money straddle premium.
- **Systematic Iron Condor** (Options Income) — Scores regime favourability only; strike selection and width require a live chain.
- **Systematic Short Strangle** (Options Income) — Scores the favourability of the short-vol regime; the actual position needs a chain and tail hedge.
- **VIX Roll Short (Contango Harvest)** (Options Income) — Real implementation shorts VIX futures. Without that curve this reads the realised-vol term structure of the underlying as the contango/backwardation proxy.
- **VPIN Order Flow Toxicity** (Microstructure) — True VPIN buckets by volume clock and classifies trades with a bulk-volume rule on tick data. This computes the analogous imbalance on time bars using the return-signed bar volume.
- **Volatility Curve Slope Proxy** (Options & Derivatives) — Derived from the realised-vol term structure of the underlying, not from listed VIX futures.
- **Volatility Risk Premium Proxy** (Options & Derivatives) — Implied variance is approximated by a forward-looking EWMA of realised variance plus the historical average premium, because no options chain is connected.

---

## Deliberate omissions

Some widely-circulated strategies are **not** included, because including them would mean presenting a discredited or unfalsifiable claim as a signal:

- **Stock-to-Flow (PlanB)** — the model's central prediction failed out of sample after 2021 and its statistical basis (regression on a deterministic time trend) is unsound.
- **Elliott Wave / Gann angles** — no falsifiable rule set; wave counts are assigned after the fact and are not reproducible between analysts.
- **Fixed-ratio martingale sizing** — mathematically guarantees ruin at a finite horizon.

_Not investment advice. Model output is for research and analysis._
