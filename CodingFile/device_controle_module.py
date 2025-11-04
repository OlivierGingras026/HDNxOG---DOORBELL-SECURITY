
import json
import time
import random
import math
from datetime import datetime, timedelta
from pathlib import Path
import logging
import os


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class device_controle_module:
    def __init__(self, config_file='config.json'):
        self.config = self.load_config(config_file)

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


    def generate_device_status(self):
        """Generate device status data based on last known state """
        device_data = []

        for device in self.config['devices']:
            status = 'off'  # default off
            device_data.append({
                'timestamp': datetime.now().isoformat(),
                'device_name': device,
                'status': status
            })

        return device_data

    def get_device_status(self):
        """Called on-demand by Flask/Adafruit IO when frontend requests it"""
        try:
            dev_data_list = self.device_conttrol.generate_device_status()

            # Optionally log to file
            with open(device_status_filename, "a", buffering=1) as file3:
                file3.write(json.dumps(dev_data_list) + "\n")

            logger.info(f"Device status requested: {len(dev_data_list)} devices")
            return dev_data_list

        except Exception as e:
            logger.error(f"Error getting device status: {e}", exc_info=True)
            return []
