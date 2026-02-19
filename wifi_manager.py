"""
WiFi Manager - Main orchestrator following the flowchart logic.
Coordinates: reset check, STA mode, AP mode, LED, reboot.
"""

import machine
import utime
import ntptime
import wifi_config
import wifi_credentials
import wifi_reset
import wifi_sta
import wifi_ap


def _led_on():
    """Turn LED steady on (connected)."""
    led = machine.Pin(wifi_config.LED_PIN, machine.Pin.OUT)
    led.value(1)


def _led_off():
    """Turn LED off."""
    led = machine.Pin(wifi_config.LED_PIN, machine.Pin.OUT)
    led.value(0)


def ensure_wifi():
    """
    Ensure WiFi is connected. Follows the flowchart:
    1. Check reset button (>3s) -> delete creds, reboot
    2. If credentials exist -> try STA connect (up to 3 retries)
    3. If connected -> LED on, return
    4. If no creds or 3 failed -> AP mode
    5. AP: user configures -> try connect -> if success: save, reboot
    6. If AP config fails 3x -> stay in AP, user can retry
    """
    # 1. Reset button check
    wifi_reset.check_reset_button()

    # 2. Credential file available?
    if wifi_credentials.has_credentials():
        # Try STA connect with retries
        if wifi_sta.try_connect_sta_with_retries():
            _led_on()
            _sync_time()
            return  # Connected in STA mode

        # 3rd try failed -> fall through to AP mode

    # 4. No credentials or STA failed -> AP mode
    _led_off()
    while True:
        success = wifi_ap.run_ap_config_loop()
        if success:
            # Save already done in wifi_ap; brief delay then reboot
            utime.sleep(2)
            machine.reset()
        # Else: 3rd try failed, loop continues (user sees "Try again" and can retry)


def _sync_time():
    """Sync RTC with NTP if connected."""
    try:
        ntptime.settime()
        print("Time synchronized.")
    except Exception:
        print("Time sync failed.")


def get_ip():
    """Return current STA IP or None."""
    import network
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        return wlan.ifconfig()[0]
    return None
