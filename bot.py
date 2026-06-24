import requests
import time
import pandas as pd

TELEGRAM_TOKEN = "8806457521:AAEhKaB0a5dHTG-yecCwlivpewlPLMlAsTE"
CHAT_ID = "8478214929"
CHECK_EVERY = 60

COINS = [
    "ZKUSDT", "CHZUSDT", "HYPEUSDT", "ETCUSDT", "APTUSDT",
    "IMXUSDT", "ALGOUSDT", "ETHFIUSDT", "QNTUSDT", "XRPUSDT",
    "KASUSDT", "AAVEUSDT", "ENAUSDT", "ETHUSDT", "SUIUSDT"
]

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
        for c in ["open", "close", "high", "low", "vol"]:
            df[c] = df[c].astype(float)
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
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

def pct(giris, hedef):
    return round(abs(hedef - giris) / giris * 100, 2)

def sinyal_gucu(skor):
    if skor >= 5:
        return "🔥 ÇOK GÜÇLÜ"
    elif skor == 4:
        return "💪 GÜÇLÜ"
    elif skor == 3:
        return "👍 ORTA"
    else:
        return "⚠️ ZAYIF"

def check_signal(symbol, df):
    if df is None or len(df) < 30:
        return None
    close, vol = df["close"], df["vol"]
    open_ = df["open"]
    e9 = ema(close, 9)
    e26 = ema(close, 26)
    r = rsi(close, 7)
    vol_ma = vol.rolling(20).mean()
    atr14 = atr(df, 14)
    i = len(df) - 2
    price = close.iloc[i]
    a = atr14.iloc[i]
    vol_oran = round(vol.iloc[i] / vol_ma.iloc[i], 1)
    ema_mesafe = round(abs(price - e26.iloc[i]) / price * 100, 2)
    atr_pct = round(a / price * 100, 2)

    # Son 3 mumun rengi
    son3 = ["🟢" if close.iloc[i-k] > open_.iloc[i-k] else "🔴" for k in range(3)]
    mumlar = " ".join(son3)

    long_kosullar = [
        e9.iloc[i] > e26.iloc[i],
        price > e9.iloc[i],
        r.iloc[i] > 50,
        vol.iloc[i] > vol_ma.iloc[i],
        vol_oran > 1.5,
        close.iloc[i] > close.iloc[i-1],  # son mum yeşil
    ]
    short_kosullar = [
        e9.iloc[i] < e26.iloc[i],
        price < e9.iloc[i],
        r.iloc[i] < 50,
        vol.iloc[i] > vol_ma.iloc[i],
        vol_oran > 1.5,
        close.iloc[i] < close.iloc[i-1],  # son mum kırmızı
    ]

    extra = {
        "rsi": round(r.iloc[i], 1),
        "vol_oran": vol_oran,
        "ema_mesafe": ema_mesafe,
        "atr_pct": atr_pct,
        "mumlar": mumlar,
    }

    if all(long_kosullar[:4]):
        skor = sum(long_kosullar)
        return ("LONG", price, round(price - a*1.5, 6), round(price + a*1.5, 6), round(price + a*3.0, 6), extra, skor)
    if all(short_kosullar[:4]):
        skor = sum(short_kosullar)
        return ("SHORT", price, round(price + a*1.5, 6), round(price - a*1.5, 6), round(price - a*3.0, 6), extra, skor)
    return None

def check_positions():
    closed = []
    for symbol, pos in active_positions.items():
        price = get_price(symbol)
        if not price:
            continue
        yon, giris, sl, tp1, tp2 = pos["yon"], pos["giris"], pos["sl"], pos["tp1"], pos["tp2"]

        if yon == "LONG":
            if not pos["tp1_hit"] and price >= tp1:
                pos["tp1_hit"] = True
                send_telegram(f"🎯 <b>TP1 HIT!</b>\n📌 {symbol} · LONG\n💰 Giriş: {giris}\n✅ TP1: {tp1} · <b>%{pct(giris,tp1)} kar</b> 📈")
            elif price >= tp2:
                send_telegram(f"🏆 <b>TP2 HIT!</b>\n📌 {symbol} · LONG\n💰 Giriş: {giris}\n✅ TP2: {tp2} · <b>%{pct(giris,tp2)} kar</b> 🚀")
                closed.append(symbol)
            elif price <= sl:
                send_telegram(f"🛑 <b>STOP HIT</b>\n📌 {symbol} · LONG\n💰 Giriş: {giris}\n❌ SL: {sl} · <b>%{pct(giris,sl)} zarar</b>")
                closed.append(symbol)
        elif yon == "SHORT":
            if not pos["tp1_hit"] and price <= tp1:
                pos["tp1_hit"] = True
                send_telegram(f"🎯 <b>TP1 HIT!</b>\n📌 {symbol} · SHORT\n💰 Giriş: {giris}\n✅ TP1: {tp1} · <b>%{pct(giris,tp1)} kar</b> 📈")
            elif price <= tp2:
                send_telegram(f"🏆 <b>TP2 HIT!</b>\n📌 {symbol} · SHORT\n💰 Giriş: {giris}\n✅ TP2: {tp2} · <b>%{pct(giris,tp2)} kar</b> 🚀")
                closed.append(symbol)
            elif price >= sl:
                send_telegram(f"🛑 <b>STOP HIT</b>\n📌 {symbol} · SHORT\n💰 Giriş: {giris}\n❌ SL: {sl} · <b>%{pct(giris,sl)} zarar</b>")
                closed.append(symbol)

    for s in closed:
        active_positions.pop(s, None)

def main():
    print("Bot başladı...")
    send_telegram("🤖 <b>Scalp Bot Başladı!</b>\nEMA9/26 + RSI7 + Volume sinyalleri geliyor.")

    while True:
        try:
            check_positions()
            for symbol in COINS:
                if symbol in active_positions:
                    continue
                df = get_candles(symbol)
                signal = check_signal(symbol, df)
                if signal:
                    yon, price, sl, tp1, tp2, ex, skor = signal
                    if skor < 5:  # sadece çok güçlü sinyaller
                        continue
                    key = f"{symbol}_{yon}"
                    if last_signal.get(key) == round(price, 6):
                        continue
                    last_signal[key] = round(price, 6)
                    emoji = "🟢" if yon == "LONG" else "🔴"
                    tag = symbol.replace("USDT", "")
                    msg = (
                        f"{emoji} <b>{yon} · #{tag}</b>\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"📍 Seviye: <code>{price}</code>\n"
                        f"🛑 SL: <code>{sl}</code>\n"
                        f"🎯 TP1: <code>{tp1}</code>\n"
                        f"🏆 TP2: <code>{tp2}</code>\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"⚠️ <i>Yatırım tavsiyesi değildir. Kendi analizinizi yapın.</i>"
                    )
                    send_telegram(msg)
                    active_positions[symbol] = {
                        "yon": yon, "giris": price,
                        "sl": sl, "tp1": tp1, "tp2": tp2, "tp1_hit": False
                    }
                    print(f"Sinyal: {symbol} {yon} @ {price} | Güç: {skor}")
                time.sleep(1)
        except Exception as e:
            print(f"Hata: {e}")

        print("Tur bitti, 60sn bekleniyor...")
        time.sleep(CHECK_EVERY)

if __name__ == "__main__":
    main()
