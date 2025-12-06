import streamlit as st
import pandas as pd
import numpy as np
from nsepython import *
from datetime import datetime, timedelta

st.set_page_config(page_title="NSE Momentum Screener", layout="wide")

st.title("📈 NSE Quantitative Momentum Dashboard (12-1 + Volatility)")

# --------------------------------------------------------------
# Step 1: Load NSE Stock List (NIFTY 100)
# --------------------------------------------------------------

st.write("Loading NSE stock list...")
all_stocks = indice_components("NIFTY 100")   # Returns list of symbols
tickers = [s + ".NS" for s in all_stocks]

# --------------------------------------------------------------
# Step 2: User Parameters
# --------------------------------------------------------------
st.sidebar.header("Settings")
lookback_months = st.sidebar.slider("Momentum Lookback (12-1 standard uses 12)", 6, 18, 12)
exclude_last_month = st.sidebar.checkbox("Exclude Most Recent Month (12-1 momentum)", True)
top_n = st.sidebar.slider("Top Stocks to Show", 5, 50, 10)

# --------------------------------------------------------------
# Step 3: Fetch OHLCV from NSE API
# --------------------------------------------------------------

@st.cache_data(show_spinner=True)
def get_price_history(symbol):
    try:
        df = nse_eq(symbol.replace(".NS", ""))
        df['date'] = pd.to_datetime(df['CH_TIMESTAMP'])
        df = df[['date', 'CH_CLOSING_PRICE']].set_index('date')
        df = df.asfreq('D').ffill()   # forward-fill missing days
        monthly = df.resample("M").last()
        return monthly
    except:
        return None

momentum_data = {}

st.write("Fetching price history (may take 15–20 sec)...")

for sym in tickers:
    data = get_price_history(sym)
    if data is None or len(data) < lookback_months + 2:
        continue
    momentum_data[sym] = data

# --------------------------------------------------------------
# Step 4: Compute 12-1 Momentum
# --------------------------------------------------------------

results = []

for sym, df in momentum_data.items():
    if exclude_last_month:
        base = df.iloc[:-1]   #


