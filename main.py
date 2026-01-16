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

                klines = client.get_klines(symbol=symbol, interval='5m', limit=100) # Взяли 100 свечей для EMA
                df = pd.DataFrame(klines, columns=['t','o','h','l','c','v','ct','q','n','v_b','q_b','i'])
                df['c'] = df['c'].astype(float)
                df['v'] = df['v'].astype(float)
                
                # --- ИНДИКАТОРЫ ---
                ema200 = ta.ema(df['c'], length=50) # Для 5м лучше взять 50 или 100, чтобы быстрее реагировал
                rsi = ta.rsi(df['c'], length=14)
                
                current_rsi = rsi.iloc[-1]
                current_ema = ema200.iloc[-1]
                # ------------------

                high_level = df['c'].iloc[-25:-2].max()
                low_level = df['c'].iloc[-25:-2].min()
                current_price = df['c'].iloc[-1]
                prev_price = df['c'].iloc[-2]

                avg_volume = df['v'].iloc[-21:-1].mean()
                current_volume = df['v'].iloc[-1]
                vol_ratio = current_volume / avg_volume if avg_volume > 0 else 0

                limit_buy = high_level * 1.005
                limit_sell = low_level * 0.995

                # 4. УСЛОВИЯ С ЖЕСТКИМ ФИЛЬТРОМ
                # Шортим только если: пробой уровня + объем + цена ниже EMA + RSI еще не в полу
                if prev_price < low_level and current_price < low_level and vol_ratio > 1.5:
                    if current_price >= limit_sell and current_price < current_ema and current_rsi > 35:
                        print(f"🔥 ПОДТВЕРЖДЕННЫЙ SELL: {symbol} (RSI: {current_rsi:.2f})")
                        sl, tp = low_level * 1.002, current_price * 0.988
                        threading.Thread(target=send_signal_with_chart, args=(symbol, df, "SELL", current_price, tp, sl, low_level)).start()
                        last_signals[symbol] = current_time
                    else:
                        print(f"❌ Фильтр отклонил SELL {symbol}: RSI {current_rsi:.1f}, Price vs EMA")

                # Покупаем только если: пробой уровня + объем + цена выше EMA + RSI еще не в потолке
                elif prev_price > high_level and current_price > high_level and vol_ratio > 1.5:
                    if current_price <= limit_buy and current_price > current_ema and current_rsi < 65:
                        print(f"🔥 ПОДТВЕРЖДЕННЫЙ BUY: {symbol} (RSI: {current_rsi:.2f})")
                        sl, tp = high_level * 0.998, current_price * 1.012
                        threading.Thread(target=send_signal_with_chart, args=(symbol, df, "BUY", current_price, tp, sl, high_level)).start()
                        last_signals[symbol] = current_time
                    else:
                        print(f"❌ Фильтр отклонил BUY {symbol}: RSI {current_rsi:.1f}, Price vs EMA")

            except Exception as e:
                print(f"❌ Ошибка по {symbol}: {e}")
        
        time.sleep(10) # Оптимальная пауза между кругами

threading.Thread(target=breaker_logic, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
