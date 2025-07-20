# code.py - Executive Module with Display
"""
Executive loop for ESP32-S3 Network Services
Coordinates WiFi Manager, NTP Sync, MQTT Publisher, and Display
"""

import time
import gc
import os
from config import WiFiConfig, MQTTConfig, DisplayConfig
from wifi_manager import WiFiManager
from ntp_sync import NTPSync
from mqtt_publisher import MQTTPublisher
from display_module import DisplayModule

# Get credentials from environment
WIFI_SSID = os.getenv("WIFI_SSID", "TestNetwork")
WIFI_PASSWORD = os.getenv("WIFI_PASSWORD", "testpass")
AIO_USERNAME = os.getenv("AIO_USERNAME")
AIO_KEY = os.getenv("AIO_KEY")

# Configuration
TICK_INTERVAL = 0.05  # 50ms main loop
HEALTH_CHECK_INTERVAL = 60  # Check system health every minute


def main():
    """Main executive loop"""
    print("Starting Network Services Executive...")
    print(f"  Free memory: {gc.mem_free()} bytes")

    # Initialize modules
    wifi = WiFiManager(WIFI_SSID, WIFI_PASSWORD, start_time="12:00:00")
    ntp = NTPSync()
    
    # Initialize Display
    display = DisplayModule()
    print(f"  Display enabled: {display.enabled}")

   # Initialize MQTT if credentials available
    mqtt = None
    if AIO_USERNAME and AIO_KEY and MQTTConfig.ENABLED:
        mqtt = MQTTPublisher(
            MQTTConfig.BROKER, 
            MQTTConfig.PORT,
            AIO_USERNAME, 
            AIO_KEY,
            max_queue_size=MQTTConfig.MAX_QUEUE_SIZE,
            publishes_per_minute=MQTTConfig.PUBLISH_RATE_PROD
        )
        print(f"MQTT: Initialized for Adafruit IO user: {AIO_USERNAME}")
        ssl_status = "SSL" if MQTTConfig.PORT == 8883 else "non-SSL"
        print(f"MQTT: Using {ssl_status} connection, {MQTTConfig.PUBLISH_RATE_PROD}/minute")
    else:
        if not MQTTConfig.ENABLED:
            print("MQTT: Disabled by configuration")
        else:
            print("MQTT: Disabled - no Adafruit IO credentials found")

    # Health monitoring
    last_health_check = time.monotonic()
    last_mqtt_publish = time.monotonic()   # Track MQTT publish timing

    print("Executive loop started")
    print(f"  Free memory after init: {gc.mem_free()} bytes")

    while True:
        # Always tick WiFi
        wifi.tick()

        # Tick NTP if WiFi available
        if wifi.is_available():
            ntp.tick()

            # Handle NTP sync
            if ntp.just_synced:
                # Get timestamp in microseconds
                timestamp_us = ntp.get_real_timestamp_us()
                print(f"Executive: Passing timestamp {timestamp_us} µs to WiFi")
                wifi.set_time_offset_us(timestamp_us)

            # Tick MQTT if available and WiFi stable
            if mqtt and not wifi.will_be_unavailable():
                if not wifi.measuring:
                    mqtt.tick()

        # Update display - pass all modules so it can read their status
        display.tick(wifi, ntp, mqtt)

        # Health monitoring
        now = time.monotonic()
        if now - last_health_check >= HEALTH_CHECK_INTERVAL:
            free_mem = gc.mem_free()
            status = wifi.get_status()
            ntp_status = ntp.get_status()

            # Single line health check
            ts = wifi.get_timestamp()
            state = status['state']
            rssi = status['rssi']
            ch = status['channel']
            bssid = wifi.current_bssid or 'None'
            ntp_qual = ntp_status['quality']
            mem = free_mem

            # Basic health line
            print(f"{ts} Health: WiFi {state} RSSI:{rssi} Ch:{ch} BSSID:{bssid} | NTP:{ntp_qual} | Mem:{mem}", end="")

            # Add MQTT status if available
            if mqtt:
                mqtt_status = mqtt.get_status()
                mqtt_state = mqtt_status['state']
                mqtt_queue = mqtt_status['queue_size']
                mqtt_sent = mqtt_status['messages_sent']
                print(f" | MQTT:{mqtt_state} Q:{mqtt_queue} Sent:{mqtt_sent}", end="")
            
            # Add display status
            if display.enabled:
                display_status = display.get_status()
                print(f" | Display:ON Updates:{display_status['updates']}")
            else:
                print(" | Display:OFF")

            # Emergency actions
            if free_mem < MQTTConfig.MIN_MEMORY_WARNING:
                print(f"  WARNING: Low memory! {free_mem} bytes")

                # If critical, reduce MQTT activity but don't force GC
                if free_mem < MQTTConfig.MIN_MEMORY_CRITICAL and mqtt:
                    print("  CRITICAL: Clearing MQTT queue")
                    # Clear the queue to reduce memory pressure
                    queue_size = len(mqtt.queue)
                    mqtt.queue.clear()
                    mqtt.messages_dropped += queue_size

            last_health_check = now

        # MQTT publishing on separate schedule
        if mqtt and mqtt.is_connected() and (now - last_mqtt_publish >= MQTTConfig.HEALTH_PUBLISH_INTERVAL):
            # Get current values
            status = wifi.get_status()
            rssi = status['rssi']
            free_mem = gc.mem_free()
            
            if free_mem > MQTTConfig.MIN_MEMORY_PUBLISH:  # Only publish if memory is reasonable
                # Publish real RSSI
                mqtt.publish_metric("rssi", rssi)

                # Publish simulated sensor data for testing
                # TODO: Replace with real sensor readings
                mqtt.publish_metric("ph", 7.2)
                mqtt.publish_metric("temp-f", 98.6)
                mqtt.publish_metric("temp-c", 37.0)
                
                last_mqtt_publish = now

        # Maintain loop timing
        time.sleep(TICK_INTERVAL)


if __name__ == "__main__":
    main()