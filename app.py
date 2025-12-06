# app.py
import streamlit as st
import pandas as pd
import numpy as np
from nsepython import nse_eq
from datetime import datetime, timedelta
import time

st.set_page_config(page_title="NSE Momentum Screener (12-minus-1)", layout="wide")
st.title("📈 NSE Momentum Screener — 12-minus-1 (Volatility Smoothed)")

st.markdown("""
This app computes **12-minus-1** momentum (i.e. return from t-12 → t-1),
monthly volatility (12-month std of monthly returns), and a **smooth momentum**
score = (12-minus-1) / volatility.  
Data source: `nsepython.nse_eq()` (fetches NSE end-of-day prices).
""")

# -------------------------
# Default ticker pool (editable)
# -------------------------
default_pool = [
    "HDFCBANK","RELIANCE","ICICIBANK","BHARTIARTL","ASIANPAINT","BAJFINANCE",
    "MARUTI","LT","SUNPHARMA","DRREDDY","TCS","INFY","AXISBANK","HCLTECH","WIPRO",
    "SBIN","MM","TITAN","ULTRACEMCO","HINDUNILVR","ITC","JSWSTEEL","GRASIM",
    "BAJAJFINSV","EICHERMOT","BRITANNIA"
]

st.sidebar.header("Settings")
pool_text = st.sidebar.text_area("Ticker pool (comma-separated, no .NS)", value=",".join(default_pool), height=160)
max_tickers = st.sidebar.number_input("Max tickers to process (to avoid timeouts)", min_value=5, max_value=80, value=25, step=5)
lookback_months = st.sidebar.number_input("Momentum lookback (months, standard 12)", min_value=6, max_value=24, value=12, step=1)
exclude_most_recent = st.sidebar.checkbox("Exclude most recent month (12-minus-1)", value=True)
top_n = st.sidebar.number_input("Top N to show", min_value=3, max_value=50, value=10, step=1)

# -------------------------
# Helpers
# -------------------------
def safe_fetch_monthly(symbol):
    """
    Uses nse_eq(symbol) to fetch recent EOD records, builds month-end prices.
    Returns a pandas Series indexed by month-end (DatetimeIndex) of closing prices.
    """
    try:
        # nse_eq returns a dict-like structure; the CH_TIMESTAMP / CH_CLOSING_PRICE approach works for many responses
        raw = nse_eq(symbol)
        if not raw or 'history' not in raw and 'CH_TIMESTAMP' not in raw:
            # try alternative returned structure
            # Some responses have a 'data' key or require different handling — try to parse basic fields
            # If not parsable, return None
            return None

        # Attempt to extract rows with timestamps and closing prices
        # Preferred: if it returns a dataframe-like structure accessible via keys
        # But nse_eq often returns a dict with CH_TIMESTAMP and CH_CLOSING_PRICE arrays
        if isinstance(raw, dict) and 'CH_TIMESTAMP' in raw and 'CH_CLOSING_PRICE' in raw:
            timestamps = raw['CH_TIMESTAMP']
            closes = raw['CH_CLOSING_PRICE']
            df = pd.DataFrame({'date': pd.to_datetime(timestamps), 'close': pd.to_numeric(closes, errors='coerce')})
        else:
            # Fallback: if raw is a list of dict rows (older versions)
            rows = []
            if isinstance(raw, list):
                for r in raw:
                    if 'CH_TIMESTAMP' in r and 'CH_CLOSING_PRICE' in r:
                        rows.append({'date': pd.to_datetime(r['CH_TIMESTAMP']), 'close': pd.to_numeric(r['CH_CLOSING_PRICE'], errors='coerce')})
            if len(rows) == 0:
                return None
            df = pd.DataFrame(rows)

        df = df.dropna(subset=['close'])
        if df.empty:
            return None

        df = df.set_index('date').sort_index()
        # Convert to daily freq to make resampling safe, forward-fill any missing days
        df = df.asfreq('D').ffill()
        monthly = df['close'].resample('M').last()
        monthly.index = pd.to_datetime(monthly.index)  # ensure datetime index
        return monthly
    except Exception as e:
        # Return None on any failure
        return None


