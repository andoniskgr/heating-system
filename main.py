"""
Heating System Controller with WiFi Manager

WiFi Configuration:
- WiFi credentials are stored in wifi_config.json
- On first run or after reset, the system will scan for networks and prompt for selection
- To reset WiFi config: Hold GPIO0 button for 3 seconds during power-up
- WiFi credentials persist across reboots

Usage:
- Connect via USB serial to configure WiFi interactively
- Or use set_wifi_credentials("SSID", "password") programmatically
- Or hold GPIO0 button on startup to reset and reconfigure
"""

import network
import urequests
import utime
import machine
import json
import ntptime

# --- Configuration ---
WIFI_CONFIG_FILE = "wifi_config.json"
FIREBASE_URL = "https://homeautomation-ecd71-default-rtdb.firebaseio.com/"
FIREBASE_AUTH = "AIzaSyCjYikZfY96MyqrczvvFItllPZI9BSPjog"

# --- Hardware Pins ---
# Start with relay OFF (active-low: HIGH = OFF)
RELAY_PIN = machine.Pin(15, machine.Pin.OUT, value=1)
TRIG = machine.Pin(3, machine.Pin.OUT)
ECHO = machine.Pin(2, machine.Pin.IN)
# GPIO0 reset button: Connect button between GPIO0 and GND (active-low with pull-up)
# Note: GPIO0 is also BOOTSEL on Pico, but works as regular GPIO after boot
RESET_BUTTON = machine.Pin(
    0, machine.Pin.IN, machine.Pin.PULL_UP)  # GPIO0 with pull-up
utime.sleep_ms(100)  # Small delay to stabilize pin after initialization


def load_wifi_config():
    """Load WiFi credentials from file"""
    try:
        with open(WIFI_CONFIG_FILE, 'r') as f:
            config = json.loads(f.read())
            return config.get('ssid'), config.get('password')
    except:
        return None, None


def save_wifi_config(ssid, password):
    """Save WiFi credentials to file"""
    try:
        config = {'ssid': ssid, 'password': password}
        with open(WIFI_CONFIG_FILE, 'w') as f:
            f.write(json.dumps(config))
        print(f"WiFi credentials saved for: {ssid}")
        return True
    except Exception as e:
        print(f"Error saving WiFi config: {e}")
        return False


def set_wifi_credentials(ssid, password):
    """
    Helper function to programmatically set WiFi credentials.
    Usage: set_wifi_credentials("YourSSID", "YourPassword")
    """
    if save_wifi_config(ssid, password):
        print("WiFi credentials updated. Reconnect to apply changes.")
        return True
    return False


def test_reset_button():
    """
    Test function to check if reset button is working.
    Call this from REPL to test button functionality.
    """
    print("Testing reset button (GPIO0)...")
    print("Press and release the button to test.")
    print("Button state: 0 = pressed, 1 = released")
    print("Press Ctrl+C to exit test\n")

    try:
        while True:
            state = RESET_BUTTON.value()
            status = "PRESSED" if state == 0 else "RELEASED"
            print(f"Button state: {state} ({status})", end="\r")
            utime.sleep_ms(100)
    except KeyboardInterrupt:
        print("\n\nTest ended.")


def delete_wifi_config():
    """Delete WiFi configuration file"""
    try:
        import os
        os.remove(WIFI_CONFIG_FILE)
        print("WiFi configuration deleted")
        return True
    except:
        return False


