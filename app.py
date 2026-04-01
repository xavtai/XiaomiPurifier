"""Xiaomi Air Purifier local control server.

Controls 7 purifiers over the local network using MiOT protocol.
Background thread polls devices every 10s — API returns cached data instantly.
"""

import json
import os
import logging
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from flask import Flask, jsonify, render_template, request

try:
    from miio import Device
    from miio.exceptions import DeviceException
    MIIO_AVAILABLE = True
except ImportError:
    MIIO_AVAILABLE = False

app = Flask(__name__)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MiOT property mapping (standard for Xiaomi air purifiers)
# ---------------------------------------------------------------------------

MIOT_PROPS = [
    {"did": "power",        "siid": 2, "piid": 1},
    {"did": "mode",         "siid": 2, "piid": 4},
    {"did": "fan_level",    "siid": 2, "piid": 5},
    {"did": "humidity",     "siid": 3, "piid": 1},
    {"did": "pm25",         "siid": 3, "piid": 4},
    {"did": "temperature",  "siid": 3, "piid": 7},
    {"did": "filter_life",  "siid": 4, "piid": 1},
    {"did": "filter_hours", "siid": 4, "piid": 3},
    {"did": "motor_speed",  "siid": 9, "piid": 1},
]

MODE_NAMES = {0: "Auto", 1: "Silent", 2: "Favorite", 3: "Fan"}
MODE_VALUES = {"auto": 0, "silent": 1, "favorite": 2, "fan": 3}
POLL_INTERVAL = 10  # seconds

# Screen brightness siid/piid varies by model
SCREEN_PROP = {
    "zhimi.airpurifier.mb4": {"siid": 7, "piid": 2},
    "zhimi.airp.mb5":        {"siid": 13, "piid": 2},
    "zhimi.airp.rmb1":       {"siid": 13, "piid": 2},
    "xiaomi.airp.cpa4":      {"siid": 13, "piid": 2},
    "xiaomi.airp.va2b":      {"siid": 13, "piid": 1},
}

# Fan speed property varies by model — some use fan_level, others use favorite_level or target RPM
FAN_SPEED_CONFIG = {
    "zhimi.airp.mb5":        {"siid": 2, "piid": 5,  "min": 1,   "max": 3},
    "xiaomi.airp.va2b":      {"siid": 2, "piid": 5,  "min": 0,   "max": 2},
    "zhimi.airp.rmb1":       {"siid": 9, "piid": 11, "min": 1,   "max": 14},
    "xiaomi.airp.cpa4":      {"siid": 9, "piid": 11, "min": 1,   "max": 14},
    "zhimi.airpurifier.mb4": {"siid": 9, "piid": 3,  "min": 300, "max": 2200},
}

LEVEL_PRESETS = {
    "zhimi.airp.mb5":        {"low": 1,   "mid": 2,    "high": 3},
    "xiaomi.airp.va2b":      {"low": 0,   "mid": 1,    "high": 2},
    "zhimi.airp.rmb1":       {"low": 3,   "mid": 7,    "high": 14},
    "xiaomi.airp.cpa4":      {"low": 3,   "mid": 7,    "high": 14},
    "zhimi.airpurifier.mb4": {"low": 600, "mid": 1200, "high": 2000},
}

# Physical filter reset instructions per model (for models that don't support remote reset)
FILTER_RESET_GUIDE = {
    "zhimi.airpurifier.mb4": "3C: Hold RIGHT button 7 sec in standby (3 beeps + green light)",
    "xiaomi.airp.cpa4":      "4 Compact: Hold POWER button 6 sec in standby (sound + green light)",
    "xiaomi.airp.va2b":      "4 Pro: Insert paperclip in reset pin-hole (near power cord) 5 sec (light turns blue/green)",
    "zhimi.airp.mb5":        "4: Hold POWER + DISPLAY buttons together 7 sec (2 beeps + green blink)",
    "zhimi.airp.rmb1":       "4 Lite: Hold RESET button on back panel 6 sec (short sound)",
}

# ---------------------------------------------------------------------------
# Device management
# ---------------------------------------------------------------------------

DEVICES_FILE = Path(__file__).parent / "devices.json"
_device_cache: dict = {}
_device_lock = threading.Lock()
_state_lock = threading.Lock()  # protects _cached_status, _manual_override, _schedule_last_state