def compute_12_minus_1(series, lookback_months=12, exclude_most_recent=True):
    """
    series: pandas Series of month-end prices (index sorted ascending)
    returns: dict with 12_minus_1, 12_incl, vol (12-month std), smooth_mom
    """
    if series is None or len(series) < (lookback_months + 2):
        return None

    # Optionally exclude most recent month from series for the 12-minus-1 calculation
    if exclude_most_recent:
        s = series.iloc[:-1]  # drop last month
    else:
        s = series

    if len(s) < lookback_months + 1:
        return None

    # Price at t-12 and t-1 (relative to the end of s)
    price_t_minus_12 = s.iloc[-(lookback_months+0)]
    price_t_minus_1 = s.iloc[-1]

    ret_12_minus_1 = (price_t_minus_1 / price_t_minus_12) - 1

    # 12-month including last month: for info
    price_t_incl = series.iloc[-1]
    price_t_minus_12_incl = series.iloc[-(lookback_months+1)]
    ret_12_incl = (price_t_incl / price_t_minus_12_incl) - 1

    # Volatility: standard deviation of last 12 monthly returns (use s to be consistent)
    mrets = s.pct_change().dropna()
    if len(mrets) >= 12:
        vol = mrets.iloc[-12:].std()
    else:
        vol = mrets.std()

    smooth = ret_12_minus_1 / vol if vol not in [0, None, np.nan] else np.nan

    return {
        "12_minus_1": ret_12_minus_1,
        "12_incl": ret_12_incl,
        "volatility": vol,
        "smooth_momentum": smooth
    }

# -------------------------
# Main flow
# -------------------------
if st.button("Run Screening"):
    # parse tickers from user input
    raw = pool_text.strip()
    tokens = [t.strip().upper().replace(".NS","") for t in raw.replace("\n",",").split(",") if t.strip()!='']
    tokens = [t for t in tokens if t != ""]
    # limit
    tokens = tokens[:int(max_tickers)]

    st.write(f"Processing {len(tokens)} tickers...")
    placeholder = st.empty()
    results = []
    errors = []

    for i, sym in enumerate(tokens):
        placeholder.info(f"({i+1}/{len(tokens)}) Fetching {sym} ...")
        # Fetch monthly series
        monthly_series = safe_fetch_monthly(sym)
        time.sleep(0.12)  # throttle slightly

        if monthly_series is None or monthly_series.isna().all() or len(monthly_series.dropna()) < (lookback_months + 2):
            errors.append(sym)
            continue

        metrics = compute_12_minus_1(monthly_series, lookback_months=lookback_months, exclude_most_recent=exclude_most_recent)
        if metrics is None:
            errors.append(sym)
            continue

        results.append({
            "symbol": sym,
            "12_minus_1": metrics["12_minus_1"],
            "12_incl": metrics["12_incl"],
            "volatility": metrics["volatility"],
            "smooth_momentum": metrics["smooth_momentum"]
        })

    placeholder.empty()

    if len(results) == 0:
        st.error("No valid price data returned for any ticker. Try a smaller pool (e.g., 8-12 tickers) or check network/logs.")
        if errors:
            st.write("Failed tickers (sample):", errors[:20])
    else:
        df = pd.DataFrame(results)
        df = df.dropna(subset=['smooth_momentum'])
        df = df.sort_values(by='smooth_momentum', ascending=False).reset_index(drop=True)

        # formatting for display
        st.success(f"Screen complete — {len(df)} tickers with valid data.")
        st.subheader("Top picks (risk-adjusted momentum)")
        display_df = df.head(int(top_n)).copy()
        display_df['12_minus_1'] = display_df['12_minus_1'].map(lambda x: f"{x:.2%}")
        display_df['12_incl'] = display_df['12_incl'].map(lambda x: f"{x:.2%}")
        display_df['volatility'] = display_df['volatility'].map(lambda x: f"{x:.2%}" if pd.notna(x) else "NA")
        display_df['smooth_momentum'] = display_df['smooth_momentum'].map(lambda x: f"{x:.3f}" if pd.notna(x) else "NA")

        st.table(display_df)

        with st.expander("Full ranked table (download CSV)"):
            st.dataframe(df.style.format({
                '12_minus_1': '{:.2%}',
                '12_incl': '{:.2%}',
                'volatility': '{:.2%}',
                'smooth_momentum': '{:.3f}'
            }), height=400)
            st.download_button("Download CSV", df.to_csv(index=False), "nse_momentum_ranked.csv", "text/csv")




