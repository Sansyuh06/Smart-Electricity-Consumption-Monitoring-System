import tkinter as tk
from tkinter import ttk, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import random
import time
import sqlite3
import threading
from datetime import datetime
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import requests
import logging
import warnings
import json

# --- Universal Import Fix ---
warnings.simplefilter("ignore") 

try:
    from ttkbootstrap.widgets.scrolled import ScrolledFrame
except ImportError:
    try:
        from ttkbootstrap.scrolled import ScrolledFrame
    except ImportError:
        logging.error("CRITICAL: Could not import ScrolledFrame. Update ttkbootstrap: pip install --upgrade ttkbootstrap")

# --- Configuration & Constants ---
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

# API Configuration
GEMINI_API_KEY = " "
COST_PER_KWH = 7.50  # INR

APPLIANCES_CONFIG = {
    "Fridge": {"range": (100, 200), "surge": 2.5, "prob": 0.05, "goal": 2.0, "icon": "🧊"},
    "AC Unit": {"range": (800, 1500), "surge": 1.8, "prob": 0.02, "goal": 10.0, "icon": "❄️"},
    "Washing Machine": {"range": (500, 1000), "surge": 2.0, "prob": 0.03, "goal": 2.5, "icon": "🧺"},
    "Smart TV": {"range": (50, 150), "surge": 1.5, "prob": 0.01, "goal": 1.5, "icon": "📺"},
    "Microwave": {"range": (800, 1200), "surge": 1.2, "prob": 0.04, "goal": 1.0, "icon": "🍕"}
}

# --- Backend Logic (Data & AI) ---

class AIAssistant:
    def __init__(self):
        self.context = (
            "You are WattFinder AI, an enterprise energy efficiency expert. "
            "Analyze power data and provide actionable, professional advice. "
            "Keep responses concise (under 80 words). Currency is INR (₹). "
            "Focus on cost savings, efficiency improvements, and surge alerts."
        )
        # List of models to try in order of preference (Failover System)
        self.model_fallbacks = ["gemini-1.5-flash", "gemini-1.5-flash-001", "gemini-pro"]

    def ask(self, prompt):
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{
                "parts": [{"text": f"{self.context}\n\n{prompt}"}]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 200
            }
        }

        # Try models in sequence until one works
        for model in self.model_fallbacks:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=10)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        return data['candidates'][0]['content']['parts'][0]['text'].strip()
                    except (KeyError, IndexError):
                        continue # Try next model if response format is unexpected
                elif response.status_code == 404:
                    logging.warning(f"Model {model} not found (404). Switching to fallback...")
                    continue # Try next model
                else:
                    logging.error(f"API Error {response.status_code} on {model}: {response.text[:100]}")
                    
            except requests.exceptions.RequestException as e:
                logging.error(f"Connection error on {model}: {e}")
                continue

        return "⚠️ AI Service Unavailable. Please check internet connection."

