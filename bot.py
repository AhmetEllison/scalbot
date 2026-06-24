import requests
import time
import pandas as pd
import numpy as np

# ===== AYARLAR =====
TELEGRAM_TOKEN = "8806457521:AAEhKaB0a5dHTG-yecCwlivpew1PLMlAsTE"
CHAT_ID = "8478214929"
INTERVAL = "5m"  # 5 dakikalık mum
CHECK_EVERY = 60  # kaç saniyede bir kontrol (saniye)

COINS = [
    "ZKUSDT", "CHZUSDT", "HYPEUSDT", "ETCUSDT", "APTUSDT",
    "IMXUSDT", "ALGOUSDT", "ETHFIUSDT", "QNTUSDT", "XRPUSDT",
    "KASUSDT", "AAVEUSDT", "ENAUSDT", "ETHUSDT", "SUIUSDT"
]

# Son sinyal takibi (aynı sinyali tekrar atmasın)
last_signal = {}

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"})

def get_candles(symbol, limit=100):
    url = f"https://api.bitget.com/api/v2/spot/market/candles"
    params = {
        "symbol": symbol,
        "granularity": "5min",
        "limit": limit
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data.get("code") != "00000":
            return None
        rows = data["data"]
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "vol", "volCcy", "volCcyQuote", "confirm"])
        df = df[df["confirm"] == "1"]  # sadece kapanmış mumlar
        df["close"] = df["close"].astype(float)
        df["vol"] = df["vol"].astype(float)
        df = df.iloc[::-1].reset_index(drop=True)  # eskiden yeniye sırala
        return df
    except Exception as e:
        print(f"Hata {symbol}: {e}")
        return None

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def rsi(series, period=7):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def atr(df, period=14):
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
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

    ema9 = ema(close, 9)
    ema26 = ema(close, 26)
    rsi7 = rsi(close, 7)
    vol_ma = vol.rolling(20).mean()
    atr14 = atr(df, 14)

    # Son kapanmış mum (son index)
    i = len(df) - 1
    price = close.iloc[i]
    e9 = ema9.iloc[i]
    e26 = ema26.iloc[i]
    r = rsi7.iloc[i]
    v = vol.iloc[i]
    vma = vol_ma.iloc[i]
    a = atr14.iloc[i]

    sl_long = round(price - a * 1.5, 6)
    tp1_long = round(price + a * 1.5, 6)
    tp2_long = round(price + a * 3.0, 6)

    sl_short = round(price + a * 1.5, 6)
    tp1_short = round(price - a * 1.5, 6)
    tp2_short = round(price - a * 3.0, 6)

    if e9 > e26 and price > e9 and price > e26 and r > 50 and v > vma:
        return ("LONG", price, sl_long, tp1_long, tp2_long, r)

    if e9 < e26 and price < e9 and price < e26 and r < 50 and v > vma:
        return ("SHORT", price, sl_short, tp1_short, tp2_short, r)

    return None

def main():
    send_telegram("🤖 <b>Scalp Bot Başladı!</b>\n5 dakikalık EMA9/26 + RSI7 + Volume sinyalleri gelecek.")
    print("Bot çalışıyor...")

    while True:
        for symbol in COINS:
            df = get_candles(symbol)
            signal = check_signal(symbol, df)

            if signal:
                yon, price, sl, tp1, tp2, r = signal
                key = f"{symbol}_{yon}"

                # Aynı sinyali tekrar gönderme
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
                    f"📊 RSI: {round(r, 1)}\n"
                    f"⏱ Zaman dilimi: 5dk"
                )
                send_telegram(msg)
                print(f"Sinyal: {symbol} {yon} @ {price}")

            time.sleep(1)  # coinler arası 1sn bekle

        print(f"Tur tamamlandı, {CHECK_EVERY}sn bekleniyor...")
        time.sleep(CHECK_EVERY)

if __name__ == "__main__":
    main()
