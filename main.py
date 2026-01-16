import os
import sys
sys.stdout.reconfigure(line_buffering=True)
import time
import requests
import threading
import pandas as pd
import pandas_ta as ta
import matplotlib.pyplot as plt
from binance.client import Client
from flask import Flask

# --- ИНИЦИАЛИЗАЦИЯ ---
# Берем данные из настроек Koyeb
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
# API ключи оставляем пустыми для чтения публичных данных
client = Client("", "") 

# Список монет, за которыми следим
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'XRPUSDT', 'LINKUSDT']

app = Flask(__name__)

@app.route('/')
def health_check():
    return "LEVEL BREAKER IS ALIVE", 200

# --- ФУНКЦИЯ ОТРИСОВКИ ГРАФИКА И ОТПРАВКИ ---
def send_signal_with_chart(symbol, df, side, entry, tp, sl, level):
    # Рисуем последние 30 свечей (5-минуток)
    plt.figure(figsize=(10, 6))
    prices = df['c'].tail(30).values
    plt.plot(prices, label='Цена', color='dodgerblue', linewidth=2)
    
    # Рисуем линии уровней
    plt.axhline(y=level, color='orange', linestyle='--', label='Уровень пробоя')
    plt.axhline(y=tp, color='limegreen', linestyle='-', linewidth=2, label='ТЕЙК (Профит)')
    plt.axhline(y=sl, color='crimson', linestyle='-', linewidth=2, label='СТОП (Убыток)')
    
    plt.title(f"СИГНАЛ: {symbol} | {side}")
    plt.legend(loc='upper left')
    plt.grid(alpha=0.3)
    
    img_path = f'signal_{symbol}.png'
    plt.savefig(img_path)
    plt.close()

    # Текст сообщения
    direction = "🚀 **ПОКУПКА (LONG)**" if side == "BUY" else "🔻 **ПРОДАЖА (SHORT)**"
    message = (
        f"{direction}\n"
        f"🪙 Монета: #{symbol}\n"
        f"📊 Пробит уровень: {level:.4f}\n"
        f"💵 **ВХОД: {entry:.4f}**\n\n"
        f"🎯 **ТЕЙК: {tp:.4f}**\n"
        f"🛑 **СТОП: {sl:.4f}**\n\n"
        f"🔗 [Торговать на Binance](https://www.binance.com/ru/trade/{symbol.replace('USDT', '_USDT')})")

    # Отправка фото в Telegram
    url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto?chat_id={CHAT_ID}&caption={message}&parse_mode=Markdown"
    with open(img_path, 'rb') as photo:
        requests.post(url, files={'photo': photo})
    
    # Удаляем файл после отправки
    if os.path.exists(img_path):
        os.remove(img_path)

# --- ГЛАВНАЯ ЛОГИКА РАЗРУШИТЕЛЯ ---
def breaker_logic():
    print(">>> ЗАПУСКАЮ ЦИКЛ СКАНЕРА...") # Это мы увидим в логах
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text=ТЕСТ"
        r = requests.get(url, timeout=10)
        # ЭТА СТРОКА СКАЖЕТ ПРАВДУ:
        print(f">>> ОТВЕТ ТГ: {r.json()}")
        
  except Exception as e:
        print(f">>> ОШИБКА ПРИВЕТСТВИЯ: {e}")
    
     while True:
        for symbol in SYMBOLS:
            try:
                # Берем 5-минутные свечи
                klines = client.get_klines(symbol=symbol, interval='5m', limit=50)
                df = pd.DataFrame(klines, columns=['t','o','h','l','c','v','ct','q','n','v_b','q_b','i'])
                df['c'] = df['c'].astype(float)
                
                # Определяем границы за последние 2 часа (24 свечи)
                high_level = df['c'].iloc[-25:-2].max()
                low_level = df['c'].iloc[-25:-2].min()
                
                current_price = df['c'].iloc[-1]  # Текущая свеча (подтверждение)
                prev_price = df['c'].iloc[-2]     # Свеча пробоя
                
                # --- ЛОГИКА LONG (ВВЕРХ) ---
                if prev_price > high_level and current_price > high_level:
                    # Стоп чуть ниже уровня, Тейк с запасом 1.2%
                    sl = high_level * 0.998
                    tp = current_price * 1.012
                    send_signal_with_chart(symbol, df, "BUY", current_price, tp, sl, high_level)
                    time.sleep(600) # Пауза 10 мин, чтобы не спамить одной монетой

                # --- ЛОГИКА SHORT (ВНИЗ) ---
                elif prev_price < low_level and current_price < low_level:
                    # Стоп чуть выше уровня, Тейк 1.2% вниз
                    sl = low_level * 1.002
                    tp = current_price * 0.988
                    send_signal_with_chart(symbol, df, "SELL", current_price, tp, sl, low_level)
                    time.sleep(600)

            except Exception as e:
                print(f"Ошибка по {symbol}: {e}")
        
        time.sleep(60) # Проверка раз в минуту

# Запуск бота в отдельном потоке
threading.Thread(target=breaker_logic, daemon=True).start()

# Запуск Flask сервера для Koyeb
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
