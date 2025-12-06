# app.py
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import date, timedelta
import time

st.set_page_config(page_title="NSE Momentum (12-minus-1) — Risk Adj", layout="wide")

st.title("NSE — 12-minus-1 Momentum (Volatility-Smoothed) — Proof of Concept")
st.markdown("""
This dashboard computes *12-minus-1* momentum for a chosen universe (monthly returns),
computes volatility (12-month SD of monthly returns), and ranks by *smooth momentum*
(= 12-minus-1 / volatility).  
Data source: yfinance (NSE tickers use .NS suffix).  
*Notes:* uses adjusted close from Yahoo Finance — reasonable for a proof of concept.
""")

# -------------------------
# Controls
# -------------------------
col1, col2 = st.columns([2,1])

with col1:
    st.header("Universe selection")
    st.markdown("Choose the tickers to screen. The app expects NSE tickers with NO suffix; it adds .NS automatically.")
    sample_pool = st.text_area("Paste tickers (comma-separated) or leave blank to use recommended pool",
                              value="HDFCBANK,RELIANCE,ICICIBANK,BHARTIARTL,ASIANPAINT,BAJFINANCE,MARUTI,LT,SUNPHARMA,DRREDDY,TCS,INFY,AXISBANK,HCLTECH,WIPRO,SBI,TECHM,TITAN,ULTRACEMCO,M_M,HINDUNILVR,ITC,JSWSTEEL,GRASIM,BAJAJFINSV,EICHERMOT,BRITANNIA",
                              height=140)

with col2:
    st.header("Parameters")
    rebal_freq = st.selectbox("Monthly aggregation: Use month-end series or last trading day?",
                              ["month-end (resample 'M')","last trading day (resample 'M' last)"])
    run_button = st.button("Run screening")
    max_tickers = st.number_input("Max tickers to process (avoid timeouts)", min_value=10, max_value=200, value=60, step=5)

# -------------------------
# Helpers
# -------------------------
@st.cache_data(ttl=60*60)  # cache for 1 hour
def fetch_monthly_adjclose(ticker, start_date, end_date):
    # yfinance ticker uses .NS
    yf_t = ticker + ".NS"
    try:
        data = yf.download(yf_t, start=start_date, end=end_date, progress=False, threads=False)
        if data is None or data.shape[0] == 0:
            return None
        # Use Adj Close if available, else Close
        if 'Adj Close' in data.columns:
            s = data['Adj Close'].copy()
        else:
            s = data['Close'].copy()
        s.index = pd.to_datetime(s.index)
        monthly = s.resample('M').last().to_frame(name='adjclose')
        # also fetch basic volume (average daily vol)
        vol = data['Volume'].resample('M').mean().to_frame(name='avgvol')
        monthly = monthly.join(vol, how='left')
        return monthly
    except Exception as e:
        return None

def compute_metrics(monthly_df):
    # monthly_df must have at least 15 months
    df = monthly_df.dropna()
    if df.shape[0] < 15:
        return None
    df['mret'] = df['adjclose'].pct_change()
    # 12-minus-1: return from index -14 to -2 (months)
    r_12_minus_1 = df['adjclose'].iloc[-2] / df['adjclose'].iloc[-14] - 1
    r_12_incl = df['adjclose'].iloc[-1] / df['adjclose'].iloc[-13] - 1
    r_3m = df['adjclose'].iloc[-1] / df['adjclose'].iloc[-4] - 1
    r_1m = df['adjclose'].pct_change().iloc[-1]
    vol = df['mret'].iloc[-12:].std()
    avg_vol = df['avgvol'].iloc[-6:].mean() if 'avgvol' in df.columns else np.nan
    smooth = r_12_minus_1 / vol if (vol is not None and vol != 0 and not np.isnan(vol)) else np.nan
    return {
        "12_minus_1": r_12_minus_1,
        "12_incl": r_12_incl,
        "3m": r_3m,
        "1m": r_1m,
        "volatility": vol,
        "avg_monthly_volume": avg_vol,
        "smooth_momentum": smooth
    }

# -------------------------
# Main run
# -------------------------
if run_button:
    tickers = [t.strip().upper().replace(".NS","").replace(" ", "") for t in sample_pool.split(",") if t.strip()!='']
    if len(tickers) == 0:
        st.error("No tickers provided.")
    else:
        tickers = tickers[:int(max_tickers)]
        st.info(f"Processing {len(tickers)} tickers. This may take a minute or two.")
        progress = st.progress(0)
        results = []
        end = date.today()
        start = date(end.year - 3, end.month, end.day)  # 3-year buffer
        for idx, t in enumerate(tickers):
            progress.progress(int((idx+1)/len(tickers)*100))
            monthly = fetch_monthly_adjclose(t, start, end)
            time.sleep(0.1)  # small throttle
            if monthly is None or monthly.empty:
                continue
            metrics = compute_metrics(monthly)
            if metrics is None:
                continue
            row = {"ticker": t}
            row.update(metrics)
            results.append(row)

        if len(results) == 0:
            st.error("No tickers returned valid monthly data. Try fewer tickers or different pool.")
        else:
            df = pd.DataFrame(results)
            df = df.dropna(subset=['smooth_momentum'])
            df_sorted = df.sort_values(by='smooth_momentum', ascending=False).reset_index(drop=True)
            st.success("Screen complete.")
            st.subheader("Top 10 (Risk-Adjusted Momentum)")
            st.dataframe(df_sorted.head(10).style.format({
                "12_minus_1": "{:.2%}",
                "12_incl": "{:.2%}",
                "3m": "{:.2%}",
                "1m": "{:.2%}",
                "volatility": "{:.2%}",
                "avg_monthly_volume": "{:,.0f}",
                "smooth_momentum": "{:.3f}"
            }), height=360)

            with st.expander("Full ranked table (downloadable)"):
                st.dataframe(df_sorted.style.format({
                    "12_minus_1": "{:.2%}",
                    "12_incl": "{:.2%}",
                    "3m": "{:.2%}",
                    "1m": "{:.2%}",
                    "volatility": "{:.2%}",
                    "avg_monthly_volume": "{:,.0f}",
                    "smooth_momentum": "{:.3f}"
                }), height=400)
                csv = df_sorted.to_csv(index=False)
                st.download_button("Download CSV", csv, file_name="nse_momentum_ranked.csv", mime="text/csv")

            st.markdown("*Interpretation & next steps:*\n- smooth_momentum = 12-minus-1 divided by monthly vol (higher is better).\n- Use liquidity (avg_monthly_volume) to prune illiquid names.\n- Backtest before deploying capital.")
