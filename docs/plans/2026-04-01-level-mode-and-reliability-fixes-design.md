# Level Mode + Reliability Fixes

**Date**: 2026-04-01
**Status**: Approved

## Problem

1. The manual fan slider (0-14 via siid=2/piid=5) silently fails on every model — each uses different MiOT properties and ranges
2. All `dev.send()` calls ignore device response codes, returning fake success
3. Schedule manual override never expires, blocking the scheduler indefinitely
4. Power toggle uses read-then-flip which races with background polling
5. `schedules.json` writes aren't atomic — crash mid-write corrupts the file
6. Schedule time inputs accept invalid values with no feedback

## Design

### 1. Model-aware fan speed config

```python
FAN_SPEED_CONFIG = {
    "zhimi.airp.mb5":        {"siid": 2, "piid": 5, "min": 1, "max": 3},
    "xiaomi.airp.va2b":      {"siid": 2, "piid": 5, "min": 0, "max": 2},
    "zhimi.airp.rmb1":       {"siid": 9, "piid": 11, "min": 1, "max": 14},
    "xiaomi.airp.cpa4":      {"siid": 9, "piid": 11, "min": 1, "max": 14},
    "zhimi.airpurifier.mb4": {"siid": 9, "piid": 3,  "min": 300, "max": 2200},
}

LEVEL_PRESETS = {
    "zhimi.airp.mb5":        {"low": 1, "mid": 2, "high": 3},
    "xiaomi.airp.va2b":      {"low": 0, "mid": 1, "high": 2},
    "zhimi.airp.rmb1":       {"low": 3, "mid": 7, "high": 14},
    "xiaomi.airp.cpa4":      {"low": 3, "mid": 7, "high": 14},
    "zhimi.airpurifier.mb4": {"low": 600, "mid": 1200, "high": 2000},
}
```

- All models switch to Favorite mode (mode=2) before setting speed
- The speed property (siid/piid) is model-specific
- FAN_SPEED_CONFIG is included in `/api/status` response so the frontend knows each device's range

### 2. Level preset buttons (replaces slider)

In the settings modal, replace the broken 0-14 slider with:
```
Fan Speed
[  Low  ] [  Mid  ] [ High  ]
```

- Each button sends `POST /api/device/{id}/fan_level` with `{"level": "low"|"mid"|"high"}`
- Backend maps the string to the correct value via LEVEL_PRESETS
- Backend also accepts numeric values for backward compatibility
- Active button highlights based on current fan_level matching a preset value

### 3. Command response validation

```python
def _send_and_check(dev, props, action="command"):
    result = dev.send("set_properties", props)
    failures = [r for r in result if r.get("code", 0) != 0]
    if failures:
        codes = [f"code={r['code']}" for r in failures]
        return False, f"{action} rejected by device ({', '.join(codes)})"
    return True, None
```

Applied to: power, mode, fan_level, brightness, buzzer, child_lock, filter_reset, schedule commands.

Frontend: toast turns red on error, green on success.

### 4. Explicit power (no toggle race)

Frontend sends `{"power": true}` or `{"power": false}` explicitly. Backend no longer reads current state to flip — just sets what was requested. Eliminates the read-modify-write race.

### 5. Schedule hardening

- **Manual override TTL**: Clear after 60 minutes OR at boundary crossing
- **Atomic writes**: `json.dump()` to `schedules.json.tmp`, then `os.replace()` to `schedules.json`
- **Time validation**: Backend rejects times not matching `HH:MM` (00:00-23:59). Frontend adds `pattern="[0-2][0-9]:[0-5][0-9]"` to time inputs.

## Files to modify

- `app.py` — FAN_SPEED_CONFIG, LEVEL_PRESETS, _send_and_check, fix all endpoints, fix scheduler
- `templates/dashboard.html` — replace slider with Level buttons, explicit power, time validation

## Verification

1. Set Low/Mid/High on each model → hear fan speed change
2. Try a command on an offline device → see red error toast
3. Set schedule, manually override, wait 60min → scheduler resumes
4. Kill Flask mid-schedule-save → schedules.json not corrupted
5. Enter invalid time → rejected with error message
6. Rapid-click power → no double-toggle
