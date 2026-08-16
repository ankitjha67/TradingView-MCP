import numpy as np
import pandas as pd
from src.tradingview_mcp.core.services.strategy_factory import BaseStrategy

# 21. Isolation Forest Anomaly Detection (Proxy using Rolling Z-Score outlier detection)
class IsolationForestProxy(BaseStrategy):
    name = "Anomaly_Detection_Isolation_Forest_Proxy"
    category = "Machine Learning"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Proxy for Isolation Forest: finding multi-dimensional outliers
        # We look at price change, volume change, and volatility change
        ret = df['close'].pct_change()
        vol = df['volume'].pct_change()
        vty = df['close'].pct_change().rolling(10).std().pct_change()
        
        # Calculate z-scores for all three
        z_ret = (ret - ret.rolling(40).mean()) / ret.rolling(40).std()
        z_vol = (vol - vol.rolling(40).mean()) / vol.rolling(40).std()
        z_vty = (vty - vty.rolling(40).mean()) / vty.rolling(40).std()
        
        # Combined anomaly score (Euclidean distance from mean)
        score = np.sqrt(z_ret**2 + z_vol**2 + z_vty**2).iloc[-1]
        
        # If anomaly is extremely high, trade the reversal (assuming flash event)
        if score > 4.0:
            if ret.iloc[-1] < 0: return "BUY"
            elif ret.iloc[-1] > 0: return "SELL"
        return "NEUTRAL"

# 22. Support Vector Machine (SVM) Decision Boundary (Linear proxy)
class SVMDecisionBoundary(BaseStrategy):
    name = "SVM_Linear_Decision_Boundary"
    category = "Machine Learning"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 60: return "NEUTRAL"
        # Proxy for a trained linear SVM on two features: RSI and MACD Histogram
        
        # Calculate RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs)).iloc[-1]
        
        # Calculate MACD
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        hist = (macd - signal).iloc[-1]
        
        if pd.isna(rsi) or pd.isna(hist): return "NEUTRAL"
        
        # Pre-calculated hyperplane equation weights (W1*RSI + W2*MACD_HIST + B = 0)
        # Normalized for typical ranges: RSI [0,100], MACD depends on price but let's normalize
        w1 = -0.05
        w2 = 15.0
        b = 2.5
        
        score = (w1 * rsi) + (w2 * hist) + b
        
        # Margin thresholds
        if score > 1.0: return "BUY"
        elif score < -1.0: return "SELL"
        return "NEUTRAL"

# 23. K-Means Clustering Market Regimes
class KMeansRegimeClustering(BaseStrategy):
    name = "K_Means_Market_Regime"
    category = "Machine Learning"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 30: return "NEUTRAL"
        
        # Simplified 1D Clustering on Volatility
        vol = df['close'].pct_change().rolling(20).std() * np.sqrt(365)
        current_vol = vol.iloc[-1]
        
        # Fixed centroids based on broad market assumptions
        c1, c2, c3 = 0.10, 0.25, 0.60 # Low, Medium, High Vol Regimes
        
        dist1 = abs(current_vol - c1)
        dist2 = abs(current_vol - c2)
        dist3 = abs(current_vol - c3)
        
        regime = np.argmin([dist1, dist2, dist3])
        z_score = (df['close'].iloc[-1] - df['close'].rolling(20).mean().iloc[-1]) / df['close'].rolling(20).std().iloc[-1]
        
        if regime == 0: # Low vol: Mean reversion works well
            if z_score < -1.5: return "BUY"
            if z_score > 1.5: return "SELL"
        elif regime == 2: # High vol: Trend following breaks out
            if z_score > 2.0: return "BUY"
            if z_score < -2.0: return "SELL"
        return "NEUTRAL"

# 24. XGBoost Feature Importance Proxy
class XGBoostFeatureSelector(BaseStrategy):
    name = "XGBoost_Ensemble_Proxy"
    category = "Machine Learning"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        
        # Simulating an XGBoost tree structure using nested logic
        c = df['close']
        sma20 = c.rolling(20).mean().iloc[-1]
        sma50 = c.rolling(50).mean().iloc[-1]
        roc10 = c.pct_change(10).iloc[-1]
        vol = df['volume'].rolling(10).mean().iloc[-1]
        curr_vol = df['volume'].iloc[-1]
        
        if pd.isna(sma50) or pd.isna(roc10) or pd.isna(vol): return "NEUTRAL"
        
        # Tree 1
        if c.iloc[-1] > sma50:
            if roc10 > 0.05:
                if curr_vol > vol * 1.5:
                    return "BUY"
        # Tree 2
        elif c.iloc[-1] < sma20:
            if roc10 < -0.05:
                if curr_vol > vol * 1.5:
                    return "SELL"
        return "NEUTRAL"

# 25. Sequence-to-Sequence (Seq2Seq) Trend Prediction Proxy
class Seq2SeqPatternMatching(BaseStrategy):
    name = "Seq2Seq_Pattern_Matching"
    category = "Machine Learning"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 100: return "NEUTRAL"
        # Proxy: Use the last 5 days to find the most similar 5-day sequence in the last 100 days
        # Then predict based on what happened on the 6th day
        
        returns = df['close'].pct_change().fillna(0).values
        query = returns[-5:]
        
        min_dist = float('inf')
        best_idx = -1
        
        for i in range(10, len(returns) - 6):
            target = returns[i:i+5]
            dist = np.sum((query - target)**2)
            if dist < min_dist:
                min_dist = dist
                best_idx = i
                
        if best_idx != -1 and min_dist < 0.01:
            future_return = returns[best_idx + 5]
            if future_return > 0.01: return "BUY"
            elif future_return < -0.01: return "SELL"
            
        return "NEUTRAL"