# Background poll state
_cached_status: list = []
_last_poll_time: float = 0
_poll_ready = threading.Event()  # set after first poll completes
_previous_aqi: dict = {}  # {device_id: last_pm25} for spike detection

# Outdoor AQI state
IQAIR_KEY = os.environ.get("IQAIR_KEY", "")
WAQI_TOKEN = os.environ.get("WAQI_TOKEN", "")
OUTDOOR_POLL_INTERVAL = 900  # 15 minutes
_outdoor_aqi: dict | None = None
_last_outdoor_poll: float = 0

# Scheduling state
SCHEDULES_FILE = Path(__file__).parent / "schedules.json"
_manual_override: dict = {}  # {device_id: timestamp} — suppresses scheduler until next boundary
_schedule_last_state: dict = {}  # {device_id: "on"/"off"} — prevents repeated commands


def _send_and_check(dev, props, action="command"):
    """Send set_properties and check response codes. Returns (ok, error_msg)."""
    result = dev.send("set_properties", props)
    failures = [r for r in result if r.get("code", 0) != 0]
    if failures:
        codes = ", ".join(f"code={r['code']}" for r in failures)
        return False, f"{action} rejected by device ({codes})"
    return True, None


def _load_device_configs_raw() -> dict:
    try:
        with open(DEVICES_FILE) as f:
            return json.load(f)
    except Exception as e:
        log.error("Failed to load devices.json: %s", e)
        return {}


def _load_device_configs() -> list[dict]:
    return _load_device_configs_raw().get("devices", [])


def _get_device(dev_cfg: dict) -> Device | None:
    if not MIIO_AVAILABLE:
        return None

    dev_id = dev_cfg["id"]
    with _device_lock:
        cached = _device_cache.get(dev_id)
        if cached and cached["config"] == dev_cfg:
            return cached["device"]

    try:
        dev = Device(dev_cfg["ip"], dev_cfg["token"])
        dev.send("miIO.info")
        with _device_lock:
            _device_cache[dev_id] = {"config": dev_cfg, "device": dev}
        log.info("Connected to %s at %s", dev_id, dev_cfg["ip"])
        return dev
    except Exception:
        # Retry once with fresh connection
        try:
            with _device_lock:
                _device_cache.pop(dev_id, None)
            dev = Device(dev_cfg["ip"], dev_cfg["token"])
            dev.send("miIO.info")
            with _device_lock:
                _device_cache[dev_id] = {"config": dev_cfg, "device": dev}
            log.info("Reconnected to %s at %s", dev_id, dev_cfg["ip"])
            return dev
        except Exception as e:
            log.warning("Cannot reach %s: %s", dev_id, e)
            with _device_lock:
                _device_cache.pop(dev_id, None)
            return None


def _poll_device(dev_cfg: dict) -> dict:
    result = {
        "id": dev_cfg["id"],
        "name": dev_cfg["name"],
        "ip": dev_cfg["ip"],
        "model": dev_cfg.get("model", ""),
        "online": False,
    }
    try:
        dev = _get_device(dev_cfg)
        if dev is None:
            return result

        # Main properties batch (consistent across all models)
        extra_props = [
            {"did": "buzzer",     "siid": 6, "piid": 1},
            {"did": "child_lock", "siid": 8, "piid": 1},
        ]
        props = dev.send("get_properties", MIOT_PROPS + extra_props)
        vals = {p["did"]: p.get("value") for p in props if p.get("code", -1) == 0}

        result["online"] = True
        result["power"] = vals.get("power", False)
        result["aqi"] = vals.get("pm25")
        result["humidity"] = vals.get("humidity")
        result["temperature"] = vals.get("temperature")
        result["mode"] = MODE_NAMES.get(vals.get("mode"), str(vals.get("mode", "?")))
        result["fan_level"] = vals.get("fan_level")
        result["motor_speed"] = vals.get("motor_speed")
        result["filter_life"] = vals.get("filter_life")
        result["filter_hours_used"] = vals.get("filter_hours")
        result["buzzer"] = vals.get("buzzer")
        result["child_lock"] = vals.get("child_lock")

        # Fan speed — reuse main batch value when same property, else poll separately
        fan_cfg = FAN_SPEED_CONFIG.get(model)
        if fan_cfg:
            if fan_cfg["siid"] == 2 and fan_cfg["piid"] == 5:
                # Same property as fan_level in main batch — no extra network call
                result["fan_speed"] = vals.get("fan_level")
            else:
                # Different property (rmb1, cpa4, mb4) — poll separately
                try:
                    fp = dev.send("get_properties", [{"did": "fan_speed", "siid": fan_cfg["siid"], "piid": fan_cfg["piid"]}])
                    if fp and fp[0].get("code", -1) == 0:
                        result["fan_speed"] = fp[0].get("value")
                except Exception:
                    pass

        # Screen brightness (model-specific siid/piid)
        model = dev_cfg.get("model", "")
        sp = SCREEN_PROP.get(model)
        if sp:
            try:
                bp = dev.send("get_properties", [{"did": "brightness", **sp}])
                if bp and bp[0].get("code", -1) == 0:
                    result["brightness"] = bp[0].get("value")
            except Exception:
                pass
    except Exception as e:
        log.warning("Error polling %s: %s", dev_cfg["id"], e)
        with _device_lock:
            _device_cache.pop(dev_cfg["id"], None)
    return result


