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
    HISTORY_SIZE = 256


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
        self._scan_results = []

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
        self.current_bssid = None
        self.connected_at = None

        # RSSI History
        self.rssi_history = []
        self._last_rssi_check = 0

        # Module coordination
        self.busy_flag = False
        self.measuring = False

        print(f"{self.get_timestamp()} WiFi Manager initialized for {ssid}")

    def tick(self):
        """Main update cycle - never blocks >100ms"""
        if self.state == self.INIT:
            self.state = self.SCANNING
            self._scan_timer = time.monotonic()
            self._scan_results = []
            print(f"{self.get_timestamp()} Starting network scan...")

        elif self.state == self.SCANNING:
            self._scan_for_networks()

        elif self.state == self.CONNECTING:
            self._handle_connection()

        elif self.state == self.CONNECTED:
            self._monitor_connection()

        elif self.state == self.DISCONNECTED:
            # Wait a bit then retry
            time.sleep(2)
            self.state = self.INIT

    def _scan_for_networks(self):
        """Scan for available networks"""
        try:
            # Start scanning
            networks = []
            for network in wifi.radio.start_scanning_networks():
                if network.ssid == self.ssid:
                    networks.append(
                        {
                            "ssid": network.ssid,
                            "rssi": network.rssi,
                            "channel": network.channel,
                            "bssid": ":".join(["%02X" % b for b in network.bssid]),
                        }
                    )
            wifi.radio.stop_scanning_networks()

            if networks:
                # Sort by RSSI (strongest first)
                networks.sort(key=lambda x: x["rssi"], reverse=True)
                self._scan_results = networks
                print(f"{self.get_timestamp()} Found {len(networks)} access points:")
                for ap in networks:
                    print(f"  Ch{ap['channel']:2d} RSSI:{ap['rssi']:3d} {ap['bssid']}")

                # Select best AP
                self.target_ap = networks[0]
                self.state = self.CONNECTING
                self._connect_timer = time.monotonic()
            else:
                print(f"{self.get_timestamp()} No networks found, retrying...")

        except Exception as e:
            print(f"{self.get_timestamp()} Scan error: {e}")
            # Try direct connect without scan
            self.state = self.CONNECTING
            self._connect_timer = time.monotonic()

    def _handle_connection(self):
        """Handle connection attempts"""
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
                    if "Already connected" not in str(e):
                        print(f"{self.get_timestamp()} Connect error: {e}")
        else:
            # Connected!
            self.state = self.CONNECTED
            self.connected_at = time.monotonic()
            self.current_rssi = wifi.radio.ap_info.rssi if wifi.radio.ap_info else 0
            self.current_channel = (
                wifi.radio.ap_info.channel if wifi.radio.ap_info else 0
            )
            print(
                f"{self.get_timestamp()} Connected! RSSI: {self.current_rssi} Ch: {self.current_channel}"
            )
            print(f"{self.get_timestamp()} IP: {wifi.radio.ipv4_address}")

    def _monitor_connection(self):
        """Monitor existing connection"""
        # Check if still connected
        if not wifi.radio.connected:
            print(f"{self.get_timestamp()} Connection lost")
            self.state = self.DISCONNECTED
            self.connected_at = None
            return

        # Update RSSI periodically
        now = time.monotonic()
        if now - self._last_rssi_check > 1.0:  # Check every second
            self._last_rssi_check = now
            if wifi.radio.ap_info:
                self.current_rssi = wifi.radio.ap_info.rssi

                # Add to history
                entry = {
                    "time": now - self.monotonic_start,
                    "rssi": self.current_rssi,
                    "channel": self.current_channel,
                }
                self.rssi_history.append(entry)

                # Limit history size
                if len(self.rssi_history) > WiFiConfig.HISTORY_SIZE:
                    self.rssi_history.pop(0)

                # Check if signal too weak
                if self.current_rssi < self.rssi_threshold:
                    print(
                        f"{self.get_timestamp()} RSSI below threshold: {self.current_rssi}"
                    )
                    # Could trigger rescan here

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
        uptime = None
        if self.connected_at:
            uptime = int(time.monotonic() - self.connected_at)

        return {
            "state": self.state,
            "rssi": self.current_rssi,
            "channel": self.current_channel,
            "ssid": self.ssid if self.state == self.CONNECTED else None,
            "connected": wifi.radio.connected,
            "uptime": uptime,
            "history_size": len(self.rssi_history),
        }

    def get_rssi_history(self, samples=60):
        """Get recent RSSI samples"""
        if samples >= len(self.rssi_history):
            return self.rssi_history
        return self.rssi_history[-samples:]


# Test code
def main():
    """Test WiFi Manager standalone"""
    # Get credentials from settings.toml or use defaults
    import os

    ssid = os.getenv("WIFI_SSID", "TestNetwork")
    password = os.getenv("WIFI_PASSWORD", "testpass")

    print(f"Starting WiFi Manager test with SSID: {ssid}")

    wifi_mgr = WiFiManager(ssid, password, start_time="17:38:00")

    last_status = time.monotonic()

    while True:
        wifi_mgr.tick()

        # Status every 5 seconds
        if time.monotonic() - last_status > 5:
            status = wifi_mgr.get_status()
            print(f"{wifi_mgr.get_timestamp()} Status: {status}")
            print(f"  Free memory: {gc.mem_free()} bytes")

            # Show RSSI trend
            history = wifi_mgr.get_rssi_history(10)
            if history:
                rssi_values = [h["rssi"] for h in history]
                print(f"  RSSI trend: {rssi_values}")

            last_status = time.monotonic()

        time.sleep(WiFiConfig.TICK_INTERVAL)


if __name__ == "__main__":
    main()
