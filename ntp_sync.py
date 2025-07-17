# ntp_sync.py - NTP Time Synchronization Module (Phase 1: Basic Structure)
"""
NTP Sync Module for ESP32-S3 CircuitPython
Provides time synchronization when WiFi is available
Phase 1: Basic structure and state machine
"""

import time
import gc
import struct
import wifi
import socketpool
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

        # NTP socket setup
        self._socket = None
        self._socket_pool = None
        self._ntp_packet = None
        self._send_time = None
        self._waiting_response = False

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
                self._cleanup_socket()
                self._handle_sync_failure()
            else:
                # Real NTP implementation
                if not self._waiting_response:
                    # Send NTP request
                    if self._send_ntp_request():
                        self._waiting_response = True
                    else:
                        self._handle_sync_failure()
                else:
                    # Check for response
                    timestamp = self._check_ntp_response()
                    if timestamp is not None:
                        self._cleanup_socket()
                        self._handle_sync_success(timestamp)

        # Fix 1: Proper resync transition
        elif self.state == self.SYNCED:
            if now - self._last_successful_sync > NTPConfig.SYNC_INTERVAL:
                print(f"NTP: Time for periodic resync")
                self._cleanup_socket()  # Clean up socket first
                self.state = self.UNSYNCED
                # Prevent immediate retry storm
                self._last_sync_attempt = now
                # Reset retry logic for fresh start
                self._retry_count = 0
                self._retry_delay = NTPConfig.INITIAL_RETRY_DELAY

    def _should_attempt_sync(self, now):
        """Check if we should attempt to sync"""
        # First attempt is immediate
        if self._last_sync_attempt == 0:
            return True

        # Otherwise respect retry delay
        return (now - self._last_sync_attempt) >= self._retry_delay

    def _handle_sync_success(self, timestamp_us):
        """Handle successful sync (timestamp in microseconds)"""
        self.state = self.SYNCED
        self._real_timestamp_us = timestamp_us  # Store as microseconds
        self._time_quality = "ntp"
        self._last_successful_sync = time.monotonic()
        self._sync_count += 1

        # Reset retry logic
        self._retry_delay = NTPConfig.INITIAL_RETRY_DELAY
        self._retry_count = 0
        self._failure_count = 0  # Reset failure count on success

        # Set coordination flag
        self.just_synced = True

        # Convert to seconds for display
        seconds = timestamp_us // 1000000
        print(f"NTP: Sync successful! Timestamp: {seconds}")
        print(f"NTP: Total successful syncs: {self._sync_count}")

    def _handle_sync_failure(self):
        self.state = self.UNSYNCED
        self._failure_count += 1
        self._waiting_response = False
        self._cleanup_socket()  # Always cleanup on failure

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

    def get_real_timestamp_us(self):
        """Get the real Unix timestamp in microseconds"""
        if self._real_timestamp_us is None:
            # Return fake timestamp in microseconds
            return int(time.time() * 1000000)

        # Calculate elapsed time in microseconds
        elapsed_us = int((time.monotonic() - self._last_successful_sync) * 1000000)
        return self._real_timestamp_us + elapsed_us

        # IMPORTANT: Return as a proper float, not scientific notation
        return float(current_timestamp)

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

    def _create_socket(self):
        """Create UDP socket for NTP"""
        try:
            if self._socket_pool is None:
                self._socket_pool = socketpool.SocketPool(wifi.radio)

            self._socket = self._socket_pool.socket(
                self._socket_pool.AF_INET, self._socket_pool.SOCK_DGRAM
            )
            self._socket.settimeout(0.1)
            return True
        except Exception as e:
            print(f"NTP: Socket creation error: {e}")
            return False

    def _cleanup_socket(self):
        """Clean up socket resources"""
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
            self._socket = None

    def _send_ntp_request(self):
        """Send NTP request packet"""
        try:
            # Ensure socket exists first
            if self._socket is None:
                self._create_socket()

            # Create NTP request packet
            packet = bytearray(NTPConfig.NTP_PACKET_SIZE)
            packet[0] = 0b00100011  # LI=0, Version=4, Mode=3 (client)

            # DEBUG: Show what we're sending
            print(f"DEBUG NTP: Sending NTP request packet")
            print(
                f"DEBUG NTP: First byte: {packet[0]:08b} (LI={packet[0]>>6}, Ver={(packet[0]>>3)&0x07}, Mode={packet[0]&0x07})"
            )

            # Send packet
            self._socket.sendto(packet, (self.ntp_server, NTPConfig.NTP_PORT))
            self._send_time = time.monotonic()
            self._waiting_response = True
            print(f"NTP: Request sent to {self.ntp_server}")

            return True

        except Exception as e:
            print(f"NTP: Send error: {e}")
            self._cleanup_socket()

    def _check_ntp_response(self):
        """Check for NTP response (non-blocking)"""
        try:
            if self._socket is None:
                return None

            buffer = bytearray(NTPConfig.NTP_PACKET_SIZE)
            bytes_received = self._socket.recv_into(buffer)
            receive_time = time.monotonic()

            if bytes_received >= NTPConfig.NTP_PACKET_SIZE:
                # Extract transmit timestamp
                ntp_seconds = struct.unpack("!I", buffer[40:44])[0]
                ntp_fraction = struct.unpack("!I", buffer[44:48])[0]

                # Convert to Unix seconds
                unix_seconds = ntp_seconds - NTPConfig.NTP_EPOCH_OFFSET

                # Convert NTP fraction to microseconds
                # NTP fraction: 2^32 = 1 second
                # So microseconds = (fraction * 1000000) / 2^32
                microseconds = (ntp_fraction * 1000000) >> 32

                # Store as microseconds since epoch (integer)
                unix_timestamp_us = unix_seconds * 1000000 + microseconds

                # Apply network delay (in microseconds)
                network_delay_us = int((receive_time - self._send_time) * 1000000 / 2)
                adjusted_timestamp_us = unix_timestamp_us + network_delay_us

                print(f"NTP: Response received, delay: {network_delay_us/1000:.1f}ms")
                print(f"DEBUG NTP: Timestamp (µs): {adjusted_timestamp_us}")

                return adjusted_timestamp_us  # Return microseconds

        except OSError:
            pass
        except Exception as e:
            print(f"NTP: Receive error: {e}")
            self._cleanup_socket()
            self._waiting_response = False

        return None


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
