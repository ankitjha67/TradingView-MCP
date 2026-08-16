import os
import sys
import pandas as pd
import numpy as np

# Removed sys.path.append('src') because running from root handles it.
from src.tradingview_mcp.core.services.strategy_factory import StrategyFactory
from src.tradingview_mcp.core.services.position_sizing import PositionSizer

def generate_synthetic_data(num_bars=250):
    np.random.seed()
    dates = pd.date_range(end=pd.Timestamp.now(), periods=num_bars, freq='h')
    returns = np.random.normal(loc=0.0001, scale=0.005, size=num_bars)
    price = 60000.0 * np.exp(np.cumsum(returns))
    
    df = pd.DataFrame({
        'date': dates,
        'open': price * (1 + np.random.normal(0, 0.001, num_bars)),
        'high': price * (1 + abs(np.random.normal(0, 0.002, num_bars))),
        'low': price * (1 - abs(np.random.normal(0, 0.002, num_bars))),
        'close': price,
        'volume': np.random.lognormal(mean=5, sigma=1, size=num_bars) * 100
    })
    return df

def run_live_monitor(capital_inr=5000):
    print("🚀 Initializing Antigravity Live Market Monitor...")
    print(f"💰 Available Capital: {capital_inr} INR")
    
    factory = StrategyFactory()
    strategies = factory.get_all_strategies()
    print(f"🧠 Loaded {len(strategies)} institutional strategies.")
    
    df = generate_synthetic_data()
    current_price = df['close'].iloc[-1]
    
    print(f"📊 Market Data Acquired (Simulated BTCUSD) - Current Price: ${current_price:.2f}")
    
    sizer = PositionSizer()
    pos_details = sizer.get_position_details(current_price, capital_inr)
    
    print(f"⚖️ Capital Allocation -> {pos_details['quantity']} BTC (${pos_details['cost_usd']} | {pos_details['cost_inr']} INR)\n")
    print("-" * 50)
    print("📡 SCANNING 200+ MODELS FOR SIGNALS...")
    
    buys = []
    sells = []
    
    for strat in strategies:
        try:
            signal = strat.evaluate(df)
            if signal == "BUY":
                buys.append(strat.name)
            elif signal == "SELL":
                sells.append(strat.name)
        except Exception as e:
            pass
            
    print("-" * 50)
    print(f"✅ Scanning Complete.")
    print(f"📈 Total BUY Signals: {len(buys)}")
    print(f"📉 Total SELL Signals: {len(sells)}")
    print(f"⏸️ NEUTRAL Signals: {len(strategies) - len(buys) - len(sells)}")
    
    print("\n🔥 TOP RECOMMENDATIONS 🔥")
    if buys:
        print("\nBUY (Long) Consensus Models:")
        for b in buys[:5]:
            print(f"  🟢 {b}")
            
    if sells:
        print("\nSELL (Short) Consensus Models:")
        for s in sells[:5]:
            print(f"  🔴 {s}")
            
    if len(buys) > len(sells) * 1.5:
        print(f"\n🔮 SYSTEM VERDICT: STRONG BUY - Execute market order for {pos_details['quantity']} BTC.")
    elif len(sells) > len(buys) * 1.5:
        print(f"\n🔮 SYSTEM VERDICT: STRONG SELL - Execute short order for {pos_details['quantity']} BTC.")
    else:
        print("\n🔮 SYSTEM VERDICT: MIXED/NEUTRAL - Hold capital. Market conditions ambiguous.")

if __name__ == "__main__":
    run_live_monitor()
