"""Provision a China-set Xiaomi Air Purifier 4 Pro onto home WiFi.

Uses raw miio protocol (no python-miio library) because the library's
socket handling conflicts with multiple network adapters on Windows.

Instructions:
1. Run this script while connected to the purifier's hotspot
2. It will auto-detect the device and send WiFi credentials
"""
import hashlib
import json
import os
import socket
import struct
import sys
import time
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# Your home WiFi credentials (IOT network)
WIFI_SSID = ""  # your IoT WiFi SSID
WIFI_PASSWORD = ""  # your IoT WiFi password

# Purifier's IP in AP mode
AP_IP = "192.168.99.1"
MIIO_PORT = 54321


def md5(data: bytes) -> bytes:
    return hashlib.md5(data).digest()


def encrypt(token: bytes, plaintext: bytes) -> bytes:
    key = md5(token)
    iv = md5(key + token)
    cipher = Cipher(algorithms.AES128(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    # PKCS7 padding
    pad_len = 16 - (len(plaintext) % 16)
    padded = plaintext + bytes([pad_len] * pad_len)
    return encryptor.update(padded) + encryptor.finalize()


def decrypt(token: bytes, ciphertext: bytes) -> bytes:
    key = md5(token)
    iv = md5(key + token)
    cipher = Cipher(algorithms.AES128(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    # Remove PKCS7 padding
    pad_len = padded[-1]
    return padded[:-pad_len]


def build_msg(token: bytes, device_id: int, stamp: int, data: bytes = b"") -> bytes:
    """Build a miio protocol message."""
    if not data:
        # Hello packet
        return bytes.fromhex("21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffff")

    encrypted = encrypt(token, data)
    length = 32 + len(encrypted)
    header = struct.pack(">HHIII", 0x2131, length, 0, device_id, stamp)
    checksum_input = header + token + encrypted
    checksum = md5(checksum_input)
    return header + checksum + encrypted


def parse_response(data: bytes, token: bytes):
    """Parse a miio protocol response."""
    if len(data) < 32:
        return None
    magic, length, unknown, device_id, stamp = struct.unpack(">HHIII", data[:16])
    resp_token = data[16:32]
    if length > 32:
        payload = data[32:]
        try:
            decrypted = decrypt(token, payload)
            return json.loads(decrypted.decode())
        except Exception as e:
            return {"_error": str(e), "_raw": payload.hex()}
    return {"_handshake": True, "device_id": device_id, "stamp": stamp, "token": resp_token.hex()}


def send_command(sock, ip, token_bytes, device_id, stamp, method, params=None):
    """Send a miio command and return the response."""
    cmd = {
        "id": int(time.time() % 10000),
        "method": method,
    }
    if params is not None:
        cmd["params"] = params

    payload = json.dumps(cmd).encode()
    msg = build_msg(token_bytes, device_id, stamp + 1, payload)

    sock.sendto(msg, (ip, MIIO_PORT))
    sock.settimeout(5)
    try:
        resp_data, _ = sock.recvfrom(4096)
        return parse_response(resp_data, token_bytes)
    except socket.timeout:
        return {"_error": "timeout"}


def main():
    print("=" * 55)
    print("  China-set Air Purifier 4 Pro — WiFi Provisioner")
    print("  (Raw miio protocol — no library dependency)")
    print("=" * 55)
    print()
    print(f"  Target WiFi: {WIFI_SSID}")
    print(f"  Purifier IP: {AP_IP}")
    print()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(3)

    # Phase 1: Handshake
    print("  Sending handshake...")
    hello = bytes.fromhex("21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffff")
    sock.sendto(hello, (AP_IP, MIIO_PORT))

    try:
        resp_data, _ = sock.recvfrom(4096)
    except socket.timeout:
        print("  ERROR: No response from purifier. Are you connected to its hotspot?")
        sys.exit(1)

    if len(resp_data) < 32:
        print(f"  ERROR: Invalid response ({len(resp_data)} bytes)")
        sys.exit(1)

    # Parse handshake
    magic, length, unknown, device_id, stamp = struct.unpack(">HHIII", resp_data[:16])
    token_bytes = resp_data[16:32]
    token_hex = token_bytes.hex()

    print(f"\n  CONNECTED!")
    print(f"  Device ID: {device_id}")
    print(f"  Stamp:     {stamp}")
    print(f"  Token:     {token_hex}")
    print()

    # Phase 2: Get device info
    print("  Getting device info (miIO.info)...")
    info = send_command(sock, AP_IP, token_bytes, device_id, stamp, "miIO.info")
    if info and "_error" not in info:
        result = info.get("result", info)
        model = result.get("model", "?")
        fw = result.get("fw_ver", "?")
        hw = result.get("hw_ver", "?")
        mac = result.get("mac", "?")
        print(f"  Model:     {model}")
        print(f"  Firmware:  {fw}")
        print(f"  Hardware:  {hw}")
        print(f"  MAC:       {mac}")
    else:
        print(f"  Info response: {info}")
        model = "unknown"
        mac = "unknown"
    print()

    # Phase 3: Send WiFi credentials
    print(f"  Sending WiFi credentials for '{WIFI_SSID}'...")
    wifi_result = send_command(sock, AP_IP, token_bytes, device_id, stamp + 1,
                               "miIO.config_router",
                               {"ssid": WIFI_SSID, "passwd": WIFI_PASSWORD, "uid": 0})
    print(f"  Response: {wifi_result}")
    print()

    if wifi_result and wifi_result.get("result") == ["ok"]:
        print("  *** SUCCESS! WiFi credentials accepted! ***")
        print()
        print("  The purifier should now join your home WiFi.")
        print("  Switch back to your normal WiFi and check your")
        print("  Deco app for a new device on the network.")
    elif wifi_result and wifi_result.get("result", {}) == "ok":
        print("  *** SUCCESS! WiFi credentials accepted! ***")
    else:
        print("  WiFi provisioning response was unexpected.")
        print("  Check the response above to see if it worked.")

    # Save results
    result_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "device_id": device_id,
        "token": token_hex,
        "model": model,
        "mac": mac,
        "wifi_ssid": WIFI_SSID,
        "wifi_response": str(wifi_result),
    }

    outfile = os.path.join(os.path.dirname(os.path.abspath(__file__)), "china_provision_result.json")
    with open(outfile, "w") as f:
        json.dump(result_data, f, indent=2)

    print(f"\n  Results saved to: {outfile}")
    print("=" * 55)

    sock.close()


if __name__ == "__main__":
    main()
