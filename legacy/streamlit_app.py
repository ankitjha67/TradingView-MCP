import streamlit as st
import json
import os
import pandas as pd
import plotly.graph_objects as go
import time
from llm_analyzer import generate_analysis

# --- Page Config & Styling ---
st.set_page_config(page_title="Universal Trading Dashboard", layout="wide", initial_sidebar_state="expanded")

# Custom CSS for modern premium feel
st.markdown("""
    <style>
    .main {
        background-color: #0E1117;
        color: #FAFAFA;
    }
    .metric-card {
        background: rgba(30, 30, 30, 0.6);
        border-radius: 12px;
        padding: 20px;
        border: 1px solid rgba(255,255,255,0.1);
        margin-bottom: 20px;
        backdrop-filter: blur(10px);
    }
    .stButton>button {
        background: linear-gradient(135deg, #00C6FF 0%, #0072FF 100%);
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        transition: 0.3s;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 114, 255, 0.4);
    }
    h1, h2, h3 {
        font-family: 'Inter', sans-serif;
        font-weight: 700;
    }
    </style>
""", unsafe_allow_html=True)

# --- Data Loading ---
JSON_PATH = "E:\\Python\\TradingViewAntigravity\\tv_active_chart.json"

@st.cache_data(ttl=5)
def load_data():
    if not os.path.exists(JSON_PATH):
        return None
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

# --- Sidebar: Configuration ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/6/6f/Logo_of_Twitter.svg/512px-Logo_of_Twitter.svg.png", width=50) # placeholder logo
    st.title("Settings")
    st.markdown("### 🤖 Universal LLM Setup")
    
    provider = st.selectbox("Provider", ["OpenAI", "Anthropic", "Ollama", "Groq", "NVIDIA"])
    model = st.text_input("Model Name", placeholder="e.g. gpt-4o, claude-3-5-sonnet, llama3")
    api_key = st.text_input("API Key", type="password", help="Leave blank for local Ollama")
    base_url = st.text_input("Base URL (Optional)", placeholder="http://localhost:11434")
    
    st.markdown("---")
    st.markdown("### 🔄 Auto-Refresh")
    auto_refresh = st.checkbox("Enable Live Refresh", value=True)
    
# --- Main Content ---
st.title("📈 Universal Trading Dashboard")

state = load_data()

if not state:
    st.warning("Waiting for data... Please ensure TradingView Daemon is running and you have an active chart open.")
    st.stop()

if "status" in state:
    st.warning(state["status"])
    st.stop()

# Auto Refresh logic
if auto_refresh:
    time.sleep(5)
    st.rerun()

# 1. Header Metrics
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(f"""
    <div class="metric-card">
        <h3>Symbol</h3>
        <h2>{state.get('tv_symbol', 'N/A')} ({state.get('tv_interval', 'N/A')})</h2>
        <p style="color: #00C6FF;">{state.get('tv_exchange', 'N/A')}</p>
    </div>
    """, unsafe_allow_html=True)

rec = state.get("recommendation", "NEUTRAL")
rec_color = "#00E676" if "BUY" in rec else "#FF1744" if "SELL" in rec else "#FFC400"
with col2:
    st.markdown(f"""
    <div class="metric-card">
        <h3>System Recommendation</h3>
        <h2 style="color: {rec_color};">{rec}</h2>
        <p>Last Updated: {state.get('last_updated', 'N/A')}</p>
    </div>
    """, unsafe_allow_html=True)

indicators = state.get("indicators", {})
if indicators:
    price = indicators.get("close", 0)
    prev = indicators.get("prev_close", 0)
    change = ((price - prev) / prev) * 100 if prev else 0
    change_color = "#00E676" if change >= 0 else "#FF1744"
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <h3>Current Price</h3>
            <h2>{price:,.2f}</h2>
            <p style="color: {change_color};">{'▲' if change >= 0 else '▼'} {change:,.2f}%</p>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")

# 2. Tabs for different views
tab1, tab2, tab3 = st.tabs(["📊 Technicals & Sizing", "🏆 Strategy Leaderboard", "🧠 AI Analysis"])

with tab1:
    st.subheader("Technical Bias")
    st.info(state.get("bias_reason", "No bias available."))
    
    if indicators:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("RSI (14)", f"{indicators.get('rsi', 0):.2f}")
        c2.metric("MACD Hist", f"{indicators.get('hist', 0):.4f}")
        c3.metric("EMA (20)", f"{indicators.get('ema20', 0):,.2f}")
        c4.metric("ATR (14)", f"{indicators.get('atr', 0):,.2f}")

        # Position Sizing
        st.markdown("### Position Sizing & Lot Calculator (1% Risk)")
        atr = indicators.get('atr', 0)
        if atr <= 0: atr = price * 0.01
        
        sl = price - 1.5 * atr if "BUY" in rec else price + 1.5 * atr if "SELL" in rec else price - 1.5 * atr
        tp = price + 3.0 * atr if "BUY" in rec else price - 3.0 * atr if "SELL" in rec else price + 3.0 * atr
        
        st.markdown(f"**Entry**: `{price:,.2f}` | **Stop Loss**: `{sl:,.2f}` | **Take Profit**: `{tp:,.2f}`")
        
with tab2:
    st.subheader("Strategy Leaderboard (Last 1 Year)")
    race = state.get("strategy_race", {})
    if "error" in race:
        st.error(race["error"])
    elif "ranking" in race:
        df_rank = pd.DataFrame(race["ranking"])
        # Format the dataframe for display
        df_rank = df_rank[['rank', 'strategy_label', 'total_return_pct', 'win_rate_pct', 'profit_factor', 'max_drawdown_pct', 'total_trades']]
        df_rank.columns = ['Rank', 'Strategy', 'Return %', 'Win Rate %', 'Profit Factor', 'Max DD %', 'Trades']
        st.dataframe(df_rank, use_container_width=True, hide_index=True)
    else:
        st.write("No leaderboard data available.")

with tab3:
    st.subheader("🤖 Universal AI Market Analysis")
    st.write("Get human-like insights by connecting your configured LLM API.")
    
    if st.button("Generate AI Analysis"):
        if not model:
            st.warning("Please configure your Provider and Model Name in the sidebar first.")
        else:
            with st.spinner("Analyzing market structure..."):
                analysis_result = generate_analysis(api_key, provider, model, base_url, state)
                st.markdown(f"""
                <div class="metric-card" style="border-left: 4px solid #00C6FF;">
                    {analysis_result}
                </div>
                """, unsafe_allow_html=True)
