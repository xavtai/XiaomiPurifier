# XiaomiPurifier

## Project Overview
Local control dashboard for 7 Xiaomi air purifiers in Chiang Mai. Flask app with waitress production server, background polling every 10s, remote access via SSH tunnel to VPS. Outdoor AQI from IQAir (Mae Hia) with WAQI fallback.

## Active System
- `app.py` — **Live production dashboard.** Waitress server, background polling, generic MiOT protocol for all models. Includes: outdoor AQI polling, spike detection, device settings (buzzer/child lock/brightness), daily scheduling with manual override.
- `templates/dashboard.html` — Mobile-first responsive dashboard with 6-tier AQI color coding, hero bar (outdoor/indoor AQI + floor averages + status), settings modal (gear icon), Low/Mid/High fan presets on Manual mode, schedule labels, filter reset with model-specific guides, model name labels on cards.
- `devices.json` — Device configs with tokens (gitignored, contains secrets). Also holds `outdoor.lat/lon` for AQI station coordinates.
- `schedules.json` — Per-device on/off schedules (created on first save).
- `.env` — API keys for IQAir and WAQI (gitignored). Read by `start.bat` at launch; `app.py` also reads it directly as a fallback if env vars are missing.
- `watchdog.pyw` — **Auto-recovery for Flask.** Runs silently via pythonw. Monitors Flask every 15s, restarts on crash with 5-crash backoff. Checks tunnel health via public URL and nudges ssh.exe if stale. Does NOT spawn SSH directly (pythonw no-console can't keep ssh.exe alive). Logs to `watchdog.log`.
- `ssh-tunnel.bat` — **SSH reverse tunnel.** Self-reconnecting `:loop` running in its own cmd.exe. Uses `127.0.0.1:5050` explicitly (not `localhost` — Windows native ssh resolves that to ::1 first and Flask is IPv4-only). Logs to `ssh-tunnel.log`. Launched by start-silent.vbs at logon.
- `start-silent.vbs` — Idempotent logon launcher. Checks Flask AND ssh.exe independently, launches whichever is missing. Invoked by Task Scheduler `PurifierDashboardLogon` (onlogon trigger, user context, no admin). Startup folder NOT used — had ~7 min delay.
- `start.bat` — Manual recovery launcher. Idempotent: real tunnel health check (VPS-side curl through tunnel), starts only what's missing. Safe to double-click anytime.
- `setup-logon-task.ps1` — One-shot script to (re)register the `PurifierDashboardLogon` scheduled task if needed.
- `restart.sh` — Bash equivalent of `start.bat` for Claude Code / unix shells. CRLF-safe `.env` parsing, lockfile, health checks, SSH auto-reconnect. Run via `bash restart.sh`.
- Remote: `https://app.xavbuilds.com/purifier/` (basic auth: admin/****)

## Setup Tools (used once, kept for reference)
- `extract_tokens.py` — Cloud token extraction with 2FA (passToken + micloud method)
- `provision_china.py` — Raw miio WiFi provisioner for unregistered China-set devices
- `discover.py` — Network discovery tool

## Key Technical Decisions
- Generic `Device.send('get_properties')` instead of model-specific python-miio classes (fixes xiaomi.airp.va2b support)
- Background polling thread with `_device_lock` (device cache) and `_state_lock` (shared state) for thread safety
- SSH reverse tunnel (not WireGuard) for remote access
- Basic auth on nginx `/purifier/` location block
- Screen brightness siid/piid varies by model — `SCREEN_PROP` dict maps model → MiOT property
- Scheduling uses `_manual_override` dict to prevent scheduler from undoing user actions until next boundary crossing
- IQAir API primary (returns Mae Hia, local to Hang Dong), WAQI as fallback
- `_poll_ready` event prevents double-poll race on first API request

## Crash Recovery
Read CHECKPOINT.md in the memory directory at session start. If ACTIVE, a previous session crashed — offer to resume. If IDLE + clean git tree, proceed normally. Full protocol details in the checkpoint file's frontmatter.
