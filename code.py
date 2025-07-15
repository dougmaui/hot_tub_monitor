# wifi_manager.py
"""
WiFi Manager Module for ESP32-S3 CircuitPython
Provides reliable WiFi connectivity with automatic recovery
"""

import time
import wifi
import socketpool
import gc


class WiFiConfig:
    """Configuration constants - move to config.py later"""

    RSSI_THRESHOLD = -75
    RSSI_GOOD = -70
    SCAN_TIMEOUT = 5.0
    CONNECT_TIMEOUT = 10.0
    TICK_INTERVAL = 0.05


class WiFiManager:
    """Manages WiFi connectivity with reliability focus"""

    # State constants
    INIT = "INIT"
    SCANNING = "SCANNING"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"

    def __init__(self, ssid, password, rssi_threshold=None, start_time=None):
        """Initialize WiFi Manager"""
        # Basic config
        self.ssid = ssid
        self.password = password
        self.rssi_threshold = rssi_threshold or WiFiConfig.RSSI_THRESHOLD

        # State
        self.state = self.INIT
        self._scan_timer = 0
        self._connect_timer = 0

        # Time management
        self.monotonic_start = time.monotonic()
        self.base_seconds = 0
        if start_time:
            try:
                h, m, s = map(int, start_time.split(":"))
                self.base_seconds = h * 3600 + m * 60 + s
            except:
                print("Invalid time format, using 00:00:00")

        # Connection info
        self.current_rssi = 0
        self.current_channel = 0

        # Module coordination
        self.busy_flag = False
        self.measuring = False

        print(f"{self.get_timestamp()} WiFi Manager initialized for {ssid}")

    def tick(self):
        """Main update cycle - never blocks >100ms"""
        if self.state == self.INIT:
            self.state = self.SCANNING
            self._scan_timer = time.monotonic()
            print(f"{self.get_timestamp()} Starting network scan...")

        elif self.state == self.SCANNING:
            # For now, skip scan and try direct connect
            if time.monotonic() - self._scan_timer > 1:
                self.state = self.CONNECTING
                self._connect_timer = time.monotonic()
                print(f"{self.get_timestamp()} Attempting connection...")

        elif self.state == self.CONNECTING:
            if not wifi.radio.connected:
                if time.monotonic() - self._connect_timer > WiFiConfig.CONNECT_TIMEOUT:
                    print(f"{self.get_timestamp()} Connection timeout")
                    self.state = self.DISCONNECTED
                else:
                    # Try to connect
                    try:
                        print(f"{self.get_timestamp()} Connecting to {self.ssid}...")
                        wifi.radio.connect(self.ssid, self.password)
                    except Exception as e:
                        print(f"{self.get_timestamp()} Connect error: {e}")
            else:
                # Connected!
                self.state = self.CONNECTED
                self.current_rssi = wifi.radio.ap_info.rssi if wifi.radio.ap_info else 0
                self.current_channel = (
                    wifi.radio.ap_info.channel if wifi.radio.ap_info else 0
                )
                print(
                    f"{self.get_timestamp()} Connected! RSSI: {self.current_rssi} Ch: {self.current_channel}"
                )
                print(f"{self.get_timestamp()} IP: {wifi.radio.ipv4_address}")

        elif self.state == self.CONNECTED:
            # Monitor connection
            if not wifi.radio.connected:
                print(f"{self.get_timestamp()} Connection lost")
                self.state = self.DISCONNECTED
            else:
                # Update RSSI
                if wifi.radio.ap_info:
                    self.current_rssi = wifi.radio.ap_info.rssi

        elif self.state == self.DISCONNECTED:
            # Wait a bit then retry
            self.state = self.INIT

    def get_timestamp(self):
        """Always returns useful time string"""
        elapsed = int(time.monotonic() - self.monotonic_start)
        total = self.base_seconds + elapsed
        h = (total // 3600) % 24
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def is_available(self):
        """Check if WiFi is connected and stable"""
        return self.state == self.CONNECTED and self.current_rssi > self.rssi_threshold

    def get_status(self):
        """Get current status dict"""
        return {
            "state": self.state,
            "rssi": self.current_rssi,
            "channel": self.current_channel,
            "ssid": self.ssid if self.state == self.CONNECTED else None,
            "connected": wifi.radio.connected,
        }


# Test code
def main():
    """Test WiFi Manager standalone"""
    # Get credentials from settings.toml or use defaults
    import os

    ssid = os.getenv("WIFI_SSID", "TestNetwork")
    password = os.getenv("WIFI_PASSWORD", "testpass")

    print(f"Starting WiFi Manager test with SSID: {ssid}")

    wifi_mgr = WiFiManager(ssid, password, start_time="12:00:00")

    last_status = time.monotonic()

    while True:
        wifi_mgr.tick()

        # Status every 5 seconds
        if time.monotonic() - last_status > 5:
            status = wifi_mgr.get_status()
            print(f"{wifi_mgr.get_timestamp()} Status: {status}")
            print(f"  Free memory: {gc.mem_free()} bytes")
            last_status = time.monotonic()

        time.sleep(WiFiConfig.TICK_INTERVAL)


if __name__ == "__main__":
    main()
