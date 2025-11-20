import tkinter as tk
from tkinter import ttk, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import random
import time
import sqlite3
import paho.mqtt.client as mqtt
import json
import threading
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import requests
import logging
import csv
import os

# Setup logging for debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Simulated appliances with realistic power ranges (in watts)
APPLIANCES = {
    "Fridge": {"power_range": (100, 200), "surge_prob": 0.05, "surge_factor": 2.5, "daily_goal_kwh": 2.0},
    "Air Conditioner": {"power_range": (800, 1500), "surge_prob": 0.02, "surge_factor": 1.8, "daily_goal_kwh": 10.0},
    "Washing Machine": {"power_range": (500, 1000), "surge_prob": 0.03, "surge_factor": 2.0, "daily_goal_kwh": 5.0},
    "Television": {"power_range": (50, 150), "surge_prob": 0.01, "surge_factor": 1.5, "daily_goal_kwh": 1.5},
    "Microwave": {"power_range": (600, 1200), "surge_prob": 0.04, "surge_factor": 1.7, "daily_goal_kwh": 3.0}
}

# Cost per kWh in INR
COST_PER_KWH = 7.5

# Gemini API configuration
GEMINI_API_KEY = " "
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent"

# Initialize SQLite database
def init_db():
    try:
        conn = sqlite3.connect("wattfinder_data.db")
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS consumption (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appliance TEXT,
                timestamp TEXT,
                power_w REAL,
                kwh REAL,
                cost_inr REAL,
                anomaly TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS historical_consumption (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                appliance TEXT,
                timestamp TEXT,
                power_w REAL,
                kwh REAL,
                cost_inr REAL,
                anomaly TEXT
            )
        ''')
        cursor.execute("SELECT COUNT(*) FROM consumption")
        count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM historical_consumption")
        hist_count = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        if count == 0:
            logging.info("Database empty, generating fake data")
            generate_fake_data()
        if hist_count == 0:
            logging.info("Historical database empty, generating fake historical data")
            generate_historical_data()
    except sqlite3.Error as e:
        logging.error(f"Database initialization error: {e}")

# Generate 24-hour fake data for current day
def generate_fake_data():
    try:
        conn = sqlite3.connect("wattfinder_data.db")
        cursor = conn.cursor()
        start_time = datetime(2025, 7, 10, 0, 0)
        end_time = start_time + timedelta(days=1)
        current_time = start_time
        while current_time < end_time:
            hour = current_time.hour
            timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")
            for appliance in APPLIANCES:
                power, anomaly = simulate_power_reading(appliance, hour)
                kwh, cost = calculate_metrics(power)
                anomaly_text = "Surge Detected" if anomaly else "Normal"
                cursor.execute('''
                    INSERT INTO consumption (appliance, timestamp, power_w, kwh, cost_inr, anomaly)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (appliance, timestamp, power, kwh, cost, anomaly_text))
            current_time += timedelta(minutes=1)
        conn.commit()
        logging.info("Fake data generation complete")
    except sqlite3.Error as e:
        logging.error(f"Data generation error: {e}")
    finally:
        conn.close()

