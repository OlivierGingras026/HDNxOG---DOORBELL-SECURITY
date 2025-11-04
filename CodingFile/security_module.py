# security_module.py
import json
import time
import random
import os
import threading
from datetime import datetime
from pathlib import Path
import logging

import cv2
from picamera2 import Picamera2

import RPi.GPIO as GPIO

from ultrasonic_module import UltrasonicModule

logger = logging.getLogger("domisafe.security")


class security_module:
    """
    Security using ultrasonic instead of PIR.

    - if distance <= DIST_THRESHOLD_CM → motion_detected = True
    - LED on BCM 21 blinks fast while alert is active
    - BUZZER on BCM 18 goes bip...bip...bip while alert is active
    - photo is rate-limited (every 10s max)
    - still returns motion/smoke so main.py can send to Adafruit
    """

    DIST_THRESHOLD_CM = 10.0
    CAPTURE_COOLDOWN_SEC = 10

    ALERT_LED_PIN = 21     # red LED
    BUZZER_PIN = 18        # your working buzzer pin

    def __init__(self, config_file="config.json"):
        self.config = self.load_config(config_file)

        # ultrasonic
        self.ultra = UltrasonicModule()

        # camera
        self.picam2 = Picamera2()
        self.picam2.start()
        self.image_dir = "/home/olivier/LabsAndFinalProject/FinalProject/captured_images"
        os.makedirs(self.image_dir, exist_ok=True)

        # LCD can be injected from main
        self.lcd = None

        # photo cooldown
        self.last_capture_ts = 0

        # GPIO setup
        GPIO.setmode(GPIO.BCM)

        # LED
        GPIO.setup(self.ALERT_LED_PIN, GPIO.OUT)
        GPIO.output(self.ALERT_LED_PIN, GPIO.LOW)

        # BUZZER
        GPIO.setup(self.BUZZER_PIN, GPIO.OUT)
        GPIO.output(self.BUZZER_PIN, GPIO.LOW)

        # alert state
        self.alert_active = False

        # threads
        self.blink_thread = None
        self.blink_lock = threading.Lock()

        self.buzzer_thread = None
        self.buzzer_lock = threading.Lock()


    def set_lcd(self, lcd):
        self.lcd = lcd


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
                cfg = json.load(f)
                return {**default_config, **cfg}
        except FileNotFoundError:
            logger.warning(f"Config file {config_file} not found, using defaults")
            return default_config


    # LED BLINKER
    def _start_blinker_if_needed(self):
        with self.blink_lock:
            if self.blink_thread is None or not self.blink_thread.is_alive():
                t = threading.Thread(target=self._blink_loop, daemon=True)
                self.blink_thread = t
                t.start()

    def _blink_loop(self):
        while self.alert_active:
            GPIO.output(self.ALERT_LED_PIN, GPIO.HIGH)
            time.sleep(0.15)
            GPIO.output(self.ALERT_LED_PIN, GPIO.LOW)
            time.sleep(0.15)
        GPIO.output(self.ALERT_LED_PIN, GPIO.LOW)


    # BUZZER BEEPER
    def _start_buzzer_if_needed(self):
        with self.buzzer_lock:
            if self.buzzer_thread is None or not self.buzzer_thread.is_alive():
                t = threading.Thread(target=self._buzzer_loop, daemon=True)
                self.buzzer_thread = t
                t.start()

    def _buzzer_loop(self):
        """
        Make a non-continuous beep:
        ON 0.15s → OFF 0.5s → repeat
        while alert is active.
        """
        while self.alert_active:
            GPIO.output(self.BUZZER_PIN, GPIO.HIGH)   # beep
            time.sleep(0.15)
            GPIO.output(self.BUZZER_PIN, GPIO.LOW)    # silence
            time.sleep(0.5)
        # make sure it's off when alert stops
        GPIO.output(self.BUZZER_PIN, GPIO.LOW)

    # -------------------------------------------------
    def get_security_data(self):
        """
        Called frequently by main (now ~0.2s).
        We detect 'motion' with the ultrasonic sensor, fast.
        """
        smoke_detected = random.random() < 0.001


        distances = []
        for _ in range(3):
            d = self.ultra.get_distance_cm()
            if d is not None:
                distances.append(d)
            # super short pause to let echo settle
            time.sleep(0.01)

        # Trigger if ANY quick sample is closer than threshold
        motion_detected = any((d <= self.DIST_THRESHOLD_CM) for d in distances)

        image_path = None
        now = time.time()

        if motion_detected:
            # turn ON alert (LED + buzzer threads will run)
            self.alert_active = True
            self._start_blinker_if_needed()
            self._start_buzzer_if_needed()

            # photo (rate-limited)
            if (
                self.config.get("camera_enabled", True)
                and (now - self.last_capture_ts) >= self.CAPTURE_COOLDOWN_SEC
            ):
                image_path = self.capture_image()
                self.last_capture_ts = now
                if self.lcd is not None:
                    try:
                        self.lcd.show_message_for_2s("Security issue", "Photo taken")
                    except Exception:
                        pass

            logger.info("Ultrasonic alert: object too close.")
        else:
            # clear alert (loops will observe this almost immediately)
            self.alert_active = False

        # report last distance we saw (or None)
        dist = distances[-1] if distances else None

        return {
            "timestamp": datetime.now().isoformat(),
            "motion_detected": motion_detected,
            "smoke_detected": smoke_detected,
            "image_path": image_path,
            "distance_cm": dist,
        }

    # -------------------------------------------------
    def capture_image(self):
        try:
            frame = self.picam2.capture_array()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_path = f"{self.image_dir}/intruder_{ts}.jpg"
            cv2.imwrite(image_path, frame)
            logger.info(f"Image captured: {image_path}")
            return image_path
        except Exception as e:
            logger.warning(f"Camera capture failed: {e}")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_path = f"{self.image_dir}/intruder_{ts}.txt"
        with open(image_path, "w") as f:
            f.write(f"Security photo placeholder at {datetime.now().isoformat()}")
        return image_path
