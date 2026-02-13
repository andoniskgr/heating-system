"""
Heating System Controller with WiFi Manager

WiFi Configuration:
- WiFi credentials are stored in wifi_config.json
- On first run or after reset, the system will scan for networks and prompt for selection
- To reset WiFi config: Hold GPIO0 button for 3 seconds during power-up
- WiFi credentials persist across reboots

WiFi Management Options:
1. Terminal Commands (via USB Serial/REPL):
   - Call terminal_command_interface() for interactive command-line interface
   - Commands: 
     * wifi scan - Scan for networks
     * wifi status - Show connection status
     * wifi connect <ssid> <password> - Connect to network
     * wifi ap - Create access point "PicoWiFiManager" (for testing)
     * wifi manager - Start web-based WiFi manager
     * wifi reset - Delete saved credentials
   
2. Web-Based Manager (Mobile Phone):
   - Call wifi_manager_web_server() to start web server
   - If not connected to WiFi, creates access point "PicoWiFiManager"
   - Connect phone to WiFi/AP and visit the displayed IP address
   - Mobile-friendly web interface for scanning and connecting to networks

3. Programmatic:
   - Use set_wifi_credentials("SSID", "password") from REPL
   - Use create_wifi_ap() to create access point directly
   - Or hold GPIO0 button on startup to reset and reconfigure

Usage Examples:
  # Terminal interface
  terminal_command_interface()
  
  # Test access point creation
  create_wifi_ap()
  
  # Web manager (mobile phone)
  wifi_manager_web_server()
  
  # Direct connection
  set_wifi_credentials("MyWiFi", "mypassword")
"""

import network
import urequests
import utime
import machine
import json
import ntptime
import socket
import _thread

# --- Configuration ---
WIFI_CONFIG_FILE = "wifi_config.json"
FIREBASE_URL = "https://homeautomation-ecd71-default-rtdb.firebaseio.com/"
FIREBASE_AUTH = "AIzaSyCjYikZfY96MyqrczvvFItllPZI9BSPjog"
WIFI_MANAGER_PORT = 80  # Web server port for WiFi manager

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


def get_wifi_status():
    """Get current WiFi connection status"""
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        ifconfig = wlan.ifconfig()
        ssid = wlan.config('essid')
        return {
            'connected': True,
            'ssid': ssid,
            'ip': ifconfig[0],
            'subnet': ifconfig[1],
            'gateway': ifconfig[2],
            'dns': ifconfig[3]
        }
    else:
        return {'connected': False}


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


def create_wifi_ap(ssid="PicoWiFiManager", password=""):
    """Create a WiFi access point (standalone function for testing)"""
    print(f"\n=== Creating WiFi Access Point: {ssid} ===")

    wlan = network.WLAN(network.STA_IF)
    ap = network.WLAN(network.AP_IF)

    # Disable STA interface
    print("Disabling STA interface...")
    wlan.active(False)
    utime.sleep(0.5)

    # Activate AP interface
    print("Activating AP interface...")
    ap.active(False)  # Ensure it's off first
    utime.sleep(0.5)
    ap.active(True)
    utime.sleep(1)  # Wait for AP to initialize

    # Configure AP
    print(f"Configuring AP: SSID='{ssid}'...")
    if password:
        ap.config(essid=ssid, password=password,
                  authmode=network.AUTH_WPA2_PSK, channel=11)
    else:
        ap.config(essid=ssid, password="",
                  authmode=network.AUTH_OPEN, channel=11)
    utime.sleep(1)  # Wait for configuration to apply

    # Get AP info
    if ap.active():
        ap_ip = ap.ifconfig()[0]
        ap_config = ap.ifconfig()
        print(f"\n✓ Access Point created successfully!")
        print(f"  SSID: '{ssid}'")
        print(f"  Password: {'(set)' if password else '(none - open)'}")
        print(f"  IP Address: {ap_config[0]}")
        print(f"  Subnet Mask: {ap_config[1]}")
        print(f"  Gateway: {ap_config[2]}")
        print(f"  DNS: {ap_config[3]}")
        print(f"  Channel: 11")
        print(f"\nConnect your device to '{ssid}' and visit:")
        print(f"  http://{ap_ip}")
        return True
    else:
        print("✗ Failed to create Access Point!")
        return False


