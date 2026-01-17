import os
import sys
sys.stdout.reconfigure(line_buffering=True)
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

    # ПРЯМАЯ ПРОВЕРКА СВЯЗИ
    print(f"📡 Пробую отправить тестовое SMS в Telegram (ID: {CHAT_ID})...")
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        test_res = requests.post(url, json={'chat_id': CHAT_ID, 'text': "🚀 Бот на связи и видит рынок!"}, timeout=10)
        if test_res.status_code == 200:
            print("✅ ТЕЛЕГРАМ ОТВЕТИЛ: Сообщение доставлено!")
        else:
            print(f"❌ ТЕЛЕГРАМ ОШИБКА: {test_res.status_code} - {test_res.text}")
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА СВЯЗИ: {e}")
    
    while True:
        print(f"\n--- НОВЫЙ КРУГ ПРОВЕРКИ: {time.strftime('%H:%M:%S')} ---")
        for symbol in SYMBOLS:
            try:
                # 1. Загрузка данных
                klines = client.get_klines(symbol=symbol, interval='5m', limit=150) # Увеличил лимит для EMA
                if len(klines) < 100:
                    print(f"❌ {symbol}: Мало данных ({len(klines)})")
                    continue
                
                df = pd.DataFrame(klines, columns=['t','o','h','l','c','v','ct','q','n','v_b','q_b','i'])
                df[['h','l','c','v']] = df[['h','l','c','v']].astype(float)

                # 2. Индикаторы
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
                tr_roll = tr.rolling(14).mean()
                p_di = 100 * (pd.Series(np.where(up > 0, up, 0)).rolling(14).mean() / tr_roll)
                m_di = 100 * (pd.Series(np.where(down > 0, down, 0)).rolling(14).mean() / tr_roll)
                adx = (100 * (abs(p_di - m_di) / (p_di + m_di).replace(0, 0.1))).rolling(14).mean().iloc[-1]

                # 3. Логика входа
                high_25 = df['c'].iloc[-26:-2].max()
                low_25 = df['c'].iloc[-26:-2].min()
                curr_c = df['c'].iloc[-1]
                vol_ratio = df['v'].iloc[-1] / df['v'].iloc[-21:-1].mean()

                # ОТЛАДКА: Пишем в консоль состояние каждой монеты (потом удалим)
                print(f"🧐 {symbol} | Цена: {curr_c:.4f} | Vol: {vol_ratio:.1f} | RSI: {rsi:.1f} | ADX: {adx:.1f}")

                if curr_c > high_25 and vol_ratio > 2.0 and rsi < 60 and adx > 20 and curr_c > ema * 1.002:
                    print(f"🎯 СИГНАЛ BUY НА {symbol}!")
                    sl, tp = curr_c - (atr * 1.8), curr_c + (atr * 1.2)
                    if time.time() - last_signals.get(symbol, 0) > 1800:
                        threading.Thread(target=send_signal_with_chart, args=(symbol, df, "BUY", curr_c, tp, sl, high_25)).start()
                        last_signals[symbol] = time.time()

                elif curr_c < low_25 and vol_ratio > 2.0 and rsi > 40 and adx > 20 and curr_c < ema * 0.998:
                    print(f"🎯 СИГНАЛ SELL НА {symbol}!")
                    sl, tp = curr_c + (atr * 1.8), curr_c - (atr * 1.2)
                    if time.time() - last_signals.get(symbol, 0) > 1800:
                        threading.Thread(target=send_signal_with_chart, args=(symbol, df, "SELL", curr_c, tp, sl, low_25)).start()
                        last_signals[symbol] = time.time()

            except Exception as e:
                print(f"⚠ Ошибка {symbol}: {str(e)}")
                        
        time.sleep(20)

if __name__ == "__main__":
   
# --- МГНОВЕННЫЙ ОБРАБОТЧИК КНОПКИ ---
# Функция должна стоять вплотную к левому краю
# --- МГНОВЕННЫЙ ОБРАБОТЧИК КНОПКИ ---
# --- ФУНКЦИЯ ОБРАБОТКИ КНОПКИ (Твой "Живой?") ---
# --- АНАЛОГ ТВОЕГО @bot.message_handler (Слушатель кнопки) ---
def fast_status_handler():
    last_id = 0
    # Сброс старых нажатий (чтобы не отвечал на то, что было 10 минут назад)
    try:
        r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", params={'offset': -1}, timeout=5).json()
        if r.get("result"):
            last_id = r["result"][0]["update_id"]
    except: pass

    while True:
        try:
            # Бот постоянно "спрашивает" Telegram: "Нажали кнопку?"
            r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", 
                             params={'offset': last_id + 1, 'timeout': 0}, timeout=5).json()
            if r.get("result"):
                for upd in r["result"]:
                    last_id = upd["update_id"]
                    # Если текст сообщения совпадает с кнопкой:
                    if upd.get("message", {}).get("text") == "📡 СТАТУС ПУШКИ":
                        # МГНОВЕННЫЙ ОТВЕТ (как в твоем примере "Да, тружусь")
                        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                                      json={"chat_id": CHAT_ID, "text": "✅ Да, тружусь, всё хорошо!"})
        except: pass
        time.sleep(0.5) # Пауза полсекунды, чтобы не перегружать процессор

# --- ГЛАВНЫЙ ЗАПУСК (Твой аналог start) ---
if __name__ == "__main__":
    # Выводим кнопку в интерфейс
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
            "chat_id": CHAT_ID,
            "text": "🚀 Бот запущен. Используй кнопку:",
            "reply_markup": {"keyboard": [[{"text": "📡 СТАТУС ПУШКИ"}]], "resize_keyboard": True}
        })
    except: pass

    # Запускаем два независимых процесса:
    # 1. Слушатель кнопки (отвечает мгновенно)
    threading.Thread(target=fast_status_handler, daemon=True).start()
    # 2. Твоя математика (считает монеты)
    threading.Thread(target=breaker_logic, daemon=True).start()
    
    # Flask для Koyeb
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8000)))