# Generate 30-day historical data (June 10–July 9, 2025)
def generate_historical_data():
    try:
        conn = sqlite3.connect("wattfinder_data.db")
        cursor = conn.cursor()
        start_date = datetime(2025, 6, 10, 0, 0)
        end_date = datetime(2025, 7, 9, 23, 59)
        current_time = start_date
        while current_time <= end_date:
            hour = current_time.hour
            timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S")
            for appliance in APPLIANCES:
                power, anomaly = simulate_power_reading(appliance, hour)
                power *= random.uniform(1.1, 1.2)  # 10–20% higher usage
                kwh, cost = calculate_metrics(power)
                anomaly_text = "Surge Detected" if anomaly else "Normal"
                cursor.execute('''
                    INSERT INTO historical_consumption (appliance, timestamp, power_w, kwh, cost_inr, anomaly)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (appliance, timestamp, power, kwh, cost, anomaly_text))
            current_time += timedelta(minutes=1)
        conn.commit()
        logging.info("Historical data generation complete")
    except sqlite3.Error as e:
        logging.error(f"Historical data generation error: {e}")
    finally:
        conn.close()

# Simulate power reading with time-based patterns
def simulate_power_reading(appliance, hour=None):
    power_range = APPLIANCES[appliance]["power_range"]
    surge_prob = APPLIANCES[appliance]["surge_prob"]
    surge_factor = APPLIANCES[appliance]["surge_factor"]
    if hour is None:
        hour = datetime.now().hour
    if appliance == "Fridge":
        power = random.uniform(power_range[0], power_range[1]) * (1.1 if 22 <= hour or hour < 6 else 1.0)
    elif appliance == "Air Conditioner":
        power = random.uniform(power_range[0], power_range[1]) * (1.3 if 18 <= hour or hour < 6 else 0.7)
    elif appliance == "Washing Machine":
        power = random.uniform(power_range[0], power_range[1]) if (8 <= hour < 12 or 18 <= hour < 20) else 0
    elif appliance == "Television":
        power = random.uniform(power_range[0], power_range[1]) if (18 <= hour < 23 or 12 <= hour < 16) else 0
    elif appliance == "Microwave":
        power = random.uniform(power_range[0], power_range[1]) if (7 <= hour < 9 or 12 <= hour < 14 or 19 <= hour < 21) else 0
    if random.random() < surge_prob and power > 0:
        power *= surge_factor
        return power, True
    return power, False

# Calculate kWh and cost
def calculate_metrics(power, duration_hours=1/60):
    kwh = power * duration_hours / 1000
    cost = kwh * COST_PER_KWH
    return kwh, cost

# Log data to SQLite
def log_to_db(appliance, power, kwh, cost, anomaly):
    try:
        conn = sqlite3.connect("wattfinder_data.db")
        cursor = conn.cursor()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        anomaly_text = "Surge Detected" if anomaly else "Normal"
        cursor.execute('''
            INSERT INTO consumption (appliance, timestamp, power_w, kwh, cost_inr, anomaly)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (appliance, timestamp, power, kwh, cost, anomaly_text))
        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"Database logging error: {e}")
    finally:
        conn.close()

# Publish data to MQTT with connection check and retry
def publish_to_mqtt(appliance, power, kwh, cost, anomaly):
    data = {
        "appliance": appliance,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "power_w": float(power),
        "kwh": float(kwh),
        "cost_inr": float(cost),
        "anomaly": "Surge Detected" if anomaly else "Normal"
    }
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if not client.is_connected():
                logging.warning("MQTT client disconnected, attempting to reconnect")
                client.reconnect()
                time.sleep(1)
            client.publish("wattfinder/data", json.dumps(data), qos=1)
            logging.info(f"Published data for {appliance}")
            return
        except Exception as e:
            logging.error(f"MQTT publish attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                logging.error(f"Failed to publish data for {appliance} after {max_retries} attempts")

# Export data to CSV
def export_data_to_csv(period="daily"):
    try:
        conn = sqlite3.connect("wattfinder_data.db")
        cursor = conn.cursor()
        if period == "daily":
            today = datetime.now().strftime("%Y-%m-%d")
            cursor.execute('''
                SELECT appliance, timestamp, power_w, kwh, cost_inr, anomaly
                FROM consumption WHERE timestamp LIKE ?
            ''', (f"{today}%",))
            filename = f"wattfinder_export_{today}.csv"
        else:
            cursor.execute('''
                SELECT appliance, timestamp, power_w, kwh, cost_inr, anomaly
                FROM historical_consumption
            ''')
            filename = f"wattfinder_export_historical_{datetime.now().strftime('%Y-%m-%d')}.csv"
        rows = cursor.fetchall()
        conn.close()
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Appliance", "Timestamp", "Power (W)", "kWh", "Cost (INR)", "Anomaly"])
            writer.writerows(rows)
        return filename
    except Exception as e:
        logging.error(f"Export data error: {e}")
        return None

# Get anomaly history
def get_anomaly_history():
    try:
        conn = sqlite3.connect("wattfinder_data.db")
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute('''
            SELECT appliance, timestamp, power_w
            FROM consumption
            WHERE anomaly = 'Surge Detected' AND timestamp LIKE ?
            ORDER BY timestamp DESC
        ''', (f"{today}%",))
        rows = cursor.fetchall()
        conn.close()
        return rows
    except sqlite3.Error as e:
        logging.error(f"Anomaly history error: {e}")
        return []

# Gemini AI for chat and conservation tips
def get_gemini_response(appliance, power, kwh, anomaly_count, user_query=None):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            prompt = f"Electricity usage for {appliance}: Current power: {power:.2f}W, daily energy: {kwh:.2f} kWh, anomalies today: {anomaly_count}."
            if user_query:
                prompt += f" User asked: {user_query}. Provide a concise, accurate response related to the WattFinder application (max 50 words)."
            else:
                prompt += " Suggest an energy-saving tip or compare with last month's average (max 50 words)."
            headers = {"Content-Type": "application/json"}
            data = {
                "contents": [{"parts": [{"text": prompt}]}]
            }
            response = requests.post(f"{GEMINI_API_URL}?key={GEMINI_API_KEY}", headers=headers, json=data, timeout=20)
            response.raise_for_status()
            result = response.json()
            text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "No response")
            if text == "No response":
                raise Exception("Empty response from API")
            logging.info(f"Gemini API success for {appliance}: {text}")
            return text
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "N/A"
            logging.error(f"Gemini API attempt {attempt + 1} failed: HTTP {status}, Response: {e.response.text if e.response else 'N/A'}")
            if status == 429:
                logging.warning("Rate limit hit, retrying after delay")
                time.sleep(2 ** attempt)
            elif attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                logging.error(f"Gemini API failed after {max_retries} attempts")
                return {
                    "Fridge": "Lower Fridge temperature to 3°C to save 10% energy.",
                    "Air Conditioner": "Set Air Conditioner to 24°C to reduce energy by 15%.",
                    "Washing Machine": "Use Washing Machine during off-peak hours to save energy.",
                    "Television": "Turn off Television when not in use to save energy.",
                    "Microwave": "Avoid preheating Microwave to save 5% energy."
                }[appliance]
        except Exception as e:
            logging.error(f"Gemini API attempt {attempt + 1} failed: {e}, Status: N/A, Response: N/A")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                logging.error(f"Gemini API failed after {max_retries} attempts")
                return {
                    "Fridge": "Lower Fridge temperature to 3°C to save 10% energy.",
                    "Air Conditioner": "Set Air Conditioner to 24°C to reduce energy by 15%.",
                    "Washing Machine": "Use Washing Machine during off-peak hours to save energy.",
                    "Television": "Turn off Television when not in use to save energy.",
                    "Microwave": "Avoid preheating Microwave to save 5% energy."
                }[appliance]
    return "AI unavailable; please check your internet connection."

