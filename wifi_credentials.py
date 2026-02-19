"""
WiFi Credential Management
Read, write, and delete WiFi credentials from file.
"""

import json
import wifi_config


def get_credentials():
    """
    Read WiFi credentials from file.
    Returns (ssid, password) tuple or (None, None) if file missing/invalid.
    """
    try:
        with open(wifi_config.CREDENTIAL_FILE, "r") as f:
            data = json.load(f)
        ssid = data.get("ssid")
        password = data.get("password", "")
        if ssid:
            return (str(ssid), str(password))
    except (OSError, ValueError, KeyError):
        pass
    return (None, None)


def save_credentials(ssid, password):
    """Save WiFi credentials to file."""
    with open(wifi_config.CREDENTIAL_FILE, "w") as f:
        json.dump({"ssid": ssid, "password": password}, f)


def delete_credentials():
    """Delete the credential file."""
    try:
        import os
        os.remove(wifi_config.CREDENTIAL_FILE)
    except OSError:
        pass


def has_credentials():
    """Check if credential file exists and contains valid data."""
    ssid, _ = get_credentials()
    return ssid is not None
