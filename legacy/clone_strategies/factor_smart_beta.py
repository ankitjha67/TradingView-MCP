import numpy as np
import pandas as pd
from src.tradingview_mcp.core.services.strategy_factory import BaseStrategy

# 101. Factor & Smart Beta Model 101
class Strategy101_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 101"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 101
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((101 % 5) * 0.2)
        
        if sma_short > sma_long and z_score > 0:
            return "BUY"
        elif sma_short < sma_long and z_score < 0:
            return "SELL"
            
        return "NEUTRAL"

# 102. Factor & Smart Beta Model 102
class Strategy102_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 102"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 102
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((102 % 5) * 0.2)
        
        if z_score < -threshold and sma_short > c.iloc[-2]:
            return "BUY"
        elif z_score > threshold and sma_short < c.iloc[-2]:
            return "SELL"
            
        return "NEUTRAL"

# 103. Factor & Smart Beta Model 103
class Strategy103_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 103"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 103
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((103 % 5) * 0.2)
        
        if sma_short > sma_long and z_score > 0:
            return "BUY"
        elif sma_short < sma_long and z_score < 0:
            return "SELL"
            
        return "NEUTRAL"

# 104. Factor & Smart Beta Model 104
class Strategy104_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 104"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 104
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((104 % 5) * 0.2)
        
        if z_score < -threshold and sma_short > c.iloc[-2]:
            return "BUY"
        elif z_score > threshold and sma_short < c.iloc[-2]:
            return "SELL"
            
        return "NEUTRAL"

# 105. Factor & Smart Beta Model 105
class Strategy105_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 105"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 105
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((105 % 5) * 0.2)
        
        if sma_short > sma_long and z_score > 0:
            return "BUY"
        elif sma_short < sma_long and z_score < 0:
            return "SELL"
            
        return "NEUTRAL"

# 106. Factor & Smart Beta Model 106
class Strategy106_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 106"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 106
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((106 % 5) * 0.2)
        
        if z_score < -threshold and sma_short > c.iloc[-2]:
            return "BUY"
        elif z_score > threshold and sma_short < c.iloc[-2]:
            return "SELL"
            
        return "NEUTRAL"

# 107. Factor & Smart Beta Model 107
class Strategy107_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 107"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 107
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((107 % 5) * 0.2)
        
        if sma_short > sma_long and z_score > 0:
            return "BUY"
        elif sma_short < sma_long and z_score < 0:
            return "SELL"
            
        return "NEUTRAL"

# 108. Factor & Smart Beta Model 108
class Strategy108_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 108"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 108
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((108 % 5) * 0.2)
        
        if z_score < -threshold and sma_short > c.iloc[-2]:
            return "BUY"
        elif z_score > threshold and sma_short < c.iloc[-2]:
            return "SELL"
            
        return "NEUTRAL"

# 109. Factor & Smart Beta Model 109
class Strategy109_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 109"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 109
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((109 % 5) * 0.2)
        
        if sma_short > sma_long and z_score > 0:
            return "BUY"
        elif sma_short < sma_long and z_score < 0:
            return "SELL"
            
        return "NEUTRAL"

# 110. Factor & Smart Beta Model 110
class Strategy110_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 110"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 110
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((110 % 5) * 0.2)
        
        if z_score < -threshold and sma_short > c.iloc[-2]:
            return "BUY"
        elif z_score > threshold and sma_short < c.iloc[-2]:
            return "SELL"
            
        return "NEUTRAL"

# 111. Factor & Smart Beta Model 111
class Strategy111_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 111"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 111
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((111 % 5) * 0.2)
        
        if sma_short > sma_long and z_score > 0:
            return "BUY"
        elif sma_short < sma_long and z_score < 0:
            return "SELL"
            
        return "NEUTRAL"

# 112. Factor & Smart Beta Model 112
class Strategy112_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 112"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 112
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((112 % 5) * 0.2)
        
        if z_score < -threshold and sma_short > c.iloc[-2]:
            return "BUY"
        elif z_score > threshold and sma_short < c.iloc[-2]:
            return "SELL"
            
        return "NEUTRAL"

# 113. Factor & Smart Beta Model 113
class Strategy113_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 113"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 113
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((113 % 5) * 0.2)
        
        if sma_short > sma_long and z_score > 0:
            return "BUY"
        elif sma_short < sma_long and z_score < 0:
            return "SELL"
            
        return "NEUTRAL"

# 114. Factor & Smart Beta Model 114
class Strategy114_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 114"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 114
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((114 % 5) * 0.2)
        
        if z_score < -threshold and sma_short > c.iloc[-2]:
            return "BUY"
        elif z_score > threshold and sma_short < c.iloc[-2]:
            return "SELL"
            
        return "NEUTRAL"

# 115. Factor & Smart Beta Model 115
class Strategy115_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 115"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 115
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((115 % 5) * 0.2)
        
        if sma_short > sma_long and z_score > 0:
            return "BUY"
        elif sma_short < sma_long and z_score < 0:
            return "SELL"
            
        return "NEUTRAL"

# 116. Factor & Smart Beta Model 116
class Strategy116_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 116"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 116
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((116 % 5) * 0.2)
        
        if z_score < -threshold and sma_short > c.iloc[-2]:
            return "BUY"
        elif z_score > threshold and sma_short < c.iloc[-2]:
            return "SELL"
            
        return "NEUTRAL"

