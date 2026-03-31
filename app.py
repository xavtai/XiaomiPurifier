"""Xiaomi Air Purifier local control server.

Communicates directly with purifiers over the local network using the miio
protocol — no Xiaomi cloud or app required.  Run on any machine on the same
WiFi as the purifiers, then open http://<ip>:5000 on your phone.
"""

import json
import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from flask import Flask, jsonify, render_template, request

try:
    from miio import AirPurifierMiot, AirPurifier
    from miio.exceptions import DeviceException
    MIIO_AVAILABLE = True
except ImportError:
    MIIO_AVAILABLE = False

app = Flask(__name__)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Device management
# ---------------------------------------------------------------------------

DEVICES_FILE = Path(__file__).parent / "devices.json"

# Cache: device_id -> {"config": {...}, "connection": <miio obj>, "protocol": "miot"|"miio"}
_device_cache: dict = {}


def _load_device_configs() -> list[dict]:
    with open(DEVICES_FILE) as f:
        return json.load(f)["devices"]


def _get_connection(dev_cfg: dict):
    """Return a miio connection object, trying MiOT first then classic miio."""
    if not MIIO_AVAILABLE:
        return None

    dev_id = dev_cfg["id"]
    cached = _device_cache.get(dev_id)
    if cached and cached["config"] == dev_cfg:
        return cached["connection"]

    ip, token = dev_cfg["ip"], dev_cfg["token"]

    # Try MiOT protocol first (newer purifiers: 4, 4 Pro, 4 Lite, Pro H)
    try:
        conn = AirPurifierMiot(ip, token)
        conn.status()  # probe
        _device_cache[dev_id] = {"config": dev_cfg, "connection": conn, "protocol": "miot"}
        log.info("Connected to %s via MiOT", dev_id)
        return conn
    except Exception:
        pass

    # Fall back to classic miio (older: 2S, 3H, Pro, etc.)
    try:
        conn = AirPurifier(ip, token)
        conn.status()  # probe
        _device_cache[dev_id] = {"config": dev_cfg, "connection": conn, "protocol": "miio"}
        log.info("Connected to %s via classic miio", dev_id)
        return conn
    except Exception:
        _device_cache.pop(dev_id, None)
        return None


def _poll_device(dev_cfg: dict) -> dict:
    """Poll a single device and return its status dict."""
    result = {
        "id": dev_cfg["id"],
        "name": dev_cfg["name"],
        "ip": dev_cfg["ip"],
        "online": False,
    }
    try:
        conn = _get_connection(dev_cfg)
        if conn is None:
            return result

        s = conn.status()
        result["online"] = True
        result["power"] = s.is_on if hasattr(s, "is_on") else s.power == "on"
        result["aqi"] = getattr(s, "aqi", None)
        result["humidity"] = getattr(s, "humidity", None)
        result["temperature"] = getattr(s, "temperature", None)
        result["mode"] = str(getattr(s, "mode", "unknown"))
        result["fan_level"] = getattr(s, "favorite_level", None) or getattr(s, "favorite_rpm", None)
        result["motor_speed"] = getattr(s, "motor_speed", None)
        result["filter_life"] = getattr(s, "filter_life_remaining", None)
        result["filter_hours_used"] = getattr(s, "filter_hours_used", None)
        result["buzzer"] = getattr(s, "buzzer", None)
        result["led"] = getattr(s, "led", None) if hasattr(s, "led") else getattr(s, "led_brightness", None)
        cached = _device_cache.get(dev_cfg["id"], {})
        result["protocol"] = cached.get("protocol", "unknown")
    except Exception as e:
        log.warning("Error polling %s: %s", dev_cfg["id"], e)
        _device_cache.pop(dev_cfg["id"], None)
    return result


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    devices = _load_device_configs()
    return render_template("dashboard.html", device_count=len(devices))


