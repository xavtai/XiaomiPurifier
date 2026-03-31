"""Xiaomi Air Purifier local control server.

Controls 7 purifiers over the local network using MiOT protocol.
Background thread polls devices every 10s — API returns cached data instantly.
"""

import json
import os
import logging
import threading
import time
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

# ---------------------------------------------------------------------------
# Device management
# ---------------------------------------------------------------------------

DEVICES_FILE = Path(__file__).parent / "devices.json"
_device_cache: dict = {}
_device_lock = threading.Lock()

# Background poll state
_cached_status: list = []
_last_poll_time: float = 0


def _load_device_configs() -> list[dict]:
    try:
        with open(DEVICES_FILE) as f:
            return json.load(f)["devices"]
    except Exception as e:
        log.error("Failed to load devices.json: %s", e)
        return []


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

        props = dev.send("get_properties", MIOT_PROPS)
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
    except Exception as e:
        log.warning("Error polling %s: %s", dev_cfg["id"], e)
        with _device_lock:
            _device_cache.pop(dev_cfg["id"], None)
    return result


def _poll_all_devices():
    """Poll all devices and update the cached status."""
    global _cached_status, _last_poll_time
    devices = _load_device_configs()
    if not devices:
        return

    results = []
    with ThreadPoolExecutor(max_workers=min(len(devices), 10)) as pool:
        futures = {pool.submit(_poll_device, d): d for d in devices}
        for fut in as_completed(futures):
            results.append(fut.result())

    id_order = {d["id"]: i for i, d in enumerate(devices)}
    results.sort(key=lambda r: id_order.get(r["id"], 999))
    _cached_status = results
    _last_poll_time = time.time()


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
    if _cached_status:
        return jsonify(_cached_status)
    # First request before background poll completes — poll now
    _poll_all_devices()
    return jsonify(_cached_status)


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


@app.route("/api/device/<device_id>/power", methods=["POST"])
def api_power(device_id):
    dev_cfg, dev = _get_device_for_command(device_id)
    if dev is None:
        return jsonify({"error": "Device offline or not found"}), 503

    try:
        action = request.json.get("action", "toggle") if request.json else "toggle"
        if action == "on":
            power = True
        elif action == "off":
            power = False
        else:
            props = dev.send("get_properties", [{"did": "power", "siid": 2, "piid": 1}])
            current = props[0].get("value", False) if props else False
            power = not current

        dev.send("set_properties", [{"did": "power", "siid": 2, "piid": 1, "value": power}])
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
        dev.send("set_properties", [{"did": "mode", "siid": 2, "piid": 4, "value": mode_val}])
        return jsonify({"ok": True, "mode": mode_str})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/device/<device_id>/fan_level", methods=["POST"])
def api_fan_level(device_id):
    dev_cfg, dev = _get_device_for_command(device_id)
    if dev is None:
        return jsonify({"error": "Device offline or not found"}), 503

    try:
        level = int(request.json.get("level", 5)) if request.json else 5
        level = max(0, min(14, level))
        dev.send("set_properties", [{"did": "fan_level", "siid": 2, "piid": 5, "value": level}])
        return jsonify({"ok": True, "fan_level": level})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/all_on", methods=["POST"])
def api_all_on():
    devices = _load_device_configs()
    results = []
    for d in devices:
        try:
            _, dev = _get_device_for_command(d["id"])
            if dev:
                dev.send("set_properties", [{"did": "power", "siid": 2, "piid": 1, "value": True}])
                results.append({"id": d["id"], "ok": True})
            else:
                results.append({"id": d["id"], "error": "offline"})
        except Exception as e:
            results.append({"id": d["id"], "error": str(e)})
    return jsonify(results)


@app.route("/api/all_off", methods=["POST"])
def api_all_off():
    devices = _load_device_configs()
    results = []
    for d in devices:
        try:
            _, dev = _get_device_for_command(d["id"])
            if dev:
                dev.send("set_properties", [{"did": "power", "siid": 2, "piid": 1, "value": False}])
                results.append({"id": d["id"], "ok": True})
            else:
                results.append({"id": d["id"], "error": "offline"})
        except Exception as e:
            results.append({"id": d["id"], "error": str(e)})
    return jsonify(results)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not MIIO_AVAILABLE:
        log.warning("python-miio not installed — running in demo mode")

    # Start background poller
    poller = threading.Thread(target=_background_poller, daemon=True)
    poller.start()

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("DEBUG", "0") == "1"

    print(f"\n  Air Purifier Control: http://{host}:{port}")
    print(f"  Devices config: {DEVICES_FILE}")
    print(f"  Background polling: every {POLL_INTERVAL}s\n")

    app.run(host=host, port=port, debug=debug)
