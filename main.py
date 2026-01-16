import os
import sys
import time
import requests
import threading
import pandas as pd
import pandas_ta as ta
import matplotlib
matplotlib.use('Agg')  # ФОНОВЫЙ РЕЖИМ РИСОВАНИЯ (обязательно здесь)
import matplotlib.pyplot as plt
from binance.client import Client
from flask import Flask

# Настройка мгновенного вывода логов
sys.stdout.reconfigure(line_buffering=True)

# --- ИНИЦИАЛИЗАЦИЯ ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
client = Client("", "") 

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'TRXUSDT', 'LINKUSDT', 'NEARUSDT']
last_signals = {} 
app = Flask(__name__)

@app.route('/')
def health_check():
    return "LEVEL BREAKER IS ALIVE", 200

# --- ФУНКЦИЯ ОТРИСОВКИ И ОТПРАВКИ (Теперь работает быстро) ---
def send_signal_with_chart(symbol, df, side, entry, tp, sl, level):
    try:
        plt.figure(figsize=(10, 6))
        prices = df['c'].tail(30).values
        plt.plot(prices, label='Цена', color='dodgerblue', linewidth=2)
        
        plt.axhline(y=level, color='orange', linestyle='--', label='Уровень пробоя')
        plt.axhline(y=tp, color='limegreen', linestyle='-', linewidth=2, label='ТЕЙК (Профит)')
        plt.axhline(y=sl, color='crimson', linestyle='-', linewidth=2, label='СТОП (Убыток)')
        
        plt.title(f"СИГНАЛ: {symbol} | {side}")
        plt.legend(loc='upper left')
        plt.grid(alpha=0.3)
        
        img_path = f'signal_{symbol}.png'
        plt.savefig(img_path)
        plt.close('all') # ОЧИСТКА ПАМЯТИ

        direction = "🚀 LONG (ПОКУПКА)" if side == "BUY" else "🔻 SHORT (ПРОДАЖА)"
        message = (
            f"{direction}\n"
            f"Монета: {symbol}\n"
            f"Уровень: {level:.4f}\n"
            f"ВХОД: {entry:.4f}\n\n"
            f"🎯 ТЕЙК: {tp:.4f}\n"
            f"🛑 СТОП: {sl:.4f}\n\n"
            f"🔗 Фьючерсы: https://www.binance.com/en/futures/{symbol}"
        )

        url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto?chat_id={CHAT_ID}&caption={message}"
        with open(img_path, 'rb') as photo:
            r = requests.post(url, files={'photo': photo})
            print(f">>> Отправка {symbol} в ТГ: {r.status_code}")
        
        if os.path.exists(img_path):
            os.remove(img_path) # УДАЛЕНИЕ ФАЙЛА
            
    except Exception as e:
        print(f"❌ Ошибка в отправке графика {symbol}: {e}")

# --- ГЛАВНАЯ ЛОГИКА ---
def breaker_logic():
    print(">>> ЗАПУСКАЮ ЦИКЛ СКАНЕРА...")
    try:
        requests.get(f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text=Работаем 👨🏻‍🔧")
    except:
        pass
    
    while True:
        for symbol in SYMBOLS:
            try:
                current_time = time.time()
                if current_time - last_signals.get(symbol, 0) < 600:
                    continue 

                print(f">>> Проверяю {symbol}...") 

                klines = client.get_klines(symbol=symbol, interval='5m', limit=50)
                df = pd.DataFrame(klines, columns=['t','o','h','l','c','v','ct','q','n','v_b','q_b','i'])
                df['c'] = df['c'].astype(float)
                
                high_level = df['c'].iloc[-25:-2].max()
                low_level = df['c'].iloc[-25:-2].min()
                current_price = df['c'].iloc[-1]
                prev_price = df['c'].iloc[-2]

                if prev_price > high_level and current_price > high_level:
                    print(f"!!! СИГНАЛ BUY: {symbol} !!!")
                    sl, tp = high_level * 0.998, current_price * 1.012
                    # ЗАПУСК ОТПРАВКИ В ФОНЕ (Thread)
                    threading.Thread(target=send_signal_with_chart, args=(symbol, df, "BUY", current_price, tp, sl, high_level)).start()
                    last_signals[symbol] = current_time

                elif prev_price < low_level and current_price < low_level:
                    print(f"!!! СИГНАЛ SELL: {symbol} !!!")
                    sl, tp = low_level * 1.002, current_price * 0.988
                    # ЗАПУСК ОТПРАВКИ В ФОНЕ (Thread)
                    threading.Thread(target=send_signal_with_chart, args=(symbol, df, "SELL", current_price, tp, sl, low_level)).start()
                    last_signals[symbol] = current_time

            except Exception as e:
                print(f"❌ Ошибка по {symbol}: {e}")
        
        time.sleep(10) # Оптимальная пауза между кругами

threading.Thread(target=breaker_logic, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
