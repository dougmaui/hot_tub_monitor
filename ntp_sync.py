# ntp_sync.py - NTP Time Synchronization Module (Phase 1: Basic Structure)
"""
NTP Sync Module for ESP32-S3 CircuitPython
Provides time synchronization when WiFi is available
Phase 1: Basic structure and state machine
"""

import time
import gc
from config import NTPConfig


class NTPSync:
    """Manages NTP time synchronization"""

    # State constants
    UNSYNCED = "UNSYNCED"
    SYNCING = "SYNCING"
    SYNCED = "SYNCED"

    def __init__(self, ntp_server=None):
        """Initialize NTP Sync Module"""
        # Configuration
        self.ntp_server = ntp_server or NTPConfig.NTP_SERVER

        # State management
        self.state = self.UNSYNCED
        self._sync_start_time = 0
        self._last_sync_attempt = 0
        self._last_successful_sync = 0
        self._sync_count = 0

        # Time tracking
        self._real_timestamp = None
        self._time_quality = "manual"  # "manual" or "ntp"

        # Retry management
        self._retry_delay = NTPConfig.INITIAL_RETRY_DELAY
        self._retry_count = 0
        self._failure_count = 0  # Track actual failures

        # Coordination flag
        self.just_synced = False

        print(f"NTP: Module initialized with server {self.ntp_server}")
        print(f"NTP: Free memory: {gc.mem_free()} bytes")

    def tick(self):
        """Main update cycle - non-blocking"""
        # Clear just_synced flag after one tick
        if self.just_synced:
            self.just_synced = False

        now = time.monotonic()

        if self.state == self.UNSYNCED:
            # Check if it's time to attempt sync
            if self._should_attempt_sync(now):
                print(f"NTP: Starting sync attempt #{self._retry_count + 1}")
                self.state = self.SYNCING
                self._sync_start_time = now
                self._last_sync_attempt = now
                self._retry_count += 1
                # TODO: Phase 2 - Initiate actual NTP query here

        elif self.state == self.SYNCING:
            # Check for timeout
            if now - self._sync_start_time > NTPConfig.SYNC_TIMEOUT:
                print(f"NTP: Sync timeout after {NTPConfig.SYNC_TIMEOUT}s")
                self._handle_sync_failure()
            else:
                # TODO: Phase 2 - Check if NTP response received
                # For now, simulate successful sync after 1 second
                if now - self._sync_start_time > 1.0:
                    self._handle_sync_success(time.time())  # Fake timestamp

        elif self.state == self.SYNCED:
            # Check if it's time to resync
            if now - self._last_successful_sync > NTPConfig.SYNC_INTERVAL:
                print(f"NTP: Time for periodic resync")
                self.state = self.UNSYNCED
                # Reset timing to attempt immediately
                self._last_sync_attempt = 0

    def _should_attempt_sync(self, now):
        """Check if we should attempt to sync"""
        # First attempt is immediate
        if self._last_sync_attempt == 0:
            return True

        # Otherwise respect retry delay
        return (now - self._last_sync_attempt) >= self._retry_delay

    def _handle_sync_success(self, timestamp):
        """Handle successful sync"""
        self.state = self.SYNCED
        self._real_timestamp = timestamp
        self._time_quality = "ntp"
        self._last_successful_sync = time.monotonic()
        self._sync_count += 1

        # Reset retry logic
        self._retry_delay = NTPConfig.INITIAL_RETRY_DELAY
        self._retry_count = 0
        self._failure_count = 0  # Reset failure count on success

        # Set coordination flag
        self.just_synced = True

        print(f"NTP: Sync successful! Timestamp: {timestamp}")
        print(f"NTP: Total successful syncs: {self._sync_count}")

    def _handle_sync_failure(self):
        """Handle failed sync attempt"""
        self.state = self.UNSYNCED
        self._failure_count += 1

        # Exponential backoff after first failure
        if self._failure_count > 1:
            old_delay = self._retry_delay
            self._retry_delay = min(self._retry_delay * 2, NTPConfig.MAX_RETRY_DELAY)

            if self._retry_delay != old_delay:
                print(f"NTP: Retry delay increased to {self._retry_delay}s")

        print(f"NTP: Will retry in {self._retry_delay}s")

    def is_synced(self):
        """Check if time is synchronized"""
        return self.state == self.SYNCED

    def get_real_timestamp(self):
        """Get the real Unix timestamp"""
        if self._real_timestamp is None:
            # Return a fake timestamp if never synced
            return time.time()

        # Calculate current time based on last sync
        elapsed = time.monotonic() - self._last_successful_sync
        return self._real_timestamp + elapsed

    def get_status(self):
        """Get current status dict"""
        last_sync = None
        if self._last_successful_sync > 0:
            last_sync = int(time.monotonic() - self._last_successful_sync)

        return {
            "synced": self.is_synced(),
            "state": self.state,
            "last_sync": last_sync,
            "sync_count": self._sync_count,
            "quality": self._time_quality,
            "retry_count": self._retry_count,
            "server": self.ntp_server,
        }

    def get_time_quality(self):
        """Get time quality indicator"""
        return self._time_quality


# Test code
def main():
    """Test NTP Sync standalone"""
    print("Starting NTP Sync test...")

    ntp = NTPSync()
    last_status = time.monotonic()

    # Simulate WiFi availability
    wifi_available = True

    while True:
        # Only tick if WiFi available (simulated)
        if wifi_available:
            ntp.tick()

            # Check for sync completion
            if ntp.just_synced:
                print(
                    f"NTP: Just synced! Would update WiFi time offset to {ntp.get_real_timestamp()}"
                )

        # Status every 5 seconds
        if time.monotonic() - last_status > 5:
            status = ntp.get_status()
            print(f"NTP: Status: {status}")
            last_status = time.monotonic()

        time.sleep(0.05)  # 50ms tick


if __name__ == "__main__":
    main()