def check_reset_button():
    """Check if reset button is held for 3 seconds during startup"""
    print("Checking reset button (GPIO0)...")

    # Read initial button state for debugging
    initial_state = RESET_BUTTON.value()
    print(
        f"Initial button state: {initial_state} (0=pressed/active-low, 1=released)")

    # Check if button is already pressed at startup
    # Button is active-low: value 0 means pressed, value 1 means released
    if initial_state == 0:
        print("Button is already pressed! Hold for 3 seconds to reset...")
        button_pressed_time = utime.ticks_ms()
    else:
        print("Hold button for 3 seconds to reset WiFi configuration...")
        print("(You have 5 seconds to press the button)")

        button_pressed_time = None
        max_wait_time = 5000  # Wait up to 5 seconds for button press
        start_time = utime.ticks_ms()

        # Wait for button to be pressed (up to 5 seconds)
        while utime.ticks_diff(utime.ticks_ms(), start_time) < max_wait_time:
            button_state = RESET_BUTTON.value()
            if button_state == 0:  # Button pressed (active-low with pull-up)
                button_pressed_time = utime.ticks_ms()
                print("Button pressed! Hold for 3 seconds...")
                break
            utime.sleep_ms(50)  # Check every 50ms

    # If button was pressed, check if it's held for 3 seconds
    check_duration = 3000  # 3 seconds in milliseconds

    if button_pressed_time is not None:
        last_print_time = button_pressed_time
        while utime.ticks_diff(utime.ticks_ms(), button_pressed_time) < check_duration:
            button_state = RESET_BUTTON.value()
            if button_state != 0:  # Button released
                print("\nButton released too early. Reset cancelled.")
                return False

            # Show progress every second
            elapsed = utime.ticks_diff(utime.ticks_ms(), button_pressed_time)
            if utime.ticks_diff(utime.ticks_ms(), last_print_time) >= 1000:
                remaining = (check_duration - elapsed) // 1000
                if remaining > 0:
                    print(f"Hold... {remaining} seconds remaining", end="\r")
                last_print_time = utime.ticks_ms()

            utime.sleep_ms(50)  # Check every 50ms

        # Button was held for 3 seconds!
        print("\n\nReset button held for 3 seconds - Resetting WiFi configuration!")
        delete_wifi_config()
        return True

    print("No button press detected, continuing...")
    return False


def scan_wifi():
    """Scan for available WiFi networks"""
    print("Scanning for WiFi networks...")
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    networks = wlan.scan()

    # Sort by signal strength (RSSI) - higher is better
    networks.sort(key=lambda x: x[3], reverse=True)

    print("\nAvailable networks:")
    print("-" * 50)
    for i, net in enumerate(networks):
        ssid = net[0].decode('utf-8') if isinstance(net[0], bytes) else net[0]
        rssi = net[3]
        security = "Open" if net[4] == 0 else "Secured"
        print(f"{i+1:2d}. {ssid:30s} (RSSI: {rssi:4d} dBm, {security})")

    return networks


def wifi_manager():
    """Interactive WiFi manager to select and configure network"""
    print("\n=== WiFi Manager ===")

    # Scan for networks
    networks = scan_wifi()

    if not networks:
        print("No networks found!")
        return None, None

    # Display networks and get selection
    print("\nSelect a network to connect:")
    print("Enter network number (1-{}) or 0 to cancel: ".format(len(networks)), end="")

    try:
        # Try to get input from serial/USB (if connected)
        selection = input().strip()
        selection_num = int(selection)

        if selection_num == 0:
            print("Cancelled.")
            return None, None

        if 1 <= selection_num <= len(networks):
            selected_net = networks[selection_num - 1]
            ssid = selected_net[0].decode(
                'utf-8') if isinstance(selected_net[0], bytes) else selected_net[0]

            # Check if network is secured
            if selected_net[4] != 0:
                print(f"Enter password for '{ssid}': ", end="")
                password = input().strip()
            else:
                password = ""
                print(f"Network '{ssid}' is open (no password required)")

            return ssid, password
        else:
            print("Invalid selection.")
            return None, None
    except (ValueError, EOFError, OSError):
        # No serial input available (headless operation)
        print("\nNo serial input available (headless mode).")
        print("Please connect via USB serial to configure WiFi,")
        print("or modify code to use default credentials.")
        return None, None


def connect_wifi():
    """Connect to WiFi using stored credentials or prompt for new ones"""
    # Check reset button first
    if check_reset_button():
        print("WiFi configuration reset. Please configure WiFi.")

    # Try to load saved credentials
    ssid, password = load_wifi_config()

    # If no saved credentials, use WiFi manager
    if not ssid:
        print("\nNo saved WiFi credentials found.")
        print("Starting WiFi Manager...")

        # Use WiFi manager to get credentials
        ssid, password = wifi_manager()

        if not ssid:
            print("WiFi configuration cancelled or failed.")
            print("Cannot connect to WiFi. System will not start.")
            return False

        # Save credentials for next time
        if save_wifi_config(ssid, password):
            print("WiFi credentials saved.")

    # Connect to WiFi
    if not ssid:
        print("No WiFi credentials available. Cannot connect.")
        return False

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    # Disconnect if already connected to a different network
    if wlan.isconnected():
        current_ssid = wlan.config('essid')
        if current_ssid != ssid:
            wlan.disconnect()
            utime.sleep(1)

    print(f"Connecting to WiFi: {ssid}", end="")
    wlan.connect(ssid, password)

    # Wait for connection (max 20 seconds)
    timeout = 20
    elapsed = 0
    while not wlan.isconnected() and elapsed < timeout:
        print(".", end="")
        utime.sleep(1)
        elapsed += 1

    if wlan.isconnected():
        print(f"\nConnected! IP: {wlan.ifconfig()[0]}")
        try:
            ntptime.settime()  # Sync Pico clock with internet time
            print("Time synchronized.")
        except:
            print("Time sync failed. Check internet connection.")
        return True
    else:
        print(f"\nConnection failed! Could not connect to {ssid}")
        print("Possible reasons:")
        print("  - Wrong password")
        print("  - Network out of range")
        print("  - Network not available")
        print("\nHold GPIO0 button for 3 seconds on next startup to reset WiFi config")
        return False


