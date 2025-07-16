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
    # ntp = NTPSync()
    # mqtt = MQTTPublisher("broker.io", 1883, "esp32_client")

    # Health monitoring
    last_health_check = time.monotonic()

    print("Executive loop started")

    while True:
        # Always tick WiFi
        wifi.tick()

        # TODO: Add NTP when available
        # if wifi.is_available():
        #     ntp.tick()
        #     if ntp.just_synced:
        #         wifi.set_time_offset(ntp.get_real_timestamp())

        # TODO: Add MQTT when available
        # if wifi.is_available() and not wifi.will_be_unavailable():
        #     if not wifi.measuring:
        #         mqtt.tick()

        # Health monitoring
        now = time.monotonic()
        if now - last_health_check >= HEALTH_CHECK_INTERVAL:
            free_mem = gc.mem_free()
            status = wifi.get_status()
            print(f"{wifi.get_timestamp()} Health Check:")
            print(f"  WiFi: {status['state']} RSSI: {status['rssi']}")
            print(f"  Free memory: {free_mem} bytes")

            # TODO: Add emergency actions
            # if free_mem < 20000:
            #     print("  WARNING: Low memory!")
            #     if mqtt:
            #         mqtt.emergency_flush()

            last_health_check = now

        # Maintain loop timing
        time.sleep(TICK_INTERVAL)


if __name__ == "__main__":
    main()
