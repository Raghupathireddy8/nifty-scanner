import os, time, json, requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ===== ENV =====
FYERS_CLIENT_ID    = os.getenv("FYERS_CLIENT_ID")
FYERS_ACCESS_TOKEN = os.getenv("FYERS_ACCESS_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

CACHE_FILE = "signals.json"
TODAY = datetime.now().strftime("%Y-%m-%d")

# ===== CACHE =====
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)

cache = load_cache()

def is_duplicate(symbol, signal):
    key = f"{symbol}_{signal}"
    return key in cache and cache[key] == TODAY

def mark_sent(symbol, signal):
    cache[f"{symbol}_{signal}"] = TODAY

# ===== TELEGRAM =====
def send(msg):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}
    )

# ===== FYERS =====
from fyers_apiv3 import fyersModel
fyers = fyersModel.FyersModel(client_id=FYERS_CLIENT_ID, token=FYERS_ACCESS_TOKEN, log_path="")

# ===== STOCK LIST =====
NIFTY100 = ["RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK","SBIN","ITC","LT","KOTAKBANK",
"HINDUNILVR","AXISBANK","BAJFINANCE","ASIANPAINT","MARUTI","SUNPHARMA",
"TITAN","ULTRACEMCO","NESTLEIND","WIPRO","TECHM","NTPC","POWERGRID",
"TATASTEEL","JSWSTEEL","HINDALCO","COALINDIA","ONGC","BPCL","IOC",
"ADANIENT","ADANIPORTS","GRASIM","CIPLA","DRREDDY","DIVISLAB",
"HEROMOTOCO","EICHERMOT","BRITANNIA","BAJAJFINSV","SBILIFE","HDFCLIFE",
"ICICIPRULI","SHREECEM","UPL","VEDL","TATAMOTORS","BAJAJ-AUTO",
"INDUSINDBK","M&M","LUPIN","TATAPOWER","DLF","GODREJCP","PIDILITIND",
"DABUR","COLPAL","MARICO","SIEMENS","SRF","HAVELLS","BERGEPAINT",
"AMBUJACEM","ACC","MUTHOOTFIN","ICICIGI","SBICARD","NAUKRI","ZOMATO",
"NYKAA","DMART","TRENT","PAGEIND","BOSCHLTD","HAL","BEL","IRCTC",
"LICI","PFC","RECLTD","CANBK","BANKBARODA","SAIL","JINDALSTEL",
"TATAELXSI","TORNTPHARM","TORNTPOWER","TVSMOTOR","VOLTAS","VBL",
"OBEROIRLTY","GODREJPROP","CHOLAFIN","SHRIRAMFIN","OFSS","ZYDUSLIFE"]

# ===== DATA =====
def get_data(sym):
    end = datetime.today()
    start = end - timedelta(days=120)

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

    return pd.DataFrame(r["candles"], columns=["t","o","h","l","c","v"])

# ===== INDICATORS =====
def zscore(df):
    c = df["c"]
    return (c - c.rolling(20).mean()) / c.rolling(20).std()

def adx(df):
    h,l,c = df["h"], df["l"], df["c"]
    tr = pd.concat([(h-l),(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    up = h.diff()
    dn = -l.diff()
    plus = np.where((up>dn)&(up>0), up, 0)
    minus = np.where((dn>up)&(dn>0), dn, 0)

    atr = tr.rolling(14).mean()
    pdi = 100 * pd.Series(plus).rolling(14).mean() / atr
    mdi = 100 * pd.Series(minus).rolling(14).mean() / atr
    dx = (abs(pdi-mdi)/(pdi+mdi))*100
    adx_val = dx.rolling(14).mean()

    return adx_val.iloc[-1], pdi.iloc[-1], mdi.iloc[-1]

# ===== SIGNAL =====
def generate_signal(z, adx_val, pdi, mdi):

    if z < -2 and adx_val > 20 and pdi > mdi:
        return "STRONG BUY"
    if z < -1:
        return "BUY"
    if z > 2 and adx_val > 20 and mdi > pdi:
        return "STRONG SELL"
    if z > 1:
        return "SELL"
    if adx_val > 25:
        return "TREND BUY" if pdi > mdi else "TREND SELL"
    return "HOLD"

# ===== INTERPRETATION =====
def trend_text(adx_val, pdi, mdi):
    if adx_val < 20:
        return "Sideways (Weak)"
    if pdi > mdi:
        return "Bullish (Strong)" if adx_val > 25 else "Bullish"
    else:
        return "Bearish (Strong)" if adx_val > 25 else "Bearish"

def insight(sig, z, pdi, mdi):
    if sig == "STRONG BUY":
        return "Buyers in control + Oversold (Best Swing Setup)"
    if sig == "BUY":
        return "Mild oversold, watch for bounce"
    if sig == "STRONG SELL":
        return "Sellers strong + Overbought"
    if sig == "SELL":
        return "Overbought, possible pullback"
    if sig == "TREND BUY":
        return "Strong uptrend, but late entry risk"
    if sig == "TREND SELL":
        return "Downtrend, avoid buying"
    return "No clear edge"

# ===== MAIN =====
print("🚀 Running Smart Swing Scanner...")

for sym in NIFTY100:
    try:
        df = get_data(sym)
        if df is None or len(df) < 30:
            continue

        price = df["c"].iloc[-1]
        z = zscore(df).iloc[-1]
        adx_val, pdi, mdi = adx(df)

        sig = generate_signal(z, adx_val, pdi, mdi)

        if sig != "HOLD" and not is_duplicate(sym, sig):

            trend = trend_text(adx_val, pdi, mdi)
            note = insight(sig, z, pdi, mdi)

            msg = f"""
<b>{sig} : {sym}</b>

💰 Price: ₹{price:.2f}
📊 Z-Score: {z:.2f}

📈 Trend: {trend}
ADX: {adx_val:.1f}
DI+: {pdi:.1f} | DI-: {mdi:.1f}

🧠 Insight: {note}

🕐 {datetime.now().strftime('%H:%M')}
"""

            send(msg)
            mark_sent(sym, sig)
            print("Sent:", sym, sig)

        time.sleep(0.25)

    except Exception as e:
        print(sym, e)

save_cache(cache)
print("✅ Done")
