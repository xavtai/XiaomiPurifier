# Project Status

**Last updated:** 2026-03-31
**State:** IDLE — waiting for Pi 5 hardware

## Completed (2026-03-31)

- Installed python-miio 0.5.12 (netifaces-plus workaround for Python 3.14)
- Extracted tokens for 5 Thai-set purifiers via Xiaomi cloud (passToken + micloud, 2FA handled via Playwright browser automation)
- Provisioned both China-set Air Purifier 4 Pro units onto WiFi via raw miio protocol (`provision_china.py`)
- Removed all purifiers from Deco Device Isolation
- Set DHCP reservations for all 7 purifiers
- All 7 tokens captured and IPs locked

## Current Priorities

1. Order Pi 5 kit (~4,500-5,000 baht)
2. Flash Home Assistant OS onto NVMe SSD
3. Install HACS + xiaomi_miot_auto
4. Add all 7 purifiers to HA
5. Build Jeane-friendly dashboard

## Key Decisions

- Pivoted from custom Flask app to Home Assistant on Pi 5
- `xiaomi_miot_auto` (HACS) as default integration, not built-in Xiaomi Miio
- Remote access via WireGuard to VPS (skip Nabu Casa)
- Separate Telegram bot for HA (not xavier-assistant)
- Ethernet for Pi, not WiFi
