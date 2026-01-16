import os
import sys
import time
import requests
import threading
import pandas as pd
import pandas_ta as ta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from binance.client import Client
from flask import Flask

# Настройка вывода логов
sys.stdout.reconfigure(line_buffering=True)

# --- ИНИЦИАЛИЗАЦИЯ ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
client = Client("", "") # Вставь ключи или оставь пустыми для публичных данных

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'TRXUSDT', 'LINKUSDT', 'NEARUSDT']
last_signals = {} 
app = Flask(__name__)

@app.route('/')
def health_check():
    return "BOT IS ALIVE", 200

# --- ФУНКЦИЯ ОТРИСОВКИ ---
def send_signal_with_chart(symbol, df, side, entry, tp, sl, level):
    try:
        plt.clf()
        plt.figure(figsize=(10, 6))
        prices = df['c'].tail(30).values
        plt.plot(prices, label='Цена', color='dodgerblue', linewidth=2)
        plt.axhline(y=level, color='orange', linestyle='--', label='Уровень')
        plt.axhline(y=tp, color='limegreen', linestyle='-', linewidth=2, label='TP')
        plt.axhline(y=sl, color='crimson', linestyle='-', linewidth=2, label='SL')
        
        img_path = f'sig_{symbol}.png'
        plt.savefig(img_path)
        plt.close('all')

       direction = "🚀 *LONG (BUY)*" if side == "BUY" else "🔻 *SHORT (SELL)*"
        message = (
            f"{direction}\n"
            f"🪙 Монета: *{symbol}*\n"
            f"📊 Уровень: `{level:.4f}`\n"
            f"🎯 **ВХОД**: `{entry:.4f}`\n\n"
            f"💰 **TP**: `{tp:.4f}`\n"
            f"🛑 **SL**: `{sl:.4f}`\n\n"
            f"🔗 [ОТКРЫТЬ ФЬЮЧЕРСЫ](https://www.binance.com/en/futures/{symbol})"
        )

        url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        with open(img_path, 'rb') as photo:
            payload = {'chat_id': CHAT_ID, 'caption': message, 'parse_mode': 'Markdown'}
            requests.post(url, data=payload, files={'photo': photo}, timeout=15)

        if os.path.exists(img_path):
            os.remove(img_path)
    except Exception as e:
        print(f"❌ Ошибка отправки {symbol}: {e}")

# --- ГЛАВНАЯ ЛОГИКА ---
def breaker_logic():
    print(">>> СКАНЕР ЗАПУЩЕН...")
    try:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text=Бот запущен. Стратегия: ATR + ADX + Trend 1H")
    except: pass
    
    while True:
        for symbol in SYMBOLS:
            try:
                current_time = time.time()
                if current_time - last_signals.get(symbol, 0) < 600:
                    continue 

                # Данные 5м
                klines = client.get_klines(symbol=symbol, interval='5m', limit=100)
                df = pd.DataFrame(klines, columns=['t','o','h','l','c','v','ct','q','n','v_b','q_b','i'])
                df[['h','l','c','v']] = df[['h','l','c','v']].astype(float)

                # Данные 1ч для тренда
                klines_1h = client.get_klines(symbol=symbol, interval='1h', limit=210)
                df_1h = pd.DataFrame(klines_1h, columns=['t','o','h','l','c','v','ct','q','n','v_b','q_b','i'])
                df_1h['c'] = df_1h['c'].astype(float)

                # Индикаторы
                rsi = ta.rsi(df['c'], length=14).iloc[-1]
                adx_df = ta.adx(df['h'], df['l'], df['c'], length=14)
                current_adx = adx_df['ADX_14'].iloc[-1]
                current_atr = ta.atr(df['h'], df['l'], df['c'], length=14).iloc[-1]
                ema_1h = ta.ema(df_1h['c'], length=200).iloc[-1]
                
                current_price = df['c'].iloc[-1]
                prev_price = df['c'].iloc[-2]
                high_level = df['c'].iloc[-25:-2].max()
                low_level = df['c'].iloc[-25:-2].min()
                
                avg_volume = df['v'].iloc[-21:-1].mean()
                vol_ratio = df['v'].iloc[-1] / avg_volume if avg_volume > 0 else 0

                # ЛОГИКА BUY
                if prev_price > high_level and current_price > high_level and vol_ratio > 1.5:
                    if current_price > ema_1h and current_adx > 25 and rsi < 70:
                        sl = current_price - (current_atr * 2.5)
                        tp = current_price + (current_atr * 5)
                        threading.Thread(target=send_signal_with_chart, args=(symbol, df, "BUY", current_price, tp, sl, high_level)).start()
                        last_signals[symbol] = current_time
                        print(f"✅ Сигнал BUY по {symbol}")

                # ЛОГИКА SELL
                elif prev_price < low_level and current_price < low_level and vol_ratio > 1.5:
                    if current_price < ema_1h and current_adx > 25 and rsi > 30:
                        sl = current_price + (current_atr * 2.5)
                        tp = current_price - (current_atr * 5)
                        threading.Thread(target=send_signal_with_chart, args=(symbol, df, "SELL", current_price, tp, sl, low_level)).start()
                        last_signals[symbol] = current_time
                        print(f"✅ Сигнал SELL по {symbol}")

            except Exception as e:
                print(f"❌ Ошибка {symbol}: {e}")
        
        time.sleep(15)

# --- СТАРТ ---
if __name__ == "__main__":
    threading.Thread(target=breaker_logic, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
