"""Extract Xiaomi device tokens with 2FA support.

Run this in a terminal:  python extract_tokens.py
It will open your browser for 2FA verification, then pull all device tokens.

NOTE: The 2FA retry approach in this script may not work for accounts with
email-based 2FA (each login attempt triggers a new challenge). The proven
method is: use Playwright to complete 2FA in a real browser, extract the
passToken cookie, then inject it into micloud to bypass 2FA. See the project
conversation history for the working approach.
"""
import requests
import hashlib
import json
import hmac
import base64
import os
import time
import sys
import webbrowser

USERNAME = ""  # your Xiaomi email
PASSWORD = ""  # your Xiaomi password
SERVERS = ["sg", "i2", "de", "us", "cn"]

def login(session):
    """Login to Xiaomi, handling 2FA if needed."""
    # Step 1: Get sign
    resp = session.get("https://account.xiaomi.com/pass/serviceLogin?sid=xiaomiio&_json=true")
    data = json.loads(resp.text.replace("&&&START&&&", ""))
    sign = data.get("_sign")

    # Step 2: Authenticate
    post = {
        "sid": "xiaomiio",
        "hash": hashlib.md5(PASSWORD.encode()).hexdigest().upper(),
        "callback": "https://sts.api.io.mi.com/sts",
        "qs": "%3Fsid%3Dxiaomiio%26_json%3Dtrue",
        "user": USERNAME,
        "_json": "true",
        "_sign": sign,
    }
    resp = session.post("https://account.xiaomi.com/pass/serviceLoginAuth2", data=post)
    data = json.loads(resp.text.replace("&&&START&&&", ""))

    # Check for 2FA
    if data.get("notificationUrl") and not data.get("ssecurity"):
        print("\n2FA verification required!")
        print("Opening your browser now...")
        webbrowser.open(data["notificationUrl"])
        print("\n  1. Check your email for a verification code")
        print("  2. Enter the code in the browser page that just opened")
        print("  3. Wait for the browser page to finish loading (you'll see a blank page or Xiaomi page)")
        print("  4. Come back here and press Enter\n")
        input("Press Enter after completing verification... ")

        # After 2FA is approved server-side, retry login with the SAME session.
        # The 2FA approval is tied to the account, not the session — so a fresh
        # login attempt should now succeed without 2FA.
        print("Retrying login after 2FA approval...")
        for attempt in range(3):
            time.sleep(2)  # Small delay for server-side propagation
            resp = session.get("https://account.xiaomi.com/pass/serviceLogin?sid=xiaomiio&_json=true")
            data2 = json.loads(resp.text.replace("&&&START&&&", ""))
            post["_sign"] = data2.get("_sign")
            resp = session.post("https://account.xiaomi.com/pass/serviceLoginAuth2", data=post)
            data = json.loads(resp.text.replace("&&&START&&&", ""))

            if data.get("ssecurity") and data.get("location"):
                print(f"  Login succeeded on attempt {attempt + 1}!")
                break
            print(f"  Attempt {attempt + 1}: still pending (result={data.get('result')})...")
        else:
            print("Login still failing after 2FA. The verification might not have completed.")
            print(f"Last response: {json.dumps(data, indent=2, ensure_ascii=True)}")
            sys.exit(1)

        location = data["location"]
        session.get(location, allow_redirects=True)
        service_token = session.cookies.get("serviceToken")

        if not service_token:
            print("Failed to get service token after 2FA.")
            sys.exit(1)

        return session, str(data["userId"]), service_token

    if not data.get("ssecurity"):
        print(f"Login failed: {data.get('description', 'unknown error')}")
        sys.exit(1)

    # Step 3: Get service token (no 2FA case)
    location = data["location"]
    session.get(location, allow_redirects=True)
    service_token = session.cookies.get("serviceToken")
    if not service_token:
        print("Failed to get service token")
        sys.exit(1)

    return session, str(data["userId"]), service_token


def get_devices(session, user_id, service_token):
    """Fetch devices from all Xiaomi cloud servers."""
    all_devices = []

    for country in SERVERS:
        try:
            url = f"https://{country}.api.io.mi.com/app/home/device_list"
            headers = {"x-xiaomi-protocal-flag-cli": "PROTOCAL-HTTP2"}
            cookies = {"userId": user_id, "serviceToken": service_token, "locale": "en_GB"}
            payload = {"data": '{"getVirtualModel":false,"getHuamiDevices":0}'}

            resp = session.post(url, data=payload, headers=headers, cookies=cookies)
            result = resp.json()

            if result.get("code") == 0 and result.get("result", {}).get("list"):
                devices = result["result"]["list"]
                for d in devices:
                    d["_server"] = country
                all_devices.extend(devices)
        except Exception as e:
            print(f"  Error querying {country}: {e}")

    return all_devices


def main():
    print("=" * 50)
    print("  Xiaomi Cloud Token Extractor")
    print("=" * 50)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Android-7.1.1-1.0.0-ONEPLUS A3010-136-QKlKERsXZJOmkGaQmFYkpEMKaaaaxoRR APP/xiaomi.smarthome APPV/62830",
    })

    print(f"\nLogging in as {USERNAME}...")
    session, user_id, service_token = login(session)
    print(f"Logged in! User ID: {user_id}")

    print(f"\nSearching servers: {', '.join(SERVERS)}...")
    devices = get_devices(session, user_id, service_token)

    if not devices:
        print("\nNo devices found on any server!")
        print("Your devices might be on a different server region.")
        sys.exit(1)

    # Display results
    print(f"\n{'=' * 50}")
    print(f"  Found {len(devices)} device(s)")
    print(f"{'=' * 50}")

    purifiers = []
    for d in devices:
        model = d.get("model", "?")
        name = d.get("name", "?")
        ip = d.get("localip", "?")
        token = d.get("token", "?")
        did = d.get("did", "?")
        mac = d.get("mac", "?")
        server = d.get("_server", "?")

        is_purifier = "airp" in model.lower() or "air-purifier" in model.lower() or "airpurifier" in model.lower()

        print(f"\n  {'>>> AIR PURIFIER <<<' if is_purifier else ''}")
        print(f"  Name:   {name}")
        print(f"  Model:  {model}")
        print(f"  IP:     {ip}")
        print(f"  Token:  {token}")
        print(f"  DID:    {did}")
        print(f"  MAC:    {mac}")
        print(f"  Server: {server}")

        if is_purifier:
            purifiers.append(d)

    # Save to file
    output = {
        "extracted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": user_id,
        "all_devices": devices,
        "purifiers": purifiers,
    }
    outfile = os.path.join(os.path.dirname(__file__), "tokens_extracted.json")
    with open(outfile, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n\nFull results saved to: {outfile}")
    print(f"Found {len(purifiers)} air purifier(s) out of {len(devices)} total device(s).")


if __name__ == "__main__":
    main()
