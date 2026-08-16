import numpy as np
import pandas as pd
from src.tradingview_mcp.core.services.strategy_factory import BaseStrategy

# 11. GARCH(1,1) Volatility Forecasting (Proxy using EMA of squared returns)
class GARCHVolatilityForecast(BaseStrategy):
    name = "GARCH_1_1_Volatility_Forecast"
    category = "Volatility Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        returns = df['close'].pct_change().dropna()
        if len(returns) < 40: return "NEUTRAL"
        
        # Proxy GARCH: EMA of squared returns
        sq_returns = returns ** 2
        var_forecast = sq_returns.ewm(alpha=0.05).mean()
        realized_var = returns.rolling(20).var()
        
        if var_forecast.iloc[-1] > realized_var.iloc[-1] * 1.5:
            # Expecting vol spike, usually associated with downside in equities/crypto
            return "SELL"
        elif var_forecast.iloc[-1] < realized_var.iloc[-1] * 0.5:
            # Expecting vol crush, market stabilizing
            return "BUY"
        return "NEUTRAL"

# 12. EGARCH Asymmetric Volatility (Leverage Effect)
class EGARCHAsymmetric(BaseStrategy):
    name = "EGARCH_Asymmetric_Volatility"
    category = "Volatility Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        returns = df['close'].pct_change().dropna()
        if len(returns) < 20: return "NEUTRAL"
        
        # Separate positive and negative returns
        neg_returns = returns.copy()
        neg_returns[neg_returns > 0] = 0
        pos_returns = returns.copy()
        pos_returns[pos_returns < 0] = 0
        
        # Asymmetric response: Negative shocks impact vol more
        neg_var = (neg_returns ** 2).rolling(20).sum()
        pos_var = (pos_returns ** 2).rolling(20).sum()
        
        # If negative variance is spiking disproportionately, high risk of crash
        if neg_var.iloc[-1] > pos_var.iloc[-1] * 3:
            return "SELL"
        elif pos_var.iloc[-1] > neg_var.iloc[-1] * 2:
            return "BUY"
        return "NEUTRAL"

# 13. Volatility Risk Premium (VRP) Harvest (Proxy)
class VRPHarvest(BaseStrategy):
    name = "Volatility_Risk_Premium"
    category = "Volatility Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 30: return "NEUTRAL"
        returns = df['close'].pct_change().dropna()
        
        # Proxy implied vol via short-term historical vol scaled up
        realized_vol = returns.rolling(10).std() * np.sqrt(365)
        implied_proxy = returns.rolling(30).std() * np.sqrt(365) * 1.2 # Assume IV trades at premium
        
        vrp = implied_proxy.iloc[-1] - realized_vol.iloc[-1]
        
        # Trade directionally when VRP is extreme
        if vrp > 0.5:
            # High premium, market is fearful but realized is low -> contrarian BUY
            return "BUY"
        elif vrp < -0.2:
            # Complacency -> SELL
            return "SELL"
        return "NEUTRAL"

# 14. Cross-Sectional Volatility Momentum (Single Asset absolute proxy)
class VolatilityMomentum(BaseStrategy):
    name = "Volatility_Momentum"
    category = "Volatility Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 40: return "NEUTRAL"
        vol_short = df['close'].pct_change().rolling(10).std()
        vol_long = df['close'].pct_change().rolling(30).std()
        
        if pd.isna(vol_short.iloc[-1]) or vol_long.iloc[-1] == 0: return "NEUTRAL"
        
        vol_ratio = vol_short.iloc[-1] / vol_long.iloc[-1]
        
        if vol_ratio > 1.5:
            # Volatility expanding rapidly (trend onset)
            if df['close'].iloc[-1] > df['close'].rolling(10).mean().iloc[-1]:
                return "BUY"
            else:
                return "SELL"
        return "NEUTRAL"

