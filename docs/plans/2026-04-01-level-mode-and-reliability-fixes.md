# Level Mode + Reliability Fixes — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the broken 0-14 fan slider with model-aware Low/Mid/High presets, and fix 5 reliability bugs (silent command failures, toggle race, schedule override expiry, atomic file writes, time validation).

**Architecture:** All changes in 2 files — `app.py` (backend) and `templates/dashboard.html` (frontend). New `FAN_SPEED_CONFIG` and `LEVEL_PRESETS` dicts map each purifier model to its correct MiOT speed property. A `_send_and_check()` helper wraps all `dev.send()` calls with response code validation.

**Tech Stack:** Python/Flask, vanilla JS, MiOT protocol via python-miio

---

### Task 1: Add _send_and_check helper + FAN_SPEED_CONFIG dicts

**Files:**
- Modify: `app.py:44-55` (after SCREEN_PROP)

**Step 1: Add the new dicts and helper function after SCREEN_PROP (line 55)**

Add after the `SCREEN_PROP` closing brace:

```python
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
```

**Step 2: Add _send_and_check helper before _load_device_configs_raw (line 94)**

```python
def _send_and_check(dev, props, action="command"):
    """Send set_properties and check response codes. Returns (ok, error_msg)."""
    result = dev.send("set_properties", props)
    failures = [r for r in result if r.get("code", 0) != 0]
    if failures:
        codes = ", ".join(f"code={r['code']}" for r in failures)
        return False, f"{action} rejected by device ({codes})"
    return True, None
```

**Step 3: Commit**

```bash
git add app.py
git commit -m "Add FAN_SPEED_CONFIG, LEVEL_PRESETS, and _send_and_check helper"
```

---

### Task 2: Fix all endpoints to use _send_and_check

**Files:**
- Modify: `app.py:358-506` (all command endpoints)

**Step 1: Fix api_power (line 358) — also remove toggle race**

Replace lines 364-378 with:

```python
    try:
        data = request.json or {}
        if "power" in data:
            power = bool(data["power"])
        elif data.get("action") == "on":
            power = True
        elif data.get("action") == "off":
            power = False
        else:
            # Legacy toggle — read current state (still supported but not used by new frontend)
            props = dev.send("get_properties", [{"did": "power", "siid": 2, "piid": 1}])
            current = props[0].get("value", False) if props else False
            power = not current

        ok, err = _send_and_check(dev, [{"did": "power", "siid": 2, "piid": 1, "value": power}], "Power")
        if not ok:
            return jsonify({"error": err}), 422
        with _state_lock:
            _manual_override[device_id] = time.time()
        return jsonify({"ok": True, "power": power})
```

**Step 2: Fix api_mode (line 394-396)**

Replace line 395-396:

```python
        ok, err = _send_and_check(dev, [{"did": "mode", "siid": 2, "piid": 4, "value": mode_val}], "Mode")
        if not ok:
            return jsonify({"error": err}), 422
        return jsonify({"ok": True, "mode": mode_str})
```

**Step 3: Rewrite api_fan_level (line 401-413) — model-aware**

Replace entire function body (lines 407-413):

```python
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

        # Switch to favorite mode first, then set speed
        ok, err = _send_and_check(dev, [{"did": "mode", "siid": 2, "piid": 4, "value": 2}], "Mode switch")
        if not ok:
            return jsonify({"error": err}), 422

        ok, err = _send_and_check(dev, [{"did": "fan_speed", "siid": fan_cfg["siid"], "piid": fan_cfg["piid"], "value": level}], "Fan speed")
        if not ok:
            return jsonify({"error": err}), 422
        return jsonify({"ok": True, "fan_level": level})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
```

**Step 4: Fix api_buzzer (line 468), api_child_lock (line 481), api_brightness (line 503)**

Same pattern for each — replace `dev.send(...)` with `_send_and_check(...)` and return error on failure.

For buzzer (line 468):
```python
        ok, err = _send_and_check(dev, [{"did": "buzzer", "siid": 6, "piid": 1, "value": enabled}], "Buzzer")
        if not ok:
            return jsonify({"error": err}), 422
        return jsonify({"ok": True, "buzzer": enabled})
```

For child_lock (line 481):
```python
        ok, err = _send_and_check(dev, [{"did": "child_lock", "siid": 8, "piid": 1, "value": enabled}], "Child lock")
        if not ok:
            return jsonify({"error": err}), 422
        return jsonify({"ok": True, "child_lock": enabled})
```

For brightness (line 503):
```python
        ok, err = _send_and_check(dev, cmds, "Brightness")
        if not ok:
            return jsonify({"error": err}), 422
        return jsonify({"ok": True, "brightness": level})
```

**Step 5: Fix _set_power_one (line 637) and _check_schedules (line 594)**

In `_set_power_one` line 637:
```python
            ok, err = _send_and_check(dev, [{"did": "power", "siid": 2, "piid": 1, "value": power}], "Power")
            if not ok:
                return {"id": dev_cfg["id"], "error": err}
```

