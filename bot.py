import requests
import time
import pandas as pd

# ===== AYARLAR =====
TELEGRAM_TOKEN = "8806457521:AAEhKaB0a5dHTG-yecCwlivpewlPLMlAsTE"
CHAT_ID = "8478214929"
CHECK_EVERY = 60

COINS = [
    "ZKUSDT", "CHZUSDT", "HYPEUSDT", "ETCUSDT", "APTUSDT",
    "IMXUSDT", "ALGOUSDT", "ETHFIUSDT", "QNTUSDT", "XRPUSDT",
    "KASUSDT", "AAVEUSDT", "ENAUSDT", "ETHUSDT", "SUIUSDT"
]

# Aktif pozisyonlar: {symbol: {yon, giris, sl, tp1, tp2, tp1_hit}}
active_positions = {}
last_signal = {}

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        print(f"Telegram: {r.status_code}")
    except Exception as e:
        print(f"Telegram hata: {e}")

def get_price(symbol):
    try:
        url = "https://api.bitget.com/api/v2/spot/market/tickers"
        r = requests.get(url, params={"symbol": symbol}, timeout=10)
        data = r.json()
        if data.get("code") == "00000":
            return float(data["data"][0]["lastPr"])
    except:
        pass
    return None

def get_candles(symbol):
    try:
        url = "https://api.bitget.com/api/v2/spot/market/candles"
        params = {"symbol": symbol, "granularity": "5min", "limit": "100"}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if data.get("code") != "00000":
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

def pct(giris, hedef):
    return round(abs(hedef - giris) / giris * 100, 2)

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
    i = len(df) - 2
    price = close.iloc[i]
    a = atr14.iloc[i]
    long_ok = e9.iloc[i] > e26.iloc[i] and price > e9.iloc[i] and r.iloc[i] > 50 and vol.iloc[i] > vol_ma.iloc[i]
    short_ok = e9.iloc[i] < e26.iloc[i] and price < e9.iloc[i] and r.iloc[i] < 50 and vol.iloc[i] > vol_ma.iloc[i]
    if long_ok:
        return ("LONG", price, round(price - a*1.5, 6), round(price + a*1.5, 6), round(price + a*3.0, 6), round(r.iloc[i], 1))
    if short_ok:
        return ("SHORT", price, round(price + a*1.5, 6), round(price - a*1.5, 6), round(price - a*3.0, 6), round(r.iloc[i], 1))
    return None

def check_positions():
    closed = []
    for symbol, pos in active_positions.items():
        price = get_price(symbol)
        if not price:
            continue
        yon = pos["yon"]
        giris = pos["giris"]
        sl = pos["sl"]
        tp1 = pos["tp1"]
        tp2 = pos["tp2"]

        if yon == "LONG":
            if not pos["tp1_hit"] and price >= tp1:
                pos["tp1_hit"] = True
                send_telegram(
                    f"🎯 <b>TP1 HIT!</b>\n"
                    f"📌 {symbol} · LONG\n"
                    f"💰 Giriş: {giris}\n"
                    f"✅ TP1: {tp1} · <b>%{pct(giris, tp1)} kar</b> 📈"
                )
            elif price >= tp2:
                send_telegram(
                    f"🏆 <b>TP2 HIT!</b>\n"
                    f"📌 {symbol} · LONG\n"
                    f"💰 Giriş: {giris}\n"
                    f"✅ TP2: {tp2} · <b>%{pct(giris, tp2)} kar</b> 🚀"
                )
                closed.append(symbol)
            elif price <= sl:
                send_telegram(
                    f"🛑 <b>STOP HIT</b>\n"
                    f"📌 {symbol} · LONG\n"
                    f"💰 Giriş: {giris}\n"
                    f"❌ SL: {sl} · <b>%{pct(giris, sl)} zarar</b>"
                )
                closed.append(symbol)

        elif yon == "SHORT":
            if not pos["tp1_hit"] and price <= tp1:
                pos["tp1_hit"] = True
                send_telegram(
                    f"🎯 <b>TP1 HIT!</b>\n"
                    f"📌 {symbol} · SHORT\n"
                    f"💰 Giriş: {giris}\n"
                    f"✅ TP1: {tp1} · <b>%{pct(giris, tp1)} kar</b> 📈"
                )
            elif price <= tp2:
                send_telegram(
                    f"🏆 <b>TP2 HIT!</b>\n"
                    f"📌 {symbol} · SHORT\n"
                    f"💰 Giriş: {giris}\n"
                    f"✅ TP2: {tp2} · <b>%{pct(giris, tp2)} kar</b> 🚀"
                )
                closed.append(symbol)
            elif price >= sl:
                send_telegram(
                    f"🛑 <b>STOP HIT</b>\n"
                    f"📌 {symbol} · SHORT\n"
                    f"💰 Giriş: {giris}\n"
                    f"❌ SL: {sl} · <b>%{pct(giris, sl)} zarar</b>"
                )
                closed.append(symbol)

    for s in closed:
        active_positions.pop(s, None)

def main():
    print("Bot başladı...")
    send_telegram("🤖 <b>Scalp Bot Başladı!</b>\nEMA9/26 + RSI7 + Volume sinyalleri geliyor.")

    while True:
        try:
            # Aktif pozisyonları kontrol et
            check_positions()

            # Yeni sinyal ara
            for symbol in COINS:
                if symbol in active_positions:
                    continue  # zaten açık pozisyon var
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
                        f"💰 Giriş: {price}\n"
                        f"🛑 SL: {sl} · %{pct(price, sl)}\n"
                        f"🎯 TP1: {tp1} · %{pct(price, tp1)}\n"
                        f"🎯 TP2: {tp2} · %{pct(price, tp2)}\n"
                        f"📊 RSI: {r}"
                    )
                    send_telegram(msg)
                    active_positions[symbol] = {
                        "yon": yon, "giris": price,
                        "sl": sl, "tp1": tp1, "tp2": tp2, "tp1_hit": False
                    }
                    print(f"Sinyal: {symbol} {yon} @ {price}")
                time.sleep(1)

        except Exception as e:
            print(f"Hata: {e}")

        print("Tur bitti, 60sn bekleniyor...")
        time.sleep(CHECK_EVERY)

if __name__ == "__main__":
    main()
