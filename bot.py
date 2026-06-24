import requests
import time
import pandas as pd

# ===== AYARLAR =====
TELEGRAM_TOKEN = "8806457521:AAEhKaB0a5dHTG-yecCwlivpew1PLMlAsTE"
CHAT_ID = "8478214929"
CHECK_EVERY = 60

COINS = [
    "ZKUSDT", "CHZUSDT", "HYPEUSDT", "ETCUSDT", "APTUSDT",
    "IMXUSDT", "ALGOUSDT", "ETHFIUSDT", "QNTUSDT", "XRPUSDT",
    "KASUSDT", "AAVEUSDT", "ENAUSDT", "ETHUSDT", "SUIUSDT"
]

last_signal = {}

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        print(f"Telegram: {r.status_code} - {r.text[:100]}")
    except Exception as e:
        print(f"Telegram hata: {e}")

def get_candles(symbol):
    try:
        url = "https://api.bitget.com/api/v2/spot/market/candles"
        params = {"symbol": symbol, "granularity": "5min", "limit": "100"}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data.get("code") != "00000":
            print(f"API hata {symbol}: {data.get('msg')}")
            return None
        rows = data["data"]
        if not rows:
            return None
        cols = ["ts", "open", "high", "low", "close", "vol", "volCcy", "volCcyQuote"][:len(rows[0])]
        df = pd.DataFrame(rows, columns=cols)
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["vol"] = df["vol"].astype(float)
        df = df.iloc[::-1].reset_index(drop=True)
        return df
    except Exception as e:
        print(f"Candle hata {symbol}: {e}")
        return None

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def rsi(series, period=7):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    return 100 - (100 / (1 + rs))

def atr(df, period=14):
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

def check_signal(symbol, df):
    if df is None or len(df) < 30:
        return None
    close = df["close"]
    vol = df["vol"]
    e9 = ema(close, 9)
    e26 = ema(close, 26)
    r = rsi(close, 7)
    vol_ma = vol.rolling(20).mean()
    atr14 = atr(df, 14)
    i = len(df) - 2  # son kapanmış mum
    price = close.iloc[i]
    a = atr14.iloc[i]
    long_ok = e9.iloc[i] > e26.iloc[i] and price > e9.iloc[i] and r.iloc[i] > 50 and vol.iloc[i] > vol_ma.iloc[i]
    short_ok = e9.iloc[i] < e26.iloc[i] and price < e9.iloc[i] and r.iloc[i] < 50 and vol.iloc[i] > vol_ma.iloc[i]
    if long_ok:
        return ("LONG", price, round(price - a*1.5, 6), round(price + a*1.5, 6), round(price + a*3.0, 6), round(r.iloc[i], 1))
    if short_ok:
        return ("SHORT", price, round(price + a*1.5, 6), round(price - a*1.5, 6), round(price - a*3.0, 6), round(r.iloc[i], 1))
    return None

def main():
    print("Bot başladı...")
    send_telegram("🤖 <b>Scalp Bot Başladı!</b>\nEMA9/26 + RSI7 + Volume sinyalleri geliyor.")
    
    while True:
        try:
            for symbol in COINS:
                df = get_candles(symbol)
                signal = check_signal(symbol, df)
                if signal:
                    yon, price, sl, tp1, tp2, r = signal
                    key = f"{symbol}_{yon}"
                    if last_signal.get(key) == round(price, 6):
                        continue
                    last_signal[key] = round(price, 6)
                    emoji = "🟢" if yon == "LONG" else "🔴"
                    msg = (
                        f"{emoji} <b>{yon} SİNYALİ</b>\n"
                        f"📌 Coin: <b>{symbol}</b>\n"
                        f"💰 Fiyat: {price}\n"
                        f"🛑 SL: {sl}\n"
                        f"🎯 TP1: {tp1}\n"
                        f"🎯 TP2: {tp2}\n"
                        f"📊 RSI: {r}"
                    )
                    send_telegram(msg)
                    print(f"Sinyal gönderildi: {symbol} {yon} @ {price}")
                time.sleep(1)
        except Exception as e:
            print(f"Döngü hata: {e}")
        
        print(f"Tur bitti, {CHECK_EVERY}sn bekleniyor...")
        time.sleep(CHECK_EVERY)

if __name__ == "__main__":
    main()
