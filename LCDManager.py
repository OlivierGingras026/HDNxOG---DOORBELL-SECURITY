# LCDManager.py
import time
import threading
from RPLCD.i2c import CharLCD


class LCDManager:
    def __init__(self, env_module=None, refresh_secs=5):
        self.env_module = env_module
        self.refresh_secs = refresh_secs

        # init lcd
        self.lcd, self.addr = self._make_lcd()
        self.lock = threading.Lock()

        # state
        self.override_text = None
        self.override_until = 0
        self.consecutive_errors = 0
        self.max_errors = 3
        self.alive = True

        # welcome
        self._safe_clear()
        self._safe_write("Welcome to")
        self._safe_set_cursor(1, 0)
        self._safe_write("HDNxOG 😎")
        time.sleep(2)
        self._safe_clear()

        # background thread
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    # -------------------------------------------------
    # init helpers
    # -------------------------------------------------
    def _make_lcd(self, possible_addresses=(0x27, 0x3f)):
        last_err = None
        for addr in possible_addresses:
            try:
                lcd = CharLCD(
                    i2c_expander='PCF8574',
                    address=addr,
                    port=1,
                    cols=16,
                    rows=2,
                    charmap='A00',
                    auto_linebreaks=True
                )
                return lcd, addr
            except Exception as e:
                last_err = e
        raise last_err

    # -------------------------------------------------
    # safe wrappers
    # -------------------------------------------------
    def _record_ok(self):
        self.consecutive_errors = 0
        self.alive = True

    def _record_error(self):
        self.consecutive_errors += 1
        if self.consecutive_errors >= self.max_errors:
            # mark as dead, background loop will try to re-init later
            self.alive = False

    def _safe_clear(self):
        if not self.alive:
            return
        try:
            self.lcd.clear()
            self._record_ok()
        except OSError:
            self._record_error()

    def _safe_write(self, text: str):
        if not self.alive:
            return
        try:
            self.lcd.write_string(text)
            self._record_ok()
        except OSError:
            self._record_error()

    def _safe_set_cursor(self, row: int, col: int):
        if not self.alive:
            return
        try:
            self.lcd.cursor_pos = (row, col)
            self._record_ok()
        except OSError:
            self._record_error()

    # -------------------------------------------------
    def _loop(self):
        """Background loop: update screen every N seconds"""
        while self.running:
            with self.lock:
                if not self.alive:
                    # try to re-init LCD once in a while
                    try:
                        self.lcd, self.addr = self._make_lcd()
                        self.alive = True
                        self.consecutive_errors = 0
                        self._safe_clear()
                        self._safe_write("LCD recovered")
                        self._safe_set_cursor(1, 0)
                        self._safe_write("DomiSafe")
                    except Exception:
                        pass
                else:
                    now = time.time()
                    if self.override_text and now < self.override_until:
                        pass
                    else:
                        self._show_temperature()
            time.sleep(self.refresh_secs)

    def _show_temperature(self):
        self._safe_clear()
        self._safe_write("DomiSafe Ready")
        self._safe_set_cursor(1, 0)

        if self.env_module:
            try:
                env = self.env_module.get_environmental_data()
                temp = env.get("temperature", "N/A")
                hum = env.get("humidity", "N/A")


                line2 = f"T:{temp}C H:{hum}%"
                self._safe_write(line2[:16])
            except Exception:
                self._safe_write("T: N/A")
        else:
            self._safe_write("T: --.-C")

    def show_message_for_2s(self, msg: str, msg2: str = ""):
        """Show a message briefly. If LCD glitches once, don’t kill the app."""
        with self.lock:
            if not self.alive:
                return
            self._safe_clear()
            self._safe_write(msg[:16])
            if msg2:
                self._safe_set_cursor(1, 0)
                self._safe_write(msg2[:16])
            self.override_text = msg
            self.override_until = time.time() + 2

    def stop(self):
        self.running = False
        self.thread.join(timeout=2)
        if self.alive:
            try:
                self.lcd.clear()
            except OSError:
                pass
