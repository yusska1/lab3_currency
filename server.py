from flask import Flask, request, jsonify   
import sqlite3   
import requests   
import datetime  
import schedule  
import time   
import threading   
import json    

app = Flask(__name__)

with open("config.json") as f:
    config = json.load(f)

CURRENCIES = config["currencies"]


#созданеи бд 
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS rates (
        date TEXT,        
        currency TEXT,   
        rate REAL         
    )
    """)

    conn.commit()
    conn.close()


#получение данных с сайта 
def fetch_rates(date):
    url = f"https://www.cnb.cz/en/financial_markets/foreign_exchange_market/exchange_rate_fixing/daily.txt?date={date}"

    response = requests.get(url)

    if response.status_code != 200:
        return []

    lines = response.text.split("\n")[2:]

    result = []

    for line in lines:
        parts = line.split("|")

        if len(parts) < 5:
            continue

        currency = parts[3]   
        rate = float(parts[4].replace(",", "."))  

        if currency in CURRENCIES:
            result.append((date, currency, rate))

    return result


def save_rates(data):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    for row in data:
        cursor.execute(
            "INSERT INTO rates VALUES (?, ?, ?)",
            row
        )

    conn.commit()
    conn.close()


def sync_today():
    today = datetime.datetime.now().strftime("%d.%m.%Y")

    data = fetch_rates(today)

    save_rates(data)

    print("Synced:", today)


@app.route("/sync")
def sync_period():
    start = request.args.get("start")
    end = request.args.get("end")

    start_date = datetime.datetime.strptime(start, "%d.%m.%Y")
    end_date = datetime.datetime.strptime(end, "%d.%m.%Y")

    current = start_date

    while current <= end_date:
        date_str = current.strftime("%d.%m.%Y")

        data = fetch_rates(date_str)
        save_rates(data)

        current += datetime.timedelta(days=1)

    return "Sync complete"


#отчет 
@app.route("/report")
def report():
    start = request.args.get("start")
    end = request.args.get("end")
    currencies = request.args.get("currencies").split(",")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    result = {}

    for cur in currencies:
        cursor.execute("""
        SELECT rate FROM rates
        WHERE currency=? AND date BETWEEN ? AND ?
        """, (cur, start, end))

        rows = cursor.fetchall()

        rates = [r[0] for r in rows]

        if not rates:
            continue

        result[cur] = {
            "min": min(rates),
            "max": max(rates),
            "avg": sum(rates) / len(rates) 
        }

    conn.close()

    return jsonify(result)


def run_scheduler():
    schedule.every().day.at(config["sync_time"]).do(sync_today)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    init_db()  

    threading.Thread(target=run_scheduler, daemon=True).start()

    app.run(debug=True)