import numpy as np
import pandas as pd
from scipy import stats
import math
from src.tradingview_mcp.core.services.strategy_factory import BaseStrategy

# 1. Engle-Granger Cointegration (Single Asset vs Moving Average Surrogate)
class EngleGrangerStatArb(BaseStrategy):
    name = "Engle_Granger_Cointegration"
    category = "Statistical Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        close = df['close']
        sma = close.rolling(50).mean()
        spread = close - sma
        mean_spread = spread.rolling(20).mean()
        std_spread = spread.rolling(20).std()
        if std_spread.iloc[-1] == 0 or pd.isna(std_spread.iloc[-1]): return "NEUTRAL"
        z_score = (spread.iloc[-1] - mean_spread.iloc[-1]) / std_spread.iloc[-1]
        if z_score < -2.0: return "BUY"
        elif z_score > 2.0: return "SELL"
        return "NEUTRAL"

# 2. Ornstein-Uhlenbeck (OU) Process Modeling
class OUProcessModeling(BaseStrategy):
    name = "Ornstein_Uhlenbeck_Process"
    category = "Statistical Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 60: return "NEUTRAL"
        close = df['close'].values
        x, y = close[:-1], close[1:] - close[:-1]
        if len(x) < 2: return "NEUTRAL"
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
        theta = -slope
        if theta <= 0: return "NEUTRAL"
        mu = intercept / theta
        current_price = close[-1]
        deviation = current_price - mu
        residuals = y - (intercept + slope * x)
        sigma = np.std(residuals)
        if sigma == 0: return "NEUTRAL"
        z = deviation / sigma
        if z < -1.5: return "BUY"
        elif z > 1.5: return "SELL"
        return "NEUTRAL"

# 3. Kalman Filter Dynamic Hedge Ratio (Simplified for single asset trend/reversion)
class KalmanFilterStatArb(BaseStrategy):
    name = "Kalman_Filter_Dynamic"
    category = "Statistical Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 30: return "NEUTRAL"
        prices = df['close'].values
        n = len(prices)
        xhat, P = np.zeros(n), np.zeros(n)
        xhat[0], P[0] = prices[0], 1.0
        Q, R = 1e-5, 1e-2
        for k in range(1, n):
            xhat_minus, P_minus = xhat[k-1], P[k-1] + Q
            K = P_minus / (P_minus + R)
            xhat[k] = xhat_minus + K * (prices[k] - xhat_minus)
            P[k] = (1 - K) * P_minus
        current_kalman = xhat[-1]
        deviation = (prices[-1] - current_kalman) / current_kalman
        if deviation < -0.02: return "BUY"
        elif deviation > 0.02: return "SELL"
        return "NEUTRAL"

# 4. Distance Method Pairs Trading (Proxy using Volume/Price distance)
class DistanceMethodArb(BaseStrategy):
    name = "Distance_Method_Arb"
    category = "Statistical Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 40 or 'volume' not in df.columns: return "NEUTRAL"
        price_norm = (df['close'] - df['close'].rolling(40).min()) / (df['close'].rolling(40).max() - df['close'].rolling(40).min())
        vol_norm = (df['volume'] - df['volume'].rolling(40).min()) / (df['volume'].rolling(40).max() - df['volume'].rolling(40).min())
        distance = price_norm - vol_norm
        if distance.iloc[-1] < -0.8: return "BUY"
        elif distance.iloc[-1] > 0.8: return "SELL"
        return "NEUTRAL"

# 5. Stochastic Oscillator on Z-Scored Spread
class StochasticZScore(BaseStrategy):
    name = "Stochastic_ZScore_Spread"
    category = "Statistical Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 30: return "NEUTRAL"
        close = df['close']
        z_score = (close - close.rolling(20).mean()) / close.rolling(20).std()
        highest_z = z_score.rolling(14).max()
        lowest_z = z_score.rolling(14).min()
        denom = (highest_z - lowest_z).replace(0, 1e-6)
        stoch_k = 100 * ((z_score - lowest_z) / denom)
        if stoch_k.iloc[-1] < 20 and z_score.iloc[-1] < -1: return "BUY"
        elif stoch_k.iloc[-1] > 80 and z_score.iloc[-1] > 1: return "SELL"
        return "NEUTRAL"

# 6. Copula-based Pairs Trading (Self-Copula over time proxy)
class CopulaBasedTimeArb(BaseStrategy):
    name = "Copula_Time_Dependence"
    category = "Statistical Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 60: return "NEUTRAL"
        # Proxy: Copula between price and its momentum
        ret = df['close'].pct_change().dropna()
        mom = df['close'].pct_change(10).dropna()
        if len(ret) < 50: return "NEUTRAL"
        # Empirical CDFs
        u = stats.rankdata(ret[-50:]) / 51.0
        v = stats.rankdata(mom[-50:]) / 51.0
        # If extreme decorrelation (e.g., U is high but V is low)
        last_u, last_v = u[-1], v[-1]
        if last_u < 0.1 and last_v > 0.9: return "BUY" # Mispricing
        elif last_u > 0.9 and last_v < 0.1: return "SELL"
        return "NEUTRAL"

