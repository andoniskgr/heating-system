"""
WiFi Manager Configuration
All configurable constants for the WiFi manager.
"""

# --- AP Mode Settings (when no credentials / connection fails) ---
AP_SSID = "pico_control"
AP_PASSWORD = "12345678"
AP_IP = "192.168.4.1"
AP_SUBNET = "255.255.255.0"
AP_GATEWAY = "192.168.4.1"
AP_DNS = "192.168.4.1"

# --- Credential Storage ---
CREDENTIAL_FILE = "wifi_creds.json"

# --- Connection Retry ---
MAX_RETRIES = 3
CONNECT_TIMEOUT_SEC = 15

# --- Hardware Pins ---
LED_PIN = "LED"       # Onboard LED (use "LED" for Pico W; GPIO 25 for original Pico)
RESET_BUTTON_PIN = 0  # GPIO for reset button (hold >3s to clear credentials)
RESET_HOLD_SEC = 3
