# Xiaomi Air Purifier Local Control

Control and monitor Xiaomi air purifiers directly over your local WiFi — no Xiaomi app or cloud required. Works with China-set, Thailand-set, or any region.

## Quick Start

```bash
cd purifier_app
pip install -r requirements.txt
python app.py
# Open http://localhost:5000 on your phone (same WiFi)
```

## Setup

### Step 1: Find Your Purifiers' IPs

Check your router's DHCP/client list for devices with hostnames containing `zhimi` or `xiaomi`. Or:

```bash
# Auto-discover on local network
python discover.py
```

### Step 2: Get Device Tokens

Each Xiaomi device has a 32-character hex token needed for local communication.

**Method A — Xiaomi Cloud (Easiest)**
```bash
python discover.py --cloud
```
This logs into your Xiaomi account and retrieves tokens. For China-set devices, use server `cn`.

**Method B — Token Extractor Tool**
```bash
pip install xiaomi_token_extractor
python -m xiaomi_token_extractor
```

**Method C — All methods explained**
```bash
python discover.py --help-tokens
```

### Step 3: Configure `devices.json`

```json
{
  "devices": [
    {
      "id": "living_room",
      "name": "Living Room",
      "ip": "192.168.1.100",
      "token": "abcdef1234567890abcdef1234567890"
    },
    {
      "id": "bedroom_master",
      "name": "Master Bedroom",
      "ip": "192.168.1.101",
      "token": "1234567890abcdef1234567890abcdef"
    }
  ]
}
```

- **id**: Unique identifier (used in API URLs, no spaces)
- **name**: Display name on dashboard
- **ip**: Device's local IP address (set a static IP in your router for stability)
- **token**: 32-char hex token from Step 2

### Step 4: Run

```bash
python app.py
```

Open `http://<your-machine-ip>:5000` from any device on the same WiFi.

**Tip:** Bookmark this URL on your phone for quick access.

## Features

- **Live monitoring**: PM2.5 (AQI), temperature, humidity, motor speed
- **Power control**: Turn purifiers on/off
- **Mode control**: Auto, Silent, Favorite, Fan
- **Fan speed**: Adjustable slider (0-14) in Favorite mode
- **Filter tracking**: Remaining life percentage and hours used
- **LED/Buzzer toggle**: Control indicator light and beep sounds
- **Auto-refresh**: Status updates every 15 seconds
- **Dark/Light theme**: Toggle in top-right corner
- **Mobile-first**: Designed for phone control

## Supported Models

Works with most Xiaomi / Smartmi air purifiers:

| Protocol | Models |
|----------|--------|
| MiOT (newer) | Air Purifier 4, 4 Pro, 4 Lite, Pro H, 3C |
| Classic miio | Air Purifier 2S, 3H, Pro, 2H, Max |

The app auto-detects which protocol each purifier uses.

## Run as a Service (Optional)

To keep the app running after you close the terminal:

```bash
# Using systemd (Linux)
sudo tee /etc/systemd/system/purifier.service << EOF
[Unit]
Description=Xiaomi Air Purifier Control
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
ExecStart=$(which python3) app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now purifier.service
```

Or simply: `nohup python app.py &`

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `5000` | Port number |
| `DEBUG` | `0` | Set to `1` for Flask debug mode |

## Troubleshooting

**"Device offline"** — Check that:
1. The purifier is powered on and connected to WiFi
2. Your machine and purifier are on the same network/VLAN
3. The IP in `devices.json` is correct (IPs can change — set static IPs in router)
4. The token is correct (re-extract if needed)
5. UDP port 54321 is not blocked by a firewall

**"python-miio not installed"** — Run `pip install python-miio`

**Token extraction fails** — Try a different method (see `python discover.py --help-tokens`)

**Slow responses** — Normal; each device takes 1-2 seconds to respond. All 7 are polled in parallel.
