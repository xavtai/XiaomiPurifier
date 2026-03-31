# Project Status

**Last updated:** 2026-03-31
**State:** IDLE — all 7/7 tokens working, waiting for Pi 5 purchase

## Completed (2026-03-31)

- Installed python-miio 0.5.12 (netifaces-plus workaround for Python 3.14)
- Extracted tokens for 5 Thai-set purifiers via Xiaomi cloud (passToken + micloud, 2FA via Playwright)
- Provisioned both China-set 4 Pros onto WiFi via raw miio protocol (`provision_china.py`)
- Solved China 4 Pro token rotation: provisioned with Xavier's uid → devices registered to SG cloud account → stable cloud-managed tokens
- Verified ALL 7/7 tokens work end-to-end (raw miio info command succeeds)
- Removed all purifiers from Deco Device Isolation
- Set DHCP reservations for all 7 purifiers

## Blockers

None. All tokens stable and verified.

## Current Priorities

1. China SIM arrives → create CN account → stabilize China 4 Pro tokens
2. Order Pi 5 8GB kit (~$300 SGD)
3. Flash HA OS → HACS + xiaomi_miot_auto → add all 7 purifiers
4. Build Jeane-friendly dashboard

## Key Decisions

- Pivoted from custom Flask app to Home Assistant on Pi 5 8GB
- `xiaomi_miot_auto` (HACS) as default integration, not built-in Xiaomi Miio
- Remote access via WireGuard to VPS (skip Nabu Casa)
- Separate Telegram bot for HA (not xavier-assistant)
- Ethernet for Pi, not WiFi
- Pi justification: purifier control + AdGuard Home + WireGuard + BLE sensors + Google Home integration
- Camera dashboard is NOT viable (Xiaomi cameras don't expose RTSP)