In `_check_schedules` line 594:
```python
                ok, err = _send_and_check(dev, [{"did": "power", "siid": 2, "piid": 1, "value": should_be_on}], "Schedule power")
                if ok:
                    log.info("Schedule: %s turned %s", dev_id, target_state)
                else:
                    log.warning("Schedule command rejected for %s: %s", dev_id, err)
```

**Step 6: Commit**

```bash
git add app.py
git commit -m "Fix all endpoints to validate device response codes via _send_and_check"
```

---

### Task 3: Poll model-aware fan speed + include FAN_SPEED_CONFIG in API

**Files:**
- Modify: `app.py:142-190` (_poll_device)
- Modify: `app.py:336-340` (api_status)

**Step 1: Poll the correct fan speed property per model in _poll_device**

After line 174 (`result["child_lock"] = ...`), add:

```python
        # Fan speed (model-specific siid/piid)
        fan_cfg = FAN_SPEED_CONFIG.get(model)
        if fan_cfg:
            try:
                fp = dev.send("get_properties", [{"did": "fan_speed", "siid": fan_cfg["siid"], "piid": fan_cfg["piid"]}])
                if fp and fp[0].get("code", -1) == 0:
                    result["fan_speed"] = fp[0].get("value")
            except Exception:
                pass
```

**Step 2: Include fan config in /api/status response**

Modify line 340 to include the config dicts:

```python
    return jsonify({
        "devices": _cached_status,
        "outdoor": _outdoor_aqi,
        "schedules": _load_schedules(),
        "fan_config": FAN_SPEED_CONFIG,
        "level_presets": LEVEL_PRESETS,
    })
```

**Step 3: Commit**

```bash
git add app.py
git commit -m "Poll model-aware fan speed, expose FAN_SPEED_CONFIG in API"
```

---

### Task 4: Schedule hardening — override TTL, atomic writes, time validation

**Files:**
- Modify: `app.py:521-629` (scheduling code)

**Step 1: Add override TTL (60 minutes) in _check_schedules**

In `_check_schedules`, before the `if dev_id in _manual_override` check (line 575), add TTL expiry:

```python
            # Expire manual override after 60 minutes
            override_time = _manual_override.get(dev_id)
            if override_time and (time.time() - override_time > 3600):
                _manual_override.pop(dev_id, None)
```

**Step 2: Atomic file writes in _save_schedules**

Replace `_save_schedules` (lines 521-523):

```python
def _save_schedules(schedules: dict):
    tmp = SCHEDULES_FILE.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(schedules, f, indent=2)
    os.replace(tmp, SCHEDULES_FILE)
```

**Step 3: Time validation in api_schedule**

Add validation before saving (after line 617 `elif "schedules" in data:`):

```python
        import re
        time_re = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
        for s in data["schedules"]:
            if not time_re.match(s.get("on", "")) or not time_re.match(s.get("off", "")):
                return jsonify({"error": f"Invalid time format: {s}. Use HH:MM (00:00-23:59)"}), 400
```

**Step 4: Commit**

```bash
git add app.py
git commit -m "Schedule hardening: 60min override TTL, atomic writes, time validation"
```

---

### Task 5: Frontend — explicit power, Level buttons replace slider

**Files:**
- Modify: `templates/dashboard.html:1026` (togglePower)
- Modify: `templates/dashboard.html:882-905` (fan slider section)
- Modify: `templates/dashboard.html:959-968` (fetchStatus — parse fan_config)

**Step 1: Fix togglePower to send explicit power state**

Replace line 1026:

```javascript
function togglePower(id, isOn) { post('/api/device/' + id + '/power', {power: !isOn}, isOn ? 'Turned off' : 'Turned on'); }
```

**Step 2: Parse fan_config and level_presets from API response**

Add global vars after line 625:

```javascript
let fanConfig = {};
let levelPresets = {};
```

In fetchStatus (after line 968 `schedules = data.schedules || {};`):

```javascript
    fanConfig = data.fan_config || {};
    levelPresets = data.level_presets || {};
```

**Step 3: Replace fan slider with Level preset buttons in createCard**

Replace lines 882-905 (the fan slider block) with:

```javascript
  // Level preset buttons — shown inline when in Manual (favorite) mode
  if (isOn && curMode === 'favorite') {
    var presets = levelPresets[d.model] || {};
    var fanSpeed = d.fan_speed;
    var presetRow = document.createElement('div');
    presetRow.className = 'mode-row';
    presetRow.style.marginBottom = '0';
    ['low', 'mid', 'high'].forEach(function(preset) {
      var val = presets[preset];
      if (val == null) return;
      var btn = document.createElement('button');
      var labels = {low: 'Low', mid: 'Mid', high: 'High'};
      btn.className = 'mode-btn' + (fanSpeed === val ? ' active' : '');
      btn.textContent = labels[preset];
      btn.onclick = function(e) { e.stopPropagation(); setFan(d.id, preset); };
      presetRow.appendChild(btn);
    });
    card.appendChild(presetRow);
  }
```

