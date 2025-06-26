import yfinance as yf
import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from scipy.signal import argrelextrema

# Alpaca imports
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

st.set_page_config(page_title="Elliott Wave Trading Bot with Alpaca", layout="wide")
st.title("Elliott Wave Trading Bot with Alpaca Paper Trading")

# --- Alpaca API Keys (Input in sidebar, keep secret!) ---
st.sidebar.header("Alpaca API Credentials")
API_KEY = st.sidebar.text_input("API Key", type="password")
API_SECRET = st.sidebar.text_input("API Secret", type="password")
APCA_API_BASE_URL = "https://paper-api.alpaca.markets"

if not API_KEY or not API_SECRET:
    st.warning("Please enter your Alpaca API Key and Secret in the sidebar.")
    st.stop()

# Initialize Alpaca client
client = TradingClient(API_KEY, API_SECRET, paper=True)

# --- Utils for Indicators ---
def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val

def macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

# --- Fibonacci Retracement Utility ---
def fib_ratio(start, end):
    diff = end - start
    levels = {
        "0%": start,
        "23.6%": end - 0.236 * diff,
        "38.2%": end - 0.382 * diff,
        "50%": end - 0.5 * diff,
        "61.8%": end - 0.618 * diff,
        "78.6%": end - 0.786 * diff,
        "100%": end
    }
    return levels

# --- Wave Detection & Validation ---
def find_wave_points(prices, order=5):
    max_idx = argrelextrema(prices.values, np.greater_equal, order=order)[0]
    min_idx = argrelextrema(prices.values, np.less_equal, order=order)[0]
    wave_points = sorted(list(max_idx) + list(min_idx))
    return max_idx, min_idx, wave_points

def validate_impulse_wave(points, prices):
    waves = []
    for i in range(len(points) - 4):
        segment = points[i:i+5]
        vals = prices[segment]

        w1, w2, w3, w4, w5 = vals

        retrace_2 = (w1 - w2) / (w1 - w3) if (w1 - w3) != 0 else 0
        retrace_4 = (w3 - w4) / (w3 - w5) if (w3 - w5) != 0 else 0

        wave_3_length = abs(w3 - w2)
        wave_1_length = abs(w2 - w1)

        wave_5_length = abs(w5 - w4)

        if (
            0 < retrace_2 < 0.618
            and 0 < retrace_4 < 0.618
            and wave_3_length > wave_1_length
            and wave_5_length >= 0.618 * wave_3_length
            and w1 < w3 < w5
        ):
            waves.append(segment)
    return waves

def detect_corrective_wave(points, prices):
    corrections = []
    for i in range(len(points) - 2):
        segment = points[i:i+3]
        vals = prices[segment]

        a, b, c = vals
        retrace_b = abs(b - a) / abs(c - a) if abs(c - a) != 0 else 0

        if 0.382 <= retrace_b <= 0.786 and ((c < a and b > a) or (c > a and b < a)):
            corrections.append(segment)
    return corrections

def compute_position_size(balance, risk_pct, entry_price, stop_loss):
    risk_amount = balance * risk_pct
    stop_loss_diff = abs(entry_price - stop_loss)
    if stop_loss_diff == 0:
        return 0
    size = risk_amount / stop_loss_diff
    return size

# --- UI Inputs ---
st.sidebar.header("Bot Settings")
tickers = st.sidebar.text_input("Tickers (comma separated)", "AAPL,MSFT,TSLA")
risk_pct = st.sidebar.slider("Risk % per trade", 0.5, 5.0, 1.0, step=0.1) / 100
period = st.sidebar.selectbox("Period", ["1mo", "3mo", "6mo", "1y", "2y"], index=2)
interval = st.sidebar.selectbox("Interval", ["1d", "1h", "30m"], index=0)

ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]

# Show account info
account = client.get_account()
st.sidebar.markdown(f"### Alpaca Account Status: {account.status}")
st.sidebar.markdown(f"**Buying Power:** ${float(account.buying_power):,.2f}")
st.sidebar.markdown(f"**Cash:** ${float(account.cash):,.2f}")
st.sidebar.markdown(f"**Portfolio Value:** ${float(account.portfolio_value):,.2f}")

summary_results = []