def wifi_manager_web_server():
    """Start a web server for WiFi manager accessible from mobile phone"""
    print("\n=== Starting WiFi Manager Web Server ===")

    # Create access point if not connected to WiFi
    wlan = network.WLAN(network.STA_IF)
    ap = network.WLAN(network.AP_IF)

    if not wlan.isconnected():
        print("Not connected to WiFi. Creating access point...")

        # Disable STA interface to avoid conflicts
        wlan.active(False)
        utime.sleep(0.5)

        # Activate AP interface
        ap.active(False)  # Ensure it's off first
        utime.sleep(0.5)
        ap.active(True)
        utime.sleep(1)  # Wait for AP to initialize

        # Configure AP with explicit settings
        ap.config(essid="PicoWiFiManager", password="",
                  authmode=network.AUTH_OPEN, channel=11)
        utime.sleep(1)  # Wait for configuration to apply

        # Get AP IP address
        ap_ip = ap.ifconfig()[0]

        # Verify AP is active
        if ap.active():
            print(f"✓ Access Point created successfully!")
            print(f"  SSID: 'PicoWiFiManager'")
            print(f"  IP Address: {ap_ip}")
            print(f"  Channel: 11")
            print(f"\nConnect your phone to 'PicoWiFiManager' and visit:")
            print(f"  http://{ap_ip}")
            print("\nNote: The AP has no password - it's open for configuration.")
        else:
            print("✗ Failed to create Access Point!")
            print("Please check your Pico's WiFi capabilities.")
            return
    else:
        ap_ip = wlan.ifconfig()[0]
        print(f"WiFi Manager available at: http://{ap_ip}")
        print("Connect your phone to the same WiFi network and visit the IP above")

    # Create socket server
    addr = socket.getaddrinfo('0.0.0.0', WIFI_MANAGER_PORT)[0][-1]
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(addr)
    s.listen(1)

    print(f"WiFi Manager web server listening on port {WIFI_MANAGER_PORT}")
    print("Press Ctrl+C to stop the server\n")

    try:
        while True:
            cl, addr = s.accept()
            print(f"Connection from {addr}")

            try:
                request = cl.recv(1024).decode('utf-8')
                print(f"Request: {request[:100]}...")

                # Parse request
                if 'GET / ' in request or 'GET /index' in request:
                    # Show WiFi networks list
                    networks = scan_wifi()
                    html = generate_wifi_list_html(networks, ap_ip)
                    send_response(cl, html)

                elif 'POST /connect' in request:
                    # Handle connection request
                    # Parse form data
                    content_length = 0
                    for line in request.split('\n'):
                        if 'Content-Length:' in line:
                            content_length = int(line.split(':')[1].strip())

                    # Read POST data
                    post_data = ""
                    if content_length > 0:
                        post_data = cl.recv(content_length).decode('utf-8')

                    # Parse SSID and password
                    ssid = None
                    password = ""
                    for item in post_data.split('&'):
                        if 'ssid=' in item:
                            ssid = item.split('ssid=')[1].split('&')[0]
                            # URL decode
                            ssid = ssid.replace('+', ' ').replace('%20', ' ')
                        elif 'password=' in item:
                            password = item.split('password=')[1].split('&')[0]
                            password = password.replace(
                                '+', ' ').replace('%20', ' ')

                    if ssid:
                        print(f"Connecting to: {ssid}")
                        result = connect_to_wifi(ssid, password)
                        html = generate_connection_result_html(
                            result, ssid, ap_ip)
                        send_response(cl, html)
                    else:
                        html = generate_error_html("Invalid request", ap_ip)
                        send_response(cl, html)

                elif 'GET /status' in request:
                    # Show WiFi status
                    status = get_wifi_status()
                    html = generate_status_html(status, ap_ip)
                    send_response(cl, html)

                else:
                    # 404
                    html = generate_error_html("Page not found", ap_ip)
                    send_response(cl, html)

            except Exception as e:
                print(f"Error handling request: {e}")
                import sys
                sys.print_exception(e)
                html = generate_error_html(str(e), ap_ip)
                send_response(cl, html)
            finally:
                cl.close()

    except KeyboardInterrupt:
        print("\n\nStopping WiFi Manager web server...")
    finally:
        s.close()
        if ap.active():
            ap.active(False)
            print("Access Point disabled")


