# Импорт библиотек
from flask import Flask, request, jsonify   # Flask - создание API
import sqlite3   # работа с базой данных
import requests   # HTTP запросы (скачивать данные)
import datetime   # работа с датами
import schedule  # планировщик задач
import time   # для задержки
import threading   # чтобы планировщик работал параллельно
import json    # чтение config

# создаём Flask приложение
app = Flask(__name__)

# ЧТЕНИЕ CONFIG
# открываем файл config.json
with open("config.json") as f:
    config = json.load(f)

# берём список валют из конфигурации
CURRENCIES = config["currencies"]


#  СОЗДАНИЕ БАЗЫ 
def init_db():
    # подключаемся к SQLite (файл который создаётся автомат.)
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # создаём таблицу...
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rates (
        date TEXT,        
        currency TEXT,   
        rate REAL         
    )
    """)

    conn.commit()
    conn.close()


# ПОЛУЧЕНИЕ ДАННЫХ С САЙТА 
def fetch_rates(date):
    # формируем URL запроса
    url = f"https://www.cnb.cz/en/financial_markets/foreign_exchange_market/exchange_rate_fixing/daily.txt?date={date}"

    # отправляем запрос
    response = requests.get(url)

    # если ошибка — то возвращаем пусто
    if response.status_code != 200:
        return []

    # разбиваем текст по строкам
    lines = response.text.split("\n")[2:]

    result = []

    # проходим по каждой строке
    for line in lines:
        parts = line.split("|")

        # проверка на корректность строки
        if len(parts) < 5:
            continue

        currency = parts[3]   # валюта
        rate = float(parts[4].replace(",", "."))  # курс

        # сохраняем только необходимие нам валюты
        if currency in CURRENCIES:
            result.append((date, currency, rate))

    return result


# СОХРАНЕНИЕ В БД 
def save_rates(data):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # вставляем данные
    for row in data:
        cursor.execute(
            "INSERT INTO rates VALUES (?, ?, ?)",
            row
        )

    conn.commit()
    conn.close()


#  СИНХРОНИЗАЦИЯ СЕГОДНЯ 
def sync_today():
    # берём текущую дату
    today = datetime.datetime.now().strftime("%d.%m.%Y")

    # получаем данные
    data = fetch_rates(today)

    #  и сохраняем
    save_rates(data)

    print("Synced:", today)


# СИНХРОНИЗАЦИЯ ЗА ПЕРИОД 
@app.route("/sync")
def sync_period():
    # получаем параметры из URL
    start = request.args.get("start")
    end = request.args.get("end")

    # переводим строки в дату
    start_date = datetime.datetime.strptime(start, "%d.%m.%Y")
    end_date = datetime.datetime.strptime(end, "%d.%m.%Y")

    current = start_date

    # идём по датам
    while current <= end_date:
        date_str = current.strftime("%d.%m.%Y")

        # скачиваем и сохраняем
        data = fetch_rates(date_str)
        save_rates(data)

        # следующий день
        current += datetime.timedelta(days=1)

    return "Sync complete"


#  ОТЧЁТ 
@app.route("/report")
def report():
    # параметры
    start = request.args.get("start")
    end = request.args.get("end")
    currencies = request.args.get("currencies").split(",")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    result = {}

    # для каждой валюты считаем статистику
    for cur in currencies:
        cursor.execute("""
        SELECT rate FROM rates
        WHERE currency=? AND date BETWEEN ? AND ?
        """, (cur, start, end))

        rows = cursor.fetchall()

        # достаём только значения
        rates = [r[0] for r in rows]

        # если нет данных то пропускаем
        if not rates:
            continue

        # считаем min, max, avg - средное
        result[cur] = {
            "min": min(rates),
            "max": max(rates),
            "avg": sum(rates) / len(rates) #= (сумма всех курсов) / количество дней
        }

    conn.close()

    return jsonify(result)


#  ПЛАНИРОВЩИК 
def run_scheduler():
    # выполняем задачу каждый день в указанное время
    schedule.every().day.at(config["sync_time"]).do(sync_today)

    while True:
        schedule.run_pending()
        time.sleep(1)


# ЗАПУСК 
if __name__ == "__main__":
    init_db()  # создаём БД

    # запускаем планировщик в отдельном потоке
    threading.Thread(target=run_scheduler, daemon=True).start()

    # запускаем сервер
    app.run(debug=True)