# Parse user query for application-specific responses
def parse_user_query(query, stats):
    query = query.lower()
    for appliance in APPLIANCES:
        if appliance.lower() in query:
            if "usage" in query or "energy" in query:
                return f"{appliance} used {stats[appliance]['current_kwh']:.2f} kWh today, {'down' if stats[appliance]['hist_kwh'] > stats[appliance]['current_kwh'] else 'up'} {abs((stats[appliance]['hist_kwh'] - stats[appliance]['current_kwh']) / stats[appliance]['hist_kwh'] * 100):.1f}% from last month's {stats[appliance]['hist_kwh']:.2f} kWh."
            elif "surge" in query or "anomaly" in query:
                return f"{appliance} had {stats[appliance]['current_anomalies']} surges today. Check for overuse or faults."
            elif "save" in query or "tip" in query:
                return get_gemini_response(appliance, stats[appliance]["power"], stats[appliance]["current_kwh"], stats[appliance]["current_anomalies"])
            elif "power" in query:
                return f"{appliance} current power: {stats[appliance]['power']:.2f} W."
            elif "cost" in query:
                return f"{appliance} cost today: ₹{stats[appliance]['current_kwh'] * COST_PER_KWH:.2f}."
    if "last question" in query:
        if recent_queries:
            return f"Last question: {recent_queries[-1]}"
    return None

# Get daily and historical stats
def get_stats():
    stats = {}
    try:
        conn = sqlite3.connect("wattfinder_data.db")
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        for appliance in APPLIANCES:
            cursor.execute('''
                SELECT SUM(kwh), COUNT(*) FROM consumption
                WHERE appliance = ? AND timestamp LIKE ? AND anomaly = 'Surge Detected'
            ''', (appliance, f"{today}%"))
            current_kwh, current_anomalies = cursor.fetchone()
            cursor.execute('''
                SELECT power_w FROM consumption
                WHERE appliance = ? ORDER BY timestamp DESC LIMIT 1
            ''', (appliance,))
            power = cursor.fetchone()[0] if cursor.rowcount > 0 else 0
            cursor.execute('''
                SELECT AVG(kwh), COUNT(*) / 30.0 FROM historical_consumption
                WHERE appliance = ? AND anomaly = 'Surge Detected'
            ''', (appliance,))
            hist_kwh, hist_anomalies = cursor.fetchone()
            stats[appliance] = {
                "power": power or 0,
                "current_kwh": current_kwh or 0,
                "current_anomalies": current_anomalies or 0,
                "hist_kwh": hist_kwh or 0,
                "hist_anomalies": hist_anomalies or 0
            }
        conn.close()
        return stats
    except sqlite3.Error as e:
        logging.error(f"Stats error: {e}")
        return {appliance: {"power": 0, "current_kwh": 0, "current_anomalies": 0, "hist_kwh": 0, "hist_anomalies": 0} for appliance in APPLIANCES}

