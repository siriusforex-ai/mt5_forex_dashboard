"""
MT5 Dashboard configuration.

Fill in MT5_LOGIN / MT5_PASSWORD / MT5_SERVER with your account details.
MT5_PATH is optional — only needed if you have multiple MT5 terminals installed
and want to attach to a specific one.
"""

# ---- MT5 account credentials --------------------------------------------------
MT5_LOGIN =  0# e.g. 12345678
MT5_PASSWORD = ""  # your investor or master password
MT5_SERVER = "" # e.g. "ICMarkets-Demo"
MT5_PATH = ""              # optional, e.g. r"C:\Program Files\MetaTrader 5\terminal64.exe"

# ---- Dashboard settings -------------------------------------------------------
HOST = "127.0.0.1"
PORT = 8000

REFRESH_INTERVAL = 1.0     # seconds between websocket pushes
HISTORY_DAYS = 90          # how far back to load closed deals for the equity curve

# ---- Display ------------------------------------------------------------------
EQUITY_CURVE_MAX_POINTS = 600   # cap live points so the chart stays smooth

# ---- Live ticks ---------------------------------------------------------------
WATCHED_SYMBOLS = ["GOLD", "EURUSD", "GBPUSD", "USDJPY"]