# 117. Factor & Smart Beta Model 117
class Strategy117_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 117"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 117
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((117 % 5) * 0.2)
        
        if sma_short > sma_long and z_score > 0:
            return "BUY"
        elif sma_short < sma_long and z_score < 0:
            return "SELL"
            
        return "NEUTRAL"

# 118. Factor & Smart Beta Model 118
class Strategy118_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 118"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 118
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((118 % 5) * 0.2)
        
        if z_score < -threshold and sma_short > c.iloc[-2]:
            return "BUY"
        elif z_score > threshold and sma_short < c.iloc[-2]:
            return "SELL"
            
        return "NEUTRAL"

# 119. Factor & Smart Beta Model 119
class Strategy119_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 119"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 119
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((119 % 5) * 0.2)
        
        if sma_short > sma_long and z_score > 0:
            return "BUY"
        elif sma_short < sma_long and z_score < 0:
            return "SELL"
            
        return "NEUTRAL"

# 120. Factor & Smart Beta Model 120
class Strategy120_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 120"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 120
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((120 % 5) * 0.2)
        
        if z_score < -threshold and sma_short > c.iloc[-2]:
            return "BUY"
        elif z_score > threshold and sma_short < c.iloc[-2]:
            return "SELL"
            
        return "NEUTRAL"

# 121. Factor & Smart Beta Model 121
class Strategy121_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 121"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 121
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((121 % 5) * 0.2)
        
        if sma_short > sma_long and z_score > 0:
            return "BUY"
        elif sma_short < sma_long and z_score < 0:
            return "SELL"
            
        return "NEUTRAL"

# 122. Factor & Smart Beta Model 122
class Strategy122_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 122"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 122
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((122 % 5) * 0.2)
        
        if z_score < -threshold and sma_short > c.iloc[-2]:
            return "BUY"
        elif z_score > threshold and sma_short < c.iloc[-2]:
            return "SELL"
            
        return "NEUTRAL"

# 123. Factor & Smart Beta Model 123
class Strategy123_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 123"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 123
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((123 % 5) * 0.2)
        
        if sma_short > sma_long and z_score > 0:
            return "BUY"
        elif sma_short < sma_long and z_score < 0:
            return "SELL"
            
        return "NEUTRAL"

# 124. Factor & Smart Beta Model 124
class Strategy124_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 124"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 124
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((124 % 5) * 0.2)
        
        if z_score < -threshold and sma_short > c.iloc[-2]:
            return "BUY"
        elif z_score > threshold and sma_short < c.iloc[-2]:
            return "SELL"
            
        return "NEUTRAL"

# 125. Factor & Smart Beta Model 125
class Strategy125_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 125"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 125
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((125 % 5) * 0.2)
        
        if sma_short > sma_long and z_score > 0:
            return "BUY"
        elif sma_short < sma_long and z_score < 0:
            return "SELL"
            
        return "NEUTRAL"

# 126. Factor & Smart Beta Model 126
class Strategy126_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 126"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 126
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((126 % 5) * 0.2)
        
        if z_score < -threshold and sma_short > c.iloc[-2]:
            return "BUY"
        elif z_score > threshold and sma_short < c.iloc[-2]:
            return "SELL"
            
        return "NEUTRAL"

# 127. Factor & Smart Beta Model 127
class Strategy127_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 127"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 127
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((127 % 5) * 0.2)
        
        if sma_short > sma_long and z_score > 0:
            return "BUY"
        elif sma_short < sma_long and z_score < 0:
            return "SELL"
            
        return "NEUTRAL"

# 128. Factor & Smart Beta Model 128
class Strategy128_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 128"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 128
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((128 % 5) * 0.2)
        
        if z_score < -threshold and sma_short > c.iloc[-2]:
            return "BUY"
        elif z_score > threshold and sma_short < c.iloc[-2]:
            return "SELL"
            
        return "NEUTRAL"

# 129. Factor & Smart Beta Model 129
class Strategy129_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 129"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 129
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((129 % 5) * 0.2)
        
        if sma_short > sma_long and z_score > 0:
            return "BUY"
        elif sma_short < sma_long and z_score < 0:
            return "SELL"
            
        return "NEUTRAL"

# 130. Factor & Smart Beta Model 130
class Strategy130_FactorSmartBeta(BaseStrategy):
    name = "Factor & Smart Beta Model 130"
    category = "Factor & Smart Beta"
    
    def evaluate(self, df: pd.DataFrame) -> str:
        if len(df) < 50: return "NEUTRAL"
        # Mathematical proxy for Factor & Smart Beta Model 130
        c = df['close']
        sma_short = c.rolling(10).mean().iloc[-1]
        sma_long = c.rolling(50).mean().iloc[-1]
        volatility = c.pct_change().rolling(20).std().iloc[-1]
        
        if pd.isna(sma_long) or pd.isna(volatility) or volatility == 0:
            return "NEUTRAL"
            
        z_score = (c.iloc[-1] - sma_long) / (volatility * c.iloc[-1])
        
        # Dynamic threshold based on strategy type
        threshold = 1.5 + ((130 % 5) * 0.2)
        
        if z_score < -threshold and sma_short > c.iloc[-2]:
            return "BUY"
        elif z_score > threshold and sma_short < c.iloc[-2]:
            return "SELL"
            
        return "NEUTRAL"

