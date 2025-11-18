import paho.mqtt.client as mqtt
import logging

def on_connect(client, userdata, flags, reason_code, properties=None):
    logging.info(f"Connected to MQTT broker with code {reason_code}")

def on_message(client, userdata, msg):
    logging.info(f"Message received: {msg.payload.decode()}")
    # Implement your message handling logic here

def setup_mqtt():
    client = mqtt.Client(client_id="", protocol=mqtt.MQTTv5)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("broker.hivemq.com", 1883, 60)  # Replace with your broker address
    return client