def _poll_outdoor_iqair(lat: float, lon: float) -> bool:
    """Try IQAir API. Returns True on success."""
    global _outdoor_aqi
    if not IQAIR_KEY:
        return False
    try:
        url = f"http://api.airvisual.com/v2/nearest_city?lat={lat}&lon={lon}&key={IQAIR_KEY}"
        req = urllib.request.Request(url, headers={"User-Agent": "XiaomiPurifier/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if data.get("status") == "success":
            d = data["data"]
            pol = d.get("current", {}).get("pollution", {})
            wthr = d.get("current", {}).get("weather", {})
            _outdoor_aqi = {
                "aqi": pol.get("aqius"),
                "pm25": pol.get("aqius"),  # IQAir free tier doesn't give raw µg/m³
                "temperature": wthr.get("tp"),
                "humidity": wthr.get("hu"),
                "wind": wthr.get("ws"),
                "station": f"{d.get('city', '')}, {d.get('state', '')}",
                "updated": pol.get("ts", ""),
            }
            log.info("Outdoor AQI (IQAir): %s (station: %s)", _outdoor_aqi["aqi"], _outdoor_aqi["station"])
            return True
    except Exception as e:
        log.warning("IQAir fetch failed: %s", e)
    return False


def _poll_outdoor_waqi(lat: float, lon: float) -> bool:
    """Try WAQI API. Returns True on success."""
    global _outdoor_aqi
    if not WAQI_TOKEN:
        return False
    try:
        url = f"http://api.waqi.info/feed/geo:{lat};{lon}/?token={WAQI_TOKEN}"
        req = urllib.request.Request(url, headers={"User-Agent": "XiaomiPurifier/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if data.get("status") == "ok":
            d = data["data"]
            iaqi = d.get("iaqi", {})
            _outdoor_aqi = {
                "aqi": d.get("aqi"),
                "pm25": iaqi.get("pm25", {}).get("v"),
                "temperature": iaqi.get("t", {}).get("v"),
                "humidity": iaqi.get("h", {}).get("v"),
                "wind": iaqi.get("w", {}).get("v"),
                "station": d.get("city", {}).get("name", "Unknown"),
                "updated": d.get("time", {}).get("s", ""),
            }
            log.info("Outdoor AQI (WAQI): %s (station: %s)", _outdoor_aqi["aqi"], _outdoor_aqi["station"])
            return True
    except Exception as e:
        log.warning("WAQI fetch failed: %s", e)
    return False


def _poll_outdoor_aqi():
    """Fetch outdoor AQI. Tries IQAir first (local station), falls back to WAQI."""
    global _last_outdoor_poll
    if not IQAIR_KEY and not WAQI_TOKEN:
        return

    # Only poll every 15 minutes
    if time.time() - _last_outdoor_poll < OUTDOOR_POLL_INTERVAL:
        return

    configs = _load_device_configs_raw()
    outdoor_cfg = configs.get("outdoor", {})
    lat = outdoor_cfg.get("lat", 18.75)
    lon = outdoor_cfg.get("lon", 98.93)

    # IQAir first (returns Mae Hia — closest to Hang Dong), then WAQI fallback
    if not _poll_outdoor_iqair(lat, lon):
        _poll_outdoor_waqi(lat, lon)

    _last_outdoor_poll = time.time()


def _poll_all_devices():
    """Poll all devices and update the cached status."""
    global _cached_status, _last_poll_time, _previous_aqi
    devices = _load_device_configs()
    if not devices:
        return

    results = []
    with ThreadPoolExecutor(max_workers=min(len(devices), 10)) as pool:
        futures = {pool.submit(_poll_device, d): d for d in devices}
        for fut in as_completed(futures):
            results.append(fut.result())

    # Spike detection: compare new AQI with previous
    for r in results:
        prev = _previous_aqi.get(r["id"])
        cur = r.get("aqi")
        r["spike"] = (prev is not None and cur is not None and cur - prev > 50)

    # Store current values as previous for next cycle
    _previous_aqi = {r["id"]: r.get("aqi") for r in results}

    id_order = {d["id"]: i for i, d in enumerate(devices)}
    results.sort(key=lambda r: id_order.get(r["id"], 999))
    with _state_lock:
        _cached_status = results
    _last_poll_time = time.time()
    _poll_ready.set()


def _background_poller():
    """Background thread that polls devices every POLL_INTERVAL seconds."""
    log.info("Background poller started (every %ds)", POLL_INTERVAL)
    while True:
        try:
            _poll_all_devices()
            online = sum(1 for d in _cached_status if d.get("online"))
            log.info("Poll complete: %d/%d online", online, len(_cached_status))
        except Exception as e:
            log.error("Background poll error: %s", e)
        try:
            _poll_outdoor_aqi()
        except Exception as e:
            log.error("Outdoor AQI poll error: %s", e)
        try:
            _check_schedules()
        except Exception as e:
            log.error("Schedule check error: %s", e)
        time.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    devices = _load_device_configs()
    return render_template("dashboard.html", device_count=len(devices))


@app.route("/api/status")
def api_status():
    if not _poll_ready.is_set():
        # First request before background poll completes — wait for it
        _poll_ready.wait(timeout=15)
    return jsonify({
        "devices": _cached_status,
        "outdoor": _outdoor_aqi,
        "schedules": _load_schedules(),
        "fan_config": FAN_SPEED_CONFIG,
        "level_presets": LEVEL_PRESETS,
    })


def _get_device_for_command(device_id: str):
    """Get device for sending commands. Uses cache, no probe needed."""
    for d in _load_device_configs():
        if d["id"] == device_id:
            dev_id = d["id"]
            with _device_lock:
                cached = _device_cache.get(dev_id)
            if cached:
                return d, cached["device"]
            # Not cached — try connecting
            dev = _get_device(d)
            return d, dev
    return None, None


def _update_cache(device_id: str, **fields):
    """Optimistically update cached device status after a successful command."""
    with _state_lock:
        for s in _cached_status:
            if s["id"] == device_id:
                s.update(fields)
                break


@app.route("/api/device/<device_id>/power", methods=["POST"])
def api_power(device_id):
    dev_cfg, dev = _get_device_for_command(device_id)
    if dev is None:
        return jsonify({"error": "Device offline or not found"}), 503

    try:
        data = request.json or {}
        if "power" in data:
            power = bool(data["power"])
        elif data.get("action") == "on":
            power = True
        elif data.get("action") == "off":
            power = False
        else:
            props = dev.send("get_properties", [{"did": "power", "siid": 2, "piid": 1}])
            current = props[0].get("value", False) if props else False
            power = not current

        ok, err = _send_and_check(dev, [{"did": "power", "siid": 2, "piid": 1, "value": power}], "Power")
        if not ok:
            return jsonify({"error": err}), 422
        with _state_lock:
            _manual_override[device_id] = time.time()
        _update_cache(device_id, power=power)
        return jsonify({"ok": True, "power": power})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/device/<device_id>/mode", methods=["POST"])
def api_mode(device_id):
    dev_cfg, dev = _get_device_for_command(device_id)
    if dev is None:
        return jsonify({"error": "Device offline or not found"}), 503

    mode_str = request.json.get("mode", "auto") if request.json else "auto"
    mode_val = MODE_VALUES.get(mode_str.lower())
    if mode_val is None:
        return jsonify({"error": f"Unknown mode: {mode_str}. Use: auto, silent, favorite, fan"}), 400

    try:
        ok, err = _send_and_check(dev, [{"did": "mode", "siid": 2, "piid": 4, "value": mode_val}], "Mode")
        if not ok:
            return jsonify({"error": err}), 422
        _update_cache(device_id, mode=MODE_NAMES.get(mode_val, mode_str))
        return jsonify({"ok": True, "mode": mode_str})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/device/<device_id>/fan_level", methods=["POST"])
def api_fan_level(device_id):
    dev_cfg, dev = _get_device_for_command(device_id)
    if dev is None:
        return jsonify({"error": "Device offline or not found"}), 503

    try:
        data = request.json or {}
        level_raw = data.get("level", "mid")
        model = dev_cfg.get("model", "")
        presets = LEVEL_PRESETS.get(model, {})
        fan_cfg = FAN_SPEED_CONFIG.get(model)
        if not fan_cfg:
            return jsonify({"error": f"Unknown fan config for model {model}"}), 400

        # Accept preset names ("low"/"mid"/"high") or numeric values
        if isinstance(level_raw, str) and level_raw in presets:
            level = presets[level_raw]
        else:
            level = int(level_raw)
            level = max(fan_cfg["min"], min(fan_cfg["max"], level))

        # Switch to favorite mode first, then set speed (with delay for device transition)
        ok, err = _send_and_check(dev, [{"did": "mode", "siid": 2, "piid": 4, "value": 2}], "Mode switch")
        if not ok:
            return jsonify({"error": err}), 422
        time.sleep(0.3)  # Device needs time to transition modes before accepting speed

        ok, err = _send_and_check(dev, [{"did": "fan_speed", "siid": fan_cfg["siid"], "piid": fan_cfg["piid"], "value": level}], "Fan speed")
        if not ok:
            return jsonify({"error": err}), 422
        _update_cache(device_id, mode="Favorite", fan_speed=level)
        return jsonify({"ok": True, "fan_level": level})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/device/<device_id>/filter_reset", methods=["POST"])
def api_filter_reset(device_id):
    dev_cfg, dev = _get_device_for_command(device_id)
    if dev is None:
        return jsonify({"error": "Device offline or not found"}), 503

    try:
        # Try MiOT action first (standard reset-filter-life action)
        action_ok = False
        try:
            result = dev.send("action", {"did": "filter_reset", "siid": 4, "aiid": 1, "in": []})
            code = result.get("code", -1) if isinstance(result, dict) else -1
            action_ok = (code == 0)
        except Exception:
            pass  # Action not supported — fall through to set_properties

        if not action_ok:
            # Fallback: set filter properties directly
            result = dev.send("set_properties", [
                {"did": "filter_life", "siid": 4, "piid": 1, "value": 100},
                {"did": "filter_hours", "siid": 4, "piid": 3, "value": 0},
            ])
            # Check if properties are read-only (-4004)
            if all(p.get("code") == -4004 for p in result):
                model = dev_cfg.get("model", "")
                hint = FILTER_RESET_GUIDE.get(model, "Hold reset button 6+ sec in standby")
                return jsonify({"error": hint, "manual_reset": True}), 422

        # Re-poll device to get fresh values
        fresh = _poll_device(dev_cfg)
        with _state_lock:
            for i, s in enumerate(_cached_status):
                if s["id"] == device_id:
                    _cached_status[i] = fresh
                    break

        return jsonify({
            "ok": True,
            "filter_life": fresh.get("filter_life"),
            "filter_hours_used": fresh.get("filter_hours_used"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/device/<device_id>/buzzer", methods=["POST"])
def api_buzzer(device_id):
    dev_cfg, dev = _get_device_for_command(device_id)
    if dev is None:
        return jsonify({"error": "Device offline or not found"}), 503
    try:
        enabled = bool(request.json.get("enabled", True)) if request.json else True
        ok, err = _send_and_check(dev, [{"did": "buzzer", "siid": 6, "piid": 1, "value": enabled}], "Buzzer")
        if not ok:
            return jsonify({"error": err}), 422
        _update_cache(device_id, buzzer=enabled)
        return jsonify({"ok": True, "buzzer": enabled})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/device/<device_id>/child_lock", methods=["POST"])
def api_child_lock(device_id):
    dev_cfg, dev = _get_device_for_command(device_id)
    if dev is None:
        return jsonify({"error": "Device offline or not found"}), 503
    try:
        enabled = bool(request.json.get("enabled", True)) if request.json else True
        ok, err = _send_and_check(dev, [{"did": "child_lock", "siid": 8, "piid": 1, "value": enabled}], "Child lock")
        if not ok:
            return jsonify({"error": err}), 422
        _update_cache(device_id, child_lock=enabled)
        return jsonify({"ok": True, "child_lock": enabled})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/device/<device_id>/brightness", methods=["POST"])
def api_brightness(device_id):
    dev_cfg, dev = _get_device_for_command(device_id)
    if dev is None:
        return jsonify({"error": "Device offline or not found"}), 503
    try:
        level = int(request.json.get("level", 2)) if request.json else 2
        level = max(0, min(2, level))
        model = dev_cfg.get("model", "")
        sp = SCREEN_PROP.get(model)
        if not sp:
            return jsonify({"error": "Unknown screen property for this model"}), 400
        cmds = [{"did": "brightness", "siid": sp["siid"], "piid": sp["piid"], "value": level}]
        # mb4 also has a separate on/off bool for screen
        if model == "zhimi.airpurifier.mb4":
            cmds.append({"did": "screen_on", "siid": 7, "piid": 1, "value": level > 0})
        ok, err = _send_and_check(dev, cmds, "Brightness")
        if not ok:
            return jsonify({"error": err}), 422
        _update_cache(device_id, brightness=level)
        return jsonify({"ok": True, "brightness": level})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

def _load_schedules() -> dict:
    try:
        with open(SCHEDULES_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_schedules(schedules: dict):
    tmp = SCHEDULES_FILE.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(schedules, f, indent=2)
    os.replace(tmp, SCHEDULES_FILE)


def _is_in_active_window(on_time: str, off_time: str) -> bool:
    """Check if current time falls within the on→off window. Handles overnight wrap."""
    from datetime import datetime
    try:
        now = datetime.now()
        h, m = map(int, on_time.split(":"))
        on_min = h * 60 + m
        h, m = map(int, off_time.split(":"))
        off_min = h * 60 + m
    except (ValueError, AttributeError):
        log.warning("Invalid schedule time format: on=%s off=%s", on_time, off_time)
        return False
    cur_min = now.hour * 60 + now.minute

    if on_min <= off_min:
        # Normal: on=07:00 off=23:00
        return on_min <= cur_min < off_min
    else:
        # Overnight: on=20:00 off=08:00
        return cur_min >= on_min or cur_min < off_min


def _check_schedules():
    """Check schedules and send power commands as needed."""
    schedules = _load_schedules()
    if not schedules:
        return

    for dev_id, sched_list in schedules.items():
        # Support both legacy {"on","off"} and new [{"on","off"}, ...] format
        if isinstance(sched_list, dict):
            sched_list = [sched_list]
        if not isinstance(sched_list, list) or not sched_list:
            continue

        # Device should be on if ANY schedule window is active
        should_be_on = any(
            _is_in_active_window(s.get("on", ""), s.get("off", ""))
            for s in sched_list if s.get("on") and s.get("off")
        )
        target_state = "on" if should_be_on else "off"
        prev_state = _schedule_last_state.get(dev_id)

        with _state_lock:
            # Boundary crossing: target changed from last known state — clear override
            if prev_state is not None and prev_state != target_state:
                _manual_override.pop(dev_id, None)

            # Expire manual override after 60 minutes
            override_time = _manual_override.get(dev_id)
            if override_time and (time.time() - override_time > 3600):
                _manual_override.pop(dev_id, None)

            # Skip if manual override is active
            if dev_id in _manual_override:
                _schedule_last_state[dev_id] = target_state
                continue

        # Find the device and check actual state
        device_status = next((d for d in _cached_status if d["id"] == dev_id), None)
        if not device_status or not device_status.get("online"):
            continue

        actual_on = device_status.get("power", False)
        if actual_on == should_be_on:
            with _state_lock:
                _schedule_last_state[dev_id] = target_state
            continue

        # Device state doesn't match schedule — send command
        try:
            _, dev = _get_device_for_command(dev_id)
            if dev:
                ok, err = _send_and_check(dev, [{"did": "power", "siid": 2, "piid": 1, "value": should_be_on}], "Schedule power")
                if ok:
                    log.info("Schedule: %s turned %s", dev_id, target_state)
                else:
                    log.warning("Schedule command rejected for %s: %s", dev_id, err)
                with _state_lock:
                    _schedule_last_state[dev_id] = target_state
        except Exception as e:
            log.warning("Schedule command failed for %s: %s", dev_id, e)


@app.route("/api/schedules")
def api_schedules():
    return jsonify(_load_schedules())


@app.route("/api/device/<device_id>/schedule", methods=["POST"])
def api_schedule(device_id):
    """Set schedules for a device. Body: {"schedules": [{"on":"07:00","off":"23:00"}, ...]} or {"clear": true}"""
    schedules = _load_schedules()
    data = request.json or {}

    if data.get("clear"):
        schedules.pop(device_id, None)
        _schedule_last_state.pop(device_id, None)
        _manual_override.pop(device_id, None)
    elif "schedules" in data:
        # Validate time format
        import re
        time_re = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
        for s in data["schedules"]:
            if not time_re.match(s.get("on", "")) or not time_re.match(s.get("off", "")):
                return jsonify({"error": f"Invalid time format: {s}. Use HH:MM (00:00-23:59)"}), 400
        schedules[device_id] = data["schedules"]
    elif data.get("on") and data.get("off"):
        # Legacy single schedule support
        schedules[device_id] = [{"on": data["on"], "off": data["off"]}]
    else:
        schedules.pop(device_id, None)
        _schedule_last_state.pop(device_id, None)
        _manual_override.pop(device_id, None)

    _save_schedules(schedules)
    return jsonify({"ok": True, "schedules": schedules})


def _set_power_one(dev_cfg: dict, power: bool) -> dict:
    """Set power for a single device. Used by all_on/all_off in parallel."""
    try:
        _, dev = _get_device_for_command(dev_cfg["id"])
        if dev:
            ok, err = _send_and_check(dev, [{"did": "power", "siid": 2, "piid": 1, "value": power}], "Power")
            if not ok:
                return {"id": dev_cfg["id"], "error": err}
            with _state_lock:
                _manual_override[dev_cfg["id"]] = time.time()
            return {"id": dev_cfg["id"], "ok": True}
        return {"id": dev_cfg["id"], "error": "offline"}
    except Exception as e:
        return {"id": dev_cfg["id"], "error": str(e)}


@app.route("/api/all_on", methods=["POST"])
def api_all_on():
    devices = _load_device_configs()
    with ThreadPoolExecutor(max_workers=min(len(devices), 10)) as pool:
        results = list(pool.map(lambda d: _set_power_one(d, True), devices))
    return jsonify(results)


@app.route("/api/all_off", methods=["POST"])
def api_all_off():
    devices = _load_device_configs()
    with ThreadPoolExecutor(max_workers=min(len(devices), 10)) as pool:
        results = list(pool.map(lambda d: _set_power_one(d, False), devices))
    return jsonify(results)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not MIIO_AVAILABLE:
        log.warning("python-miio not installed — running in demo mode")
    if not IQAIR_KEY and not WAQI_TOKEN:
        log.warning("IQAIR_KEY/WAQI_TOKEN not set — outdoor AQI disabled")

    # Start background poller
    poller = threading.Thread(target=_background_poller, daemon=True)
    poller.start()

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))

    print(f"\n  Air Purifier Control: http://{host}:{port}")
    print(f"  Devices config: {DEVICES_FILE}")
    print(f"  Background polling: every {POLL_INTERVAL}s\n")

    try:
        from waitress import serve
        print("  Server: waitress (production)\n")
        serve(app, host=host, port=port, threads=4)
    except ImportError:
        print("  Server: Flask dev (install waitress for production)\n")
        app.run(host=host, port=port)
