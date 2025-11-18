import sqlite3
import logging

def init_db():
    try:
        conn = sqlite3.connect("wattfinder_data.db")
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS consumption (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appliance TEXT,
            timestamp TEXT,
            power_w REAL,
            kwh REAL,
            cost_inr REAL,
            anomaly TEXT
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS historical_consumption (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appliance TEXT,
            timestamp TEXT,
            power_w REAL,
            kwh REAL,
            cost_inr REAL,
            anomaly TEXT
        )''')
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        logging.error(f"Database initialization error: {e}")

def save_data_to_db(appliance, timestamp, power, kwh, cost, anomaly):
    try:
        conn = sqlite3.connect("wattfinder_data.db")
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO consumption (appliance, timestamp, power_w, kwh, cost_inr, anomaly)
                          VALUES (?, ?, ?, ?, ?, ?)''', 
                       (appliance, timestamp, power, kwh, cost, anomaly))
        conn.commit()
        conn.close()
    except sqlite3.Error as e:
        logging.error(f"Data saving error: {e}")
