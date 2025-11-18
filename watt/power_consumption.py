import random
from datetime import datetime

APPLIANCES = {
    "Fridge": {"power_range": (100, 200), "surge_prob": 0.05, "surge_factor": 2.5},
    "Air Conditioner": {"power_range": (800, 1500), "surge_prob": 0.02, "surge_factor": 1.8},
    "Washing Machine": {"power_range": (500, 1000), "surge_prob": 0.03, "surge_factor": 2.0},
    "Television": {"power_range": (50, 150), "surge_prob": 0.01, "surge_factor": 1.5},
    "Microwave": {"power_range": (600, 1200), "surge_prob": 0.04, "surge_factor": 1.7}
}

def simulate_power_reading(appliance, hour=None):
    if hour is None:
        hour = datetime.now().hour
    power_range = APPLIANCES[appliance]["power_range"]
    surge_prob = APPLIANCES[appliance]["surge_prob"]
    surge_factor = APPLIANCES[appliance]["surge_factor"]
    power = random.uniform(power_range[0], power_range[1])
    if random.random() < surge_prob:
        power *= surge_factor
        return power, True  # Surge detected
    return power, False  # No surge

