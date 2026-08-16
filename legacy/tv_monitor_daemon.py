import asyncio
import json
import os
import sys
import time
import urllib.request
import pandas as pd
import numpy as np
import websockets

# Import backtest service and yahoo finance service
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from tradingview_mcp.core.services.backtest_service import _fetch_ohlcv, compare_strategies

# Paths
MD_PATH = r"E:\Python\TradingViewAntigravity\tv_active_chart.md"
JSON_PATH = r"E:\Python\TradingViewAntigravity\tv_active_chart.json"

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return np.zeros_like(prices)
    deltas = np.diff(prices)
    seed = deltas[:period+1]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else 0
    rsi = np.zeros_like(prices)
    rsi[:period] = 100. - 100. / (1. + rs)

    for i in range(period, len(prices)):
        delta = deltas[i-1]
        if delta > 0:
            upval = delta
            downval = 0.
        else:
            upval = 0.
            downval = -delta

        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        rs = up / down if down != 0 else 0
        rsi[i] = 100. - 100. / (1. + rs)
    return rsi

def get_websocket_url():
    try:
        req = urllib.request.Request("http://127.0.0.1:9222/json")
        with urllib.request.urlopen(req, timeout=2) as response:
            data = json.loads(response.read().decode())
            for item in data:
                if 'tradingview.com' in item.get('url', ''):
                    return item.get('webSocketDebuggerUrl'), item.get('title'), item.get('url')
    except Exception as e:
        print(f"Error in get_websocket_url: {e}", file=sys.stderr)
    return None, None, None


async def query_chart_details(ws_url):
    try:
        async with websockets.connect(ws_url, close_timeout=2) as ws:
            js_expr = """
            (() => {
                const results = {};
                results.title = document.title;
                results.href = window.location.href;
                
                const searchEl = document.getElementById('header-toolbar-symbol-search') || 
                                 document.querySelector('[id*="symbol-search"]') || 
                                 document.querySelector('[data-name*="symbol-search"]') ||
                                 document.querySelector('[class*="symbol-search"]');
                
                results.symbol = searchEl ? searchEl.textContent.trim() : null;
                
                const exchangeEl = document.querySelector('[class*="exchangeTitle-"]');
                results.exchange = exchangeEl ? exchangeEl.textContent.trim() : null;
                
                const intervalEl = document.querySelector('[class*="intervalTitle-"]');
                results.interval = intervalEl ? intervalEl.textContent.trim() : "1D";
                
                return results;
            })()
            """
            await ws.send(json.dumps({
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {"expression": js_expr, "returnByValue": True}
            }))
            
            for _ in range(30):
                msg = json.loads(await ws.recv())
                if msg.get("id") == 1:
                    result = msg.get("result", {}).get("result", {}).get("value", {})
                    return result

    except Exception as e:
        print(f"Error communicating with tab: {e}", file=sys.stderr)
    return None