for ticker in ticker_list:
    st.header(f"Ticker: {ticker}")
    data = yf.download(ticker, period=period, interval=interval, progress=False)
    if data.empty:
        st.error("No data found for ticker.")
        continue

    close = data['Close']
    rsi_vals = rsi(close)
    macd_line, signal_line, macd_hist = macd(close)

    max_idx, min_idx, wave_points = find_wave_points(close, order=5)
    impulse_waves = validate_impulse_wave(wave_points, close.values)
    corrective_waves = detect_corrective_wave(wave_points, close.values)

    fig, ax = plt.subplots(figsize=(14,7))
    ax.plot(close.index, close.values, label='Close Price')
    ax.scatter(close.index[max_idx], close.values[max_idx], marker='^', color='green', label='Peaks')
    ax.scatter(close.index[min_idx], close.values[min_idx], marker='v', color='red', label='Troughs')

    for wave in impulse_waves:
        ax.plot(close.index[wave], close.values[wave], 'o-', color='orange', linewidth=3, label='Impulse Wave')

    for wave in corrective_waves:
        ax.plot(close.index[wave], close.values[wave], 'x--', color='blue', linewidth=2, label='Corrective Wave')

    ax.legend()
    st.pyplot(fig)

    # Fetch current balance & positions
    try:
        account = client.get_account()
        buying_power = float(account.buying_power)
        cash = float(account.cash)
    except Exception as e:
        st.error(f"Error fetching Alpaca account info: {e}")
        continue

    st.write(f"Buying Power: ${buying_power:,.2f}")

    trade_log = []
    position_size = 0
    position_qty = 0

    # Check existing position in this ticker
    try:
        position = client.get_position(ticker)
        position_qty = int(position.qty)
        st.write(f"Existing position: {position_qty} shares")
    except Exception:
        position_qty = 0
        st.write("No existing position.")

    # Trading logic: buy at wave 3, sell at wave 5 or stop loss at wave 2 price
    for wave in impulse_waves:
        buy_idx = wave[2]
        sell_idx = wave[4]
        stop_loss_idx = wave[1]

        buy_price = close.values[buy_idx]
        sell_price = close.values[sell_idx]
        stop_loss_price = close.values[stop_loss_idx]

        # Filters
        if rsi_vals.iloc[buy_idx] > 70:
            trade_log.append(f"Skipped Buy @ {buy_price:.2f} on {close.index[buy_idx].date()} due to RSI {rsi_vals.iloc[buy_idx]:.1f}")
            continue
        if macd_hist.iloc[buy_idx] < 0:
            trade_log.append(f"Skipped Buy @ {buy_price:.2f} on {close.index[buy_idx].date()} due to MACD histogram negative")
            continue

        # Only enter if no position already
        if position_qty == 0:
            # Calculate qty based on buying power and risk_pct
            qty = int(compute_position_size(buying_power, risk_pct, buy_price, stop_loss_price))
            if qty <= 0:
                trade_log.append("Position size zero, skipping trade.")
                continue

            try:
                order_data = MarketOrderRequest(
                    symbol=ticker,
                    qty=qty,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY
                )
                order = client.submit_order(order_data)
                trade_log.append(f"BUY ORDER SUBMITTED: {qty} shares @ {buy_price:.2f} on {close.index[buy_idx].date()}")
                position_qty += qty
            except Exception as e:
                trade_log.append(f"BUY ORDER FAILED: {e}")
                continue

        # Sell logic — we check if stop loss would have triggered (simulate), else sell at wave 5 price
        trade_period = close.iloc[buy_idx:sell_idx+1]
        if trade_period.min() <= stop_loss_price:
            # Stop loss triggered: submit sell order
            try:
                order_data = MarketOrderRequest(
                    symbol=ticker,
                    qty=position_qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY
                )
                order = client.submit_order(order_data)
                trade_log.append(f"STOP LOSS SELL ORDER SUBMITTED: {position_qty} shares @ {stop_loss_price:.2f}")
                position_qty = 0
            except Exception as e:
                trade_log.append(f"STOP LOSS SELL ORDER FAILED: {e}")
        else:
            # Sell at wave 5 price
            try:
                order_data = MarketOrderRequest(
                    symbol=ticker,
                    qty=position_qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY
                )
                order = client.submit_order(order_data)
                trade_log.append(f"SELL ORDER SUBMITTED: {position_qty} shares @ {sell_price:.2f} on {close.index[sell_idx].date()}")
                position_qty = 0
            except Exception as e:
                trade_log.append(f"SELL ORDER FAILED: {e}")

    st.subheader("Trade Log")
    for entry in trade_log:
        st.write(entry)

st.info("Note: This bot trades on historical signals using yfinance data and places real market orders on Alpaca paper trading account based on those signals. Use cautiously and monitor your Alpaca account.")
