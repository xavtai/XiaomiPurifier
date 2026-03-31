# Project Status

**Last updated:** 2026-04-01
**State:** ACTIVE — Flask dashboard running, remote access live

## Completed

- All 7 purifier tokens extracted and verified (5 Thai-set cloud + 2 China-set uid provisioning)
- China 4 Pro token rotation solved: provisioned with uid → registered to SG cloud → stable tokens
- Flask dashboard rewritten with generic MiOT protocol (all models work including xiaomi.airp.va2b)
- Background polling: devices polled every 10s, API returns cached data instantly (~0.2s vs 3-8s)
- Remote access: SSH tunnel to VPS, nginx proxy at https://app.xavbuilds.com/purifier/
- Basic auth on remote endpoint (admin/****)
- Deco: purifiers un-isolated, DHCP reservations set for all 7
- New dashboard UI: mobile-first, AQI color coding, filter warnings, All On/Off

## How to Run

Double-click `start.bat` — starts Flask app + SSH tunnel with auto-reconnect.
- Local: http://localhost:5000
- Remote: https://app.xavbuilds.com/purifier/

## Hardware Decision (pending)

Pi 5 8GB ordered but under reconsideration. UPS for Deco modem is higher priority.
Flask dashboard on laptop covers burning season use case without Pi.

## Key Decisions

- Generic MiOT protocol (Device.send) instead of model-specific python-miio classes
- Background polling thread with cached status (instant API responses)
- SSH reverse tunnel for remote access (no VPN, no Nabu Casa)
- Basic auth on nginx for remote security
