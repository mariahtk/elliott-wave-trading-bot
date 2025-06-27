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
    def __init__(self, symbol='AAPL', exchange='SMART', currency='USD', client_id=1, account='DU5237549'):
        self.ib = IB()
        self.symbol = symbol
        self.exchange = exchange
        self.currency = currency
        self.client_id = client_id
        self.account = account
        self.contract = Stock(self.symbol, self.exchange, self.currency)
        self._stop_event = threading.Event()
        self._thread = None
        self.last_signal = False
        self.position_open = False
        self.ib_connected = False

    def connect(self):
        if not self.ib_connected:
            ensure_event_loop()
            self.ib.connect('127.0.0.1', 7497, clientId=self.client_id)
            self.ib.qualifyContracts(self.contract)
            self.ib_connected = True

    def disconnect(self):
        if self.ib_connected:
            self.ib.disconnect()
            self.ib_connected = False

    def get_historical_data(self, duration='1 D', bar_size='5 mins'):
        bars = self.ib.reqHistoricalData(
            self.contract,
            endDateTime='',
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow='MIDPOINT',
            useRTH=True,
            formatDate=1)
        df = util.df(bars)
        return df

    def detect_waves(self, prices):
        peaks, _ = find_peaks(prices, distance=5)
        troughs, _ = find_peaks(-prices, distance=5)
        return peaks, troughs

    def check_buy_signal(self, df):
        prices = df['close'].values
        peaks, troughs = self.detect_waves(prices)

        if len(troughs) == 0 or len(peaks) == 0:
            return False

        last_peak = peaks[-1]
        last_trough = troughs[-1]

        if last_trough > last_peak and prices[-1] > prices[last_trough]:
            return True
        return False

    def place_order(self, action='BUY', quantity=10):
        order = MarketOrder(action, quantity, account=self.account)
        trade = self.ib.placeOrder(self.contract, order)
        return trade

    def check_position(self):
        positions = self.ib.positions()
        for pos in positions:
            if pos.contract.symbol == self.symbol:
                return pos.position > 0
        return False

    def _auto_trade_loop(self, interval_seconds=300):
        ensure_event_loop()
        self.connect()
        print(f"Started auto-trading for {self.symbol}")

        while not self._stop_event.is_set():
            try:
                df = self.get_historical_data()
                buy_signal = self.check_buy_signal(df)
                self.position_open = self.check_position()

                if buy_signal and not self.position_open and not self.last_signal:
                    print("Buy signal detected - placing order")
                    trade = self.place_order('BUY', 10)
                    print(f"Order status: {trade.orderStatus.status}")
                    self.last_signal = True
                    self.position_open = True
                elif not buy_signal:
                    self.last_signal = False

            except Exception as e:
                print(f"Error in auto trade loop: {e}")

            for _ in range(interval_seconds):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

        self.disconnect()
        print("Auto trading stopped.")

    def start_auto_trade(self, interval_seconds=300):
        if self._thread and self._thread.is_alive():
            print("Auto trade already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._auto_trade_loop, args=(interval_seconds,), daemon=True)
        self._thread.start()

    def stop_auto_trade(self):
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join()

# Initialize bot
bot = ElliottWaveBot(account='DU5237549')

st.title("Elliott Wave IBKR Trading Bot")

# Connect to IBKR
if st.button("Connect to IBKR"):
    try:
        bot.connect()
        st.success("Connected to IBKR")
        accounts = bot.ib.accounts()
        st.write("Available accounts:", accounts)
    except Exception as e:
        st.error(f"Failed to connect: {e}")

# Manual order section
st.header("Manual Stock Order")
plain_symbol = st.text_input("Stock Symbol to Buy/Sell", value="AAPL").upper()
plain_action = st.selectbox("Buy or Sell", options=["BUY", "SELL"])
plain_qty = st.number_input("Number of Shares", min_value=1, value=10)

if st.button("Place Plain Stock Order"):
    try:
        bot.symbol = plain_symbol
        bot.contract = Stock(bot.symbol, bot.exchange, bot.currency)
        if not bot.ib_connected:
            bot.connect()
        trade = bot.place_order(plain_action, int(plain_qty))
        st.success(f"Placed {plain_action} order for {plain_qty} shares of {plain_symbol}")
        st.write(f"Order Status: {trade.orderStatus.status}")
    except Exception as e:
        st.error(f"Failed to place order: {e}")

# Auto-trading controls
st.header("Auto Trading")
auto_trade_button = st.button("Start Auto Trading")
stop_trade_button = st.button("Stop Auto Trading")

if auto_trade_button:
    try:
        bot.start_auto_trade()
        st.success("Started auto trading")
    except Exception as e:
        st.error(f"Failed to start auto trading: {e}")

if stop_trade_button:
    try:
        bot.stop_auto_trade()
        st.success("Stopped auto trading")
    except Exception as e:
        st.error(f"Failed to stop auto trading: {e}")