def analyze_index_or_stock(yahoo_symbol, interval_str):
    try:
        candles = _fetch_ohlcv(yahoo_symbol, '6mo', interval_str)
        if not candles:
            return None
            
        df = pd.DataFrame(candles)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['sma50'] = df['close'].rolling(window=50).mean()
        
        df['rsi'] = calculate_rsi(df['close'].values, 14)
        
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26
        df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['hist'] = df['macd'] - df['signal']
        
        df['std20'] = df['close'].rolling(window=20).std()
        df['bb_mid'] = df['close'].rolling(window=20).mean()
        df['bb_upper'] = df['bb_mid'] + 2 * df['std20']
        df['bb_lower'] = df['bb_mid'] - 2 * df['std20']
        df['bbw'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid']
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df['atr'] = true_range.rolling(14).mean()
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        return {
            "close": float(latest['close']),
            "prev_close": float(prev['close']),
            "ema20": float(latest['ema20']),
            "sma50": float(latest['sma50']) if not pd.isna(latest['sma50']) else None,
            "rsi": float(latest['rsi']),
            "macd": float(latest['macd']),
            "signal": float(latest['signal']),
            "hist": float(latest['hist']),
            "bb_upper": float(latest['bb_upper']),
            "bb_mid": float(latest['bb_mid']),
            "bb_lower": float(latest['bb_lower']),
            "bbw": float(latest['bbw']),
            "atr": float(latest['atr']) if not pd.isna(latest['atr']) else None
        }
    except Exception as e:
        print(f"Error computing indicators for {yahoo_symbol}: {e}", file=sys.stderr)
    return None



def get_position_sizing_table(symbol, close_price, atr, bias):
    if not atr or atr <= 0:
        atr = close_price * 0.01  # fallback to 1% of price
    
    if "BUY" in bias:
        sl = close_price - 1.5 * atr
        tp = close_price + 3.0 * atr
    elif "SELL" in bias:
        sl = close_price + 1.5 * atr
        tp = close_price - 3.0 * atr
    else:
        # Neutral - use a hypothetical breakout setup
        sl = close_price - 1.5 * atr
        tp = close_price + 3.0 * atr
        
    from tradingview_mcp.core.services.position_sizer import calculate_position_size
    
    tiers = [
        ("₹1,000", 1000.0),
        ("₹2,000", 2000.0),
        ("₹3,000", 3000.0),
        ("₹4,000", 4000.0),
        ("₹5,000", 5000.0)
    ]
    
    # Run a test calculation to determine if we are in Option Buying mode
    sample_res = calculate_position_size(symbol, 1000.0, 1.0, close_price, sl, tp)
    is_opt = "Option" in sample_res.get("asset_class", "")
    
    lines = []
    if is_opt:
        lines.append("## 📊 Index Options Buying Sizer (₹1,000 to ₹5,000 Tiers)")
        lines.append(f"* **Mode**: Weekly Out-of-the-Money Option Buying")
        lines.append(f"* **Est. Premium Entry**: `₹{sample_res['entry_price']:.2f}` | **Premium Stop Loss**: `₹{sample_res['stop_loss']:.2f}` | **Premium Target**: `₹{sample_res['take_profit']:.2f}`")
        lines.append("")
        lines.append("| Capital Tier | Recommended Size | Premium Cost | Projected Profit | Risk-Reward | Actual Risk |")
        lines.append("|---|---|---|---|---|---|")
        
        for label, cap in tiers:
            res = calculate_position_size(symbol, cap, 1.0, close_price, sl, tp)
            if "error" in res:
                continue
            size_str = f"{res['recommended_size']} {res['units_label']}"
            if res['lot_details']['contract_lots'] is not None:
                size_str += f" ({res['lot_details']['contract_lots']} lots)"
            lines.append(f"| {label} | {size_str} | ₹{res['capital_required']:,.2f} | ₹{res['projected_profit']:,.2f} | {res['risk_reward_ratio']}:1 | ₹{res['actual_risk_amount']:,.2f} |")
    else:
        lines.append("## 📊 Position Sizing & Lot Calculator (1% Risk)")
        lines.append(f"* **Entry**: `{close_price:,.2f}` | **Stop Loss**: `{sl:,.2f}` | **Take Profit**: `{tp:,.2f}`")
        lines.append("")
        lines.append("| Capital Tier | Recommended Size | Required Margin | Projected Profit | Risk-Reward |")
        lines.append("|---|---|---|---|---|")
        
        for label, cap in tiers:
            res = calculate_position_size(symbol, cap, 1.0, close_price, sl, tp)
            if "error" in res:
                continue
            
            size_str = f"{res['recommended_size']:,} {res['units_label']}"
            if res['lot_details']['contract_lots'] is not None:
                size_str += f" ({res['lot_details']['contract_lots']} lots)"
            elif res['lot_details']['standard_lots'] is not None:
                size_str += f" ({res['lot_details']['standard_lots']} std lots)"
                
            lines.append(f"| {label} | {size_str} | ₹{res['capital_required']:,.2f} | ₹{res['projected_profit']:,.2f} | {res['risk_reward_ratio']}:1 |")
        
    return "\n".join(lines) + "\n"


async def monitor_loop():
    last_symbol = None
    last_interval = None
    last_update_time = 0
    
    print("Starting TradingView Monitor Daemon...")
    
    while True:
        try:
            ws_url, tab_title, tab_url = get_websocket_url()
            if not ws_url:
                # No active TradingView tab
                if last_symbol is not None:
                    status = {"status": "No active TradingView tab detected."}
                    with open(JSON_PATH, "w", encoding="utf-8") as f:
                        json.dump(status, f, indent=2)
                    with open(MD_PATH, "w", encoding="utf-8") as f:
                        f.write("# TradingView Monitor\n\nNo active TradingView tab detected. Please open TradingView in your browser.")

                    last_symbol = None
                    last_interval = None
                await asyncio.sleep(2)
                continue
                
            details = await query_chart_details(ws_url)
            if not details or not details.get("symbol"):
                await asyncio.sleep(2)
                continue
                
            tv_symbol = details.get("symbol")
            tv_exchange = details.get("exchange")
            tv_interval = details.get("interval", "1D")
            
            # Map interval to refresh time in seconds (e.g. 1 minute refresh for intraday, 5 minutes for daily)
            interval_secs = 60
            if tv_interval == "1D":
                interval_secs = 300
                
            elapsed = time.time() - last_update_time
            
            if tv_symbol == last_symbol and tv_interval == last_interval and elapsed < interval_secs:
                await asyncio.sleep(2)
                continue
                
            if tv_symbol != last_symbol or tv_interval != last_interval:
                print(f"Detected change: {tv_symbol} on {tv_exchange} ({tv_interval})")
            else:
                print(f"Periodic refresh for {tv_symbol} ({tv_interval})")
            
            # Map symbol to Yahoo Finance
            yahoo_symbol = tv_symbol
            if "BANKNIFTY" in tv_symbol:
                yahoo_symbol = "^NSEBANK"
            elif "NIFTY" in tv_symbol:
                yahoo_symbol = "^NSEI"
            elif "SENSEX" in tv_symbol:
                yahoo_symbol = "^BSESN"
            elif tv_exchange in ["BINANCE", "COINBASE", "KRAKEN", "BYBIT"] or any(coin in tv_symbol for coin in ["BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "DOT", "LINK", "LTC", "AVAX"]):
                base_coin = tv_symbol.replace("USDT", "").replace("USD", "").replace("-", "").strip()
                yahoo_symbol = f"{base_coin}-USD"
            elif tv_exchange == "NSE":
                if len(tv_symbol) <= 15:
                    yahoo_symbol = f"{tv_symbol}.NS"
            elif tv_exchange == "BIST":
                yahoo_symbol = f"{tv_symbol}.IS"
            
            # Interval map
            interval_map = {"1D": "1d", "1W": "1w", "1M": "1m", "1h": "1h", "4h": "1h", "15m": "1h", "5m": "1h", "1": "1h", "3": "1h", "5": "1h", "15": "1h", "30": "1h", "45": "1h", "60": "1h", "120": "1h", "240": "1h"}
            backtest_interval = interval_map.get(tv_interval, "1d")
            
            # Fetch technical indicators
            ta = analyze_index_or_stock(yahoo_symbol, backtest_interval)
            
            # Run strategy race
            try:
                race = compare_strategies(yahoo_symbol, period="1y", initial_capital=10000.0, interval=backtest_interval)
            except Exception as e:
                race = {"error": str(e)}
                
            # Compute trade recommendation
            rec = "NEUTRAL"
            bias_reason = "Indicators are in consolidation."
            if ta:
                rsi = ta["rsi"]
                close = ta["close"]
                ema20 = ta["ema20"]
                sma50 = ta["sma50"]
                hist = ta["hist"]
                
                # Simple logic for recommendations
                if close > ema20 and (sma50 is None or close > sma50) and rsi > 50 and hist > 0:
                    rec = "BUY / LONG"
                    bias_reason = "Bullish momentum confirmed by price trading above EMA20/SMA50, RSI > 50, and MACD crossing bullishly."
                elif close < ema20 and (sma50 is None or close < sma50) and rsi < 50 and hist < 0:
                    rec = "SELL / SHORT"
                    bias_reason = "Bearish momentum confirmed by price trading below EMA20/SMA50, RSI < 50, and MACD crossing bearishly."
                else:
                    rec = "NEUTRAL (CONSOLIDATION)"
                    if sma50:
                        bias_reason = f"Mixed signals. Price ({close:,.2f}) stands relative to EMA20 ({ema20:,.2f}) and SMA50 ({sma50:,.2f}), RSI is neutral at {rsi:.1f}."
                    else:
                        bias_reason = f"Mixed signals. Price ({close:,.2f}) stands relative to EMA20 ({ema20:,.2f}), RSI is neutral at {rsi:.1f}."
            
            # Save JSON status
            status = {
                "tv_symbol": tv_symbol,
                "tv_exchange": tv_exchange,
                "tv_interval": tv_interval,
                "yahoo_symbol": yahoo_symbol,
                "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "recommendation": rec,
                "bias_reason": bias_reason,
                "indicators": ta,
                "strategy_race": race
            }
            with open(JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(status, f, indent=2)

                
            # Save Markdown file
            md_content = f"""# TradingView Real-Time Recommendation

**Active Chart**: `{tv_symbol}` on `{tv_exchange}` (`{tv_interval}`)  
**Last Updated**: `{status['last_updated']}`

---

## ⚡ Active Recommendation: **{rec}**
**Bias Reason**: {bias_reason}

---

## 📈 Technical Indicators
"""
            if ta:
                sma_str = f"`{ta['sma50']:,.2f}`" if ta['sma50'] else "N/A"
                bbw_str = f"Squeeze active (width: {ta['bbw']:.4f})" if ta['bbw'] < 0.05 else f"Normal range (width: {ta['bbw']:.4f})"
                md_content += f"""
* **Current Close**: `{ta['close']:,.2f}`
* **20-day EMA**: `{ta['ema20']:,.2f}`
* **50-day SMA**: {sma_str}
* **RSI (14)**: `{ta['rsi']:.2f}` ({"Overbought" if ta['rsi'] > 70 else "Oversold" if ta['rsi'] < 30 else "Neutral"})
* **MACD**: `{ta['macd']:.2f}` | **Signal**: `{ta['signal']:.2f}` | **Hist**: `{ta['hist']:.2f}`
* **Bollinger Bands**: Upper `{ta['bb_upper']:,.2f}` | Mid `{ta['bb_mid']:,.2f}` | Lower `{ta['bb_lower']:,.2f}`
* **Bollinger Band Width (BBW)**: {bbw_str}
* **ATR (14)**: `{ta['atr']:.2f}`
"""
                sizing_table = get_position_sizing_table(tv_symbol, ta['close'], ta['atr'], rec)
                md_content += "\n" + sizing_table
            else:
                md_content += "\n*(Unable to calculate indicators - index/stock may not be supported on Yahoo Finance)*\n"
                
            md_content += "\n## 🏆 Strategy Comparison Leaderboard (Last 1 Year)\n"
            if "ranking" in race:
                md_content += "| Rank | Strategy | Return % | Win Rate % | Profit Factor | Max DD % | Trades |\n"
                md_content += "|---|---|---|---|---|---|---|\n"
                for entry in race["ranking"][:5]:
                    pf = f"{entry['profit_factor']:.2f}" if entry['profit_factor'] != float('inf') else "∞"
                    md_content += f"| {entry['rank']} | {entry['strategy_label']} | {entry['total_return_pct']:.2f}% | {entry['win_rate_pct']:.1f}% | {pf} | {entry['max_drawdown_pct']:.2f}% | {entry['total_trades']} |\n"
            else:
                md_content += "\n*(Strategy comparison not available)*\n"
                
            with open(MD_PATH, "w", encoding="utf-8") as f:
                f.write(md_content)

                
            last_symbol = tv_symbol
            last_interval = tv_interval
            last_update_time = time.time()
            
        except Exception as e:
            print(f"Error in monitor loop: {e}", file=sys.stderr)
            
        await asyncio.sleep(2)

if __name__ == '__main__':
    asyncio.run(monitor_loop())
