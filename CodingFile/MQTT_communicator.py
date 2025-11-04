
import json
import time
import random
import math
from datetime import datetime, timedelta
from pathlib import Path
import logging
import os
import paho.mqtt.client as mqtt


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MQTT_communicator:
    def __init__(self, config_file='config.json'):
        self.config = self.load_config(config_file)
        self.mqtt_client = None
        self.mqtt_connected = False
        self.setup_mqtt()

    def load_config(self, config_file):
        """Load configuration from JSON file"""
        default_config = {
            "ADAFRUIT_IO_USERNAME": "username",
            "ADAFRUIT_IO_KEY": "userkey",
            "MQTT_BROKER": "io.adafruit.com",
            "MQTT_PORT": 1883,
            "MQTT_KEEPALIVE": 60,
            "devices": ["living_room_light", "bedroom_fan", "front_door", "garage_door"],
            "camera_enabled": True,
            "capturing_interval": 900,
            "flushing_interval": 10,
            "sync_interval": 300
        }

        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
                return {**default_config, **config}
        except FileNotFoundError:
            logger.warning(f"Config file {config_file} not found, using defaults")
            return default_config

    def setup_mqtt(self):
        """Setup MQTT client for Adafruit IO"""
        try:
            self.mqtt_client = mqtt.Client()
            self.mqtt_client.username_pw_set(
                self.config["ADAFRUIT_IO_USERNAME"],
                self.config["ADAFRUIT_IO_KEY"]
            )

            self.mqtt_client.on_connect = self.on_mqtt_connect
            self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
            self.mqtt_client.on_publish = self.on_mqtt_publish


            self.mqtt_client.connect(
                self.config["MQTT_BROKER"],
                self.config["MQTT_PORT"],
                self.config["MQTT_KEEPALIVE"]
            )


            self.mqtt_client.loop_start()
            logger.info("MQTT client setup completed")

        except Exception as e:
            logger.error(f"Failed to setup MQTT client: {e}")
            self.mqtt_connected = False

    def on_mqtt_connect(self, client, userdata, flags, rc):
        """Callback for when MQTT client connects"""
        if rc == 0:
            self.mqtt_connected = True
            logger.info("Connected to MQTT broker")
        else:
            self.mqtt_connected = False
            logger.error(f"Failed to connect to MQTT broker, return code {rc}")

    def on_mqtt_disconnect(self, client, userdata, rc):
        """Callback for when MQTT client disconnects"""
        self.mqtt_connected = False
        logger.warning("Disconnected from MQTT broker")

    def on_mqtt_publish(self, client, userdata, mid):
        """Callback for when message is published"""
        logger.debug(f"Message {mid} published successfully")

    # Send data to Adafruit IO
    def send_to_adafruit_io(self, feed_name, value):
        if not self.mqtt_connected or not self.mqtt_client:
            logger.warning("MQTT client not connected")
            return False

        try:   # send data to Adafruit using MQTT

            topic = f"{self.config['ADAFRUIT_IO_USERNAME']}/feeds/{feed_name}"
            result, mid = self.mqtt_client.publish(topic, str(value))
            if result == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Published {value} to {topic}")
                return True
            else:
                logger.error(f"Failed to publish {value} to {topic}, result={result}")
                return False

        except Exception as e:
            logger.error(f"Error publishing to MQTT: {e}")
            return False
