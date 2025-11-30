from flask import Flask, render_template, jsonify, request
import requests
import json
import datetime as dt
from datetime import timedelta
import pytz
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import os

from db import SessionLocal, init_db
from models import EnvironmentData, MotionEvent


import threading
import time

# -------------------------------------------------------------
# INIT
# -------------------------------------------------------------
app = Flask(__name__)
init_db()

# Try Windows-safe timezone load
try:
    LOCAL_TZ = ZoneInfo("America/Toronto")
except ZoneInfoNotFoundError:
    LOCAL_TZ = pytz.timezone("America/Toronto")

# Default devices if not provided in config.json
DEFAULT_DEVICES = [
    "led1-control",
    "led2-control",
    "led3-control",
    "relay-control",
    "buzzer-control",
]
PROJECT_NAME = "HDNxOG"
# Try to load local config.json (for development on your PC)
CONFIG = {}
try:
    with open("config.json") as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    CONFIG = {}  # no local file → fine, we'll use env vars / defaults

# Adafruit credentials:
#   - first try config.json (local dev)
#   - if missing, fall back to environment variables (Render / production)
USERNAME = CONFIG.get("ADAFRUIT_IO_USERNAME") or os.getenv("ADAFRUIT_IO_USERNAME")
AIO_KEY  = CONFIG.get("ADAFRUIT_IO_KEY")       or os.getenv("ADAFRUIT_IO_KEY")

# Devices list:
#   - use config.json["devices"] if present
#   - otherwise use the default list above
DEVICES = CONFIG.get("devices") or DEFAULT_DEVICES

BASE_URL = f"https://io.adafruit.com/api/v2/{USERNAME}"
HEADERS = {"X-AIO-Key": AIO_KEY}

# Correct feed names from your dashboard
FEED_MAP = {
    "temperature": "temperature",
    "humidity": "humidity",
    "pressure": "pressure",
    "motion": "motion-feed"
}

last_motion_ts = None
last_env_store_ts = None
ENV_STORE_INTERVAL_MIN = 5

motion_active_until = None
current_motion_bucket = None
motion_bucket_count = 0

is_armed = False


# -------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------
def get_latest(feed_key, max_age_minutes=5):
    try:
        url = f"{BASE_URL}/feeds/{feed_key}/data?limit=1"
        r = requests.get(url, headers=HEADERS)
        if r.status_code == 200:
            arr = r.json()
            if not arr:
                return None

            latest = arr[0]
            ts = latest.get("created_at")
            if not ts:
                return latest  # no timestamp, just return

            created = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(LOCAL_TZ)
            age_sec = (dt.datetime.now(LOCAL_TZ) - created).total_seconds()

            if age_sec > max_age_minutes * 60:
                # too old → treat as offline
                return None

            return latest
        return None
    except Exception as e:
        print("get_latest error:", e)
        return None


