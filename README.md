# Xiaomi Air Purifier Control

Local dashboard for controlling 7 Xiaomi air purifiers over WiFi using the MiOT protocol. No Xiaomi cloud or app required for control. Works with China-set, Thailand-set, or any region.

## Quick Start

```bash
pip install -r requirements.txt
python app.py
# Open http://localhost:5000 on your phone (same WiFi)
```

Or double-click `start.bat` to also start the SSH tunnel for remote access.

## Dashboard

- Real-time AQI, temperature, humidity, motor speed, filter life for all 7 purifiers
- Power on/off, mode switching (Auto/Silent/Custom/Fan), fan level control
- All On / All Off buttons
- Background polling every 10s — instant page loads
- Mobile-first responsive layout
- Remote access at `https://app.xavbuilds.com/purifier/` (basic auth)

## Setup Tools

### Token Extraction (cloud-registered devices)
```bash
python extract_tokens.py
```
Logs into Xiaomi cloud to retrieve device tokens. Handles 2FA via browser. The proven method for 2FA accounts is passToken injection via Playwright + micloud.

### WiFi Provisioning (unregistered China-set devices)
```bash
# 1. Factory reset purifier (hold button ~5s)
# 2. Connect laptop to purifier's hotspot
python provision_china.py
```
Uses raw miio UDP protocol (not python-miio) to avoid Windows multi-adapter socket issues. Edit WIFI_SSID, WIFI_PASSWORD, and XIAOMI_UID before running.

### Network Discovery
```bash
python discover.py
python discover.py --help-tokens
```

## Supported Models (tested)

| Model | miio string | Notes |
|-------|------------|-------|
| Air Purifier 4 | zhimi.airp.mb5 | Full support |
| Air Purifier 4 Lite | zhimi.airp.rmb1 | Full support |
| Air Purifier 4 Compact | xiaomi.airp.cpa4 | No temp/humidity sensor |
| Air Purifier 3C | zhimi.airpurifier.mb4 | No temp/humidity sensor |
| Air Purifier 4 Pro (CN) | xiaomi.airp.va2b | Provisioned via raw miio, registered to SG account via uid trick |

## Troubleshooting

**provision_china.py times out** — python-miio socket handling fails with multiple network adapters (NordVPN etc). Script uses raw sockets to bypass this.

**Purifier AP mode IP** — Not always 192.168.8.1. Check `ipconfig` for the gateway when connected to the purifier hotspot. Tested: 192.168.99.1.

**China 4 Pro token rotation** — Provision with `uid` + `country_domain` to register to your cloud account. Tokens become cloud-managed and stable.