# 7. Hidden Markov Model (HMM) Regime Arb (Simplified 2-State proxy)
class HMMRegimeArb(BaseStrategy):
    name = "HMM_Regime_Arb"
    category = "Statistical Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        ret = df['close'].pct_change().dropna()
        # Fast proxy for 2-state Gaussian HMM: compare short vs long variance
        var_short = ret.rolling(10).var().iloc[-1]
        var_long = ret.rolling(50).var().iloc[-1]
        if var_short == 0 or pd.isna(var_short) or pd.isna(var_long): return "NEUTRAL"
        ratio = var_short / var_long
        # If transitioning to high vol regime, mean reversion fails; if low vol, it works
        z_score = (df['close'].iloc[-1] - df['close'].rolling(20).mean().iloc[-1]) / df['close'].rolling(20).std().iloc[-1]
        if ratio < 0.8: # Low vol regime -> Mean revert
            if z_score < -1.5: return "BUY"
            elif z_score > 1.5: return "SELL"
        elif ratio > 1.5: # High vol regime -> Trend follow
            if z_score > 2.0: return "BUY"
            elif z_score < -2.0: return "SELL"
        return "NEUTRAL"

# 8. Fractional Brownian Motion Arb (Hurst Exponent)
class HurstExponentArb(BaseStrategy):
    name = "Fractional_Brownian_Motion"
    category = "Statistical Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 100: return "NEUTRAL"
        close = df['close'].values[-100:]
        # Calculate Hurst exponent proxy (Rescaled Range)
        diffs = np.diff(close)
        if np.std(diffs) == 0: return "NEUTRAL"
        
        # Simplified R/S analysis on single 100-period window
        cum_dev = np.cumsum(close - np.mean(close))
        R = np.max(cum_dev) - np.min(cum_dev)
        S = np.std(close)
        if S == 0: return "NEUTRAL"
        # H = log(R/S) / log(N)
        hurst = math.log(R/S) / math.log(100)
        
        # If H < 0.5 (Mean Reverting)
        if hurst < 0.45:
            sma = np.mean(close[-20:])
            std = np.std(close[-20:])
            if std > 0:
                z = (close[-1] - sma) / std
                if z < -1.0: return "BUY"
                if z > 1.0: return "SELL"
        # If H > 0.55 (Trending)
        elif hurst > 0.55:
            sma = np.mean(close[-20:])
            if close[-1] > sma * 1.02: return "BUY"
            if close[-1] < sma * 0.98: return "SELL"
        return "NEUTRAL"

# 9. Bayesian Pairs Trading (Bayesian updating of moving average)
class BayesianMeanReversion(BaseStrategy):
    name = "Bayesian_Mean_Reversion"
    category = "Statistical Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 30: return "NEUTRAL"
        # Prior is the 30-day mean
        prior_mean = df['close'].rolling(30).mean().iloc[-2]
        prior_var = df['close'].rolling(30).var().iloc[-2]
        
        latest_price = df['close'].iloc[-1]
        meas_var = prior_var * 0.5 # Assume newer data has 50% variance of prior
        
        if pd.isna(prior_mean) or prior_var == 0: return "NEUTRAL"
        
        # Posterior update
        posterior_mean = (prior_mean * meas_var + latest_price * prior_var) / (prior_var + meas_var)
        
        # Trade if price significantly deviates from posterior belief
        deviation = (latest_price - posterior_mean) / math.sqrt(prior_var)
        if deviation < -1.5: return "BUY"
        elif deviation > 1.5: return "SELL"
        return "NEUTRAL"

# 10. Dynamic Time Warping (DTW) Stat Arb Proxy
class DTWPatternMatch(BaseStrategy):
    name = "Dynamic_Time_Warping_Arb"
    category = "Statistical Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 60: return "NEUTRAL"
        # Proxy: Match the last 10 candles with a known mean-reverting pattern (V-shape or inverted V)
        recent = df['close'].values[-10:]
        norm_recent = (recent - np.min(recent)) / (np.max(recent) - np.min(recent) + 1e-6)
        
        v_shape = np.array([1, 0.8, 0.6, 0.4, 0.2, 0.0, 0.2, 0.4, 0.6, 0.8])
        inv_v = 1.0 - v_shape
        
        # Euclidean distance as proxy for DTW cost
        dist_v = np.sum((norm_recent - v_shape)**2)
        dist_inv = np.sum((norm_recent - inv_v)**2)
        
        # If it closely matches a V-shape, it's already rebounded, so buy the momentum
        if dist_v < 1.0:
            return "BUY"
        elif dist_inv < 1.0:
            return "SELL"
        return "NEUTRAL"