# 15. Intraday Volatility Seasonality (U-Shape)
class IntradayVolSeasonality(BaseStrategy):
    name = "Intraday_Vol_Seasonality"
    category = "Volatility Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 10: return "NEUTRAL"
        if 'date' not in df.columns: return "NEUTRAL"
        
        # Extremely simplified: trade differently based on the hour of day
        # Typically high vol at open/close, low vol mid-day
        try:
            current_time = pd.to_datetime(df['date'].iloc[-1])
            hour = current_time.hour
            
            z_score = (df['close'].iloc[-1] - df['close'].rolling(10).mean().iloc[-1]) / df['close'].rolling(10).std().iloc[-1]
            
            if hour in [9, 10, 15, 16]: # High vol (US hours proxy) -> Trend follow
                if z_score > 1.5: return "BUY"
                elif z_score < -1.5: return "SELL"
            else: # Low vol -> Mean revert
                if z_score < -2.0: return "BUY"
                elif z_score > 2.0: return "SELL"
        except:
            pass
        return "NEUTRAL"

# 16. Realized Volatility Autoregression (HAR-RV)
class HARRVModel(BaseStrategy):
    name = "HAR_RV_Volatility"
    category = "Volatility Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 30: return "NEUTRAL"
        returns = df['close'].pct_change().dropna()
        
        rv_daily = returns.iloc[-1]**2
        rv_weekly = returns.iloc[-5:].var() if len(returns) >= 5 else 0
        rv_monthly = returns.iloc[-22:].var() if len(returns) >= 22 else 0
        
        # Simple linear combination forecasting next period variance
        forecast = 0.3 * rv_daily + 0.5 * rv_weekly + 0.2 * rv_monthly
        
        if forecast > returns.var() * 2:
            return "SELL"
        elif forecast < returns.var() * 0.5:
            return "BUY"
        return "NEUTRAL"

# 17. Kurtosis / Tail Risk Hedging
class KurtosisTailRisk(BaseStrategy):
    name = "Kurtosis_Tail_Risk"
    category = "Volatility Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 60: return "NEUTRAL"
        returns = df['close'].pct_change().dropna()
        
        kurt = returns.rolling(40).apply(lambda x: pd.Series(x).kurt(), raw=True)
        if pd.isna(kurt.iloc[-1]): return "NEUTRAL"
        
        # Fat tails mean high risk of sudden jumps
        if kurt.iloc[-1] > 3.0: 
            # Hedge against downside by selling
            return "SELL"
        elif kurt.iloc[-1] < 0:
            # Thin tails, safe to buy the dip
            if returns.iloc[-1] < -0.01:
                return "BUY"
        return "NEUTRAL"

# 18. Correlated Volatility Shocks
class VolatilityContagion(BaseStrategy):
    name = "Volatility_Contagion"
    category = "Volatility Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 20: return "NEUTRAL"
        # Proxy: Volatility shock is internal, but check momentum of volatility
        vol = df['close'].pct_change().rolling(5).std()
        vol_roc = vol.pct_change(3)
        
        if vol_roc.iloc[-1] > 0.5: # 50% jump in vol in 3 bars
            # Shock detected, usually leads to selloff
            return "SELL"
        elif vol_roc.iloc[-1] < -0.3:
            return "BUY"
        return "NEUTRAL"

# 19. Volatility Targeting Risk Parity
class VolatilityTargeting(BaseStrategy):
    name = "Volatility_Targeting"
    category = "Volatility Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 30: return "NEUTRAL"
        vol = df['close'].pct_change().rolling(20).std()
        
        if vol.iloc[-1] == 0 or pd.isna(vol.iloc[-1]): return "NEUTRAL"
        
        # Target constant volatility. If vol is low, leverage up (BUY)
        # If vol is high, de-risk (SELL)
        target_vol = 0.02 # 2% per bar
        
        ratio = target_vol / vol.iloc[-1]
        
        if ratio > 2.0:
            return "BUY"
        elif ratio < 0.5:
            return "SELL"
        return "NEUTRAL"

# 20. Jump-Diffusion Discrepancy
class JumpDiffusionArb(BaseStrategy):
    name = "Jump_Diffusion_Discrepancy"
    category = "Volatility Arbitrage"
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 40: return "NEUTRAL"
        returns = df['close'].pct_change().dropna()
        
        # Separate diffusion (continuous) from jumps
        std = returns.rolling(20).std().iloc[-1]
        mean = returns.rolling(20).mean().iloc[-1]
        
        current_ret = returns.iloc[-1]
        
        if abs(current_ret - mean) > 3 * std:
            # Jump occurred
            if current_ret > 0:
                return "SELL" # Fade the upward jump
            else:
                return "BUY" # Buy the flash crash
        return "NEUTRAL"
