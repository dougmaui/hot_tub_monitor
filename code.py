# test_ntp_basic.py - Test script for NTP module basic structure
"""
Test the NTP module's state machine, retry logic, and coordination
without actual NTP protocol implementation
"""

import time
import gc
from ntp_sync import NTPSync


def test_basic_sync():
    """Test basic sync operation"""
    print("\n=== TEST 1: Basic Sync Operation ===")
    ntp = NTPSync()

    # Should start in UNSYNCED state
    print(f"Initial state: {ntp.state}")
    assert ntp.state == NTPSync.UNSYNCED
    assert not ntp.is_synced()
    assert ntp.get_time_quality() == "manual"

    # First tick should start sync immediately
    ntp.tick()
    print(f"After first tick: {ntp.state}")
    assert ntp.state == NTPSync.SYNCING

    # Wait for simulated sync to complete (1 second)
    start = time.monotonic()
    while time.monotonic() - start < 1.5:
        ntp.tick()
        if ntp.just_synced:
            print(f"Sync completed! State: {ntp.state}")
            print(f"Time quality: {ntp.get_time_quality()}")
            print(f"Real timestamp: {ntp.get_real_timestamp()}")
            break
        time.sleep(0.05)

    assert ntp.state == NTPSync.SYNCED
    assert ntp.is_synced()
    assert ntp.get_time_quality() == "ntp"

    # Check that just_synced flag clears
    ntp.tick()
    assert not ntp.just_synced

    print("✓ Basic sync test passed")


def test_sync_timeout():
    """Test sync timeout handling"""
    print("\n=== TEST 2: Sync Timeout ===")

    # Modify the module temporarily to not auto-succeed
    class NTPSyncTimeout(NTPSync):
        def tick(self):
            # Clear just_synced flag after one tick
            if self.just_synced:
                self.just_synced = False

            now = time.monotonic()

            if self.state == self.UNSYNCED:
                if self._should_attempt_sync(now):
                    print(f"Starting sync attempt #{self._retry_count + 1}")
                    self.state = self.SYNCING
                    self._sync_start_time = now
                    self._last_sync_attempt = now
                    self._retry_count += 1

            elif self.state == self.SYNCING:
                # Always timeout, never succeed
                if now - self._sync_start_time > 5.0:  # Use actual timeout
                    print(f"Sync timeout after 5.0s")
                    self._handle_sync_failure()

    ntp = NTPSyncTimeout()

    # Start sync
    ntp.tick()
    assert ntp.state == NTPSync.SYNCING

    # Wait for timeout
    print("Waiting for timeout...")
    start = time.monotonic()
    while time.monotonic() - start < 6:
        ntp.tick()
        time.sleep(0.05)

    # Should be back to UNSYNCED with retry delay
    assert ntp.state == NTPSync.UNSYNCED
    assert ntp._retry_delay == 30  # Initial retry delay

    print("✓ Timeout test passed")


def test_retry_backoff():
    """Test exponential backoff on failures"""
    print("\n=== TEST 3: Retry Backoff ===")

    # Use the timeout version from previous test
    class NTPSyncTimeout(NTPSync):
        def tick(self):
            if self.just_synced:
                self.just_synced = False

            now = time.monotonic()

            if self.state == self.UNSYNCED:
                if self._should_attempt_sync(now):
                    print(f"Retry #{self._retry_count + 1} at {now:.1f}s")
                    self.state = self.SYNCING
                    self._sync_start_time = now
                    self._last_sync_attempt = now
                    self._retry_count += 1

            elif self.state == self.SYNCING:
                # Fail immediately for faster testing
                if now - self._sync_start_time > 0.1:
                    self._handle_sync_failure()

    ntp = NTPSyncTimeout()

    # Track retry delays
    expected_delays = [30, 60, 120, 240, 300, 300]  # Capped at 300

    for i, expected in enumerate(expected_delays[:4]):  # Test first 4
        # Wait for sync attempt
        while ntp.state != NTPSync.SYNCING:
            ntp.tick()
            time.sleep(0.01)

        # Wait for failure
        while ntp.state != NTPSync.UNSYNCED:
            ntp.tick()
            time.sleep(0.01)

        print(f"After failure {i+1}: retry_delay = {ntp._retry_delay}s")
        assert ntp._retry_delay == expected_delays[i]

    print("✓ Retry backoff test passed")


def test_periodic_resync():
    """Test periodic resync after successful sync"""
    print("\n=== TEST 4: Periodic Resync ===")

    # Create version with very short resync interval
    class NTPSyncShortInterval(NTPSync):
        def tick(self):
            if self.just_synced:
                self.just_synced = False

            now = time.monotonic()

            if self.state == self.UNSYNCED:
                if self._should_attempt_sync(now):
                    self.state = self.SYNCING
                    self._sync_start_time = now
                    self._last_sync_attempt = now
                    self._retry_count += 1

            elif self.state == self.SYNCING:
                # Succeed quickly
                if now - self._sync_start_time > 0.1:
                    self._handle_sync_success(time.time())

            elif self.state == self.SYNCED:
                # Check for resync with short interval (2 seconds for testing)
                if now - self._last_successful_sync > 2.0:
                    print(f"Time for periodic resync")
                    self.state = self.UNSYNCED

    ntp = NTPSyncShortInterval()

    # Get initial sync
    while not ntp.is_synced():
        ntp.tick()
        time.sleep(0.01)

    print("Initial sync complete")
    sync_count = ntp._sync_count

    # Wait for periodic resync
    print("Waiting for periodic resync...")
    start = time.monotonic()
    while time.monotonic() - start < 3:
        ntp.tick()
        if ntp._sync_count > sync_count:
            print(f"Resync completed! Total syncs: {ntp._sync_count}")
            break
        time.sleep(0.05)

    assert ntp._sync_count == 2
    print("✓ Periodic resync test passed")


def test_status_and_memory():
    """Test status reporting and memory usage"""
    print("\n=== TEST 5: Status and Memory ===")

    initial_free = gc.mem_free()
    print(f"Initial free memory: {initial_free} bytes")

    ntp = NTPSync()

    after_init = gc.mem_free()
    print(f"After NTP init: {after_init} bytes")
    print(f"NTP module used: {initial_free - after_init} bytes")

    # Get status in different states
    print("\nUNSYNCED status:")
    status = ntp.get_status()
    for k, v in status.items():
        print(f"  {k}: {v}")

    # Start sync
    ntp.tick()
    print("\nSYNCING status:")
    status = ntp.get_status()
    for k, v in status.items():
        print(f"  {k}: {v}")

    # Complete sync
    start = time.monotonic()
    while time.monotonic() - start < 1.5:
        ntp.tick()
        if ntp.is_synced():
            break
        time.sleep(0.05)

    print("\nSYNCED status:")
    status = ntp.get_status()
    for k, v in status.items():
        print(f"  {k}: {v}")

    # Memory should be under 2KB
    assert (initial_free - after_init) < 2048
    print(f"\n✓ Memory usage under 2KB limit")


def run_all_tests():
    """Run all tests"""
    print("=== NTP Basic Structure Tests ===")
    print(f"Free memory at start: {gc.mem_free()} bytes")

    test_basic_sync()
    gc.collect()

    test_sync_timeout()
    gc.collect()

    test_retry_backoff()
    gc.collect()

    test_periodic_resync()
    gc.collect()

    test_status_and_memory()

    print("\n=== All tests passed! ===")
    print(f"Free memory at end: {gc.mem_free()} bytes")


if __name__ == "__main__":
    run_all_tests()
