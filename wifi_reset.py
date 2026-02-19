"""
Reset Button Handler
Detects long press (>3s) to delete credentials and reboot.
"""

import machine
import utime
import wifi_config
import wifi_credentials


def check_reset_button():
    """
    Check if reset button has been held for > RESET_HOLD_SEC.
    If so: delete credentials and reboot.
    Returns immediately if button not held long enough.
    """
    btn = machine.Pin(wifi_config.RESET_BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
    if btn.value() == 1:  # Not pressed (pulled up)
        return

    start = utime.ticks_ms()
    while btn.value() == 0:  # Held low
        if utime.ticks_diff(utime.ticks_ms(), start) >= wifi_config.RESET_HOLD_SEC * 1000:
            print("Reset button held >3s - clearing credentials and rebooting")
            wifi_credentials.delete_credentials()
            machine.reset()
        utime.sleep(0.1)
