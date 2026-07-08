import requests
import time
import pandas as pd
from datetime import datetime, timezone

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

# ─── TELEGRAM ───────────────────────────────────────────
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        print(f"Telegram: {r.status_code}")
    except Exception as e:
        print(f"Telegram hata: {e}")

# ─── VERİ ÇEKME ─────────────────────────────────────────
def get_candles(symbol, granularity="5min", limit=100):
    try:
        url = "https://api.bitget.com/api/v2/spot/market/candles"
        r = requests.get(url, params={"symbol": symbol, "granularity": granularity, "limit": str(limit)}, timeout=10)
        data = r.json()
        if data.get("code") != "00000" or not data["data"]:
            return None
        cols = ["ts", "open", "high", "low", "close", "vol", "volCcy", "volCcyQuote"][:len(data["data"][0])]
        df = pd.DataFrame(data["data"], columns=cols)
        for c in ["open", "high", "low", "close", "vol"]:
            df[c] = df[c].astype(float)
        return df.iloc[::-1].reset_index(drop=True)
    except Exception as e:
        print(f"Candle hata {symbol}: {e}")
        return None

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

def get_open_interest(symbol):
    # Futures sembolü (USDT-M)
    try:
        fsym = symbol.replace("USDT", "") + "USDT"
        url = "https://api.bitget.com/api/v2/mix/market/open-interest"
        r = requests.get(url, params={"symbol": fsym + "_UMCBL", "productType": "USDT-FUTURES"}, timeout=10)
        data = r.json()
        if data.get("code") == "00000":
            return float(data["data"]["openInterest"])
    except:
        pass
    return None

def get_long_short_ratio(symbol):
    try:
        fsym = symbol.replace("USDT", "") + "USDT_UMCBL"
        url = "https://api.bitget.com/api/v2/mix/market/account-long-short-ratio"
        r = requests.get(url, params={"symbol": fsym, "productType": "USDT-FUTURES", "period": "5m"}, timeout=10)
        data = r.json()
        if data.get("code") == "00000" and data["data"]:
            d = data["data"][-1]
            return float(d.get("longRatio", 0.5)), float(d.get("shortRatio", 0.5))
    except:
        pass
    return None, None

