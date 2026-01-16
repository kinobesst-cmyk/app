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
        # 1. Рисуем график
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

        # 2. Оформляем текст (Markdown: `текст` делает его копируемым)
        direction = "🚀 *LONG (ПОКУПКА)*" if side == "BUY" else "🔻 *SHORT (ПРОДАЖА)*"
        
        # Эмодзи как на твоем примере для удобства
        message = (
            f"{direction}\n"
            f"🪙 Монета: *{symbol}*\n"
            f"📊 Уровень: `{level:.4f}`\n"
            f"🎯 **ВХОД**: `{entry:.4f}`\n\n"
            f"💰 **TP**: `{tp:.4f}`\n"
            f"🛑 **SL**: `{sl:.4f}`\n\n"
            f"🔗 [ОТКРЫТЬ ФЬЮЧЕРСЫ](https://www.binance.com/en/futures/{symbol})"
        )

        # 3. Отправка через правильный метод (чтобы Markdown не ломался)
        url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        
        with open(img_path, 'rb') as photo:
            payload = {
                'chat_id': CHAT_ID,
                'caption': message,
                'parse_mode': 'Markdown' # Используем Markdown для простоты и красоты
            }
            r = requests.post(url, data=payload, files={'photo': photo}, timeout=15)
            print(f">>> Сигнал {symbol} отправлен. Статус: {r.status_code}")

        # 4. Удаляем временный файл
        if os.path.exists(img_path):
            os.remove(img_path)

    except Exception as e:
        print(f"❌ Ошибка в блоке отправки {symbol}: {e}")

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

                # 2. Получение данных (50 свечей по 5 минут)
                klines = client.get_klines(symbol=symbol, interval='5m', limit=50)
                df = pd.DataFrame(klines, columns=['t','o','h','l','c','v','ct','q','n','v_b','q_b','i'])
                df['c'] = df['c'].astype(float)
                df['v'] = df['v'].astype(float) # Работаем с объемом
                
                # 3. Расчет уровней и Индикатора Объема
                high_level = df['c'].iloc[-25:-2].max()
                low_level = df['c'].iloc[-25:-2].min()
                current_price = df['c'].iloc[-1]
                prev_price = df['c'].iloc[-2]

                # Средний объем за предыдущие 20 свечей (исключая текущую)
                avg_volume = df['v'].iloc[-21:-1].mean()
                current_volume = df['v'].iloc[-1]
                # Во сколько раз текущий объем выше среднего
                vol_ratio = current_volume / avg_volume if avg_volume > 0 else 0

                # 4. Условия пробоя с подтверждением объема
                if prev_price > high_level and current_price > high_level and vol_ratio > 1.5:
                    print(f"!!! СИЛЬНЫЙ СИГНАЛ BUY: {symbol} (Vol x{vol_ratio:.2f}) !!!")
                    sl, tp = high_level * 0.998, current_price * 1.012
                    
                    # Запуск отправки в фоновом потоке
                    threading.Thread(target=send_signal_with_chart, args=(symbol, df, "BUY", current_price, tp, sl, high_level)).start()
                    last_signals[symbol] = current_time

                elif prev_price < low_level and current_price < low_level and vol_ratio > 1.5:
                    print(f"!!! СИЛЬНЫЙ СИГНАЛ SELL: {symbol} (Vol x{vol_ratio:.2f}) !!!")
                    sl, tp = low_level * 1.002, current_price * 0.988
                    
                    # Запуск отправки в фоновом потоке
                    threading.Thread(target=send_signal_with_chart, args=(symbol, df, "SELL", current_price, tp, sl, low_level)).start()
                    last_signals[symbol] = current_time

            except Exception as e:
                print(f"❌ Ошибка по {symbol}: {e}")
        
        time.sleep(10) # Оптимальная пауза между кругами

threading.Thread(target=breaker_logic, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
