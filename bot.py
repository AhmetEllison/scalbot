import requests
import time
import pandas as pd
from datetime import datetime

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
notified = {}
gunluk = {"sinyal": 0, "tp1": 0, "tp2": 0, "sl": 0}
rapor_tarihi = ""

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

def get_candles(symbol, granularity="5min", limit=100):
    try:
        url = "https://api.bitget.com/api/v2/spot/market/candles"
        params = {"symbol": symbol, "granularity": granularity, "limit": str(limit)}
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

def supertrend(df, period=10, multiplier=3.0):
    a = atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2
    upper = hl2 + multiplier * a
    lower = hl2 - multiplier * a
    close = df["close"]
    st = [True] * len(df)
    for i in range(1, len(df)):
        if close.iloc[i] > upper.iloc[i-1]:
            st[i] = True
        elif close.iloc[i] < lower.iloc[i-1]:
            st[i] = False
        else:
            st[i] = st[i-1]
    return st

def pct(giris, hedef):
    return round(abs(hedef - giris) / giris * 100, 2)

def btc_yon():
    try:
        df = get_candles("BTCUSDT", "5min", 50)
        if df is None:
            return None
        close = df["close"]
        e9 = ema(close, 9)
        e26 = ema(close, 26)
        i = len(df) - 2
        return "LONG" if e9.iloc[i] > e26.iloc[i] else "SHORT"
    except:
        return None

def degisim_filtresi(symbol, yon):
    try:
        url = "https://api.bitget.com/api/v2/spot/market/tickers"
        r = requests.get(url, params={"symbol": symbol}, timeout=10)
        data = r.json()
        if data.get("code") == "00000":
            change = float(data["data"][0]["change24h"]) * 100
            if yon == "LONG" and change > 10:
                return False
            if yon == "SHORT" and change < -10:
                return False
        return True
    except:
        return True

def aktif_saat():
    saat = datetime.utcnow().hour + 3
    if saat >= 24:
        saat -= 24
    return 8 <= saat <= 23

def gunluk_rapor_gonder():
    global rapor_tarihi, gunluk
    bugun = datetime.utcnow().strftime("%Y-%m-%d")
    saat = datetime.utcnow().hour + 3
    if saat >= 24:
        saat -= 24
    if saat == 23 and rapor_tarihi != bugun:
        rapor_tarihi = bugun
        toplam = gunluk["tp1"] + gunluk["tp2"] + gunluk["sl"]
        basari = round((gunluk["tp1"] + gunluk["tp2"]) / toplam * 100) if toplam > 0 else 0
        msg = (
            f"📊 <b>GÜNLÜK RAPOR</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"📅 {bugun}\n"
            f"📡 Toplam Sinyal: {gunluk['sinyal']}\n"
            f"━━━━━━━━━━━━━━\n"
            f"🎯 TP1 Hit: {gunluk['tp1']}\n"
            f"🏆 TP2 Hit: {gunluk['tp2']}\n"
            f"🛑 Stop Hit: {gunluk['sl']}\n"
            f"━━━━━━━━━━━━━━\n"
            f"✅ Başarı Oranı: %{basari}\n"
        )
        send_telegram(msg)
        gunluk = {"sinyal": 0, "tp1": 0, "tp2": 0, "sl": 0}