# MQTT client setup
def on_connect(client, userdata, flags, reason_code, properties=None):
    logging.info(f"Connected to MQTT broker with code {reason_code}")

client = mqtt.Client(client_id="", protocol=mqtt.MQTTv5)
client.on_connect = on_connect
try:
    client.connect("broker.hivemq.com", 1883, 60)
except Exception as e:
    logging.error(f"MQTT initial connection error: {e}")

# Professional laptop-optimized UI
class WattFinderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WattFinder: Electricity Assistant")
        self.root.geometry("1600x900")
        self.root.configure(bg="#1E3A8A")
        self.theme = "darkly"
        self.recent_queries = []

        # Use ttkbootstrap for modern styling
        self.style = ttk.Style(self.theme)
        self.style.configure("TButton", font=("Helvetica", 12, "bold"), padding=10, borderwidth=0)
        self.style.configure("TLabel", font=("Helvetica", 12), foreground="#FFFFFF")
        self.style.configure("TProgressbar", thickness=20)

        # Main frame
        self.main_frame = tk.Frame(self.root, bg="#2A2A3C")
        self.main_frame.pack(fill="both", expand=True)

        # Sidebar (350px wide)
        self.sidebar = tk.Frame(self.main_frame, bg="#252537", width=350)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        tk.Label(self.sidebar, text="AI Assistant", font=("Helvetica", 14, "bold"), bg="#252537", fg="#FFFFFF").pack(pady=10)
        self.chatbox = tk.Text(self.sidebar, height=20, width=35, bg="#2A2A3C", fg="#FFFFFF", font=("Helvetica", 10), wrap="word", bd=0)
        self.chatbox.pack(padx=10, pady=5)
        self.chatbox.config(state="disabled")
        input_frame = tk.Frame(self.sidebar, bg="#252537")
        input_frame.pack(fill="x", padx=10, pady=5)
        self.chat_input = tk.Entry(input_frame, font=("Helvetica", 10), bg="#2A2A3C", fg="#FFFFFF", bd=0)
        self.chat_input.pack(side="left", fill="x", expand=True, ipady=5)
        self.chat_input.bind("<Return>", self.send_chat_message)
        send_btn = ttk.Button(input_frame, text="➤", style="success.TButton", command=self.send_chat_message, width=3)
        send_btn.pack(side="left", padx=5)
        clear_btn = ttk.Button(self.sidebar, text="Clear Chat", style="danger.TButton", command=self.clear_chatbox)
        clear_btn.pack(pady=5)
        self.api_status_label = tk.Label(self.sidebar, text="AI Status: Online", font=("Helvetica", 10), bg="#252537", fg="#22C55E")
        self.api_status_label.pack(pady=5)
        theme_btn = ttk.Button(self.sidebar, text="Toggle Theme", style="secondary.TButton", command=self.toggle_theme)
        theme_btn.pack(pady=5)

        # Dashboard frame (~1250px wide)
        self.dashboard = tk.Frame(self.main_frame, bg="#2A2A3C")
        self.dashboard.pack(side="left", fill="both", expand=True)

        # Header
        header_frame = tk.Frame(self.dashboard, bg="#252537", pady=10)
        header_frame.pack(fill="x")
        tk.Label(header_frame, text="WattFinder Dashboard", font=("Helvetica", 16, "bold"), bg="#252537", fg="#FFFFFF").pack()
        self.status_label = tk.Label(header_frame, text="🟢 Connected", font=("Helvetica", 10), bg="#252537", fg="#22C55E")
        self.status_label.pack()

        # Chart
        self.fig, self.ax = plt.subplots(figsize=(7, 3))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.dashboard)
        self.canvas.get_tk_widget().pack(pady=10)
        self.plot_data = {appliance: [] for appliance in APPLIANCES}
        self.plot_times = []

        # Scrollable appliance cards
        self.canvas_frame = tk.Canvas(self.dashboard, bg="#2A2A3C", highlightthickness=0)
        self.scroll_frame = tk.Frame(self.canvas_frame, bg="#2A2A3C")
        self.canvas_frame.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas_frame.pack(side="left", fill="both", expand=True)
        self.scroll_frame.bind("<Configure>", lambda e: self.canvas_frame.configure(scrollregion=self.canvas_frame.bbox("all")))
        
        # Appliance cards
        self.cards = {}
        for appliance in APPLIANCES:
            self.create_appliance_card(appliance)

        # Control buttons
        button_frame = tk.Frame(self.dashboard, bg="#2A2A3C", pady=10)
        button_frame.pack(fill="x")
        self.start_btn = ttk.Button(button_frame, text="Start Monitoring", style="success.TButton", command=self.start_monitoring)
        self.start_btn.pack(side="left", padx=10)
        self.stop_btn = ttk.Button(button_frame, text="Stop Monitoring", style="danger.TButton", command=self.stop_monitoring, state="disabled")
        self.stop_btn.pack(side="left", padx=10)
        self.refresh_btn = ttk.Button(button_frame, text="Refresh Data", style="info.TButton", command=self.refresh_data)
        self.refresh_btn.pack(side="left", padx=10)
        export_btn = ttk.Button(button_frame, text="Export Data", style="info.TButton", command=self.export_data)
        export_btn.pack(side="left", padx=10)
        anomaly_btn = ttk.Button(button_frame, text="View Anomalies", style="warning.TButton", command=self.show_anomaly_history)
        anomaly_btn.pack(side="left", padx=10)

        # Monitoring state
        self.running = False
        self.recent_queries = []
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        client.loop_start()
        threading.Thread(target=self.update_chatbox, daemon=True).start()

    def create_appliance_card(self, appliance):
        card = tk.Frame(self.scroll_frame, bg="#2A2A3C", bd=0, relief="flat", pady=10, padx=10)
        card.pack(fill="x", padx=10, pady=5)
        card.configure(highlightbackground="#22C55E", highlightthickness=2)
        card.bind("<Button-1>", lambda e: self.toggle_card(appliance))

        title = tk.Label(card, text=appliance, font=("Helvetica", 12, "bold"), bg="#2A2A3C", fg="#FFFFFF")
        title.pack(anchor="w")
        details = tk.Frame(card, bg="#2A2A3C")
        power_label = tk.Label(details, text="Power: 0.00 W", font=("Helvetica", 10), bg="#2A2A3C", fg="#FFFFFF")
        power_label.pack(anchor="w")
        kwh_label = tk.Label(details, text="Energy: 0.0000 kWh", font=("Helvetica", 10), bg="#2A2A3C", fg="#FFFFFF")
        kwh_label.pack(anchor="w")
        cost_label = tk.Label(details, text="Cost: ₹0.00", font=("Helvetica", 10), bg="#2A2A3C", fg="#FFFFFF")
        cost_label.pack(anchor="w")
        status_label = tk.Label(details, text="Status: Normal", font=("Helvetica", 10), bg="#2A2A3C", fg="#22C55E")
        status_label.pack(anchor="w")
        ai_button = ttk.Button(details, text="AI Insight", style="info.TButton", command=lambda: self.show_ai_insight(appliance))
        ai_button.pack(anchor="w", pady=5)
        progress = ttk.Progressbar(details, length=350, maximum=APPLIANCES[appliance]["daily_goal_kwh"], style="success.Horizontal.TProgressbar")
        progress.pack(pady=5)

        self.cards[appliance] = {
            "card": card,
            "details": details,
            "power_label": power_label,
            "kwh_label": kwh_label,
            "cost_label": cost_label,
            "status_label": status_label,
            "progress": progress,
            "expanded": True
        }
        details.pack()

    def toggle_card(self, appliance):
        card = self.cards[appliance]
        if card["expanded"]:
            card["details"].pack_forget()
            card["expanded"] = False
        else:
            card["details"].pack()
            card["expanded"] = True

    def toggle_theme(self):
        try:
            if self.theme == "darkly":
                self.theme = "flatly"
                self.main_frame.configure(bg="#D1D5DB")
                self.sidebar.configure(bg="#E5E7EB")
                self.dashboard.configure(bg="#D1D5DB")
                self.canvas_frame.configure(bg="#D1D5DB")
                self.scroll_frame.configure(bg="#D1D5DB")
                for card in self.cards.values():
                    card["card"].configure(bg="#D1D5DB", highlightbackground="#22C55E")
                    card["details"].configure(bg="#D1D5DB")
                    card["power_label"].configure(bg="#D1D5DB", fg="#000000")
                    card["kwh_label"].configure(bg="#D1D5DB", fg="#000000")
                    card["cost_label"].configure(bg="#D1D5DB", fg="#000000")
                    card["status_label"].configure(bg="#D1D5DB", fg="#22C55E" if card["status_label"].cget("text") == "Status: Normal" else "#EF4444")
                    self.chatbox.configure(bg="#E5E7EB", fg="#000000")
                    self.chat_input.configure(bg="#E5E7EB", fg="#000000")
                    self.api_status_label.configure(bg="#E5E7EB", fg="#22C55E" if self.api_status_label.cget("text") == "AI Status: Online" else "#EF4444")
            else:
                self.theme = "darkly"
                self.main_frame.configure(bg="#2A2A3C")
                self.sidebar.configure(bg="#252537")
                self.dashboard.configure(bg="#2A2A3C")
                self.canvas_frame.configure(bg="#2A2A3C")
                self.scroll_frame.configure(bg="#2A2A3C")
                for card in self.cards.values():
                    card["card"].configure(bg="#2A2A3C", highlightbackground="#22C55E")
                    card["details"].configure(bg="#2A2A3C")
                    card["power_label"].configure(bg="#2A2A3C", fg="#FFFFFF")
                    card["kwh_label"].configure(bg="#2A2A3C", fg="#FFFFFF")
                    card["cost_label"].configure(bg="#2A2A3C", fg="#FFFFFF")
                    card["status_label"].configure(bg="#2A2A3C", fg="#22C55E" if card["status_label"].cget("text") == "Status: Normal" else "#EF4444")
                    self.chatbox.configure(bg="#2A2A3C", fg="#FFFFFF")
                    self.chat_input.configure(bg="#2A2A3C", fg="#FFFFFF")
                    self.api_status_label.configure(bg="#252537", fg="#22C55E" if self.api_status_label.cget("text") == "AI Status: Online" else "#EF4444")
            self.style = ttk.Style(self.theme)
            self.style.configure("TButton", font=("Helvetica", 12, "bold"), padding=10, borderwidth=0)
            self.style.configure("TLabel", font=("Helvetica", 12), foreground="#FFFFFF" if self.theme == "darkly" else "#000000")
            self.style.configure("TProgressbar", thickness=20)
        except Exception as e:
            logging.error(f"Theme toggle error: {e}")

    def start_monitoring(self):
        try:
            self.running = True
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
            self.status_label.config(text="🟢 Monitoring", fg="#22C55E")
            threading.Thread(target=self.monitor_loop, daemon=True).start()
        except Exception as e:
            logging.error(f"Start monitoring error: {e}")
            self.status_label.config(text="🔴 Error", fg="#EF4444")

    def stop_monitoring(self):
        try:
            self.running = False
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.status_label.config(text="🟢 Connected", fg="#22C55E")
        except Exception as e:
            logging.error(f"Stop monitoring error: {e}")

    def refresh_data(self):
        try:
            for appliance in APPLIANCES:
                data = self.get_latest_data(appliance)
                self.update_card(appliance, data)
            self.update_chart()
        except Exception as e:
            logging.error(f"Refresh data error: {e}")
            self.status_label.config(text="🔴 Error", fg="#EF4444")

    def export_data(self):
        try:
            filename = export_data_to_csv("daily")
            if filename:
                messagebox.showinfo("Export Success", f"Data exported to {filename}")
            else:
                messagebox.showerror("Export Error", "Failed to export data")
        except Exception as e:
            logging.error(f"Export data error: {e}")
            messagebox.showerror("Export Error", "Failed to export data")

    def show_anomaly_history(self):
        try:
            rows = get_anomaly_history()
            if not rows:
                messagebox.showinfo("Anomaly History", "No anomalies detected today.")
                return
            anomaly_window = tk.Toplevel(self.root)
            anomaly_window.title("Anomaly History")
            anomaly_window.geometry("600x400")
            anomaly_window.configure(bg="#2A2A3C")
            tree = ttk.Treeview(anomaly_window, columns=("Appliance", "Timestamp", "Power"), show="headings")
            tree.heading("Appliance", text="Appliance")
            tree.heading("Timestamp", text="Timestamp")
            tree.heading("Power", text="Power (W)")
            tree.pack(fill="both", expand=True, padx=10, pady=10)
            for row in rows:
                tree.insert("", "end", values=(row[0], row[1], f"{row[2]:.2f}"))
        except Exception as e:
            logging.error(f"Anomaly history error: {e}")
            messagebox.showerror("Anomaly History", "Failed to load anomaly history")

    def monitor_loop(self):
        while self.running:
            try:
                stats = get_stats()
                for appliance in APPLIANCES:
                    power, anomaly = simulate_power_reading(appliance)
                    kwh, cost = calculate_metrics(power)
                    log_to_db(appliance, power, kwh, cost, anomaly)
                    publish_to_mqtt(appliance, power, kwh, cost, anomaly)
                    self.update_card(appliance, {
                        "power_w": power,
                        "kwh": kwh,
                        "cost_inr": cost,
                        "anomaly": "Surge Detected" if anomaly else "Normal"
                    })
                    if anomaly:
                        insight = get_gemini_response(appliance, stats[appliance]["power"], stats[appliance]["current_kwh"], stats[appliance]["current_anomalies"])
                        self.root.after(0, lambda: messagebox.showinfo("AI Alert", insight))
                    if stats[appliance]["current_kwh"] > APPLIANCES[appliance]["daily_goal_kwh"]:
                        self.root.after(0, lambda: self.chatbox.config(state="normal"))
                        self.root.after(0, lambda: self.chatbox.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] AI: {appliance} exceeded {APPLIANCES[appliance]['daily_goal_kwh']:.1f} kWh goal!\n"))
                        self.root.after(0, lambda: self.chatbox.see(tk.END))
                        self.root.after(0, lambda: self.chatbox.config(state="disabled"))
                    self.plot_data[appliance].append(power)
                    if len(self.plot_data[appliance]) > 60:
                        self.plot_data[appliance].pop(0)
                self.plot_times.append(datetime.now())
                if len(self.plot_times) > 60:
                    self.plot_times.pop(0)
                self.root.after(0, self.update_chart)
                time.sleep(1)
            except Exception as e:
                logging.error(f"Monitor loop error: {e}")
                self.root.after(0, lambda: self.status_label.config(text="🔴 Error", fg="#EF4444"))

    def update_card(self, appliance, data):
        try:
            card = self.cards[appliance]
            card["power_label"].config(text=f"Power: {data['power_w']:.2f} W")
            card["kwh_label"].config(text=f"Energy: {data['kwh']:.4f} kWh")
            card["cost_label"].config(text=f"Cost: ₹{data['cost_inr']:.2f}")
            card["status_label"].config(
                text=f"Status: {data['anomaly']}",
                fg="#EF4444" if data["anomaly"] == "Surge Detected" else "#22C55E"
            )
            card["progress"].config(value=data["kwh"], style="danger.Horizontal.TProgressbar" if data["kwh"] > APPLIANCES[appliance]["daily_goal_kwh"] else "success.Horizontal.TProgressbar")
        except Exception as e:
            logging.error(f"Update card error: {e}")

    def get_latest_data(self, appliance):
        try:
            conn = sqlite3.connect("wattfinder_data.db")
            cursor = conn.cursor()
            cursor.execute('''
                SELECT power_w, kwh, cost_inr, anomaly FROM consumption
                WHERE appliance = ? ORDER BY timestamp DESC LIMIT 1
            ''', (appliance,))
            row = cursor.fetchone()
            conn.close()
            return {
                "power_w": row[0] if row else 0,
                "kwh": row[1] if row else 0,
                "cost_inr": row[2] if row else 0,
                "anomaly": row[3] if row else "Normal"
            }
        except sqlite3.Error as e:
            logging.error(f"Get latest data error: {e}")
            return {"power_w": 0, "kwh": 0, "cost_inr": 0, "anomaly": "Normal"}

    def send_chat_message(self, event=None):
        try:
            query = self.chat_input.get().strip()
            if not query:
                return
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.chatbox.config(state="normal")
            self.chatbox.insert(tk.END, f"[{timestamp}] You: {query}\n")
            self.chat_input.delete(0, tk.END)
            self.recent_queries.append(query)
            if len(self.recent_queries) > 10:
                self.recent_queries.pop(0)
            stats = get_stats()
            response = parse_user_query(query, stats)
            if not response:
                appliance = random.choice(list(APPLIANCES.keys()))
                response = get_gemini_response(appliance, stats[appliance]["power"], stats[appliance]["current_kwh"], stats[appliance]["current_anomalies"], query)
            self.chatbox.insert(tk.END, f"[{timestamp}] AI: {response}\n")
            self.chatbox.see(tk.END)
            self.chatbox.config(state="disabled")
            self.api_status_label.config(text="AI Status: Online", fg="#22C55E")
        except Exception as e:
            logging.error(f"Chat message error: {e}")
            self.chatbox.config(state="normal")
            self.chatbox.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] AI: Error processing request; check internet.\n")
            self.chatbox.see(tk.END)
            self.chatbox.config(state="disabled")
            self.api_status_label.config(text="AI Status: Offline", fg="#EF4444")

    def show_ai_insight(self, appliance):
        try:
            stats = get_stats()
            insight = get_gemini_response(appliance, stats[appliance]["power"], stats[appliance]["current_kwh"], stats[appliance]["current_anomalies"])
            messagebox.showinfo(f"{appliance} AI Insight", insight)
            self.api_status_label.config(text="AI Status: Online", fg="#22C55E")
        except Exception as e:
            logging.error(f"AI insight error: {e}")
            messagebox.showinfo(f"{appliance} AI Insight", f"Error retrieving insight for {appliance}")
            self.api_status_label.config(text="AI Status: Offline", fg="#EF4444")

    def update_chatbox(self):
        while True:
            try:
                if self.running:
                    stats = get_stats()
                    for appliance in APPLIANCES:
                        current_kwh = stats[appliance]["current_kwh"]
                        hist_kwh = stats[appliance]["hist_kwh"]
                        improvement = ((hist_kwh - current_kwh) / hist_kwh * 100) if hist_kwh > 0 else 0
                        msg = f"{appliance} usage {'down' if improvement > 0 else 'up'} {abs(improvement):.1f}% from last month's {hist_kwh:.2f} kWh average."
                        insight = get_gemini_response(appliance, stats[appliance]["power"], stats[appliance]["current_kwh"], stats[appliance]["current_anomalies"])
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        self.chatbox.config(state="normal")
                        self.chatbox.insert(tk.END, f"[{timestamp}] AI: {msg}\n[{timestamp}] AI: {insight}\n")
                        self.chatbox.see(tk.END)
                        self.chatbox.config(state="disabled")
                        self.api_status_label.config(text="AI Status: Online", fg="#22C55E")
                time.sleep(10)
            except Exception as e:
                logging.error(f"Chatbox update error: {e}")
                self.root.after(0, lambda: self.chatbox.config(state="normal"))
                self.root.after(0, lambda: self.chatbox.insert(tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] AI: Error fetching AI tips\n"))
                self.root.after(0, lambda: self.chatbox.see(tk.END))
                self.root.after(0, lambda: self.chatbox.config(state="disabled"))
                self.root.after(0, lambda: self.api_status_label.config(text="AI Status: Offline", fg="#EF4444"))

    def clear_chatbox(self):
        try:
            self.chatbox.config(state="normal")
            self.chatbox.delete(1.0, tk.END)
            self.chatbox.config(state="disabled")
            self.recent_queries = []
        except Exception as e:
            logging.error(f"Clear chatbox error: {e}")

    def update_chart(self):
        try:
            self.ax.clear()
            for appliance, data in self.plot_data.items():
                if len(data) > 0:
                    self.ax.plot(self.plot_times[-len(data):], data, label=appliance)
            self.ax.set_ylabel("Power (W)")
            self.ax.legend(fontsize=8)
            self.ax.grid(True, linestyle="--", alpha=0.7)
            plt.setp(self.ax.get_xticklabels(), rotation=45, ha="right", fontsize=8)
            self.canvas.draw()
        except Exception as e:
            logging.error(f"Chart update error: {e}")
            self.status_label.config(text="🔴 Error", fg="#EF4444")

    def on_closing(self):
        try:
            self.running = False
            client.loop_stop()
            client.disconnect()
            self.root.destroy()
        except Exception as e:
            logging.error(f"Closing error: {e}")

# Main execution
if __name__ == "__main__":
    try:
        init_db()
        root = tk.Tk()
        app = WattFinderApp(root)
        root.mainloop()
    except Exception as e:
        logging.error(f"Application startup error: {e}")
