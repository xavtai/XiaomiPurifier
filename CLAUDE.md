# XiaomiPurifier

## Project Overview
Local control dashboard for 7 Xiaomi air purifiers in Chiang Mai. Flask app with waitress production server, background polling every 10s, remote access via SSH tunnel to VPS.

## Active System
- `app.py` — **Live production dashboard.** Waitress server, background polling, generic MiOT protocol for all models.
- `templates/dashboard.html` — Mobile-first responsive dashboard with AQI color coding, filter warnings, All On/Off.
- `devices.json` — Device configs with tokens (gitignored, contains secrets).
- `start.bat` — Starts Flask + SSH tunnel with auto-reconnect. Double-click to run.
- Remote: `https://app.xavbuilds.com/purifier/` (basic auth: admin/****)

## Setup Tools (used once, kept for reference)
- `extract_tokens.py` — Cloud token extraction with 2FA (passToken + micloud method)
- `provision_china.py` — Raw miio WiFi provisioner for unregistered China-set devices
- `discover.py` — Network discovery tool

## Key Technical Decisions
- Generic `Device.send('get_properties')` instead of model-specific python-miio classes (fixes xiaomi.airp.va2b support)
- Background polling thread with `_device_lock` for thread safety
- SSH reverse tunnel (not WireGuard) for remote access
- Basic auth on nginx `/purifier/` location block

## Crash Recovery
Read CHECKPOINT.md in the memory directory at session start. If ACTIVE, a previous session crashed — offer to resume. If IDLE + clean git tree, proceed normally. Full protocol details in the checkpoint file's frontmatter.