class EnergyBackend:
    def __init__(self):
        self.db_name = "wattfinder_enterprise.db"
        self.init_db()
        self.running = False
        self.data_buffer = {k: [] for k in APPLIANCES_CONFIG.keys()}
        self.latest_readings = {k: {'power': 0, 'kwh': 0, 'cost': 0, 'status': 'Off'} for k in APPLIANCES_CONFIG}
        self.surge_count = {k: 0 for k in APPLIANCES_CONFIG}
        self.session_start = None

    def init_db(self):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute('''CREATE TABLE IF NOT EXISTS readings 
                              (id INTEGER PRIMARY KEY, appliance TEXT, timestamp TEXT, 
                               power REAL, kwh REAL, cost REAL, status TEXT)''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS sessions 
                              (id INTEGER PRIMARY KEY, start_time TEXT, end_time TEXT,
                               total_kwh REAL, total_cost REAL, surges INTEGER)''')
            conn.commit()

    def simulate_reading(self, appliance):
        cfg = APPLIANCES_CONFIG[appliance]
        hour = datetime.now().hour
        
        # Enhanced time-of-day logic
        is_active = True
        if appliance == "Microwave" and not (7 <= hour <= 9 or 18 <= hour <= 21): 
            is_active = False
        if appliance == "Washing Machine" and not (8 <= hour <= 13): 
            is_active = False
        if appliance == "AC Unit" and not (10 <= hour <= 23):
            is_active = False
        
        if not is_active:
            return 0, "Standby"

        base_power = random.uniform(*cfg['range'])
        status = "Normal"
        
        # Surge detection
        if random.random() < cfg['prob']:
            base_power *= cfg['surge']
            status = "⚠️ SURGE"
            self.surge_count[appliance] += 1
        
        return base_power, status

    def start_monitoring(self, update_callback):
        self.running = True
        self.session_start = datetime.now()
        threading.Thread(target=self._monitor_loop, args=(update_callback,), daemon=True).start()

    def stop_monitoring(self):
        if self.running:
            self.running = False
            self._save_session()

    def _save_session(self):
        if not self.session_start:
            return
            
        total_kwh = sum(r['kwh'] for r in self.latest_readings.values())
        total_cost = sum(r['cost'] for r in self.latest_readings.values())
        total_surges = sum(self.surge_count.values())
        
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO sessions (start_time, end_time, total_kwh, total_cost, surges) VALUES (?,?,?,?,?)",
                (self.session_start.strftime("%Y-%m-%d %H:%M:%S"),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 total_kwh, total_cost, total_surges)
            )
            conn.commit()

    def _monitor_loop(self, update_callback):
        while self.running:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                
                for app_name in APPLIANCES_CONFIG:
                    power, status = self.simulate_reading(app_name)
                    
                    # Calculate metrics (2 second interval)
                    kwh_inc = (power * (2/3600)) / 1000 
                    cost_inc = kwh_inc * COST_PER_KWH
                    
                    # Update state
                    prev = self.latest_readings[app_name]
                    new_kwh = prev['kwh'] + kwh_inc
                    new_cost = prev['cost'] + cost_inc
                    
                    self.latest_readings[app_name] = {
                        'power': power,
                        'kwh': new_kwh,
                        'cost': new_cost,
                        'status': status
                    }
                    
                    # Buffer for graphing
                    self.data_buffer[app_name].append(power)
                    if len(self.data_buffer[app_name]) > 50:
                        self.data_buffer[app_name].pop(0)

                    # DB logging
                    cursor.execute(
                        "INSERT INTO readings (appliance, timestamp, power, kwh, cost, status) VALUES (?,?,?,?,?,?)",
                        (app_name, timestamp, power, kwh_inc, cost_inc, status)
                    )
            
                conn.commit()
            
            try:
                update_callback()
            except RuntimeError:
                break
            
            time.sleep(2)

    def get_history_data(self):
        return self.data_buffer
    
    def get_insights_summary(self):
        """Generate data summary for AI context"""
        readings = self.latest_readings
        total_power = sum(r['power'] for r in readings.values())
        total_cost = sum(r['cost'] for r in readings.values())
        
        # Find top consumers
        sorted_apps = sorted(readings.items(), key=lambda x: x[1]['cost'], reverse=True)
        top_3 = [(name, data['cost'], data['kwh']) for name, data in sorted_apps[:3]]
        
        # Surge analysis
        surge_apps = [name for name, count in self.surge_count.items() if count > 0]
        
        summary = f"""Current System Status:
- Total Load: {total_power:.0f}W
- Session Cost: ₹{total_cost:.2f}
- Top Consumers: {', '.join([f"{n} (₹{c:.2f})" for n,c,_ in top_3])}
- Surges Detected: {', '.join(surge_apps) if surge_apps else 'None'}
- Total Surge Events: {sum(self.surge_count.values())}"""
        
        return summary

# --- UI Components ---