@app.route("/api/status")
def api_status():
    devices = _load_device_configs()
    results = []
    with ThreadPoolExecutor(max_workers=min(len(devices), 10)) as pool:
        futures = {pool.submit(_poll_device, d): d for d in devices}
        for fut in as_completed(futures):
            results.append(fut.result())
    # Sort by config order
    id_order = {d["id"]: i for i, d in enumerate(devices)}
    results.sort(key=lambda r: id_order.get(r["id"], 999))
    return jsonify(results)


def _find_device(device_id: str):
    """Find device config and connection by id."""
    for d in _load_device_configs():
        if d["id"] == device_id:
            conn = _get_connection(d)
            return d, conn
    return None, None


@app.route("/api/device/<device_id>/power", methods=["POST"])
def api_power(device_id):
    dev_cfg, conn = _find_device(device_id)
    if conn is None:
        return jsonify({"error": "Device offline or not found"}), 503

    try:
        action = request.json.get("action", "toggle") if request.json else "toggle"
        if action == "on":
            conn.on()
        elif action == "off":
            conn.off()
        else:
            s = conn.status()
            is_on = s.is_on if hasattr(s, "is_on") else s.power == "on"
            if is_on:
                conn.off()
            else:
                conn.on()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/device/<device_id>/mode", methods=["POST"])
def api_mode(device_id):
    dev_cfg, conn = _find_device(device_id)
    if conn is None:
        return jsonify({"error": "Device offline or not found"}), 503

    mode_str = request.json.get("mode", "auto") if request.json else "auto"

    try:
        cached = _device_cache.get(device_id, {})
        protocol = cached.get("protocol", "miot")

        if protocol == "miot":
            from miio.integrations.airpurifier.zhimi.airpurifier_miot import OperationMode as MiotMode
            mode_map = {
                "auto": MiotMode.Auto,
                "silent": MiotMode.Silent,
                "favorite": MiotMode.Favorite,
                "fan": MiotMode.Fan,
            }
        else:
            from miio.integrations.airpurifier.zhimi.airpurifier import OperationMode as ClassicMode
            mode_map = {
                "auto": ClassicMode.Auto,
                "silent": ClassicMode.Silent,
                "favorite": ClassicMode.Favorite,
            }

        mode = mode_map.get(mode_str.lower())
        if mode is None:
            return jsonify({"error": f"Unknown mode: {mode_str}"}), 400
        conn.set_mode(mode)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/device/<device_id>/fan_level", methods=["POST"])
def api_fan_level(device_id):
    dev_cfg, conn = _find_device(device_id)
    if conn is None:
        return jsonify({"error": "Device offline or not found"}), 503

    try:
        level = int(request.json.get("level", 5)) if request.json else 5
        level = max(0, min(14, level))
        conn.set_favorite_level(level)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/device/<device_id>/buzzer", methods=["POST"])
def api_buzzer(device_id):
    dev_cfg, conn = _find_device(device_id)
    if conn is None:
        return jsonify({"error": "Device offline or not found"}), 503

    try:
        enabled = request.json.get("enabled", True) if request.json else True
        conn.set_buzzer(enabled)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/device/<device_id>/led", methods=["POST"])
def api_led(device_id):
    dev_cfg, conn = _find_device(device_id)
    if conn is None:
        return jsonify({"error": "Device offline or not found"}), 503

    try:
        enabled = request.json.get("enabled", True) if request.json else True
        if hasattr(conn, "set_led"):
            conn.set_led(enabled)
        elif hasattr(conn, "set_led_brightness"):
            from miio.integrations.airpurifier.zhimi.airpurifier_miot import LedBrightness
            conn.set_led_brightness(LedBrightness.Bright if enabled else LedBrightness.Off)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not MIIO_AVAILABLE:
        log.warning("python-miio not installed — running in demo mode (all devices will show offline)")

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("DEBUG", "0") == "1"

    print(f"\n  Air Purifier Control: http://{host}:{port}")
    print(f"  Devices config: {DEVICES_FILE}\n")

    app.run(host=host, port=port, debug=debug)
