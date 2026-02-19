"""
One-time setup: create wifi_creds.json with your WiFi credentials.
Run this on the Pico (or copy the generated file) before first boot,
or use AP mode (connect to pico_control) to configure via web UI.

Usage: Edit SSID and PASSWORD below, then run:
  python setup_wifi_creds.py
"""
import json

SSID = "your_wifi_ssid"
PASSWORD = "your_wifi_password"

with open("wifi_creds.json", "w") as f:
    json.dump({"ssid": SSID, "password": PASSWORD}, f)
print("Created wifi_creds.json")
