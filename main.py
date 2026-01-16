import os
import sys
import time
import requests
import threading
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from binance.client import Client
from flask import Flask

sys.stdout.reconfigure(line_buffering=True)

# --- КОНФИГ ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
client = Client("", "") 

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'TRXUSDT', 'LINKUSDT', 'NEARUSDT']
last_signals = {} 
app = Flask(__name__)

@app.route('/')
def health_check():
    return "OK", 200

# --- ГРАФИКА ---
def send_signal_with_chart(symbol, df, side, entry, tp, sl, level):
    try:
        plt.clf()
        plt.figure(figsize=(10, 6))
        prices = df['c'].tail(30).values
        plt.plot(prices, color='dodgerblue', linewidth=2)
        plt.axhline(y=level, color='orange', linestyle='--')
        plt.axhline(y=tp, color='limegreen', linewidth=2)
        plt.axhline(y=sl, color='crimson', linewidth=2)
        
        img_path = f'sig_{symbol}.png'
        plt.savefig(img_path)
        plt.close('all')

        direction = "🚀 *LONG (BUY)*" if side == "BUY" else "🔻 *SHORT (SELL)*"
        message = (
            f"{direction}\n🪙 *{symbol}*\n"
            f"🎯 ВХОД: `{entry:.4f}`\n"
            f"💰 TP: `{tp:.4f}`\n🛑 SL: `{sl:.4f}`\n\n"
            f"🔗 [BINANCE](https://www.binance.com/en/futures/{symbol})"
        )

        url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        with open(img_path, 'rb') as photo:
            requests.post(url, data={'chat_id': CHAT_ID, 'caption': message, 'parse_mode': 'Markdown'}, files={'photo': photo}, timeout=15)
        if os.path.exists(img_path): os.remove(img_path)
    except Exception as e: print(f"Ошибка графики: {e}")

# --- ТА САМАЯ МАТЕМАТИКА ИЗ ТЕСТОВ ---
def breaker_logic():
    print(">>> ПУШКА ЗАРЯЖЕНА: СКАНЕР ЗАПУЩЕН")
    while True:
        print(f">>> Запуск цикла проверки: {time.strftime('%H:%M:%S')}") # Добавь этот принт!
        for symbol in SYMBOLS:
            try: # ТЕПЕРЬ С ОТСТУПОМ
                klines = client.get_klines(symbol=symbol, interval='5m', limit=100)
                # ... весь остальной код внутри try тоже должен иметь +1 отступ ...
                # 1. Данные 5м
                klines = client.get_klines(symbol=symbol, interval='5m', limit=100)
                df = pd.DataFrame(klines, columns=['t','o','h','l','c','v','ct','q','n','v_b','q_b','i'])
                df[['h','l','c','v']] = df[['h','l','c','v']].astype(float)

                # 2. Индикаторы (ИДЕНТИЧНО ТЕСТУ)
                ema = df['c'].ewm(span=200, adjust=False).mean().iloc[-1]
                
                # ATR
                hl, hc, lc = df['h']-df['l'], (df['h']-df['c'].shift()).abs(), (df['l']-df['c'].shift()).abs()
                tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
                atr = tr.rolling(14).mean().iloc[-1]
                
                # RSI
                delta = df['c'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = ((-delta).where(delta < 0, 0)).rolling(14).mean().replace(0, 0.0001)
                rsi = 100 - (100 / (1 + gain / loss)).iloc[-1]
                
                # ADX
                up, down = df['h'].diff(), df['l'].diff().shift(-1)
                p_di = 100 * (pd.Series(np.where(up > 0, up, 0)).rolling(14).mean() / tr.rolling(14).mean())
                m_di = 100 * (pd.Series(np.where(down > 0, down, 0)).rolling(14).mean() / tr.rolling(14).mean())
                adx = (100 * (abs(p_di - m_di) / (p_di + m_di).replace(0, 0.1))).rolling(14).mean().iloc[-1]

                # 3. Условия входа (ИДЕНТИЧНО ТЕСТУ)
                high_25 = df['c'].iloc[-26:-2].max()
                low_25 = df['c'].iloc[-26:-2].min()
                curr_c = df['c'].iloc[-1]
                
                # ПРАВИЛЬНЫЙ ОБЪЕМ: Текущий V / Средний V
                vol_ratio = df['v'].iloc[-1] / df['v'].iloc[-21:-1].mean()

                # LONG
                if curr_c > high_25 and vol_ratio > 2.0 and rsi < 60 and adx > 20:
                    if curr_c > ema * 1.002:
                        sl, tp = curr_c - (atr * 1.8), curr_c + (atr * 1.2)
                        if time.time() - last_signals.get(symbol, 0) > 1800:
                            threading.Thread(target=send_signal_with_chart, args=(symbol, df, "BUY", curr_c, tp, sl, high_25)).start()
                            last_signals[symbol] = time.time()

                # SHORT
                elif curr_c < low_25 and vol_ratio > 2.0 and rsi > 40 and adx > 20:
                    if curr_c < ema * 0.998:
                        sl, tp = curr_c + (atr * 1.8), curr_c - (atr * 1.2)
                        if time.time() - last_signals.get(symbol, 0) > 1800:
                            threading.Thread(target=send_signal_with_chart, args=(symbol, df, "SELL", curr_c, tp, sl, low_25)).start()
                            last_signals[symbol] = time.time()

            except Exception as e: print(f"Ошибка {symbol}: {e}")
        time.sleep(20)

if __name__ == "__main__":
    threading.Thread(target=breaker_logic, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))
