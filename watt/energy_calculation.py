COST_PER_KWH = 7.5

def calculate_metrics(power, duration_hours=1/60):
    kwh = power * duration_hours / 1000  #
    cost = kwh * COST_PER_KWH  
    return kwh, cost
