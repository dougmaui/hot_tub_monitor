# wifi_manager.py - MEMORY OPTIMIZED VERSION
"""
WiFi Manager Module for ESP32-S3 CircuitPython
Memory-optimized version with leak prevention
"""

import time
import wifi
import gc
import array
import microcontroller

from config import WiFiConfig


class WiFiManager:
    """Manages WiFi connectivity with reliability focus"""

    # State constants
    INIT = "INIT"
    SCANNING = "SCANNING"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"

    def __init__(
        self,
        ssid,
        password,
        rssi_threshold=None,
        start_time=None,
        watchdog_timeout=None,
    ):
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
        self._target_ap = None

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

        # Module coordination
        self.busy_flag = False
        self.measuring = False

        # Memory monitoring
        self._last_gc = time.monotonic()
        self._low_memory_mode = False

        # RSSI warning tracking
        self._last_rssi_warning = 0
        self._rssi_was_good = True
        self._low_rssi_start = None
        self._in_connected_state = False

        # Better AP detection
        self._last_better_ap_check = 0
        self._better_ap_found_time = None
        self._better_ap_bssid = None
        self._better_ap_rssi = None

        # Watchdog tracking
        self.watchdog_timeout = (
            watchdog_timeout or WiFiConfig.CONNECTION_WATCHDOG_TIMEOUT
        )
        self.last_connected_time = time.monotonic()  # Last time we had good connection
        self.disconnected_since = None  # When current disconnect started
        self.retry_delay = 2  # Starting retry delay
        self.retry_count = 0
        self._disconnect_time = 0

        print(f"{self.get_timestamp()} WiFi Manager initialized for {ssid}")
        print(f"  Free memory: {gc.mem_free()} bytes")

    def tick(self):
        """Main update cycle - never blocks >100ms"""
        # Memory check every 10 seconds
        now = time.monotonic()
        if now - self._last_gc > 10:
            self._check_memory()
            self._last_gc = now

        # Check watchdog timer
        if self.state != self.CONNECTED:
            if self.disconnected_since is None:
                self.disconnected_since = now
                print(
                    f"{self.get_timestamp()} Disconnected - starting watchdog timer ({self.watchdog_timeout}s)"
                )

            # Check if we've exceeded watchdog timeout
            disconnect_duration = now - self.disconnected_since
            if disconnect_duration > self.watchdog_timeout:
                print(
                    f"{self.get_timestamp()} WATCHDOG: No connection for {disconnect_duration:.0f}s"
                )
                print(f"{self.get_timestamp()} WATCHDOG: Initiating hard reset...")

                # Log final status before reset
                print(f"  Last connected: {self.last_connected_time}")
                print(f"  Retry count: {self.retry_count}")
                print(f"  Free memory: {gc.mem_free()}")

                # Perform hard reset
                microcontroller.reset()

        if self.state == self.INIT:
            self.state = self.SCANNING
            self._scan_timer = time.monotonic()
            self._scan_results = []
            self.retry_count += 1
            print(
                f"{self.get_timestamp()} Starting network scan (attempt #{self.retry_count})..."
            )

        elif self.state == self.SCANNING:
            self._scan_for_networks()

        elif self.state == self.CONNECTING:
            self._handle_connection()

        elif self.state == self.CONNECTED:
            # Reset watchdog tracking on successful connection
            self.last_connected_time = now
            self.disconnected_since = None

            # Only reset retry info if connection is good
            if self.current_rssi > self.rssi_threshold:
                self.retry_delay = 2  # Reset retry delay
                self.retry_count = 0

            # Reset RSSI tracking on fresh connection
            if not self._in_connected_state:
                self._low_rssi_start = None
                self._rssi_was_good = True
                self._in_connected_state = True
                # Initialize better AP check timer to current time
                self._last_better_ap_check = now

            self._monitor_connection()

        elif self.state == self.DISCONNECTED:
            # Progressive retry delay with max limit
            if now - self._disconnect_time > self.retry_delay:
                print(
                    f"{self.get_timestamp()} Waited {self.retry_delay}s, starting retry..."
                )
                self.state = self.INIT
                # Increase delay for next retry (exponential backoff)
                old_delay = self.retry_delay
                self.retry_delay = min(
                    self.retry_delay * 2, WiFiConfig.RETRY_BACKOFF_MAX
                )
                if self.retry_delay != old_delay:
                    print(
                        f"{self.get_timestamp()} Next retry delay increased to {self.retry_delay}s"
                    )

    def _check_memory(self):
        """Monitor and manage memory"""
        free = gc.mem_free()

        if free < WiFiConfig.MEMORY_WARNING:
            if not self._low_memory_mode:
                print(f"{self.get_timestamp()} WARNING: Low memory {free} bytes")
                self._low_memory_mode = True

            # Emergency actions
            if free < 40000:
                print(
                    f"{self.get_timestamp()} CRITICAL: Memory at {free}, collecting garbage"
                )
                gc.collect()

                # Clear scan results
                self._scan_results = []

        else:
            self._low_memory_mode = False

    def _scan_for_networks(self):
        """Scan for available networks"""
        try:
            # Clear old results first
            self._scan_results = []

            # Start scanning
            networks = []
            for network in wifi.radio.start_scanning_networks():
                if network.ssid == self.ssid:
                    # Store raw bssid bytes for connection
                    networks.append(
                        {
                            "ssid": network.ssid,
                            "rssi": network.rssi,
                            "channel": network.channel,
                            "bssid": network.bssid,  # Keep raw bytes
                            "bssid_str": ":".join(["%02X" % b for b in network.bssid]),
                        }
                    )
            wifi.radio.stop_scanning_networks()

            if networks:
                # Sort by RSSI (strongest first)
                networks.sort(key=lambda x: x["rssi"], reverse=True)
                self._scan_results = networks
                print(f"{self.get_timestamp()} Found {len(networks)} access points:")
                for ap in networks[:3]:  # Only print top 3
                    print(
                        f"  Ch{ap['channel']:2d} RSSI:{ap['rssi']:3d} {ap['bssid_str']}"
                    )

                # Store the target AP we want to connect to
                self._target_ap = networks[0]  # Strongest
                print(
                    f"{self.get_timestamp()} Target AP: {self._target_ap['bssid_str']} (RSSI: {self._target_ap['rssi']})"
                )

                self.state = self.CONNECTING
                self._connect_timer = time.monotonic()
            else:
                print(f"{self.get_timestamp()} No networks found, retrying...")

        except Exception as e:
            print(f"{self.get_timestamp()} Scan error: {e}")
            # Try direct connect without scan
            self.state = self.CONNECTING
            self._connect_timer = time.monotonic()
            self._target_ap = None

    def _handle_connection(self):
        """Handle connection attempts"""
        if not wifi.radio.connected:
            if time.monotonic() - self._connect_timer > WiFiConfig.CONNECT_TIMEOUT:
                print(f"{self.get_timestamp()} Connection timeout")
                self.state = self.DISCONNECTED
                self._disconnect_time = time.monotonic()  # Track when we disconnected
            else:
                # Try to connect
                try:
                    if self._target_ap:
                        # Connect to specific AP using BSSID
                        print(
                            f"{self.get_timestamp()} Connecting to {self.ssid} at {self._target_ap['bssid_str']}..."
                        )
                        wifi.radio.connect(
                            self.ssid,
                            self.password,
                            channel=self._target_ap["channel"],
                            bssid=self._target_ap["bssid"],
                        )
                    else:
                        # Fallback: connect without BSSID
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

            # Log which AP we actually connected to
            if wifi.radio.ap_info:
                actual_bssid = ":".join(["%02X" % b for b in wifi.radio.ap_info.bssid])
                self.current_bssid = actual_bssid
                print(
                    f"{self.get_timestamp()} Connected to {actual_bssid}! RSSI: {self.current_rssi} Ch: {self.current_channel}"
                )

                # Verify we got the AP we wanted
                if self._target_ap and actual_bssid == self._target_ap["bssid_str"]:
                    print(f"{self.get_timestamp()} ✓ Connected to requested AP")
                elif self._target_ap:
                    print(
                        f"{self.get_timestamp()} ⚠ Connected to different AP than requested"
                    )
            else:
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
            self._disconnect_time = time.monotonic()
            self._low_rssi_start = None  # Reset low RSSI tracking
            self._rssi_was_good = True  # Reset RSSI state
            self._in_connected_state = False  # Clear connection flag
            return

        # NOW we're connected, so define 'now' and do the monitoring
        now = time.monotonic()

        # Update RSSI periodically
        if wifi.radio.ap_info and self.can_measure():
            self.current_rssi = wifi.radio.ap_info.rssi

            # Check if signal too weak - with spam prevention and reconnection
            if self.current_rssi < self.rssi_threshold:
                # Only print on transition or every 5 seconds
                if self._rssi_was_good:  # Just went bad
                    print(
                        f"{self.get_timestamp()} WARNING: RSSI below threshold: {self.current_rssi}"
                    )
                    self._last_rssi_warning = now
                    self._rssi_was_good = False
                    self._low_rssi_start = now  # Track when low RSSI started
                elif now - self._last_rssi_warning > 5:  # Periodic warning
                    print(
                        f"{self.get_timestamp()} WARNING: RSSI still low: {self.current_rssi}"
                    )
                    self._last_rssi_warning = now

                    # Check if we've been in low RSSI state for too long
                    if (
                        self._low_rssi_start
                        and (now - self._low_rssi_start)
                        > WiFiConfig.LOW_RSSI_DISCONNECT_TIME
                    ):
                        print(
                            f"{self.get_timestamp()} RSSI too low for too long, checking for better APs..."
                        )
                        self._check_for_better_ap()
                        # Reset the low RSSI timer since we just checked
                        self._low_rssi_start = now

            else:
                self._rssi_was_good = True  # Signal recovered
                self._low_rssi_start = None  # Clear the low RSSI timer

        # Periodically check for better APs even if signal is acceptable
        if now - self._last_better_ap_check > WiFiConfig.BETTER_AP_CHECK_INTERVAL:
            if self.current_rssi < WiFiConfig.RSSI_GOOD:  # Not excellent signal
                self._check_for_better_ap()
                self._last_better_ap_check = now

    def _check_for_better_ap(self):
        """Check if there's a significantly better AP available"""
        print(f"{self.get_timestamp()} Scanning for better access points...")

        try:
            # Quick scan while connected
            networks = []
            for network in wifi.radio.start_scanning_networks():
                if network.ssid == self.ssid:
                    networks.append({
                        "rssi": network.rssi,
                        "bssid_str": ":".join(["%02X" % b for b in network.bssid]),
                    })
            wifi.radio.stop_scanning_networks()

            if not networks:
                return

            # Find the best AP
            best_ap = max(networks, key=lambda x: x["rssi"])

            # Check if we found a significantly better AP
            rssi_improvement = best_ap["rssi"] - self.current_rssi

            if best_ap["bssid_str"] != self.current_bssid and rssi_improvement >= WiFiConfig.BETTER_AP_MARGIN:
                now = time.monotonic()

                # First time finding this better AP?
                if self._better_ap_bssid != best_ap["bssid_str"]:
                    self._better_ap_bssid = best_ap["bssid_str"]
                    self._better_ap_rssi = best_ap["rssi"]
                    self._better_ap_found_time = now
                    print("{} Found better AP: {} (RSSI: {}, improvement: +{}dB)".format(
                        self.get_timestamp(), best_ap['bssid_str'], best_ap['rssi'], rssi_improvement))
                    print("{} Will switch if better AP remains stable for {}s".format(
                        self.get_timestamp(), WiFiConfig.BETTER_AP_STABLE_TIME))

                # Check if better AP has been stable long enough
                elif now - self._better_ap_found_time >= WiFiConfig.BETTER_AP_STABLE_TIME:
                    print(f"{self.get_timestamp()} Better AP stable, initiating switch...")
                    print(f"{self.get_timestamp()} Current: {self.current_bssid} (RSSI: {self.current_rssi})")
                    print(f"{self.get_timestamp()} Target:  {best_ap['bssid_str']} (RSSI: {best_ap['rssi']})")
                    print(f"{self.get_timestamp()} Resetting to switch access points...")
                    microcontroller.reset()
            else:
                # No better AP or improvement not significant enough
                if self._better_ap_bssid:
                    print(f"{self.get_timestamp()} Better AP no longer viable, continuing with current")
                self._better_ap_bssid = None
                self._better_ap_found_time = None

        except Exception as e:
            print(f"{self.get_timestamp()} Error checking for better AP: {e}")

    def get_timestamp(self):
        """Always returns useful time string"""
        elapsed = int(time.monotonic() - self.monotonic_start)
        total = self.base_seconds + elapsed
        h = (total // 3600) % 24
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def set_time_offset_us(self, real_timestamp_us):
        """Update time offset when NTP syncs (microseconds)"""
        from config import get_local_offset, is_dst

        # Convert to seconds for timezone calculation
        real_timestamp = real_timestamp_us / 1000000

        # Get local offset
        local_offset = get_local_offset(real_timestamp)

        # Apply timezone offset (in microseconds)
        local_timestamp_us = real_timestamp_us + (local_offset * 1000000)

        # Convert to seconds since midnight LOCAL time
        local_seconds = local_timestamp_us // 1000000
        seconds_since_midnight_local = int(local_seconds) % 86400

        # Calculate time components
        h = seconds_since_midnight_local // 3600
        m = (seconds_since_midnight_local % 3600) // 60
        s = seconds_since_midnight_local % 60
        ms = (local_timestamp_us % 1000000) // 1000

        # Update base_seconds
        current_monotonic = time.monotonic()
        elapsed_since_start = int(current_monotonic - self.monotonic_start)
        self.base_seconds = seconds_since_midnight_local - elapsed_since_start

        # Show timezone
        tz_name = "CEST" if is_dst(real_timestamp) else "CET"
        print(
            f"{self.get_timestamp()} WiFi: Time offset updated from NTP sync ({tz_name})"
        )

    def is_available(self):
        """Check if WiFi is connected and stable"""
        return self.state == self.CONNECTED
    def get_status(self):
        """Get current status dict"""
        uptime = None
        if self.connected_at:
            uptime = int(time.monotonic() - self.connected_at)

        watchdog_remaining = None
        if self.disconnected_since:
            elapsed = time.monotonic() - self.disconnected_since
            watchdog_remaining = max(0, self.watchdog_timeout - elapsed)

        return {
            "state": self.state,
            "rssi": self.current_rssi,
            "channel": self.current_channel,
            "ssid": self.ssid if self.state == self.CONNECTED else None,
            "connected": wifi.radio.connected,
            "uptime": uptime,
            "free_memory": gc.mem_free(),
            "retry_count": self.retry_count,
            "watchdog_remaining": watchdog_remaining,
        }

    def will_be_unavailable(self):
        if self._low_rssi_start:
            elapsed = time.monotonic() - self._low_rssi_start
            if elapsed > WiFiConfig.LOW_RSSI_DISCONNECT_TIME:
                return True
        return self.state != self.CONNECTED

    def can_measure(self):
        """Check if safe to measure RSSI (respects MQTT busy flag)"""
        return not self.busy_flag and self.state == self.CONNECTED


# Test code
def main():
    """Test WiFi Manager standalone"""
    import os
    from watchdog import WatchDogMode

    ssid = os.getenv("WIFI_SSID", "TestNetwork")
    password = os.getenv("WIFI_PASSWORD", "testpass")

    print(f"Starting WiFi Manager test with SSID: {ssid}")

    wifi_mgr = WiFiManager(ssid, password, start_time="12:00:00")

    last_status = time.monotonic()

    # Set up watchdog - CircuitPython uses WatchDogMode
    wdt = microcontroller.watchdog
    wdt.timeout = 5
    wdt.mode = WatchDogMode.RESET
    wdt.feed()

    while True:
        wifi_mgr.tick()

        # Feed watchdog
        wdt.feed()

        # Status every 5 seconds
        if time.monotonic() - last_status > 5:
            status = wifi_mgr.get_status()
            print(f"{wifi_mgr.get_timestamp()} Status: {status}")

            last_status = time.monotonic()

        time.sleep(WiFiConfig.TICK_INTERVAL)


if __name__ == "__main__":
    main()