def get_last_hour_from_feed(feed_key):
    url = f"{BASE_URL}/feeds/{feed_key}/data"
    params = {"limit": 200, "include": "created_at,value"}
    r = requests.get(url, headers=HEADERS, params=params)
    if r.status_code != 200:
        return []

    raw = r.json()
    out = []

    now = dt.datetime.now(LOCAL_TZ)
    one_hour_ago = now - dt.timedelta(hours=1)

    for row in raw:
        ts = row.get("created_at")
        if not ts:
            continue

        dt_utc = dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        dt_local = dt_utc.astimezone(LOCAL_TZ)

        if dt_local < one_hour_ago:
            continue

        try:
            value = float(row["value"])
        except ValueError:
            value = row["value"]

        out.append({
            "time": dt_local.strftime("%H:%M"),
            "value": value
        })

    out.sort(key=lambda x: x["time"])

    # 5-min bucket
    filtered = []
    used = set()

    for p in out:
        minute = int(p["time"].split(":")[1])
        bucket = (minute // 5) * 5
        bucket_key = (p["time"].split(":")[0], bucket)

        if bucket_key not in used:
            filtered.append(p)
            used.add(bucket_key)

    return filtered


def store_environment_snapshot(values):
    global last_env_store_ts
    now = dt.datetime.now(LOCAL_TZ)

    if last_env_store_ts and (now - last_env_store_ts).total_seconds() < ENV_STORE_INTERVAL_MIN * 60:
        return

    last_env_store_ts = now

    db = SessionLocal()
    db.add(EnvironmentData(
        temperature=values["temperature"],
        humidity=values["humidity"],
        pressure=values["pressure"]
    ))
    db.commit()
    db.close()


def store_motion_event(image_path=None):
    global last_motion_ts
    now = dt.datetime.now(LOCAL_TZ)

    if last_motion_ts and (now - last_motion_ts).total_seconds() < 15:
        return

    last_motion_ts = now
    db = SessionLocal()
    db.add(MotionEvent(timestamp=now, image_path=image_path))
    db.commit()
    db.close()


# -------------------------------------------------------------
# ROUTES — HTML PAGES
# -------------------------------------------------------------
@app.route("/")
def home_page():
    return render_template("home.html")


@app.route("/environment")
def environment_page():
    return render_template("environment.html")


@app.route("/security")
def security_page():
    return render_template("security.html")


@app.route("/controls")
def controls_page():
    return render_template("controls.html")

@app.route("/about")
def about_page():
    # Pass datetime for dynamic copyright year in footer
    return render_template("about.html", project_name=PROJECT_NAME, now=dt.datetime.now)


# -------------------------------------------------------------
# LIVE SENSOR API
# -------------------------------------------------------------
@app.route("/api/live/<sensor>")
def api_live(sensor):
    if sensor not in FEED_MAP:
        return jsonify({"error": "invalid sensor"}), 400

    feed_key = FEED_MAP[sensor]
    latest = get_latest(feed_key)
    if latest is None:
        return jsonify({"value": None})

    if sensor in ("temperature", "humidity", "pressure"):
        try:
            store_environment_snapshot({
                "temperature": float(get_latest(FEED_MAP["temperature"])["value"]),
                "humidity": float(get_latest(FEED_MAP["humidity"])["value"]),
                "pressure": float(get_latest(FEED_MAP["pressure"])["value"])
            })
        except:
            pass

    if sensor == "motion":
        try:
            motion_value = float(latest["value"])
            now = dt.datetime.now(LOCAL_TZ)

            global motion_active_until, current_motion_bucket, motion_bucket_count

            # ----------- 5–MIN BUCKET (always fixed by the clock) -----------
            bucket_minute = (now.minute // 5) * 5
            new_bucket = f"{now.hour:02d}:{bucket_minute:02d}"

            # If bucket changed → reset everything including cooldown
            if new_bucket != current_motion_bucket:
                current_motion_bucket = new_bucket
                motion_bucket_count = 0
                motion_active_until = None  # <<< IMPORTANT FIX

            if motion_value > 0:
                # NEW motion detected → store
                store_motion_event()
                motion_bucket_count += 1
                motion_active_until = now + dt.timedelta(seconds=15)

            elif motion_active_until and now <= motion_active_until:
                # STILL SAME session → ignore, no new store
                pass

        except Exception as e:
            print("Motion logic error:", e)

    return jsonify(latest)


# -------------------------------------------------------------
# LIVE LAST HOUR (Adafruit → DB)
# -------------------------------------------------------------
@app.route("/api/live/hour/<sensor>")
def api_live_hour(sensor):
    if sensor not in FEED_MAP:
        return jsonify({"error": "invalid sensor"}), 400

    now = dt.datetime.now(LOCAL_TZ)
    start = now - dt.timedelta(hours=1)

    db = SessionLocal()

    # --- MOTION SPECIAL LOGIC ---
    if sensor == "motion":
        rows = db.query(MotionEvent).filter(
            MotionEvent.timestamp >= start,
            MotionEvent.timestamp <= now
        ).all()
        db.close()

        # Build dynamic buckets, including current unfinished one
        buckets = {}

        for r in rows:
            ts = r.timestamp.astimezone(LOCAL_TZ)
            bucket = ts.replace(
                minute=(ts.minute // 5) * 5,
                second=0,
                microsecond=0
            )
            key = bucket.strftime("%H:%M")
            buckets[key] = buckets.get(key, 0) + 1

        result = [{
            "time": k,
            "value": v
        } for k, v in sorted(buckets.items())]

        return jsonify(result)

    # --- ENVIRONMENT (unchanged) ---
    rows = db.query(EnvironmentData).filter(
        EnvironmentData.timestamp >= start,
        EnvironmentData.timestamp <= now
    ).all()
    db.close()

    return jsonify([{
        "time": r.timestamp.astimezone(LOCAL_TZ).strftime("%H:%M"),
        "value": getattr(r, sensor)
    } for r in rows])


@app.route("/api/status/security")
def api_status_security():
    """Returns the current armed state and recent event counts for the Home page summary (3 min max)."""
    db = SessionLocal()
    now = dt.datetime.now(LOCAL_TZ)

    # OLD: one_day_ago = now - dt.timedelta(days=1)
    # NEW: Check motion events in the last 3 minutes
    three_minutes_ago = now - dt.timedelta(minutes=3)

    # Get motion event count in the last 3 minutes
    motion_count = db.query(MotionEvent).filter(
        MotionEvent.timestamp >= three_minutes_ago,
        MotionEvent.timestamp <= now
    ).count()
    db.close()

    # Smoke count is a placeholder since no smoke feed/model was provided
    smoke_count = 0

    return jsonify({
        "armed_status": is_armed,
        "motion_count": motion_count,
        "smoke_count": smoke_count,
    })


@app.post("/api/control/security")
def api_control_security():
    """Sets the armed state of the security system."""
    global is_armed
    action = request.args.get("action")

    if action == "arm":
        is_armed = True
        message = "Security system armed."
    elif action == "disarm":
        is_armed = False
        message = "Security system disarmed."
    else:
        return jsonify({
            "success": False,
            "error": "Invalid action. Must be 'arm' or 'disarm'."
        }), 400

    print(f"[SECURITY] Status changed to: {action.upper()}")
    return jsonify({
        "success": True,
        "message": message,
        "armed_status": is_armed
    })

# -------------------------------------------------------------
# DB HISTORY BY DATE — ENVIRONMENT
# -------------------------------------------------------------
@app.get("/api/history_db/environment")
def history_db_environment():

    sensor = request.args.get("sensor")
    date = request.args.get("date")

    if not sensor or not date:
        return jsonify({"error": "sensor and date required"}), 400

    session = SessionLocal()

    try:
        start = dt.datetime.fromisoformat(date).replace(tzinfo=LOCAL_TZ)
        end = start + timedelta(days=1)

        rows = session.query(EnvironmentData).filter(
            EnvironmentData.timestamp >= start,
            EnvironmentData.timestamp < end
        ).order_by(EnvironmentData.timestamp).all()

        buckets = {}

        for r in rows:
            ts = r.timestamp.astimezone(LOCAL_TZ)
            bucket = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
            key = bucket.strftime("%H:%M")

            value = getattr(r, sensor)
            if value is None:
                continue

            buckets.setdefault(key, []).append(value)

        result = [{
            "time": k,
            "value": round(sum(v) / len(v), 2)
        } for k, v in sorted(buckets.items())]

        return jsonify(result)

    finally:
        session.close()


# -------------------------------------------------------------
# DB HISTORY — MOTION
# -------------------------------------------------------------
@app.get("/api/history_db/motion")
def api_history_motion_db():

    date = request.args.get("date")
    if not date:
        return jsonify({"error": "date required"}), 400

    start = dt.datetime.fromisoformat(date).replace(tzinfo=LOCAL_TZ)
    end = start + timedelta(days=1)

    db = SessionLocal()
    rows = db.query(MotionEvent).filter(
        MotionEvent.timestamp >= start,
        MotionEvent.timestamp < end
    ).order_by(MotionEvent.timestamp).all()
    db.close()

    buckets = {}

    for r in rows:
        ts = r.timestamp.astimezone(LOCAL_TZ)
        bucket = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        key = bucket.strftime("%H:%M")
        buckets[key] = buckets.get(key, 0) + 1

    result = [{
        "time": k,
        "value": v
    } for k, v in sorted(buckets.items())]

    return jsonify(result)

@app.post("/api/device/<device>")
def device_control(device):

    # Validate device from config.json
    if device not in DEVICES:
        return jsonify({
            "success": False,
            "error": f"Unknown device '{device}'"
        }), 400

    # JSON payload must include {"value": something}
    data = request.get_json(silent=True)
    if not data or "value" not in data:
        return jsonify({"success": False, "error": "Missing 'value' field"}), 400

    value = data["value"]

    # Send to Adafruit feed matching the device name
    feed_name = device  # EXACT SAME as feed name in Adafruit

    url = f"{BASE_URL}/feeds/{feed_name}/data"
    try:
        r = requests.post(url, headers=HEADERS, json={"value": value})

        if r.status_code not in (200, 201):
            return jsonify({
                "success": False,
                "error": f"Adafruit responded {r.status_code}"
            }), 500

        return jsonify({"success": True})

    except Exception as e:
        print("Device control failed:", e)
        return jsonify({"success": False, "error": "Internal error"}), 500

def cleanup_old_entries():
    print("[DB CLEANUP] Running cleanup for entries older than 7 days...")

    db = SessionLocal()

    try:
        now = dt.datetime.now(LOCAL_TZ)
        cutoff = now - dt.timedelta(days=7)

        # Cleanup EnvironmentData
        env_deleted = db.query(EnvironmentData)\
            .filter(EnvironmentData.timestamp < cutoff)\
            .delete()

        # Cleanup MotionEvent
        motion_deleted = db.query(MotionEvent)\
            .filter(MotionEvent.timestamp < cutoff)\
            .delete()

        db.commit()

        print(f"[DB CLEANUP] Environment deleted: {env_deleted}, Motion deleted: {motion_deleted}")

    except Exception as e:
        print("[DB CLEANUP ERROR]", e)

    finally:
        db.close()

def start_cleanup_scheduler():
    def run():
        while True:
            cleanup_old_entries()
            time.sleep(24 * 3600)  # run every 24 hours

    t = threading.Thread(target=run, daemon=True)
    t.start()

# -------------------------------------------------------------
# RUN
# -------------------------------------------------------------
if __name__ == "__main__":
    if os.environ.get("RENDER") != "true":
        start_cleanup_scheduler()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
