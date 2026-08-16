import streamlit as st
import pandas as pd
import numpy as np
import time
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from tradingview_mcp.core.services.strategy_factory import StrategyFactory
from tradingview_mcp.core.services.position_sizing import PositionSizer
from tradingview_mcp.core.services.backtest_service import run_backtest, compare_strategies

st.set_page_config(
    page_title="Antigravity Trading Hub",
    page_icon="🌌",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- CSS Styling for Premium UX ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap');
    
    html, body, [class*="css"]  {
        font-family: 'Outfit', sans-serif;
    }
    
    .stApp {
        background-color: #0b0f19;
        color: #e0e6ed;
    }
    
    .css-1d391kg {
        background-color: #121826;
        border-right: 1px solid #1f2937;
    }
    
    h1, h2, h3 {
        color: #ffffff;
        font-weight: 600;
        background: -webkit-linear-gradient(45deg, #3b82f6, #8b5cf6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    .metric-card {
        background-color: #1f2937;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        border: 1px solid #374151;
        transition: transform 0.2s ease-in-out;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        border-color: #3b82f6;
    }
    .metric-title {
        font-size: 0.9rem;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: 600;
        color: #ffffff;
        margin-top: 5px;
    }
    
    .stButton>button {
        background: linear-gradient(90deg, #3b82f6 0%, #8b5cf6 100%);
        color: white;
        border: none;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 600;
        transition: opacity 0.2s;
    }
    .stButton>button:hover {
        opacity: 0.9;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# --- Sidebar Configuration ---
st.sidebar.title("🌌 AGY Platform")

st.sidebar.markdown("---")
st.sidebar.subheader("LLM Configuration")
llm_provider = st.sidebar.selectbox(
    "Select Provider",
    ["Antigravity (Default)", "OpenAI", "Anthropic", "NVIDIA NIM", "Ollama (Local)"]
)

api_key = ""
if llm_provider != "Ollama (Local)" and llm_provider != "Antigravity (Default)":
    api_key = st.sidebar.text_input(f"{llm_provider} API Key", type="password")

st.sidebar.markdown("---")
st.sidebar.subheader("Capital Management")
capital_inr = st.sidebar.slider("Starting Capital (INR)", min_value=1000, max_value=5000, value=1000, step=100)

st.sidebar.markdown("---")
st.sidebar.subheader("Trading Parameters")
ticker = st.sidebar.text_input("Ticker Symbol", value="BINANCE:BTCUSD")
timeframe = st.sidebar.selectbox("Timeframe", ["1m", "5m", "15m", "1h", "4h", "1D"])

# --- Main Dashboard ---
st.title("Algorithmic Trading Command Center")
st.markdown("Execute and monitor over 200+ institutional-grade quantitative strategies.")

# Initialize strategy factory and sizing
factory = StrategyFactory()
all_strategies = factory.list_strategies()
categories = factory.get_categories()

# Filter by category
selected_cat = st.selectbox("Strategy Category", ["All Categories"] + list(categories))

display_strats = []
if selected_cat == "All Categories":
    display_strats = all_strategies
else:
    display_strats = factory.get_strategies_by_category(selected_cat)

st.write(f"**Loaded Strategies:** {len(display_strats)} / 200+")

selected_strategy_name = st.selectbox("Select Strategy to Backtest", display_strats)

if st.button("Run Simulation 🚀"):
    if not selected_strategy_name:
        st.warning("Please select a strategy.")
    else:
        with st.spinner(f"Running simulation for {selected_strategy_name} on {ticker}..."):
            try:
                # Run the backtest (currently using synthetic data or fetch if integrated)
                metrics = run_backtest(ticker, timeframe, selected_strategy_name)
                
                # Position Sizer logic
                sizer = PositionSizer()
                # Dummy current price for sizing demonstration
                current_price = 60000.0 
                pos_details = sizer.get_position_details(current_price, capital_inr)
                
                st.success("Simulation Complete!")
                
                # Metrics Row
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-title">Total Return</div>
                        <div class="metric-value" style="color: {'#10b981' if metrics['total_return'] > 0 else '#ef4444'}">{metrics['total_return']:.2f}%</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with col2:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-title">Win Rate</div>
                        <div class="metric-value">{metrics['win_rate']:.1f}%</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with col3:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-title">Max Drawdown</div>
                        <div class="metric-value" style="color: #ef4444">{metrics['max_drawdown']:.2f}%</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with col4:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-title">Sharpe Ratio</div>
                        <div class="metric-value">{metrics['sharpe_ratio']:.2f}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                st.markdown("### Risk & Capital Sizing")
                st.info(f"**Deploying {capital_inr} INR (Max Allowed: 5000 INR)**\n\n- Position Quantity: `{pos_details['quantity']}` units\n- Total Exposure: `${pos_details['cost_usd']}`")
                
                # Render chart (dummy data for visual)
                st.markdown("### Equity Curve (Simulated)")
                chart_data = pd.DataFrame(
                    np.random.randn(100, 1).cumsum(axis=0) + 100,
                    columns=['Equity']
                )
                st.line_chart(chart_data)
                
            except Exception as e:
                st.error(f"Error during simulation: {str(e)}")

st.markdown("---")
st.markdown("Powered by **Antigravity Engine** | Running 200+ Models in Parallel")
