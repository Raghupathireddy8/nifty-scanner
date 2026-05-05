import os, time, math, json, warnings, requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

# ===== LOAD FROM GITHUB SECRETS =====
FYERS_CLIENT_ID    = os.getenv("FYERS_CLIENT_ID")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

if not all([FYERS_CLIENT_ID, FYERS_ACCESS_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    raise Exception("❌ Missing GitHub Secrets")

# ===== SETTINGS =====
LOOKBACK = 100
ZSCORE_WINDOW = 20

NIFTY100 = ["RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK","SBIN","ITC"]

# ===== FYERS =====
from fyers_apiv3 import fyersModel

fyers = fyersModel.FyersModel(
    client_id=FYERS_CLIENT_ID,
    token=FYERS_ACCESS_TOKEN,
    log_path=""
)

# ===== TELEGRAM =====
def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    )

# ===== DATA =====
def get_data(sym):
    end = datetime.today()
    start = end - timedelta(days=LOOKBACK)

    r = fyers.history({
        "symbol": f"NSE:{sym}-EQ",
        "resolution": "D",
        "date_format": "1",
        "range_from": start.strftime("%Y-%m-%d"),
        "range_to": end.strftime("%Y-%m-%d"),
        "cont_flag": "1"
    })

    if r.get("s") != "ok":
        return None

    df = pd.DataFrame(r["candles"], columns=["t","o","h","l","c","v"])
    return df

# ===== SIGNAL =====
def zscore(df):
    c = df["c"]
    return (c - c.rolling(ZSCORE_WINDOW).mean()) / c.rolling(ZSCORE_WINDOW).std()

def signal(z):
    if z < -2: return "STRONG BUY"
    if z < -1: return "BUY"
    if z > 2: return "STRONG SELL"
    if z > 1: return "SELL"
    return "HOLD"

# ===== MAIN =====
print("🚀 Running scan...")

for sym in NIFTY100:
    try:
        df = get_data(sym)
        if df is None or len(df) < 30:
            continue

        z = zscore(df).iloc[-1]
        sig = signal(z)

        if sig != "HOLD":
            msg = f"{sym} → {sig} | Z={round(z,2)}"
            print(msg)
            send(msg)

        time.sleep(0.3)

    except Exception as e:
        print(sym, e)

print("✅ Done")