# 26. Random Forest (Majority Voting)
class RandomForestVoting(BaseStrategy):
    name = "Random_Forest_Majority_Vote"
    category = "Machine Learning"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        
        # 3 distinct weak learners
        c = df['close']
        
        # Learner 1: Momentum
        l1 = "BUY" if c.iloc[-1] > c.iloc[-10] else "SELL"
        
        # Learner 2: Mean Reversion
        z = (c.iloc[-1] - c.rolling(20).mean().iloc[-1]) / c.rolling(20).std().iloc[-1]
        l2 = "BUY" if z < -1 else ("SELL" if z > 1 else "NEUTRAL")
        
        # Learner 3: Volume confirmation
        v_trend = df['volume'].iloc[-1] > df['volume'].rolling(20).mean().iloc[-1]
        if v_trend:
            l3 = "BUY" if c.iloc[-1] > c.iloc[-2] else "SELL"
        else:
            l3 = "NEUTRAL"
            
        votes = [l1, l2, l3]
        buy_votes = votes.count("BUY")
        sell_votes = votes.count("SELL")
        
        if buy_votes >= 2: return "BUY"
        if sell_votes >= 2: return "SELL"
        return "NEUTRAL"

# 27. Elastic Net Regularized Regression
class ElasticNetRegressionProxy(BaseStrategy):
    name = "Elastic_Net_Regression_Proxy"
    category = "Machine Learning"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 40: return "NEUTRAL"
        # Elastic Net penalizes high coefficients and shrinks them (L1 + L2)
        # Proxy: A robust linear model that ignores highly collinear signals
        
        ret1 = df['close'].pct_change(1).iloc[-1]
        ret3 = df['close'].pct_change(3).iloc[-1]
        ret5 = df['close'].pct_change(5).iloc[-1]
        
        if any(pd.isna([ret1, ret3, ret5])): return "NEUTRAL"
        
        # Penalized weights (shrunk towards zero for older data)
        w1, w3, w5 = 0.6, 0.3, 0.1
        
        pred = (w1 * ret1) + (w3 * ret3) + (w5 * ret5)
        
        if pred > 0.02: return "BUY"
        elif pred < -0.02: return "SELL"
        return "NEUTRAL"

# 28. Generative Adversarial Network (GAN) Stress Tester
class GANStressTestProxy(BaseStrategy):
    name = "GAN_Scenario_Stress_Test"
    category = "Machine Learning"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 30: return "NEUTRAL"
        # Proxy: Adding synthetic Gaussian noise to current state to see if signal holds
        c = df['close'].iloc[-1]
        std = df['close'].rolling(20).std().iloc[-1]
        sma = df['close'].rolling(20).mean().iloc[-1]
        
        if pd.isna(std) or std == 0: return "NEUTRAL"
        
        # Generate 10 perturbed scenarios
        scenarios = c + np.random.normal(0, std * 0.5, 10)
        
        buys = sum([1 for s in scenarios if s < sma * 0.95])
        sells = sum([1 for s in scenarios if s > sma * 1.05])
        
        if buys > 8: return "BUY" # Highly robust buy signal despite noise
        if sells > 8: return "SELL"
        return "NEUTRAL"

# 29. Bayesian Neural Networks (BNN) Uncertainty Proxy
class BNNUncertaintyProxy(BaseStrategy):
    name = "BNN_Uncertainty_Aware"
    category = "Machine Learning"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 30: return "NEUTRAL"
        
        # Measure uncertainty via the dispersion of multiple moving averages
        ma10 = df['close'].rolling(10).mean().iloc[-1]
        ma20 = df['close'].rolling(20).mean().iloc[-1]
        ma30 = df['close'].rolling(30).mean().iloc[-1]
        
        if pd.isna([ma10, ma20, ma30]).any(): return "NEUTRAL"
        
        # Uncertainty = standard deviation of the moving averages
        ma_std = np.std([ma10, ma20, ma30])
        current = df['close'].iloc[-1]
        
        # Only trade if uncertainty is low (MAs are clustered together)
        # And price has broken out of the cluster
        if ma_std < (current * 0.005): # Very tight cluster
            if current > np.mean([ma10, ma20, ma30]) * 1.01: return "BUY"
            if current < np.mean([ma10, ma20, ma30]) * 0.99: return "SELL"
            
        return "NEUTRAL"

# 30. Deep LOB (CNN + LSTM) Imbalance
class DeepLOBProxy(BaseStrategy):
    name = "Deep_LOB_Imbalance_CNN"
    category = "Machine Learning"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 10: return "NEUTRAL"
        # Proxy: Deep LOB uses spatial features of the order book.
        # Since we only have OHLCV, we use the intra-bar candle shape (wick vs body)
        # to approximate buy/sell pressure.
        
        O, H, L, C = df['open'].iloc[-1], df['high'].iloc[-1], df['low'].iloc[-1], df['close'].iloc[-1]
        
        body = abs(C - O)
        upper_wick = H - max(C, O)
        lower_wick = min(C, O) - L
        
        total_range = H - L
        if total_range == 0: return "NEUTRAL"
        
        # Strong rejection of lower prices (hammer-like spatial feature)
        if lower_wick > body * 2 and lower_wick > upper_wick * 2:
            return "BUY"
        # Strong rejection of higher prices (shooting star spatial feature)
        elif upper_wick > body * 2 and upper_wick > lower_wick * 2:
            return "SELL"
            
        return "NEUTRAL"