def get_distance():
    """Returns the distance from ultrasonic sensor in cm"""
    TRIG.low()
    utime.sleep_us(2)
    TRIG.high()
    utime.sleep_us(10)
    TRIG.low()

    # Wait for echo
    while ECHO.value() == 0:
        signaloff = utime.ticks_us()
    while ECHO.value() == 1:
        signalon = utime.ticks_us()

    timepassed = signalon - signaloff
    distance = (timepassed * 0.0343) / 2
    return round(distance, 2)


def get_timestamp():
    """Generates a formatted string: YYYY-MM-DD HH:MM:SS"""
    t = utime.localtime()
    return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(t[0], t[1], t[2], t[3], t[4], t[5])


def update_firebase(is_on, level):
    """Sends current state and logs to Firebase"""
    print(f"\n[update_firebase called] is_on={is_on}, level={level}")
    ts = get_timestamp()
    status_str = "ON" if is_on else "OFF"

    # 1. Update Current Status
    system_data = {
        "current_status": status_str,
        "current_level": level,
        "last_update": ts
    }
    try:
        url = f"{FIREBASE_URL}system.json?auth={FIREBASE_AUTH}"
        # Convert to JSON string and set headers explicitly
        json_data = json.dumps(system_data)
        headers = {"Content-Type": "application/json"}

        print(f"Updating Firebase: {json_data}")
        r = urequests.patch(url, data=json_data, headers=headers)

        # Check status code and response
        print(f"Response code: {r.status_code}, Response: {r.text[:100]}")
        if r.status_code == 200:
            print(f"✓ Status updated: {status_str} | {level}cm")
        else:
            print(f"✗ Status update failed (code {r.status_code}): {r.text}")

        r.close()

        # 2. Append to History Log
        log_entry = {"time": ts, "status": status_str, "level": level}
        url_log = f"{FIREBASE_URL}history.json?auth={FIREBASE_AUTH}"
        json_log = json.dumps(log_entry)

        print(f"Logging to history: {json_log}")
        r = urequests.post(url_log, data=json_log, headers=headers)

        # Check status code
        print(
            f"History response code: {r.status_code}, Response: {r.text[:100]}")
        if r.status_code == 200:
            print(f"✓ History logged")
        else:
            print(f"✗ History log failed (code {r.status_code}): {r.text}")

        r.close()
    except Exception as e:
        print("Firebase Update Error:", e)
        import sys
        sys.print_exception(e)


def test_firebase_connection():
    """Test Firebase connection with a simple write"""
    try:
        test_url = f"{FIREBASE_URL}test.json?auth={FIREBASE_AUTH}"
        test_data = json.dumps(
            {"test": "connection", "timestamp": get_timestamp()})
        headers = {"Content-Type": "application/json"}

        print("Testing Firebase connection...")
        r = urequests.put(test_url, data=test_data, headers=headers)
        print(f"Test response: code {r.status_code}, body: {r.text[:200]}")
        r.close()

        if r.status_code == 200:
            print("✓ Firebase connection successful!")
            return True
        else:
            print(f"✗ Firebase connection failed: {r.status_code}")
            return False
    except Exception as e:
        print(f"Firebase test error: {e}")
        import sys
        sys.print_exception(e)
        return False


# --- Main Logic ---
last_periodic_check = 0
# THIRTY_MINUTES_MS = 30 * 60 * 1000  # 30 minutes for production
THIRTY_MINUTES_MS = 60 * 1000  # 1 min for testing; use 30*60*1000 for production

# Track last processed commands to prevent duplicate processing
last_processed_sys_cmd = None
last_processed_manual_update = None


def run():
    """Entry point: connect WiFi, test Firebase, then run command loop."""
    global last_periodic_check

    # Connect to WiFi
    if not connect_wifi():
        print("WiFi connection failed. System cannot continue.")
        print("Hold GPIO0 button for 3 seconds on next startup to reset WiFi config.")
        return

    test_firebase_connection()  # Test connection at startup
    last_periodic_check = utime.ticks_ms()
    print("System running...")
    _main_loop()


