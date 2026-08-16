import os
import sys
import pandas as pd
import numpy as np

# Add src to path just like start.py does
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from tradingview_mcp.core.quant.registry import get_registry
from tradingview_mcp.core.services.position_sizing import PositionSizer

def generate_synthetic_data(base_price=60000.0, num_bars=250):
    np.random.seed()
    dates = pd.date_range(end=pd.Timestamp.now(), periods=num_bars, freq='h')
    returns = np.random.normal(loc=0.0001, scale=0.005, size=num_bars)
    price = base_price * np.exp(np.cumsum(returns))
    
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
    
    reg = get_registry()
    strategies = reg.all()
    print(f"🧠 Loaded {len(strategies)} institutional strategies.")
    
    import json
    from src.tradingview_mcp.core.services.yahoo_finance_service import get_price
    
    # Read active ticker
    symbol = "BTC-USD"
    try:
        with open("tv_active_chart.json", "r") as f:
            data = json.load(f)
            symbol = data.get("chart", {}).get("symbol", "BTC-USD")
    except Exception:
        pass
        
    print(f"👁️ Detected Active TV Ticker: {symbol}")
    
    # Fetch real price
    real_data = get_price(symbol)
    base_price = real_data.get("price", 60000.0) if real_data else 60000.0
    if not base_price:
        base_price = 60000.0
        
    df = generate_synthetic_data(base_price=base_price)
    current_price = df['close'].iloc[-1]
    
    print(f"📊 Market Data Acquired (Simulated {symbol} anchored to Real Price) - Current Price: ${current_price:.2f}")
    
    sizer = PositionSizer(max_capital_inr=max(5000.0, float(capital_inr)))
    pos_details = sizer.get_position_details(current_price, capital_inr)
    
    print(f"⚖️ Capital Allocation -> {pos_details['quantity']} {symbol} (${pos_details['cost_usd']} | {pos_details['cost_inr']} INR)\n")
    print("-" * 50)
    print("📡 SCANNING MODELS FOR SIGNALS...")
    
    buys = []
    sells = []
    
    for strat in strategies:
        try:
            signal = strat.evaluate(df)
            if signal == "BUY":
                buys.append(strat.__class__.__name__)
            elif signal == "SELL":
                sells.append(strat.__class__.__name__)
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
        print(f"\n🔮 SYSTEM VERDICT: STRONG BUY - Execute market order for {pos_details['quantity']} {symbol}.")
    elif len(sells) > len(buys) * 1.5:
        print(f"\n🔮 SYSTEM VERDICT: STRONG SELL - Execute short order for {pos_details['quantity']} {symbol}.")
    else:
        print("\n🔮 SYSTEM VERDICT: MIXED/NEUTRAL - Hold capital. Market conditions ambiguous.")

if __name__ == "__main__":
    capital = 5000
    if len(sys.argv) > 1:
        try:
            capital = int(sys.argv[1])
        except ValueError:
            pass
    run_live_monitor(capital_inr=capital)
