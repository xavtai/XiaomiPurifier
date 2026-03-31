#!/usr/bin/env python3
"""Discover Xiaomi devices on the local network and help extract tokens.

Usage:
    python discover.py              # Scan local network for devices
    python discover.py --cloud      # Extract tokens via Xiaomi cloud login
"""

import argparse
import sys


def scan_network():
    """Use miio discovery to find devices on the local network."""
    try:
        from miio import Discovery
    except ImportError:
        print("python-miio not installed. Run: pip install python-miio")
        sys.exit(1)

    print("Scanning local network for Xiaomi devices...")
    print("(This takes about 5 seconds)\n")

    devices = Discovery.discover_mdns(timeout=5)

    if not devices:
        print("No devices found via mDNS. Trying handshake scan...")
        # Try broadcast handshake — finds devices that don't advertise via mDNS
        from miio.miioprotocol import MiIOProtocol
        proto = MiIOProtocol()
        try:
            info = proto.info()
            print(f"  Found: {info}")
        except Exception:
            pass

    if not devices:
        print("No devices found automatically.\n")
        print("Tips:")
        print("  1. Check your router's DHCP table for devices with 'zhimi' or 'xiaomi' in hostname")
        print("  2. Try: miiocli discover")
        print("  3. Use the cloud token method: python discover.py --cloud")
        return

    print(f"Found {len(devices)} device(s):\n")
    for addr, dev in devices.items():
        print(f"  IP: {addr}")
        print(f"  Model: {getattr(dev, 'model', 'unknown')}")
        token = getattr(dev, "token", None)
        if token and token != "0" * 32 and token != "f" * 32:
            print(f"  Token: {token}")
        else:
            print("  Token: (hidden — use cloud method to extract)")
        print()


def cloud_tokens():
    """Extract device tokens from Xiaomi cloud account."""
    try:
        from miio.cloud import CloudInterface
    except ImportError:
        print("Cloud interface not available in your python-miio version.")
        print("Try: pip install python-miio[cloud]")
        print("\nAlternative: use the micloud package:")
        print("  pip install micloud")
        print("  micloud get-token --username YOUR_EMAIL --password YOUR_PASS --server cn")
        return

    import getpass

    print("=== Xiaomi Cloud Token Extractor ===\n")
    print("This logs into your Xiaomi account to retrieve device tokens.")
    print("Use the account that originally set up the China-set purifiers.\n")

    username = input("Xiaomi account (email/phone): ")
    password = getpass.getpass("Password: ")

    servers = ["cn", "de", "us", "ru", "tw", "sg", "in", "i2"]
    print(f"\nAvailable servers: {', '.join(servers)}")
    server = input("Server (cn for China-set devices): ").strip() or "cn"

    try:
        cloud = CloudInterface(username, password)
        devices = cloud.get_devices(server)
    except Exception as e:
        print(f"\nError: {e}")
        print("If login failed, check your credentials.")
        print("For China-set devices, use server 'cn'.")
        return

    print(f"\nFound {len(devices)} device(s) on server '{server}':\n")
    for dev in devices:
        name = dev.get("name", "Unknown")
        model = dev.get("model", "Unknown")
        ip = dev.get("localip", "Unknown")
        token = dev.get("token", "Unknown")
        did = dev.get("did", "")

        print(f"  Name:  {name}")
        print(f"  Model: {model}")
        print(f"  IP:    {ip}")
        print(f"  Token: {token}")
        print(f"  DID:   {did}")

        if "airpurifier" in model.lower() or "air-purifier" in model.lower():
            print("  ^^^ This is an air purifier!")
        print()

    print("Copy the token values into devices.json for each purifier.")


def print_manual_instructions():
    """Print manual token extraction methods."""
    print("""
=== Manual Token Extraction Methods ===

METHOD 1: Xiaomi Cloud Tokens (Easiest)
----------------------------------------
  python discover.py --cloud
  - Logs into your Xiaomi account and retrieves all device tokens
  - For China-set devices, use server "cn"
  - Use the Xiaomi account that set up those purifiers

METHOD 2: Mi Home App Database (Android, requires root or older app)
--------------------------------------------------------------------
  1. Install Mi Home app v5.4.54 (older version stores tokens in plain text)
  2. Add your devices to the app
  3. Find the database: /data/data/com.xiaomi.smarthome/databases/miio2.db
  4. Open with SQLite browser, table "devicerecord", column "token"

METHOD 3: Modified Mi Home App (Android, no root needed)
--------------------------------------------------------
  1. Download modified Mi Home from github.com/nickneos/Xiaomi-cloud-tokens-extractor
  2. Or use: pip install xiaomi_token_extractor
  3. Run: python -m xiaomi_token_extractor

METHOD 4: Packet Sniffing (Advanced)
-------------------------------------
  1. Factory reset the purifier (hold button 5+ seconds until beep)
  2. Sniff WiFi setup packets — the token is sent in plaintext during provisioning
  3. Tools: Wireshark with miio dissector

After extracting tokens, add them to devices.json:
  {
    "devices": [
      {
        "id": "living_room",
        "name": "Living Room Purifier",
        "ip": "192.168.1.100",
        "token": "your_32_char_hex_token_here_0000"
      }
    ]
  }
""")


def main():
    parser = argparse.ArgumentParser(description="Discover Xiaomi devices and extract tokens")
    parser.add_argument("--cloud", action="store_true", help="Extract tokens via Xiaomi cloud login")
    parser.add_argument("--help-tokens", action="store_true", help="Show manual token extraction methods")
    args = parser.parse_args()

    if args.help_tokens:
        print_manual_instructions()
    elif args.cloud:
        cloud_tokens()
    else:
        scan_network()
        print("\n--- For more token extraction methods: python discover.py --help-tokens ---")


if __name__ == "__main__":
    main()