# ─── İNDİKATÖRLER ───────────────────────────────────────
def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def calc_rsi(series, period=7):
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(span=period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(span=period, adjust=False).mean()
    rs = gain / (loss + 1e-10)
    return 100 - (100 / (1 + rs))

def calc_atr(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

def calc_supertrend(df, period=10, multiplier=3.0):
    atr = calc_atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr
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

def calc_vwap(df):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    vwap = (tp * df["vol"]).cumsum() / df["vol"].cumsum()
    return vwap

def calc_cvd(df):
    # Basit CVD: kapanış > açılış ise hacim pozitif, değilse negatif
    delta = df["vol"] * ((df["close"] - df["open"]).apply(lambda x: 1 if x > 0 else -1))
    return delta.cumsum()

def pct(giris, hedef):
    return round(abs(hedef - giris) / giris * 100, 2)

# ─── FİLTRELER ──────────────────────────────────────────
def btc_yon():
    try:
        df = get_candles("BTCUSDT", "5min", 50)
        if df is None or len(df) < 30:
            return None
        e9 = calc_ema(df["close"], 9)
        e26 = calc_ema(df["close"], 26)
        i = len(df) - 2
        return "LONG" if e9.iloc[i] > e26.iloc[i] else "SHORT"
    except:
        return None

def atr_spike_filtresi(df):
    # ATR aniden %50'den fazla artmışsa haber anı olabilir
    try:
        atr = calc_atr(df, 14)
        i = len(df) - 2
        atr_ort = atr.iloc[max(0, i-10):i].mean()
        return atr.iloc[i] < atr_ort * 1.5  # True = normal, False = spike var
    except:
        return True

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
    saat = datetime.now(timezone.utc).hour + 3
    if saat >= 24:
        saat -= 24
    return 8 <= saat <= 23

# ─── SİNYAL KONTROL ─────────────────────────────────────
def check_signal(symbol, df):
    if df is None or len(df) < 30:
        return None

    close = df["close"]
    vol = df["vol"]
    i = len(df) - 2  # son kapanmış mum

    # İndikatörler
    e9 = calc_ema(close, 9)
    e26 = calc_ema(close, 26)
    e200_period = min(200, len(df) // 2)
    e200 = calc_ema(close, e200_period)
    rsi = calc_rsi(close, 7)
    atr = calc_atr(df, 14)
    st = calc_supertrend(df, 10, 3.0)
    vwap = calc_vwap(df)
    cvd = calc_cvd(df)
    vol_ma = vol.rolling(20).mean()

    price = close.iloc[i]
    a = atr.iloc[i]
    st_bullish = st[i]
    above_e200 = price > e200.iloc[i]
    above_vwap = price > vwap.iloc[i]
    cvd_pozitif = cvd.iloc[i] > cvd.iloc[i-3]  # CVD son 3 mumda artıyor mu

    # Fake breakout filtresi: bir önceki mum kapanışı da aynı yönde mi
    long_breakout_ok = close.iloc[i] > e9.iloc[i] and close.iloc[i-1] > e9.iloc[i-1]
    short_breakout_ok = close.iloc[i] < e9.iloc[i] and close.iloc[i-1] < e9.iloc[i-1]

    long_kosullar = [
        e9.iloc[i] > e26.iloc[i],       # 1. EMA9 > EMA26
        above_e200,                       # 2. EMA200 üstünde
        rsi.iloc[i] > 50,                # 3. RSI > 50
        vol.iloc[i] > vol_ma.iloc[i],    # 4. Hacim ortalamanın üstünde
        st_bullish,                       # 5. SuperTrend bullish
        above_vwap,                       # 6. VWAP üstünde
        cvd_pozitif,                      # 7. CVD artıyor
        long_breakout_ok,                 # 8. Fake breakout yok
        price > e9.iloc[i],              # 9. Fiyat EMA9 üstünde
        close.iloc[i] > close.iloc[i-1], # 10. Son mum yeşil
    ]

    short_kosullar = [
        e9.iloc[i] < e26.iloc[i],        # 1. EMA9 < EMA26
        not above_e200,                   # 2. EMA200 altında
        rsi.iloc[i] < 50,                # 3. RSI < 50
        vol.iloc[i] > vol_ma.iloc[i],    # 4. Hacim ortalamanın üstünde
        not st_bullish,                   # 5. SuperTrend bearish
        not above_vwap,                   # 6. VWAP altında
        not cvd_pozitif,                  # 7. CVD düşüyor
        short_breakout_ok,                # 8. Fake breakout yok
        price < e9.iloc[i],              # 9. Fiyat EMA9 altında
        close.iloc[i] < close.iloc[i-1], # 10. Son mum kırmızı
    ]

    skor_long = sum(long_kosullar)
    skor_short = sum(short_kosullar)

    if all(long_kosullar[:4]) and skor_long >= 7:
        return ("LONG", price, round(price - a*1.5, 6), round(price + a*1.5, 6), round(price + a*3.0, 6), skor_long)
    if all(short_kosullar[:4]) and skor_short >= 7:
        return ("SHORT", price, round(price + a*1.5, 6), round(price - a*1.5, 6), round(price - a*3.0, 6), skor_short)
    return None

# ─── POZİSYON TAKİP ─────────────────────────────────────
def check_positions():
    closed = []
    for symbol, pos in active_positions.items():
        price = get_price(symbol)
        if not price:
            continue
        yon, giris, sl, tp1, tp2 = pos["yon"], pos["giris"], pos["sl"], pos["tp1"], pos["tp2"]
        tag = symbol.replace("USDT", "")

        if yon == "LONG":
            if not notified.get(f"{symbol}_tp1") and price >= tp1:
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
            if not notified.get(f"{symbol}_tp1") and price <= tp1:
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

# ─── GÜNLÜK RAPOR ───────────────────────────────────────
def gunluk_rapor_gonder():
    global rapor_tarihi, gunluk
    bugun = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    saat = datetime.now(timezone.utc).hour + 3
    if saat >= 24:
        saat -= 24
    if saat == 23 and rapor_tarihi != bugun:
        rapor_tarihi = bugun
        toplam = gunluk["tp1"] + gunluk["tp2"] + gunluk["sl"]
        basari = round((gunluk["tp1"] + gunluk["tp2"]) / toplam * 100) if toplam > 0 else 0
        send_telegram(
            f"📊 <b>GÜNLÜK RAPOR</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"📅 {bugun}\n"
            f"📡 Toplam Sinyal: {gunluk['sinyal']}\n"
            f"━━━━━━━━━━━━━━\n"
            f"🎯 TP1 Hit: {gunluk['tp1']}\n"
            f"🏆 TP2 Hit: {gunluk['tp2']}\n"
            f"🛑 Stop Hit: {gunluk['sl']}\n"
            f"━━━━━━━━━━━━━━\n"
            f"✅ Başarı Oranı: %{basari}"
        )
        gunluk = {"sinyal": 0, "tp1": 0, "tp2": 0, "sl": 0}

# ─── ANA DÖNGÜ ──────────────────────────────────────────
def main():
    print("Bot başladı...")
    send_telegram(
        "🤖 <b>Scalp Bot Başladı!</b>\n"
        "━━━━━━━━━━━━━━\n"
        "EMA 9/26 · EMA 200 · RSI 7\n"
        "SuperTrend · VWAP · CVD\n"
        "Fake Breakout · ATR Spike\n"
        "BTC Filtresi · 24s Değişim\n"
        "━━━━━━━━━━━━━━\n"
        "Min. güç: 7/10 | SL: ATR×1.5 | TP2: ATR×3"
    )

    oi_onceki = {}

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

                df = get_candles(symbol, "5min", 100)
                signal = check_signal(symbol, df)

                if not signal:
                    time.sleep(1)
                    continue

                yon, price, sl, tp1, tp2, skor = signal

                # BTC filtresi
                if btc and btc != yon:
                    print(f"{symbol} {yon} BTC'ye aykırı, atlandı.")
                    time.sleep(1)
                    continue

                # ATR spike filtresi (haber anı)
                if not atr_spike_filtresi(df):
                    print(f"{symbol} ATR spike var (haber anı?), atlandı.")
                    time.sleep(1)
                    continue

                # 24s değişim filtresi
                if not degisim_filtresi(symbol, yon):
                    print(f"{symbol} 24s değişim filtresi, atlandı.")
                    time.sleep(1)
                    continue

                # Open Interest filtresi
                oi = get_open_interest(symbol)
                if oi and symbol in oi_onceki:
                    oi_degisim = (oi - oi_onceki[symbol]) / (oi_onceki[symbol] + 1e-10)
                    if yon == "LONG" and oi_degisim < -0.05:
                        print(f"{symbol} OI düşüyor, LONG atlandı.")
                        time.sleep(1)
                        continue
                    if yon == "SHORT" and oi_degisim < -0.05:
                        print(f"{symbol} OI düşüyor, SHORT atlandı.")
                        time.sleep(1)
                        continue
                if oi:
                    oi_onceki[symbol] = oi

                # Long/Short oranı filtresi
                long_r, short_r = get_long_short_ratio(symbol)
                if long_r and short_r:
                    if yon == "LONG" and long_r > 0.75:
                        print(f"{symbol} Long oranı çok yüksek (%{round(long_r*100)}), LONG atlandı.")
                        time.sleep(1)
                        continue
                    if yon == "SHORT" and short_r > 0.75:
                        print(f"{symbol} Short oranı çok yüksek (%{round(short_r*100)}), SHORT atlandı.")
                        time.sleep(1)
                        continue

                # Tekrar sinyal önleme
                key = f"{symbol}_{yon}"
                if last_signal.get(key) == round(price, 6):
                    time.sleep(1)
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
                    f"⚡ Güç: {skor}/10\n"
                    f"━━━━━━━━━━━━━━\n"
                    f"⚠️ <i>Yatırım tavsiyesi değildir.</i>"
                )
                send_telegram(msg)
                gunluk["sinyal"] += 1
                active_positions[symbol] = {
                    "yon": yon, "giris": price,
                    "sl": sl, "tp1": tp1, "tp2": tp2
                }
                print(f"✅ Sinyal: {symbol} {yon} @ {price} | Güç: {skor}/10")
                time.sleep(1)

        except Exception as e:
            print(f"Hata: {e}")

        print("Tur bitti, 60sn bekleniyor...")
        time.sleep(CHECK_EVERY)

if __name__ == "__main__":
    main()