class DashboardApp(ttk.Window):
    def __init__(self):
        super().__init__(themename="darkly")
        self.title("WattFinder Enterprise | Energy Management System")
        self.geometry("1450x950")
        
        try:
            self.place_window_center()
        except AttributeError:
            pass 
        
        self.backend = EnergyBackend()
        self.ai = AIAssistant()
        
        self.meters = {}
        self.stat_labels = {}
        
        self._setup_ui()
        plt.style.use('dark_background')

    def _setup_ui(self):
        # Sidebar
        sidebar = ttk.Frame(self, bootstyle="secondary", width=250)
        sidebar.pack(side=LEFT, fill=Y)
        
        # Logo
        ttk.Label(sidebar, text="⚡ WattFinder", font=("Helvetica", 22, "bold"), 
                  bootstyle="inverse-secondary").pack(pady=20)
        ttk.Label(sidebar, text="Enterprise Edition", font=("Helvetica", 9), 
                  bootstyle="secondary").pack()
        ttk.Separator(sidebar, bootstyle="light").pack(fill=X, padx=10, pady=10)

        # Notebook
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(side=RIGHT, fill=BOTH, expand=True)

        # Tabs
        self.tab_dashboard = ttk.Frame(self.notebook, padding=20)
        self.tab_analytics = ttk.Frame(self.notebook, padding=20)
        
        self.notebook.add(self.tab_dashboard, text="  📊 Live Dashboard  ")
        self.notebook.add(self.tab_analytics, text="  🤖 AI Analytics  ")

        # Sidebar Controls
        ttk.Button(sidebar, text="▶ Start Monitoring", bootstyle="success-outline", 
                   command=self.start_system).pack(fill=X, padx=20, pady=5)
        ttk.Button(sidebar, text="⏸ Pause System", bootstyle="warning-outline", 
                   command=self.stop_system).pack(fill=X, padx=20, pady=5)
        ttk.Button(sidebar, text="💡 Quick Insights", bootstyle="info-outline", 
                   command=self.quick_insights).pack(fill=X, padx=20, pady=5)
        
        ttk.Separator(sidebar, bootstyle="light").pack(fill=X, padx=10, pady=15)
        
        ttk.Label(sidebar, text="System Status", bootstyle="inverse-secondary", 
                  font=("Helvetica", 10)).pack(pady=(10, 5))
        self.status_lbl = ttk.Label(sidebar, text="⚫ OFFLINE", font=("Consolas", 12, "bold"), 
                                     bootstyle="secondary-inverse")
        self.status_lbl.pack()

        # Build tabs
        self._build_dashboard_tab()
        self._build_analytics_tab()

    def _build_dashboard_tab(self):
        # KPI Cards
        kpi_frame = ttk.Frame(self.tab_dashboard)
        kpi_frame.pack(fill=X, pady=(0, 20))
        
        self.card_total_power = self._create_kpi_card(kpi_frame, "⚡ Total Load", "0 W", "warning")
        self.card_total_cost = self._create_kpi_card(kpi_frame, "💰 Session Cost", "₹0.00", "success")
        self.card_efficiency = self._create_kpi_card(kpi_frame, "📈 Efficiency", "100%", "info")
        self.card_surges = self._create_kpi_card(kpi_frame, "⚠️ Surge Events", "0", "danger")

        # Scrollable appliances
        scroll_container = ScrolledFrame(self.tab_dashboard, autohide=True)
        scroll_container.pack(fill=BOTH, expand=True)
        
        self.appliance_frame = scroll_container
        
        row, col = 0, 0
        for app in APPLIANCES_CONFIG:
            self._create_appliance_widget(self.appliance_frame, app, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1

    def _create_kpi_card(self, parent, title, value, color):
        frame = ttk.Frame(parent, bootstyle=f"{color}", padding=2)
        frame.pack(side=LEFT, fill=BOTH, expand=True, padx=5)
        
        inner = ttk.Frame(frame, bootstyle="dark", padding=15)
        inner.pack(fill=BOTH, expand=True)
        
        ttk.Label(inner, text=title, bootstyle="secondary", font=("Helvetica", 10)).pack(anchor=NW)
        val_lbl = ttk.Label(inner, text=value, bootstyle=f"inverse-{color}", 
                            font=("Helvetica", 20, "bold"))
        val_lbl.pack(anchor=W, pady=(5, 0))
        return val_lbl

    def _create_appliance_widget(self, parent, name, row, col):
        cfg = APPLIANCES_CONFIG[name]
        frame = ttk.Labelframe(parent, text=f" {cfg['icon']} {name} ", padding=15, bootstyle="info")
        frame.grid(row=row, column=col, sticky="nsew", padx=10, pady=10)
        parent.columnconfigure(col, weight=1)

        # Meter
        meter = ttk.Meter(
            master=frame,
            metersize=180,
            amountused=0,
            metertype="semi",
            subtext="Watts",
            interactive=False,
            bootstyle="success",
            stripethickness=10,
            amounttotal=cfg['range'][1] * 1.5
        )
        meter.pack(side=TOP, pady=5)
        self.meters[name] = meter

        # Stats
        stats_frame = ttk.Frame(frame)
        stats_frame.pack(fill=X, pady=8)
        
        lbl_kwh = ttk.Label(stats_frame, text="0.000 kWh", font=("Consolas", 10))
        lbl_kwh.pack(side=LEFT)
        
        lbl_cost = ttk.Label(stats_frame, text="₹0.00", font=("Consolas", 10, "bold"), 
                             bootstyle="warning")
        lbl_cost.pack(side=RIGHT)
        
        status_lbl = ttk.Label(frame, text="● Standby", font=("Helvetica", 9), anchor=CENTER)
        status_lbl.pack(fill=X)

        self.stat_labels[name] = {
            "kwh": lbl_kwh,
            "cost": lbl_cost,
            "status": status_lbl
        }

    def _build_analytics_tab(self):
        paned = ttk.Panedwindow(self.tab_analytics, orient=HORIZONTAL)
        paned.pack(fill=BOTH, expand=True)

        # AI Chat
        chat_frame = ttk.Labelframe(paned, text=" 🤖 AI Energy Consultant ", padding=15)
        paned.add(chat_frame, weight=1)

        self.chat_history = ttk.Text(chat_frame, height=20, width=45, font=("Segoe UI", 10), 
                                      wrap=WORD, state=DISABLED)
        self.chat_history.pack(fill=BOTH, expand=True, pady=(0, 10))
        
        # Quick action buttons
        quick_frame = ttk.Frame(chat_frame)
        quick_frame.pack(fill=X, pady=(0, 10))
        ttk.Button(quick_frame, text="💡 Insights", command=self.quick_insights, 
                   bootstyle="info-outline").pack(side=LEFT, padx=2)
        ttk.Button(quick_frame, text="💰 Save Money", 
                   command=lambda: self.send_to_ai_direct("How can I reduce costs?"), 
                   bootstyle="success-outline").pack(side=LEFT, padx=2)
        ttk.Button(quick_frame, text="⚠️ Surges", 
                   command=lambda: self.send_to_ai_direct("Explain the surge events"), 
                   bootstyle="warning-outline").pack(side=LEFT, padx=2)
        
        input_frame = ttk.Frame(chat_frame)
        input_frame.pack(fill=X)
        self.chat_input = ttk.Entry(input_frame, font=("Segoe UI", 10))
        self.chat_input.pack(side=LEFT, fill=X, expand=True, padx=(0, 5))
        self.chat_input.bind("<Return>", self.send_to_ai)
        
        ttk.Button(input_frame, text="Send", command=self.send_to_ai, 
                   bootstyle="primary").pack(side=RIGHT)

        # Graph
        graph_frame = ttk.Labelframe(paned, text=" 📈 Real-time Power Graph ", padding=15)
        paned.add(graph_frame, weight=2)
        
        self.fig, self.ax = plt.subplots(figsize=(6, 5), dpi=100)
        self.fig.patch.set_facecolor('#222222')
        self.ax.set_facecolor('#222222')
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_frame)
        self.canvas.get_tk_widget().pack(fill=BOTH, expand=True)

    # --- Core Logic ---

    def start_system(self):
        if not self.backend.running:
            self.status_lbl.configure(text="🟢 ONLINE", bootstyle="success-inverse")
            self.backend.start_monitoring(self.schedule_ui_update)
            self.append_chat("System", "✅ Monitoring started. Collecting real-time data...")

    def stop_system(self):
        self.backend.stop_monitoring()
        self.status_lbl.configure(text="🟡 PAUSED", bootstyle="warning-inverse")
        self.append_chat("System", "⏸ Monitoring paused. Session data saved.")

    def schedule_ui_update(self):
        self.after(0, self.update_ui)

    def update_ui(self):
        readings = self.backend.latest_readings
        total_watts = 0
        total_cost = 0
        total_surges = sum(self.backend.surge_count.values())

        for name, data in readings.items():
            self.meters[name].configure(amountused=int(data['power']))
            
            if data['status'] == "⚠️ SURGE":
                self.meters[name].configure(bootstyle="danger")
            elif data['power'] == 0:
                self.meters[name].configure(bootstyle="secondary")
            else:
                self.meters[name].configure(bootstyle="success")

            self.stat_labels[name]['kwh'].configure(text=f"{data['kwh']:.3f} kWh")
            self.stat_labels[name]['cost'].configure(text=f"₹{data['cost']:.2f}")
            self.stat_labels[name]['status'].configure(
                text=f"● {data['status']}", 
                bootstyle="danger" if "SURGE" in data['status'] else "success"
            )

            total_watts += data['power']
            total_cost += data['cost']

        # Update KPIs
        self.card_total_power.configure(text=f"{int(total_watts)} W")
        self.card_total_cost.configure(text=f"₹{total_cost:.2f}")
        self.card_surges.configure(text=str(total_surges))
        
        eff = max(0, 100 - (total_watts / 5000 * 100))
        self.card_efficiency.configure(text=f"{eff:.1f}%")

        self.update_graph()

    def update_graph(self):
        self.ax.clear()
        history = self.backend.get_history_data()
        
        colors = {'Fridge': '#3498db', 'AC Unit': '#e74c3c', 'Washing Machine': '#2ecc71',
                  'Smart TV': '#f39c12', 'Microwave': '#9b59b6'}
        
        for name, values in history.items():
            if values and max(values) > 10:
                self.ax.plot(values, label=name, color=colors.get(name, '#ffffff'), linewidth=2)

        self.ax.set_title("Power Consumption Trends", color='white', fontsize=12, fontweight='bold')
        self.ax.set_ylabel("Watts", color='white', fontsize=10)
        self.ax.set_xlabel("Time (ticks)", color='white', fontsize=10)
        self.ax.tick_params(colors='white', labelsize=8)
        self.ax.grid(True, color='#444444', linestyle='--', linewidth=0.5, alpha=0.7)
        self.ax.legend(facecolor='#333333', labelcolor='white', fontsize=9, loc='upper left', 
                       framealpha=0.9)
        
        self.canvas.draw()

    # --- AI Functions ---

    def append_chat(self, sender, message):
        self.chat_history.configure(state=NORMAL)
        timestamp = datetime.now().strftime("%H:%M")
        
        if sender == "You":
            tag, color = "user", "#00bc8c"
        elif sender == "System":
            tag, color = "system", "#f39c12"
        else:
            tag, color = "ai", "#3498db"
        
        self.chat_history.tag_config(tag, foreground=color, font=("Segoe UI", 10, "bold"))
        self.chat_history.insert(END, f"[{timestamp}] {sender}: ", tag)
        self.chat_history.insert(END, f"{message}\n\n")
        self.chat_history.see(END)
        self.chat_history.configure(state=DISABLED)

    def send_to_ai(self, event=None):
        user_text = self.chat_input.get().strip()
        if not user_text: 
            return
        
        self.append_chat("You", user_text)
        self.chat_input.delete(0, END)
        threading.Thread(target=self._fetch_ai_response, args=(user_text,), daemon=True).start()

    def send_to_ai_direct(self, prompt):
        """Send predefined prompt to AI"""
        self.append_chat("You", prompt)
        threading.Thread(target=self._fetch_ai_response, args=(prompt,), daemon=True).start()

    def quick_insights(self):
        """Quick insights button"""
        if not self.backend.running and sum(r['cost'] for r in self.backend.latest_readings.values()) == 0:
            self.append_chat("System", "⚠️ Start monitoring first to get insights!")
            return
        
        prompt = "Provide key insights and recommendations based on current data"
        self.send_to_ai_direct(prompt)

    def _fetch_ai_response(self, user_prompt):
        # Build comprehensive context
        summary = self.backend.get_insights_summary()
        
        full_prompt = f"{summary}\n\nUser Question: {user_prompt}"
        
        response = self.ai.ask(full_prompt)
        self.after(0, lambda: self.append_chat("WattFinder AI", response))

    def on_close(self):
        self.backend.stop_monitoring()
        self.destroy()

if __name__ == "__main__":
    app = DashboardApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()