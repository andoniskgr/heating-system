import urequests
import utime
import machine
import json

# --- Configuration ---
FIREBASE_URL = "https://homeautomation-ecd71-default-rtdb.firebaseio.com/"
FIREBASE_AUTH = "AIzaSyCjYikZfY96MyqrczvvFItllPZI9BSPjog"

# --- Hardware Pins ---
# Start with relay OFF (active-low: HIGH = OFF)
RELAY_PIN = machine.Pin(15, machine.Pin.OUT, value=1)
TRIG = machine.Pin(3, machine.Pin.OUT)
ECHO = machine.Pin(2, machine.Pin.IN)


def connect_wifi():
    """Connect via WiFi Manager (STA/AP flow, credentials from file)."""
    import wifi_manager
    wifi_manager.ensure_wifi()
    print("Connected! IP:", wifi_manager.get_ip())


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
    connect_wifi()
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
