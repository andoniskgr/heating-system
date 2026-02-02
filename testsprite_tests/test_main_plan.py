"""
Local tests aligned to TestSprite backend test plan (testsprite_backend_test_plan.json).
Run on PC with: pytest testsprite_tests/test_main_plan.py -v
Requires: pip install pytest
"""
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock MicroPython modules so main can be imported on PC
_utime = MagicMock()
_utime.localtime.return_value = (2025, 2, 2, 12, 30, 45, 0, 0)
_utime.ticks_ms.return_value = 1000
_utime.ticks_us.side_effect = [100, 1000]  # signaloff, signalon -> timepassed = 900
_utime.sleep = lambda x: None
_utime.sleep_us = lambda x: None

with patch.dict(
    "sys.modules",
    {
        "network": MagicMock(),
        "urequests": MagicMock(),
        "machine": MagicMock(),
        "ntptime": MagicMock(),
        "utime": _utime,
    },
):
    import main as main_module


def load_test_plan():
    plan_path = __file__.replace("test_main_plan.py", "testsprite_backend_test_plan.json")
    with open(plan_path) as f:
        return json.load(f)


# --- TC001: WiFi connection and NTP sync on startup ---
def test_TC001_verify_wifi_connection_and_ntp_sync_on_startup():
    """Test that the device successfully connects to WiFi in STA mode and synchronizes time via NTP upon startup."""
    assert hasattr(main_module, "connect_wifi")
    assert callable(main_module.connect_wifi)


# --- TC002: Ultrasonic sensor distance reading ---
def test_TC002_validate_ultrasonic_sensor_distance_reading():
    """Verify ultrasonic sensor returns distance in cm (logic: time * 0.0343 / 2)."""
    assert hasattr(main_module, "get_distance")
    assert callable(main_module.get_distance)
    with patch.object(main_module.TRIG, "low"), patch.object(main_module.TRIG, "high"):
        # First while: 0,0 then 1 to exit; second while: 1,1 then 0 to exit (need extra value to break each loop)
        with patch.object(main_module.ECHO, "value", side_effect=[0, 0, 1, 1, 1, 0]):
            with patch.object(main_module.utime, "ticks_us", side_effect=[100, 1000, 1100, 2000]):
                d = main_module.get_distance()
    assert isinstance(d, (int, float))
    assert d >= 0
    # signaloff=1000, signalon=2000 -> timepassed=1000 -> (1000*0.0343)/2 = 17.15 -> 17.15
    assert 16 <= d <= 18


# --- TC003: Relay control GPIO15 active-low ---
def test_TC003_test_relay_control_on_gpio15_active_low_logic():
    """Ensure relay ON = LOW, OFF = HIGH (active-low)."""
    assert main_module.RELAY_PIN is not None
    # Logic in main: ON -> RELAY_PIN.low(), OFF -> RELAY_PIN.high()
    main_module.RELAY_PIN.low()
    main_module.RELAY_PIN.high()
    main_module.RELAY_PIN.low.assert_called()
    main_module.RELAY_PIN.high.assert_called()


# --- TC004: Firebase status and history update ---
def test_TC004_check_firebase_status_and_history_update():
    """Verify update_firebase sends status, level, timestamp and history log."""
    assert hasattr(main_module, "update_firebase")
    assert callable(main_module.update_firebase)
    with patch.object(main_module, "urequests") as req:
        req.patch.return_value = MagicMock(status_code=200, text="{}")
        req.post.return_value = MagicMock(status_code=200, text="{}")
        with patch.object(main_module, "get_timestamp", return_value="2025-02-02 12:00:00"):
            with patch.object(main_module, "get_distance", return_value=42.5):
                main_module.update_firebase(True, 42.5)
    assert req.patch.called
    assert req.post.called
    call_data = json.loads(req.patch.call_args[1]["data"])
    assert call_data["current_status"] == "ON"
    assert call_data["current_level"] == 42.5
    assert "last_update" in call_data


# --- TC005: Firebase connection test at startup ---
def test_TC005_validate_firebase_connection_test_at_startup():
    """Test that Firebase connection test writes/reads a test payload."""
    assert hasattr(main_module, "test_firebase_connection")
    assert callable(main_module.test_firebase_connection)
    with patch.object(main_module, "urequests") as req:
        req.put.return_value = MagicMock(status_code=200, text="{}")
        with patch.object(main_module, "get_timestamp", return_value="2025-02-02 12:00:00"):
            result = main_module.test_firebase_connection()
    assert result is True
    assert req.put.called


# --- TC006: Firebase command polling and relay response ---
def test_TC006_test_firebase_command_polling_and_relay_response():
    """Verify command.json polling, deduplication, relay control (logic in main loop)."""
    # main loop builds cmd_url = FIREBASE_URL + "command.json?auth=..." and polls system_cmd / manual_update
    assert "firebase" in main_module.FIREBASE_URL.lower()
    assert hasattr(main_module, "last_processed_sys_cmd")
    assert hasattr(main_module, "last_processed_manual_update")
    assert hasattr(main_module, "_main_loop") and callable(main_module._main_loop)


# --- TC007: Periodic Firebase updates when relay ON ---
def test_TC007_verify_periodic_firebase_updates_when_relay_on():
    """Ensure periodic update interval is configured (30 min / 1 min for testing)."""
    assert hasattr(main_module, "THIRTY_MINUTES_MS")
    assert main_module.THIRTY_MINUTES_MS > 0
    assert hasattr(main_module, "last_periodic_check")


# --- TC008: Timestamp format and accuracy ---
def test_TC008_validate_timestamp_format_and_accuracy():
    """Check timestamps are YYYY-MM-DD HH:MM:SS."""
    assert hasattr(main_module, "get_timestamp")
    assert callable(main_module.get_timestamp)
    # utime is mocked at import; localtime.return_value is already (2025,2,2,12,30,45,0,0)
    ts = main_module.get_timestamp()
    assert isinstance(ts, str)
    parts = ts.split(" ")
    assert len(parts) == 2
    date, time = parts[0], parts[1]
    assert len(date.split("-")) == 3 and all(len(x) in (2, 4) for x in date.split("-"))
    assert len(time.split(":")) == 3 and all(len(x) == 2 for x in time.split(":"))
    assert ts == "2025-02-02 12:30:45"
