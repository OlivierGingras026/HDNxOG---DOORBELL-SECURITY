# ultrasonic_module.py
import time
import logging
import RPi.GPIO as GPIO

logger = logging.getLogger("domisafe.ultrasonic")

# BCM pin numbers
TRIG_PIN = 5    # GPIO5
ECHO_PIN = 12   # GPIO12

class UltrasonicModule:
    def __init__(self):
        # make sure we use BCM
        GPIO.setmode(GPIO.BCM)

        GPIO.setup(TRIG_PIN, GPIO.OUT)
        GPIO.setup(ECHO_PIN, GPIO.IN)

        # TRIG low to start
        GPIO.output(TRIG_PIN, False)
        time.sleep(0.2)

    def get_distance_cm(self):
        # 1) send 10 µs pulse
        GPIO.output(TRIG_PIN, True)
        time.sleep(0.00001)
        GPIO.output(TRIG_PIN, False)

        # 2) wait for echo HIGH
        start = None
        timeout = time.time() + 0.04  # 40 ms
        while GPIO.input(ECHO_PIN) == 0 and time.time() < timeout:
            start = time.time()

        if start is None:
            logger.debug("ultrasonic: timeout waiting for echo HIGH")
            return None

        # 3) wait for echo LOW
        stop = None
        timeout = time.time() + 0.04
        while GPIO.input(ECHO_PIN) == 1 and time.time() < timeout:
            stop = time.time()

        if stop is None:
            logger.debug("ultrasonic: timeout waiting for echo LOW")
            return None

        elapsed = stop - start
        # speed of sound ~34300 cm/s
        distance_cm = (elapsed * 34300) / 2.0
        return round(distance_cm, 1)
