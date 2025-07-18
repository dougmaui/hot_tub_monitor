# code.py - Minimal Executive Module
"""
Executive loop for ESP32-S3 Network Services
Coordinates WiFi Manager, NTP Sync, and MQTT Publisher
"""

import time
import gc
import os
from config import WiFiConfig
from wifi_manager import WiFiManager
from ntp_sync import NTPSync


def test_float_math():
    """Test basic float operations"""
    big_int = 1752752692
    small_float = 0.030818746

    print(f"Test 1: {big_int} + {small_float} = {big_int + small_float}")
    print(f"Test 2: float({big_int}) + {small_float} = {float(big_int) + small_float}")
    print(f"Test 3: {big_int} + float({small_float}) = {big_int + float(small_float)}")

    # Test with explicit float conversion
    result = float(big_int) + small_float
    print(f"Test 4: result = {result}")
    print(f"Test 5: result type = {type(result)}")
    print(f"Test 6: formatted = {result:.11f}")


def main():
    """Main executive loop"""
    print("Starting Network Services Executive...")
    print(f"  Free memory: {gc.mem_free()} bytes")

    # Add this test before starting
    print("\n=== Testing float arithmetic ===")
    test_float_math()
    print("=== End float test ===\n")

    # Continue with rest of main...


# Get credentials from environment
WIFI_SSID = os.getenv("WIFI_SSID", "TestNetwork")
WIFI_PASSWORD = os.getenv("WIFI_PASSWORD", "testpass")

# Configuration
TICK_INTERVAL = 0.05  # 50ms main loop
HEALTH_CHECK_INTERVAL = 60  # Check system health every minute


def main():
    """Main executive loop"""
    print("Starting Network Services Executive...")
    print(f"  Free memory: {gc.mem_free()} bytes")

    # Initialize modules
    wifi = WiFiManager(WIFI_SSID, WIFI_PASSWORD, start_time="12:00:00")

    # TODO: Add these as you build them
    ntp = NTPSync()
    # mqtt = MQTTPublisher("broker.io", 1883, "esp32_client")

    # Health monitoring
    last_health_check = time.monotonic()

    print("Executive loop started")

    while True:
        # Always tick WiFi
        wifi.tick()

        # TODO: Add NTP when available
        if wifi.is_available():
            ntp.tick()
            # In code.py, when NTP syncs:
            if ntp.just_synced:
                # Get timestamp in microseconds
                timestamp_us = ntp.get_real_timestamp_us()
                print(f"Executive: Passing timestamp {timestamp_us} µs to WiFi")
                wifi.set_time_offset_us(timestamp_us)

        # TODO: Add MQTT when available
        # if wifi.is_available() and not wifi.will_be_unavailable():
        #     if not wifi.measuring:
        #         mqtt.tick()

        # Health monitoring
        now = time.monotonic()
        if now - last_health_check >= HEALTH_CHECK_INTERVAL:
            free_mem = gc.mem_free()
            status = wifi.get_status()
            ntp_status = ntp.get_status()

            # Single line health check
            print(
                f"{wifi.get_timestamp()} Health: WiFi {status['state']} RSSI:{status['rssi']} Ch:{status['channel']} | NTP:{ntp_status['quality']} | Mem:{free_mem}"
            )

            last_health_check = now

            # TODO: Add emergency actions
            # if free_mem < 20000:
            #     print("  WARNING: Low memory!")
            #     if mqtt:
            #         mqtt.emergency_flush()

            last_health_check = now

        # Maintain loop timing
        time.sleep(TICK_INTERVAL)


# Then modify the very bottom of code.py:
if __name__ == "__main__":
    print("\n=== Testing float arithmetic ===")
    test_float_math()
    print("=== End float test ===\n")
    main()
