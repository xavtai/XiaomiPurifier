# Project Status

**Last updated:** 2026-03-31
**State:** IDLE — waiting for China SIM (~Apr 4) and Pi 5 purchase

## Completed (2026-03-31)

- Installed python-miio 0.5.12 (netifaces-plus workaround for Python 3.14)
- Extracted tokens for 5 Thai-set purifiers via Xiaomi cloud (passToken + micloud, 2FA via Playwright)
- Provisioned both China-set 4 Pros onto WiFi via raw miio protocol (`provision_china.py`)
- Verified 5/7 tokens work end-to-end (raw miio info command succeeds)
- China 4 Pro tokens rotate after WiFi join — need China Xiaomi account for stable tokens
- Ordered China Telecom tourist SIM from Shopee (154 baht, arriving ~Apr 4)
- Removed all purifiers from Deco Device Isolation
- Set DHCP reservations for all 7 purifiers
- Deco Parental Controls DNS block on China 4 Pros (ot.io.mi.com, ott.io.mi.com, io.mi.com)

## Blockers

- **China 4 Pro tokens:** Need China SIM → create CN Xiaomi account → add devices → extract stable tokens via cloud. SIM arriving ~Apr 4.

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
