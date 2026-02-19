"""
STA (Station) Mode - Connect to WiFi using saved credentials.
"""

import network
import utime
import wifi_config
import wifi_credentials


def connect_sta(ssid=None, password=None):
    """
    Attempt to connect to WiFi in STA mode.
    Uses provided ssid/password or loads from credential file.
    Returns True if connected, False otherwise.
    """
    if ssid is None or password is None:
        ssid, password = wifi_credentials.get_credentials()
    if not ssid:
        return False

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(ssid, password)

    start = utime.ticks_ms()
    while not wlan.isconnected():
        if utime.ticks_diff(utime.ticks_ms(), start) >= wifi_config.CONNECT_TIMEOUT_SEC * 1000:
            return False
        utime.sleep(0.5)

    return True


def try_connect_sta_with_retries():
    """
    Try to connect using saved credentials, up to MAX_RETRIES times.
    Returns True if connected, False if all retries failed.
    """
    for attempt in range(1, wifi_config.MAX_RETRIES + 1):
        print(f"STA connect attempt {attempt}/{wifi_config.MAX_RETRIES}...")
        if connect_sta():
            return True
        utime.sleep(1)
    return False