**Step 4: Simplify setFan to just send the preset name**

Replace lines 1031-1034:

```javascript
function setFan(id, preset) {
  var labels = {low: 'Low', mid: 'Mid', high: 'High'};
  post('/api/device/' + id + '/fan_level', {level: preset}, 'Speed: ' + (labels[preset] || preset));
}
```

**Step 5: Remove fan slider CSS that's no longer needed**

Delete lines 366-384 (`.fan-row`, `.fan-slider`, `.fan-val` CSS rules). Keep `.card-expand-area` for now (no longer used but harmless).

**Step 6: Commit**

```bash
git add templates/dashboard.html
git commit -m "Replace broken fan slider with model-aware Low/Mid/High preset buttons"
```

---

### Task 6: Frontend — time input validation

**Files:**
- Modify: `templates/dashboard.html:1163-1206` (addScheduleRow, saveSchedules)

**Step 1: Add pattern attribute to time inputs in addScheduleRow**

After creating onInput and offInput (lines 1169-1176), add:

```javascript
  onInput.pattern = '[0-2][0-9]:[0-5][0-9]';
  offInput.pattern = '[0-2][0-9]:[0-5][0-9]';
```

**Step 2: Validate times in saveSchedules before sending**

After line 1213, add validation:

```javascript
  var timeRe = /^([01]\d|2[0-3]):[0-5]\d$/;
  for (var i = 0; i < pairs.length; i++) {
    if (!timeRe.test(pairs[i].on) || !timeRe.test(pairs[i].off)) {
      showToast('Invalid time format — use HH:MM', 'error');
      return;
    }
  }
```

**Step 3: Commit**

```bash
git add templates/dashboard.html
git commit -m "Add schedule time input validation (frontend + backend)"
```

---

### Task 7: Restart Flask and verify all fixes end-to-end

**Step 1: Kill existing Flask and restart**

```bash
taskkill //F //IM python.exe 2>/dev/null
cd "d:/UsersClaude/Xavier/Claude_Projects/XiaomiPurifier"
IQAIR_KEY=909478a1-319e-410b-b00b-4f7471062e5f WAQI_TOKEN=55d5cb4bfbcc67de8fc923d68e132005af92dfed python app.py &
```

Wait 8 seconds for first poll.

**Step 2: Verify fan_config in API response**

```bash
curl -s http://localhost:5000/api/status | python -c "
import sys, json; d = json.load(sys.stdin)
print('fan_config:', json.dumps(d.get('fan_config', {}), indent=2))
print('level_presets:', json.dumps(d.get('level_presets', {}), indent=2))
print('fan_speed (office):', d['devices'][0].get('fan_speed'))
"
```

Expected: FAN_SPEED_CONFIG and LEVEL_PRESETS dicts, plus fan_speed value per device.

**Step 3: Test Level preset on a device**

```bash
curl -s -X POST http://localhost:5000/api/device/office/fan_level \
  -H "Content-Type: application/json" -d '{"level":"low"}'
```

Expected: `{"ok": true, "fan_level": 1}` (mb5 low=1)

**Step 4: Test command rejection on offline device**

```bash
curl -s -X POST http://localhost:5000/api/device/nonexistent/power \
  -H "Content-Type: application/json" -d '{"power": true}'
```

Expected: `{"error": "Device offline or not found"}` with HTTP 503

**Step 5: Test explicit power (no toggle)**

```bash
curl -s -X POST http://localhost:5000/api/device/office/power \
  -H "Content-Type: application/json" -d '{"power": true}'
```

Expected: `{"ok": true, "power": true}`

**Step 6: Test schedule time validation**

```bash
curl -s -X POST http://localhost:5000/api/device/office/schedule \
  -H "Content-Type: application/json" -d '{"schedules":[{"on":"25:00","off":"08:00"}]}'
```

Expected: `{"error": "Invalid time format..."}` with HTTP 400

**Step 7: Test atomic write**

```bash
curl -s -X POST http://localhost:5000/api/device/office/schedule \
  -H "Content-Type: application/json" -d '{"schedules":[{"on":"07:00","off":"23:00"}]}'
# Verify file exists and is valid JSON
python -c "import json; print(json.load(open('schedules.json')))"
# Clean up
curl -s -X POST http://localhost:5000/api/device/office/schedule \
  -H "Content-Type: application/json" -d '{"clear":true}'
```

**Step 8: Test dashboard in browser**

Open http://localhost:5000 and verify:
- Gear icon → settings modal shows Level buttons (Low/Mid/High) instead of slider
- Click Low → fan slows, button highlights
- Click High → fan speeds up, button highlights
- Toggle power → explicit on/off, no race
- Invalid schedule time → red toast error

**Step 9: Final commit and push**

```bash
git push
```
