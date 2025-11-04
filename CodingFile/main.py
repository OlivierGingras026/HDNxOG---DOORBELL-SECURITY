#!/usr/bin/env python3
import time
import os
import json
import threading
import logging
import random
from pathlib import Path
import RPi.GPIO as GPIO

from LCDManager import LCDManager

# LOGGING SETUP
def setup_logging():
    """
    - everything → logs/domisafe.log (INFO+)
    - console → CRITICAL only (so CLI stays clean)
    """
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    log_file = logs_dir / "domisafe.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # file handler
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    root.addHandler(fh)

    # console handler → ONLY CRITICAL
    ch = logging.StreamHandler()
    ch.setLevel(logging.CRITICAL)
    ch.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
    root.addHandler(ch)

    return root


logger = logging.getLogger(__name__)


def init_gpio():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)



# MAIN
if __name__ == "__main__":
    # 1) logging first
    setup_logging()

    # 2) import noisy stuff after logging
    from MQTT_communicator import MQTT_communicator
    from environmental_module import environmental_module
    from security_module import security_module
    from device_controle_module import device_controle_module

    # cloud feeds
    ENV_FEEDS = {
        "temperature": "temperature",
        "humidity": "humidity",
        "pressure": "pressure"
    }

    SECURITY_FEEDS = {
        "motion_count": "motion_feed",
        "smoke_count": "smoke_feed",
    }



    class DomiSafeApp:
        def __init__(self, config_file='config.json'):
            self.config = self.load_config(config_file)

            self.security_check_interval = 1
            self.security_send_interval = 30
            self.env_interval = 30

            self.running = True

            self.mqtt_agent = MQTT_communicator(config_file)
            self.env_data = environmental_module(config_file)
            self.security_data = security_module(config_file)
            self.device_controle = device_controle_module(config_file)

            self.heartbeat_interval = 30
            self.last_heartbeat = 0
            self.online_feed = "online_status"

        def load_config(self, config_file):
            default_config = {
                "ADAFRUIT_IO_USERNAME": "username",
                "ADAFRUIT_IO_KEY": "userkey",
                "MQTT_BROKER": "io.adafruit.com",
                "MQTT_PORT": 1883,
                "MQTT_KEEPALIVE": 60,
                "flushing_interval": 10,
            }
            try:
                with open(config_file, 'r') as f:
                    cfg = json.load(f)
                    return {**default_config, **cfg}
            except FileNotFoundError:
                logger.warning(f"Config file {config_file} not found, using defaults")
                return default_config

        def send_to_cloud(self, data, feeds):
            ok = True
            ts = data.get("timestamp")
            logger.info(f"Processing reading from {ts}")

            for field, feed_key in feeds.items():
                if field not in data:
                    continue
                value = data[field]
                sent = self.mqtt_agent.send_to_adafruit_io(feed_key, value)
                if not sent:
                    logger.warning(f"Failed to send {field}={value} to {feed_key}")
                    ok = False
                time.sleep(0.5)
            return ok

        def collect_environmental_data(self, current_time, timers, file_handle):
            if current_time - timers["env_check"] >= self.env_interval:
                env_data = self.env_data.get_environmental_data()
                file_handle.write(json.dumps(env_data) + "\n")

                if self.send_to_cloud(env_data, ENV_FEEDS):
                    logger.info("Environmental data sent to cloud")
                else:
                    logger.info("Offline, env data saved locally. Will sync later.")
                logger.info(f"Environmental data: {env_data}")

                timers["env_check"] = current_time

        def collect_security_data(self, current_time, timers, security_counts, file_handle):
            if current_time - timers["security_check"] >= self.security_check_interval:
                sec_data = self.security_data.get_security_data()

            if sec_data.get("motion_detected"):
                security_counts["motion"] += 1
                # IMMEDIATE publish of cumulative count so dashboard updates right away
                self.mqtt_agent.send_to_adafruit_io("motion_feed", security_counts["motion"])
                logger.info(f"Motion detected! Total: {security_counts['motion']}")

            if sec_data.get("smoke_detected"):
                security_counts["smoke"] += 1
                self.mqtt_agent.send_to_adafruit_io("smoke_feed", security_counts["smoke"])
                logger.info(f"Smoke detected! Total: {security_counts['smoke']}")

            if sec_data.get("motion_detected") or sec_data.get("smoke_detected"):
                file_handle.write(json.dumps(sec_data) + "\n")

            timers["security_check"] = current_time

            if current_time - timers["security_send"] >= self.security_send_interval:
                summary = {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "motion_count": security_counts["motion"],
                    "smoke_count": security_counts["smoke"],
                }

                if self.send_to_cloud(summary, SECURITY_FEEDS):
                    logger.info(
                        f"Security summary sent: {security_counts['motion']} motion, {security_counts['smoke']} smoke"
                    )
                else:
                    logger.warning("Failed to send security summary")

                security_counts["motion"] = 0
                security_counts["smoke"] = 0
                timers["security_send"] = current_time

        def data_collection_loop(self):
            timestamp = time.strftime("%Y%m%d")
            env_file = os.path.abspath(f"{timestamp}_environmental_data.txt")
            sec_file = os.path.abspath(f"{timestamp}_security_data.txt")
            dev_file = os.path.abspath(f"{timestamp}_device_status.txt")

            logger.info(
                "Writing to:\n"
                f"  {env_file}\n"
                f"  {sec_file}\n"
                f"  {dev_file}"
            )

            with open(env_file, "a", buffering=1) as f_env, \
                    open(sec_file, "a", buffering=1) as f_sec, \
                    open(dev_file, "a", buffering=1) as f_dev:

                last_fsync = time.time()

                timers = {
                    "env_check": 0,
                    "security_check": 0,
                    "security_send": 0,
                }

                security_counts = {"motion": 0, "smoke": 0}

                while self.running:
                    try:
                        now = time.time()

                        self.collect_security_data(now, timers, security_counts, f_sec)
                        self.collect_environmental_data(now, timers, f_env)

                        flush_interval = self.config.get("flushing_interval", 10)
                        if now - last_fsync > flush_interval:
                            for fh in (f_env, f_sec, f_dev):
                                fh.flush()
                                os.fsync(fh.fileno())
                            last_fsync = now
                        # --- heartbeat every N seconds ---
                        if now - self.last_heartbeat >= self.heartbeat_interval:
                            # publish a simple heartbeat value; epoch time is handy
                            self.mqtt_agent.send_to_adafruit_io("heartbeat", int(now))
                            # optional explicit status (lets you use a green/red Indicator block)
                            self.mqtt_agent.send_to_adafruit_io(self.online_feed, 1)
                            self.last_heartbeat = now
                        # ---------------------------------

                        time.sleep(self.security_check_interval)

                    except Exception as e:
                        logger.error(f"Error in data collection loop: {e}", exc_info=True)
                        time.sleep(5)

        def start_background(self):
            t = threading.Thread(target=self.data_collection_loop, daemon=True)
            t.start()
            return t



    DEVICES = {
        "led1": {"pin": 16, "name": "Yellow Led", "state": False, "active_low": False},
        "led2": {"pin": 23, "name": "Red Led", "state": False, "active_low": False},
        "led3": {"pin": 24, "name": "Green Led", "state": False, "active_low": False},
        "fan": {"pin": 22, "name": "Fan", "state": False, "active_low": False},
        "relay": {"pin": 17, "name": "Relay", "state": False, "active_low": True},
    }

    party_mode_active = False
    party_thread = None


    def _write_device(device: dict, on: bool):
        if device["active_low"]:
            GPIO.output(device["pin"], GPIO.LOW if on else GPIO.HIGH)
        else:
            GPIO.output(device["pin"], GPIO.HIGH if on else GPIO.LOW)


    def gpio_init_all():
        init_gpio()
        for dev in DEVICES.values():
            GPIO.setup(dev["pin"], GPIO.OUT)
            _write_device(dev, False)


    def show_menu():
        print("\n/////////////////////////////")
        print("Raspberry Pi Device Control")
        print("/////////////////////////////\n")
        for idx, key in enumerate(DEVICES.keys(), start=1):
            d = DEVICES[key]
            print(f"{idx}. {d['name']} - [{'ON' if d['state'] else 'OFF'}]")
        print("p. Party mode")
        print("q. Quit")
        print("/////////////////////////////\n")


    def toggle_device(device_id: str, lcd=None):
        dev = DEVICES[device_id]
        dev["state"] = not dev["state"]
        _write_device(dev, dev["state"])

        msg = f"{dev['name']} {'ON' if dev['state'] else 'OFF'}"
        print(f"✓ {msg}")

        if lcd and device_id in ("fan", "relay"):
            try:
                lcd.alive = False
                lcd.consecutive_errors = lcd.max_errors
            except Exception:
                pass
            return


        if lcd:
            try:
                lcd.show_message_for_2s(msg)
            except Exception:
                pass


    def party_mode():
        global party_mode_active
        led_devices = ["led1", "led2", "led3"]

        while party_mode_active:
            random.shuffle(led_devices)

            for led_key in led_devices:
                if not party_mode_active:
                    break
                DEVICES[led_key]["state"] = True
                _write_device(DEVICES[led_key], True)
                time.sleep(0.12)
                DEVICES[led_key]["state"] = False
                _write_device(DEVICES[led_key], False)

            if party_mode_active and random.random() < 0.35:
                pair = random.sample(led_devices, 2)
                for k in pair:
                    DEVICES[k]["state"] = True
                    _write_device(DEVICES[k], True)
                time.sleep(0.1)
                for k in pair:
                    DEVICES[k]["state"] = False
                    _write_device(DEVICES[k], False)

        for led_key in led_devices:
            DEVICES[led_key]["state"] = False
            _write_device(DEVICES[led_key], False)


    def toggle_party_mode(lcd=None):
        global party_mode_active, party_thread
        if party_mode_active:
            party_mode_active = False
            if party_thread:
                party_thread.join()
            if lcd:
                lcd.show_message_for_2s("Party OFF")
        else:
            party_mode_active = True
            party_thread = threading.Thread(target=party_mode, daemon=True)
            party_thread.start()
            if lcd:
                lcd.show_message_for_2s("Party ON")


    def cli_loop(lcd):
        device_keys = list(DEVICES.keys())
        try:
            while True:
                show_menu()
                choice = input("Enter command: ").strip().lower()
                if choice == "q":
                    break
                elif choice == "p":
                    toggle_party_mode(lcd)
                elif choice.isdigit() and 1 <= int(choice) <= len(device_keys):
                    dev_key = device_keys[int(choice) - 1]
                    toggle_device(dev_key, lcd)
                else:
                    print("❌ Invalid command!")
                time.sleep(0.3)
        except KeyboardInterrupt:
            pass
        finally:
            lcd.stop()
            print("Bye.")


    # run it
    app = DomiSafeApp(config_file="./config.json")
    data_thread = app.start_background()

    app.mqtt_agent.send_to_adafruit_io("online_status", 1)

    gpio_init_all()
    lcd = LCDManager(env_module=app.env_data, refresh_secs=5)

    if hasattr(app.security_data, "set_lcd"):
        app.security_data.set_lcd(lcd)

    try:
        cli_loop(lcd)
    finally:
        app.running = False
        data_thread.join(timeout=5)

        GPIO.cleanup()

        app.mqtt_agent.send_to_adafruit_io("online_status", 0)
