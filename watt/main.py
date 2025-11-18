import tkinter as tk
import ttkbootstrap as ttk
from tkinter import messagebox
import threading
import time
import datetime
from database import init_db, save_data_to_db
from power_consumption import simulate_power_reading
from energy_calculation import calculate_metrics
from ai_assistant import get_ai_response
from mqtt_handler import setup_mqtt

class WattFinderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("WattFinder: Electricity Assistant")
        self.root.geometry("1600x900")
        self.root.configure(bg="#1E3A8A")
        
        # Setup MQTT
        self.mqtt_client = setup_mqtt()

        # Initialize the database
        init_db()

        # GUI Setup
        self.main_frame = ttk.Frame(self.root, padding=10)
        self.main_frame.grid(row=0, column=0, sticky="nsew")
        
        self.create_widgets()
        self.run_mqtt()

    def create_widgets(self):
        # Creating the header
        header = ttk.Label(self.main_frame, text="WattFinder Dashboard", font=("Helvetica", 24, "bold"))
        header.grid(row=0, column=0, pady=20)

        # Create buttons for appliances
        self.appliance_buttons_frame = ttk.Frame(self.main_frame)
        self.appliance_buttons_frame.grid(row=1, column=0, pady=20)
        
        self.appliance_buttons = {}
        for idx, appliance in enumerate(["Fridge", "Air Conditioner", "Washing Machine", "Television", "Microwave"]):
            button = ttk.Button(self.appliance_buttons_frame, text=appliance, command=lambda app=appliance: self.toggle_appliance(app))
            button.grid(row=idx, column=0, padx=5, pady=5, sticky="ew")
            self.appliance_buttons[appliance] = button
        
        # Text area for AI assistant
        self.chatbox = tk.Text(self.main_frame, width=60, height=15, wrap="word", bd=0, font=("Helvetica", 12))
        self.chatbox.grid(row=2, column=0, pady=20)

        # Input area for chat
        self.chat_input = ttk.Entry(self.main_frame, font=("Helvetica", 12))
        self.chat_input.grid(row=3, column=0, pady=5, sticky="ew")
        self.chat_input.bind("<Return>", self.send_chat_message)

    def toggle_appliance(self, appliance):
        # Simulate power reading for the appliance
        power, anomaly = simulate_power_reading(appliance)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        kwh, cost = calculate_metrics(power)
        anomaly_text = "Surge Detected" if anomaly else "Normal"
        save_data_to_db(appliance, timestamp, power, kwh, cost, anomaly_text)
        self.update_ai_response(f"Appliance {appliance} status: {anomaly_text}, Power used: {power:.2f}W")

    def send_chat_message(self, event=None):
        message = self.chat_input.get().strip()
        if message:
            self.update_ai_response(f"You: {message}")
            ai_response = get_ai_response(message)
            self.update_ai_response(f"AI: {ai_response}")

    def update_ai_response(self, response):
        self.chatbox.config(state="normal")
        self.chatbox.insert(tk.END, response + "\n")
        self.chatbox.config(state="disabled")
        self.chatbox.yview(tk.END)

    def run_mqtt(self):
        def mqtt_loop():
            self.mqtt_client.loop_start()
        threading.Thread(target=mqtt_loop, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = WattFinderApp(root)
    root.mainloop()
