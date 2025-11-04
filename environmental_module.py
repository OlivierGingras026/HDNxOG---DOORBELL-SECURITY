import json
import time
import random
from datetime import datetime
import logging

import board
import adafruit_dht

# IMPORTANT: no logging.basicConfig() here
logger = logging.getLogger("domisafe.environment")


class environmental_module:
    def __init__(self, config_file="config.json"):
        self.config = self.load_config(config_file)

        try:
            self.dht = adafruit_dht.DHT11(board.D4)
            logger.info("DHT11 initialized on GPIO4")
            time.sleep(2)
        except Exception as e:
            logger.error(f"Failed to init DHT11: {e}")
            self.dht = None


        self.last_temp = None
        self.last_hum = None

    def load_config(self, config_file):
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
            "sync_interval": 300,
        }

        try:
            with open(config_file, "r") as f:
                config = json.load(f)
                return {**default_config, **config}
        except FileNotFoundError:
            logger.warning(f"Config file {config_file} not found, using defaults")
            return default_config

    def get_environmental_data(self):
        """Read DHT (with retries) and return a dict."""
        temperature_c = None
        humidity = None

        if self.dht is None:
            # this is important but we keep it at WARNING
            logger.warning("DHT object not initialized")
        else:
            # try up to 5 times just like before
            for attempt in range(5):
                try:
                    temperature_c = self.dht.temperature
                    humidity = self.dht.humidity

                    if temperature_c is None or humidity is None:
                        raise RuntimeError("DHT returned None")

                    self.last_temp = float(temperature_c)
                    self.last_hum = float(humidity)

                    temp_f = temperature_c * 9 / 5 + 32
                    # this was spamming the console → make it DEBUG
                    logger.debug(
                        f"DHT OK (try {attempt+1}): {temperature_c:.1f}°C ({temp_f:.1f}°F), {humidity:.1f}%"
                    )
                    break
                except RuntimeError as e:
                    # also make retries DEBUG so they don't show in CLI
                    logger.debug(f"DHT read failed (try {attempt+1}/5): {e}")
                    time.sleep(1.0)
                except Exception as e:
                    logger.error(f"Unexpected DHT error: {e}")
                    try:
                        self.dht.exit()
                    except Exception:
                        pass
                    self.dht = None
                    break

        # fake pressure
        pressure = round(1013.25 + random.uniform(-8, 8), 2)

        return {
            "timestamp": datetime.now().isoformat(),
            "temperature": temperature_c,
            "humidity": humidity,
            "pressure": pressure,
        }

