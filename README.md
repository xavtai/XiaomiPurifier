# Xiaomi Air Purifier — Token Extraction & Provisioning Tools

Tools for extracting device tokens and provisioning Xiaomi air purifiers for local control. Tokens are needed by Home Assistant or any local control system using the miio protocol.

**Status:** Pivoted from custom Flask app to Home Assistant on Raspberry Pi 5. The Flask app (`app.py`) is archived — not actively developed. The token extraction and provisioning scripts are the active tools.

## Tools

### `extract_tokens.py` — Cloud token extraction (Thai-set / cloud-registered devices)

Logs into Xiaomi cloud to retrieve tokens for devices registered to your account.
Handles 2FA via browser redirect.

```bash
pip install python-miio requests
python extract_tokens.py
```

Note: For accounts with email-based 2FA, the script's retry approach may fail.
The proven method is passToken injection via Playwright + micloud. See project memory for details.

### `provision_china.py` — WiFi provisioning (China-set / unregistered devices)

Provisions unregistered Xiaomi devices onto your WiFi using raw miio protocol.
Uses raw UDP sockets (not python-miio) to avoid Windows multi-adapter issues.

```bash
# 1. Factory reset the purifier (hold button ~5s)
# 2. Connect laptop WiFi to the purifier's hotspot (xiaomi-airp-xxx)
# 3. Run:
python provision_china.py
```

Edit `WIFI_SSID` and `WIFI_PASSWORD` in the script before running.

### `discover.py` — Local network discovery

Scans for Xiaomi devices on the local network via mDNS and handshake.

```bash
python discover.py
python discover.py --cloud       # Cloud token extraction (basic, no 2FA)
python discover.py --help-tokens # Manual extraction methods
```

### `app.py` — Flask dashboard (archived)

Original custom Flask dashboard for purifier control. Superseded by Home Assistant.
Still functional if you want a standalone web UI without HA.

## Supported Models (tested)

| Model | miio model string | Protocol | Provisioning |
|-------|-------------------|----------|-------------|
| Air Purifier 4 | zhimi.airp.mb5 | MiOT | Cloud token |
| Air Purifier 4 Lite | zhimi.airp.rmb1 | MiOT | Cloud token |
| Air Purifier 4 Compact | xiaomi.airp.cpa4 | MiOT | Cloud token |
| Air Purifier 3C | zhimi.airpurifier.mb4 | MiOT | Cloud token |
| Air Purifier 4 Pro (CN) | xiaomi.airp.va2b | MiOT | AP mode provisioning |

## Troubleshooting

**provision_china.py times out** — `python-miio` socket handling fails with multiple network adapters (e.g., NordVPN). The script uses raw sockets to bypass this. If the raw handshake test works but the script doesn't, check for VPN adapters.

**extract_tokens.py 2FA fails** — Use Playwright browser automation to complete 2FA, extract the passToken cookie, then inject into micloud. See project conversation history.

**Purifier AP mode IP** — Not always `192.168.8.1`. Check `ipconfig` (Windows) or `ifconfig` (Mac/Linux) for the gateway IP when connected to the purifier hotspot. Tested: `192.168.99.1`.
