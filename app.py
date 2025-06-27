import threading
import time
import asyncio
import nest_asyncio
nest_asyncio.apply()

from ib_insync import *
import pandas as pd
from scipy.signal import find_peaks
import streamlit as st

# Helper to ensure asyncio event loop exists in any thread
def ensure_event_loop():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop

class ElliottWaveBot:
    def __init__(self, symbol='AAPL', exchange='SMART', currency='USD', client_id=1):
        self.ib = IB()
        self.symbol = symbol
        self.exchange = exchange
        self.currency = currency
        self.client_id = client_id
        self.contract = Stock(self.symbol, self.exchange, self.currency)
        self._stop_event = threading.Event()
        self._thread = None
        self.last_signal = False
        self.position_open = False
        self.ib_connected = False

    def connect(self):
        if not self.ib_connected:
            ensure_event_loop()  # Ensure event loop before connecting
            self.ib.connect('127.0.0.1', 7497, clientId=self.client_id)  # 7497 paper trading port
            self.ib.qualifyContracts(self.contract)
            self.ib_connected = True

    def disconnect(self):
        if self.ib_connected:
            self.ib.disconnect()
            self.ib_connected = False

    def place_order(self, action='BUY', quantity=10):
        order = MarketOrder(action, quantity)
        trade = self.ib.placeOrder(self.contract, order)
        return trade

    # Placeholder for your auto trade methods
    def start_auto_trade(self, interval_seconds=300):
        pass

    def stop_auto_trade(self):
        pass

bot = ElliottWaveBot()

st.title("Elliott Wave IBKR Trading Bot")

# Connect button
if st.button("Connect to IBKR"):
    try:
        bot.connect()
        st.success("Connected to IBKR")
        accounts = bot.ib.accounts()
        st.write("Available accounts:", accounts)
    except Exception as e:
        st.error(f"Failed to connect: {e}")

st.header("Manual Order Test")

test_symbol = st.text_input("Ticker Symbol", value="AAPL").upper()
test_action = st.selectbox("Action", options=["BUY", "SELL"])
test_qty = st.number_input("Quantity", min_value=1, value=1)

if st.button("Place Market Order"):
    try:
        bot.symbol = test_symbol
        bot.contract = Stock(bot.symbol, bot.exchange, bot.currency)
        if not bot.ib_connected:
            bot.connect()
        trade = bot.place_order(test_action, int(test_qty))
        st.success(f"Placed {test_action} order for {test_qty} shares of {test_symbol}")
        st.write(f"Order Status: {trade.orderStatus.status}")
    except Exception as e:
        st.error(f"Failed to place order: {e}")
