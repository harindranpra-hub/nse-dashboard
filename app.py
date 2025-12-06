import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import datetime

# ------------------------------
# 1. NSE Ticker Normalization Fix
# ------------------------------

def normalize_ticker(t):
    t = t.strip().upper()

    # Fix known special tickers
    special_map = {
        "M&M": "MM",
        "SBI": "SBIN",
        "SBIN": "SBIN",
        "BRITANNIA": "BRITANNIA",
        "HDFCBANK": "HDFCBANK",
        "BAJFINANCE": "BAJFINANCE",
    }

    if t in special_map:
        t = special_map[t]

    # Remove invalid characters
    t = t.replace("&", "").replace(" ", "").replace(",", "").replace("\n", "")

    # Avoid double .NS
    if t.endswith(".NS"):
        return t
    else:
        return t + ".NS"


# ------------------------------
# 2. Download Prices Safely
# ------------------------------

def safe_price_download(tickers):
    valid = {}
    for t in tickers:
        try:
            df = yf.download(t, period="2y", interval="1mo", progress=False)
            if df is not None and not df.empty:
                valid[t] = df["Adj Close"]
        except:
            pass
    return valid


# ------------------------------
# 3. Momentum (12-1) + Volatility
# ------------------------------

def compute_scores(price_dict):
    results = []

    for ticker, series in price_dict.items():
        if len(series) < 13:
            continue

        # 12-month return minus last month's return
        momentum_12 = series.pct_change(12).iloc[-1]
        last_month = series.pct_change(1).iloc[-1]
        momentum_12_1 = momentum_12 - last_month

        # Volatility (last 6 months)
        vol = series.pct_change().iloc[-6:].std()

        # Risk-adjusted score
        score = momentum_12_1 / vol if vol != 0 else np.nan

        results.append([ticker, momentum_12, momentum_12_1, vol, score])

    df = pd.DataFrame(results, columns=["Ticker", "12m_Return", "12-1_Momentum", "Vol", "Score"])
    df = df.sort_values("Score", ascending=False).reset_index(drop=True)

    return df


# ------------------------------
# 4. STREAMLIT UI
# ------------------------------

st.title("📈 NSE Momentum Screener (12-1 + Volatility Adjusted)")
st.write("Automatically fixes tickers like M&M → MM, SBI → SBIN, removes .NS duplicates, and ensures stable data.")

tickers_input = st.text_area("Enter NSE tickers (NO .NS needed):",
"""
HDFCBANK, RELIANCE, ICICIBANK, BHARTIARTL, ASIANPAINT, BAJFINANCE, MARUTI,
LT, SUNPHARMA, DRREDDY, TCS, INFY, AXISBANK, HCLTECH, WIPRO, SBIN, MM,
TITAN, ULTRACEMCO, HINDUNILVR, ITC, JSWSTEEL, GRASIM, BAJAJFINSV, EICHERMOT,
BRITANNIA
""".strip())

max_tickers = st.slider("Max tickers to process:", 5, 40, 20)

if st.button("Run Screening"):

    raw_list = tickers_input.replace("\n", " ").split()
    raw_list = [t.replace(",", "") for t in raw_list if t.strip()]

    # Normalize tickers
    clean_tickers = []
    for t in raw_list:
        try:
            nt = normalize_ticker(t)
            clean_tickers.append(nt)
        except:
            pass

    clean_tickers = list(dict.fromkeys(clean_tickers))  # remove duplicates
    clean_tickers = clean_tickers[:max_tickers]

    st.write("### ✔ Normalized tickers:")
    st.write(clean_tickers)

    # Download
    st.write("Downloading price data...")
    price_dict = safe_price_download(clean_tickers)

    if len(price_dict) == 0:
        st.error("No valid price data returned. Try fewer tickers or remove invalid ones.")
    else:
        st.success(f"Valid tickers received data: {list(price_dict.keys())}")

        # Compute scores
        df = compute_scores(price_dict)

        st.write("### 📊 Ranking Table")
        st.dataframe(df)

        st.write("### 🏆 Top 10 Stocks")
        st.table(df.head(10))