def generate_wifi_list_html(networks, ip):
    """Generate HTML page showing available WiFi networks"""
    networks_html = ""
    if networks:
        for i, net in enumerate(networks):
            ssid = net[0].decode(
                'utf-8') if isinstance(net[0], bytes) else net[0]
            rssi = net[3]
            security = net[4] != 0
            security_text = "🔒 Secured" if security else "🔓 Open"
            signal_bars = "█" * min(5, max(1, (rssi + 100) // 20))

            networks_html += f"""
            <div class="network-item">
                <div class="network-info">
                    <strong>{ssid}</strong>
                    <span class="security">{security_text}</span>
                    <span class="signal">Signal: {signal_bars} ({rssi} dBm)</span>
                </div>
                <form method="POST" action="/connect" class="connect-form">
                    <input type="hidden" name="ssid" value="{ssid}">
                    <input type="hidden" name="security" value="{security}">
                    {"<input type='password' name='password' placeholder='Password' required class='password-input'>" if security else ""}
                    <button type="submit" class="connect-btn">Connect</button>
                </form>
            </div>
            """
    else:
        networks_html = "<p>No networks found. Please try again.</p>"

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WiFi Manager - Pico</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        }}
        h1 {{
            color: #333;
            margin-bottom: 10px;
            text-align: center;
        }}
        .subtitle {{
            text-align: center;
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }}
        .network-item {{
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 15px;
            background: #f9f9f9;
        }}
        .network-info {{
            margin-bottom: 10px;
        }}
        .network-info strong {{
            display: block;
            font-size: 18px;
            color: #333;
            margin-bottom: 5px;
        }}
        .security {{
            display: inline-block;
            background: #e3f2fd;
            color: #1976d2;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            margin-right: 10px;
        }}
        .signal {{
            display: block;
            color: #666;
            font-size: 12px;
            margin-top: 5px;
        }}
        .connect-form {{
            display: flex;
            gap: 10px;
            align-items: center;
        }}
        .password-input {{
            flex: 1;
            padding: 10px;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 14px;
        }}
        .connect-btn {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.2s;
        }}
        .connect-btn:active {{
            transform: scale(0.95);
        }}
        .status-link {{
            display: block;
            text-align: center;
            margin-top: 20px;
            color: #667eea;
            text-decoration: none;
            font-weight: bold;
        }}
        .message {{
            background: #e8f5e9;
            border: 2px solid #4caf50;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
            color: #2e7d32;
        }}
        .error {{
            background: #ffebee;
            border-color: #f44336;
            color: #c62828;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📶 WiFi Manager</h1>
        <p class="subtitle">Select a network to connect</p>
        {networks_html}
        <a href="/status" class="status-link">View WiFi Status</a>
    </div>
</body>
</html>"""
    return html


def generate_connection_result_html(result, ssid, ip):
    """Generate HTML page showing connection result"""
    if result:
        message = f"Successfully connected to {ssid}!"
        status = get_wifi_status()
        if status['connected']:
            details = f"<p>IP Address: {status['ip']}</p><p>Gateway: {status['gateway']}</p>"
        else:
            details = "<p>Connecting...</p>"
        css_class = "message"
    else:
        message = f"Failed to connect to {ssid}. Please try again."
        details = "<p>Check your password and try again.</p>"
        css_class = "message error"

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Connection Result - Pico</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        }}
        h1 {{ color: #333; margin-bottom: 20px; text-align: center; }}
        .message {{
            background: #e8f5e9;
            border: 2px solid #4caf50;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
            color: #2e7d32;
        }}
        .error {{
            background: #ffebee;
            border-color: #f44336;
            color: #c62828;
        }}
        .link {{
            display: block;
            text-align: center;
            margin-top: 20px;
            color: #667eea;
            text-decoration: none;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Connection Result</h1>
        <div class="{css_class}">
            <p><strong>{message}</strong></p>
            {details}
        </div>
        <a href="/" class="link">← Back to Networks</a>
        <a href="/status" class="link">View WiFi Status</a>
    </div>
</body>
</html>"""
    return html


def generate_status_html(status, ip):
    """Generate HTML page showing WiFi status"""
    if status['connected']:
        status_html = f"""
        <div class="message">
            <h2>✅ Connected</h2>
            <p><strong>SSID:</strong> {status['ssid']}</p>
            <p><strong>IP Address:</strong> {status['ip']}</p>
            <p><strong>Subnet Mask:</strong> {status['subnet']}</p>
            <p><strong>Gateway:</strong> {status['gateway']}</p>
            <p><strong>DNS:</strong> {status['dns']}</p>
        </div>
        """
    else:
        status_html = """
        <div class="message error">
            <h2>❌ Not Connected</h2>
            <p>Not connected to any WiFi network.</p>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WiFi Status - Pico</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        }}
        h1 {{ color: #333; margin-bottom: 20px; text-align: center; }}
        .message {{
            background: #e8f5e9;
            border: 2px solid #4caf50;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
            color: #2e7d32;
        }}
        .error {{
            background: #ffebee;
            border-color: #f44336;
            color: #c62828;
        }}
        .link {{
            display: block;
            text-align: center;
            margin-top: 20px;
            color: #667eea;
            text-decoration: none;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📡 WiFi Status</h1>
        {status_html}
        <a href="/" class="link">← Back to Networks</a>
    </div>
</body>
</html>"""
    return html


def generate_error_html(error_msg, ip):
    """Generate HTML error page"""
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Error - Pico</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        }}
        h1 {{ color: #333; margin-bottom: 20px; text-align: center; }}
        .message {{
            background: #ffebee;
            border: 2px solid #f44336;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
            color: #c62828;
        }}
        .link {{
            display: block;
            text-align: center;
            margin-top: 20px;
            color: #667eea;
            text-decoration: none;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>⚠️ Error</h1>
        <div class="message">
            <p>{error_msg}</p>
        </div>
        <a href="/" class="link">← Back to Networks</a>
    </div>
</body>
</html>"""
    return html


def send_response(cl, html):
    """Send HTTP response to client"""
    cl.send('HTTP/1.0 200 OK\r\nContent-type: text/html\r\n\r\n')
    cl.send(html)
    cl.close()


def connect_to_wifi(ssid, password):
    """Connect to WiFi network and save credentials"""
    try:
        # Save credentials
        if save_wifi_config(ssid, password):
            print(f"Credentials saved for: {ssid}")

        # Connect
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)

        # Disconnect if already connected
        if wlan.isconnected():
            wlan.disconnect()
            utime.sleep(1)

        print(f"Connecting to: {ssid}")
        wlan.connect(ssid, password)

        # Wait for connection (max 15 seconds)
        timeout = 15
        elapsed = 0
        while not wlan.isconnected() and elapsed < timeout:
            utime.sleep(1)
            elapsed += 1

        if wlan.isconnected():
            print(f"Connected! IP: {wlan.ifconfig()[0]}")
            try:
                ntptime.settime()
                print("Time synchronized.")
            except:
                print("Time sync failed.")
            return True
        else:
            print("Connection failed!")
            return False
    except Exception as e:
        print(f"Connection error: {e}")
        import sys
        sys.print_exception(e)
        return False


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


def terminal_command_interface():
    """Terminal command interface for WiFi management"""
    print("\n" + "="*60)
    print("WiFi Terminal Commands")
    print("="*60)
    print("Available commands:")
    print("  wifi scan              - Scan for available WiFi networks")
    print("  wifi status            - Show current WiFi connection status")
    print("  wifi connect <ssid> <password> - Connect to WiFi network")
    print("  wifi ap                - Create WiFi access point 'PicoWiFiManager'")
    print("  wifi manager           - Start web-based WiFi manager (mobile phone)")
    print("  wifi reset             - Delete saved WiFi credentials")
    print("  help                   - Show this help message")
    print("  exit                   - Exit terminal interface")
    print("="*60 + "\n")

    while True:
        try:
            print("> ", end="")
            cmd = input().strip()

            if not cmd:
                continue

            parts = cmd.split()
            command = parts[0].lower()

            if command == "exit" or command == "quit":
                print("Exiting terminal interface...")
                break

            elif command == "help":
                print("\nAvailable commands:")
                print("  wifi scan              - Scan for available WiFi networks")
                print("  wifi status            - Show current WiFi connection status")
                print("  wifi connect <ssid> <password> - Connect to WiFi network")
                print(
                    "  wifi ap                - Create WiFi access point 'PicoWiFiManager'")
                print(
                    "  wifi manager           - Start web-based WiFi manager (mobile phone)")
                print("  wifi reset             - Delete saved WiFi credentials")
                print("  help                   - Show this help message")
                print("  exit                   - Exit terminal interface\n")

            elif command == "wifi":
                if len(parts) < 2:
                    print(
                        "Error: WiFi command requires an action (scan, status, connect, ap, manager, reset)")
                    continue

                action = parts[1].lower()

                if action == "scan":
                    scan_wifi()
                    print()

                elif action == "ap":
                    print("\nCreating WiFi Access Point...")
                    if create_wifi_ap():
                        print("\n✓ Access Point is now active!")
                        print(
                            "Look for 'PicoWiFiManager' in your phone's WiFi settings.")
                    else:
                        print("\n✗ Failed to create Access Point!")
                    print()

                elif action == "status":
                    status = get_wifi_status()
                    print("\n" + "-"*50)
                    if status['connected']:
                        print("WiFi Status: CONNECTED")
                        print(f"SSID: {status['ssid']}")
                        print(f"IP Address: {status['ip']}")
                        print(f"Subnet Mask: {status['subnet']}")
                        print(f"Gateway: {status['gateway']}")
                        print(f"DNS: {status['dns']}")
                    else:
                        print("WiFi Status: NOT CONNECTED")
                    print("-"*50 + "\n")

                elif action == "connect":
                    if len(parts) < 3:
                        print("Error: wifi connect requires SSID and password")
                        print("Usage: wifi connect <SSID> <password>")
                        continue
                    ssid = parts[2]
                    password = parts[3] if len(parts) > 3 else ""
                    print(f"\nConnecting to: {ssid}")
                    if connect_to_wifi(ssid, password):
                        print("✓ Connection successful!")
                        status = get_wifi_status()
                        if status['connected']:
                            print(f"IP Address: {status['ip']}")
                    else:
                        print("✗ Connection failed!")
                    print()

                elif action == "manager":
                    print("\nStarting WiFi Manager web server...")
                    print(
                        "This will start a web server accessible from your mobile phone.")
                    print("Press Ctrl+C to stop the server.\n")
                    try:
                        wifi_manager_web_server()
                    except KeyboardInterrupt:
                        print("\nWiFi Manager web server stopped.")
                    print()

                elif action == "reset":
                    if delete_wifi_config():
                        print("✓ WiFi configuration deleted")
                        print("WiFi will need to be reconfigured on next startup.")
                    else:
                        print("✗ Failed to delete WiFi configuration")
                    print()

                else:
                    print(f"Error: Unknown WiFi action '{action}'")
                    print(
                        "Available actions: scan, status, connect, ap, manager, reset")

            else:
                print(f"Error: Unknown command '{command}'")
                print("Type 'help' for available commands")

        except EOFError:
            print("\nNo input available. Exiting terminal interface...")
            break
        except KeyboardInterrupt:
            print("\n\nTerminal interface interrupted.")
            break
        except Exception as e:
            print(f"Error: {e}")
            import sys
            sys.print_exception(e)


def start_terminal_interface_thread():
    """Start terminal command interface in a separate thread"""
    try:
        _thread.start_new_thread(terminal_command_interface, ())
        print("Terminal interface started in background thread.")
        print("You can also call terminal_command_interface() directly from REPL.")
    except Exception as e:
        print(f"Failed to start terminal interface thread: {e}")
        print("You can call terminal_command_interface() directly from REPL.")


def run():
    """Entry point: connect WiFi, test Firebase, then run command loop."""
    global last_periodic_check

    # Connect to WiFi
    if not connect_wifi():
        print("WiFi connection failed. System cannot continue.")
        print("Hold GPIO0 button for 3 seconds on next startup to reset WiFi config.")
        print("\nYou can use the terminal interface to configure WiFi:")
        print("  Call terminal_command_interface() from REPL")
        print("  Or call wifi_manager_web_server() for mobile phone access")
        return

    test_firebase_connection()  # Test connection at startup
    last_periodic_check = utime.ticks_ms()
    print("System running...")
    print("\nWiFi Terminal Commands available:")
    print("  - Call terminal_command_interface() for command-line WiFi management")
    print("  - Call wifi_manager_web_server() for mobile phone web interface")
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