def _main_loop():
    global last_periodic_check, last_processed_sys_cmd, last_processed_manual_update
    while True:
        try:
            # Check for commands from Kodular
            cmd_url = f"{FIREBASE_URL}command.json?auth={FIREBASE_AUTH}"
            r = urequests.get(cmd_url)

            if r.status_code == 200:
                response = r.json()

                if response:
                    # Debug: Print received response
                    print(f"Received command: {response}")

                    # 1. Check System ON/OFF buttons
                    # Handle both "ON"/"OFF" (with quotes) and ON/OFF (without quotes)
                    sys_cmd = response.get("system_cmd")
                    if sys_cmd:
                        # Strip quotes if they exist (handles "ON" -> ON, "OFF" -> OFF)
                        sys_cmd_clean = str(sys_cmd).strip('"').strip("'")
                        print(
                            f"System command: '{sys_cmd}' (cleaned: '{sys_cmd_clean}')")

                        # Only process if this is a new command (different from last processed)
                        if sys_cmd_clean != last_processed_sys_cmd:
                            if sys_cmd_clean == "ON":
                                RELAY_PIN.low()  # Active-low: LOW = ON
                                print("System turned ON")
                                # Update Firebase with new status and current level
                                update_firebase(True, get_distance())
                                last_processed_sys_cmd = sys_cmd_clean
                            elif sys_cmd_clean == "OFF":
                                RELAY_PIN.high()  # Active-low: HIGH = OFF
                                print("System turned OFF")
                                # Update Firebase with OFF status (status change notification only)
                                update_firebase(False, get_distance())
                                last_processed_sys_cmd = sys_cmd_clean
                        else:
                            print(
                                f"Skipping duplicate system_cmd: {sys_cmd_clean}")

                    # 2. Check Manual Data Update Request
                    # Android app sets manual_update to true to trigger a data refresh without energizing relay
                    manual_update = response.get("manual_update")
                    if manual_update is not None:
                        # Handle both boolean (true/false) and string ("true"/"false") values
                        is_request = False
                        if isinstance(manual_update, bool):
                            is_request = manual_update
                        elif isinstance(manual_update, str):
                            is_request = manual_update.lower().strip('"').strip("'") == "true"
                        else:
                            is_request = bool(manual_update)

                        print(
                            f"Manual update value: {manual_update} (boolean: {is_request})")

                        # Only process if this is a new request (true) and different from last processed
                        if is_request and manual_update != last_processed_manual_update:
                            print(
                                "Manual data request received - updating Firebase without energizing relay.")
                            # Update Firebase with current system state regardless of relay status
                            # Active-low: value 0 (LOW) means ON, value 1 (HIGH) means OFF
                            is_relay_on = (RELAY_PIN.value() == 0)
                            update_firebase(is_relay_on, get_distance())
                            # Reset manual_update to false to acknowledge processing
                            reset_data = json.dumps({"manual_update": False})
                            reset_r = urequests.patch(
                                cmd_url, data=reset_data, headers={"Content-Type": "application/json"})
                            if reset_r.status_code != 200:
                                print(
                                    f"Failed to reset manual_update (code {reset_r.status_code})")
                            else:
                                # Only update last_processed_manual_update after successful reset
                                last_processed_manual_update = manual_update
                            reset_r.close()
                        elif is_request:
                            print(
                                f"Skipping duplicate manual_update: {manual_update}")
                        else:
                            # Reset tracking when manual_update is false
                            last_processed_manual_update = None
                # else: response is empty/None, which is fine - just no commands to process

                r.close()
            else:
                print(f"Command poll failed (code {r.status_code}): {r.text}")
                r.close()

        except Exception as e:
            print("Polling Error:", e)

        # 3. Periodic Update (Every 30 mins) ONLY if System is ON
        # Data is sent to Firebase only when relay is ON or manually requested
        # Active-low: value 0 (LOW) means ON, value 1 (HIGH) means OFF
        if RELAY_PIN.value() == 0:  # Only send when relay is ON
            if utime.ticks_diff(utime.ticks_ms(), last_periodic_check) > THIRTY_MINUTES_MS:
                update_firebase(True, get_distance())
                last_periodic_check = utime.ticks_ms()

        utime.sleep(2)  # Poll Firebase every 2 seconds


if __name__ == "__main__":
    run()