def check_signal(symbol, df):
    if df is None or len(df) < 30:
        return None
    close = df["close"]
    vol = df["vol"]
    e9 = ema(close, 9)
    e26 = ema(close, 26)
    e200_period = 200 if len(df) >= 200 else len(df) // 2
    e200 = ema(close, e200_period)
    r = rsi(close, 7)
    vol_ma = vol.rolling(20).mean()
    atr14 = atr(df, 14)
    st = supertrend(df, 10, 3.0)
    i = len(df) - 2
    price = close.iloc[i]
    a = atr14.iloc[i]
    vol_oran = round(vol.iloc[i] / (vol_ma.iloc[i] + 1e-10), 1)
    st_bullish = st[i]
    above_ema200 = price > e200.iloc[i]

    long_kosullar = [
        e9.iloc[i] > e26.iloc[i],
        price > e9.iloc[i],
        r.iloc[i] > 50,
        vol.iloc[i] > vol_ma.iloc[i],
        vol_oran > 1.5,
        st_bullish,
        above_ema200,
        close.iloc[i] > close.iloc[i-1],
    ]
    short_kosullar = [
        e9.iloc[i] < e26.iloc[i],
        price < e9.iloc[i],
        r.iloc[i] < 50,
        vol.iloc[i] > vol_ma.iloc[i],
        vol_oran > 1.5,
        not st_bullish,
        not above_ema200,
        close.iloc[i] < close.iloc[i-1],
    ]

    skor_long = sum(long_kosullar)
    skor_short = sum(short_kosullar)

    # Debug: ilk 4 koşul sağlanıyor mu?
    if all(long_kosullar[:4]):
        print(f"{symbol} LONG adayı | skor: {skor_long}/8 | koşullar: {long_kosullar}")
        return ("LONG", price, round(price - a*1.5, 6), round(price + a*1.5, 6), round(price + a*3.0, 6), skor_long)
    if all(short_kosullar[:4]):
        print(f"{symbol} SHORT adayı | skor: {skor_short}/8 | koşullar: {short_kosullar}")
        return ("SHORT", price, round(price + a*1.5, 6), round(price - a*1.5, 6), round(price - a*3.0, 6), skor_short)
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
        tag = symbol.replace("USDT", "")

        if yon == "LONG":
            if not pos.get("tp1_hit") and not notified.get(f"{symbol}_tp1") and price >= tp1:
                pos["tp1_hit"] = True
                notified[f"{symbol}_tp1"] = True
                gunluk["tp1"] += 1
                send_telegram(f"🎯 <b>TP1 HIT!</b>\n📌 #{tag} · LONG\n💰 Giriş: {giris}\n✅ TP1: {tp1} · <b>%{pct(giris,tp1)} kar</b> 📈")
            elif not notified.get(f"{symbol}_tp2") and price >= tp2:
                notified[f"{symbol}_tp2"] = True
                gunluk["tp2"] += 1
                send_telegram(f"🏆 <b>TP2 HIT!</b>\n📌 #{tag} · LONG\n💰 Giriş: {giris}\n✅ TP2: {tp2} · <b>%{pct(giris,tp2)} kar</b> 🚀")
                closed.append(symbol)
            elif not notified.get(f"{symbol}_sl") and price <= sl:
                notified[f"{symbol}_sl"] = True
                gunluk["sl"] += 1
                send_telegram(f"🛑 <b>STOP HIT</b>\n📌 #{tag} · LONG\n💰 Giriş: {giris}\n❌ SL: {sl} · <b>%{pct(giris,sl)} zarar</b>")
                closed.append(symbol)
        elif yon == "SHORT":
            if not pos.get("tp1_hit") and not notified.get(f"{symbol}_tp1") and price <= tp1:
                pos["tp1_hit"] = True
                notified[f"{symbol}_tp1"] = True
                gunluk["tp1"] += 1
                send_telegram(f"🎯 <b>TP1 HIT!</b>\n📌 #{tag} · SHORT\n💰 Giriş: {giris}\n✅ TP1: {tp1} · <b>%{pct(giris,tp1)} kar</b> 📈")
            elif not notified.get(f"{symbol}_tp2") and price <= tp2:
                notified[f"{symbol}_tp2"] = True
                gunluk["tp2"] += 1
                send_telegram(f"🏆 <b>TP2 HIT!</b>\n📌 #{tag} · SHORT\n💰 Giriş: {giris}\n✅ TP2: {tp2} · <b>%{pct(giris,tp2)} kar</b> 🚀")
                closed.append(symbol)
            elif not notified.get(f"{symbol}_sl") and price >= sl:
                notified[f"{symbol}_sl"] = True
                gunluk["sl"] += 1
                send_telegram(f"🛑 <b>STOP HIT</b>\n📌 #{tag} · SHORT\n💰 Giriş: {giris}\n❌ SL: {sl} · <b>%{pct(giris,sl)} zarar</b>")
                closed.append(symbol)

    for s in closed:
        active_positions.pop(s, None)
        for k in [f"{s}_tp1", f"{s}_tp2", f"{s}_sl"]:
            notified.pop(k, None)

def main():
    print("Bot başladı...")
    send_telegram("🤖 <b>Scalp Bot Başladı!</b>\nEMA9/26 + EMA200 + RSI + Volume + SuperTrend + BTC Filtresi aktif.\nGünlük rapor 23:00'de gelecek.")

    while True:
        try:
            gunluk_rapor_gonder()

            if not aktif_saat():
                print("Aktif saat değil, bekleniyor...")
                time.sleep(CHECK_EVERY)
                continue

            check_positions()
            btc = btc_yon()
            print(f"BTC yönü: {btc}")

            for symbol in COINS:
                if symbol in active_positions:
                    continue
                if symbol == "BTCUSDT":
                    continue

                df = get_candles(symbol, "5min", 100)
                signal = check_signal(symbol, df)

                if signal:
                    yon, price, sl, tp1, tp2, skor = signal

                    if skor < 5:
                        print(f"{symbol} skor düşük ({skor}/8), atlandı.")
                        continue
                    if btc and btc != yon:
                        print(f"{symbol} {yon} BTC'ye ({btc}) aykırı, atlandı.")
                        continue
                    if not degisim_filtresi(symbol, yon):
                        print(f"{symbol} 24s filtresi geçemedi, atlandı.")
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
                        f"⚡ Güç: {skor}/8\n"
                        f"━━━━━━━━━━━━━━\n"
                        f"⚠️ <i>Yatırım tavsiyesi değildir. Kendi analizinizi yapın.</i>"
                    )
                    send_telegram(msg)
                    gunluk["sinyal"] += 1
                    active_positions[symbol] = {
                        "yon": yon, "giris": price,
                        "sl": sl, "tp1": tp1, "tp2": tp2, "tp1_hit": False
                    }
                    print(f"✅ Sinyal gönderildi: {symbol} {yon} @ {price} | Güç: {skor}/8")

                time.sleep(1)

        except Exception as e:
            print(f"Hata: {e}")

        print("Tur bitti, 60sn bekleniyor...")
        time.sleep(CHECK_EVERY)

if __name__ == "__main__":
    main()
