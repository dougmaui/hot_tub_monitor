# rate_manager.py - Rate Manager for MQTT Publisher
"""
Token bucket rate limiter for controlling publish rates
Supports normal operation and burst modes
"""

import time


class RateManager:
    """Token bucket implementation for rate limiting"""

    def __init__(self, publishes_per_minute=20):
        """Initialize rate manager
        
        Args:
            publishes_per_minute: Target publish rate
        """
        # Basic settings
        self.publishes_per_minute = publishes_per_minute
        self.tokens_per_second = publishes_per_minute / 60.0

        # Token bucket
        self.max_tokens = publishes_per_minute  # Bucket size = 1 minute worth
        self.tokens = self.max_tokens  # Start full
        self.last_update = time.monotonic()

        # Burst mode support
        self.burst_mode = False
        self.burst_end_time = 0
        self.borrowed_tokens = 0
        self.max_burst_borrow = 10  # Can borrow up to 10 tokens

        # Statistics
        self.tokens_consumed = 0
        self.tokens_denied = 0
        self.burst_count = 0

        print(f"RateManager: Initialized at {publishes_per_minute}/minute")
        print(f"RateManager: Token refill rate: {self.tokens_per_second:.2f}/second")
        print(f"RateManager: Max tokens (bucket size): {self.max_tokens}")

    def can_publish(self):
        """Check if we have tokens available"""
        self._refill_tokens()
        return self.tokens >= 1.0

    def consume(self, count=1):
        """Attempt to consume tokens
        
        Returns:
            True if tokens were available, False otherwise
        """
        self._refill_tokens()

        if self.tokens >= count:
            self.tokens -= count
            self.tokens_consumed += count
            return True
        else:
            self.tokens_denied += count
            return False

    def _refill_tokens(self):
        """Refill tokens based on elapsed time"""
        now = time.monotonic()
        elapsed = now - self.last_update

        # Add tokens based on time passed
        tokens_to_add = elapsed * self.tokens_per_second
        self.tokens = min(self.tokens + tokens_to_add, self.max_tokens)

        self.last_update = now

        # Check if burst mode expired
        if self.burst_mode and now > self.burst_end_time:
            self._end_burst_mode()

    def request_burst_mode(self, duration=30, reason=""):
        """Request burst mode for urgent publishing
        
        Args:
            duration: How long burst mode should last (seconds)
            reason: Why burst mode is needed
            
        Returns:
            True if burst mode granted, False if not enough tokens
        """
        if self.burst_mode:
            print("RateManager: Already in burst mode")
            return False

        # Calculate tokens needed for burst
        burst_rate = self.publishes_per_minute * 2  # Double rate during burst
        tokens_needed = (burst_rate / 60.0) * duration

        # Check if we can borrow enough tokens
        tokens_to_borrow = max(0, tokens_needed - self.tokens)
        if tokens_to_borrow > self.max_burst_borrow:
            print(f"RateManager: Burst denied - would need to borrow {tokens_to_borrow:.1f} tokens")
            return False

        # Enter burst mode
        self.burst_mode = True
        self.burst_end_time = time.monotonic() + duration
        self.borrowed_tokens = tokens_to_borrow
        self.burst_count += 1

        print(f"RateManager: Burst mode ACTIVATED for {duration}s - {reason}")
        print(f"RateManager: Borrowed {tokens_to_borrow:.1f} tokens")

        # Temporarily increase rate
        self.tokens_per_second = burst_rate / 60.0

        return True

    def _end_burst_mode(self):
        """End burst mode and enter recovery"""
        self.burst_mode = False

        print(f"RateManager: Burst mode ENDED")

        # Pay back borrowed tokens by reducing rate
        if self.borrowed_tokens > 0:
            # Reduce rate to 50% until tokens repaid
            normal_rate = self.publishes_per_minute / 60.0
            self.tokens_per_second = normal_rate * 0.5
            print(f"RateManager: Entering recovery mode (50% rate) to repay {self.borrowed_tokens:.1f} tokens")
        else:
            # Return to normal rate
            self.tokens_per_second = self.publishes_per_minute / 60.0

    def set_rate(self, publishes_per_minute):
        """Change the publish rate"""
        old_rate = self.publishes_per_minute
        self.publishes_per_minute = publishes_per_minute
        self.tokens_per_second = publishes_per_minute / 60.0
        self.max_tokens = publishes_per_minute

        # Don't let current tokens exceed new max
        self.tokens = min(self.tokens, self.max_tokens)

        print(f"RateManager: Rate changed from {old_rate}/min to {publishes_per_minute}/min")

    def get_status(self):
        """Get current status"""
        self._refill_tokens()

        return {
            "rate": self.publishes_per_minute,
            "tokens": round(self.tokens, 1),
            "max_tokens": self.max_tokens,
            "in_burst": self.burst_mode,
            "consumed": self.tokens_consumed,
            "denied": self.tokens_denied,
            "burst_count": self.burst_count
        }

    def get_wait_time(self):
        """How long until next token available"""
        if self.tokens >= 1.0:
            return 0

        tokens_needed = 1.0 - self.tokens
        return tokens_needed / self.tokens_per_second


# Test code
def main():
    """Test Rate Manager standalone"""
    print("Rate Manager Test")
    print("=" * 50)

    # Create manager at development rate
    rate_mgr = RateManager(publishes_per_minute=20)

    # Test tracking
    test_start = time.monotonic()
    last_status = test_start
    publish_times = []

    print("\nPhase 1: Normal publishing at 20/minute rate")
    print("-" * 50)

    while True:
        now = time.monotonic()
        elapsed = now - test_start

        # Try to publish
        if rate_mgr.can_publish():
            if rate_mgr.consume():
                publish_times.append(now)
                tokens_left = rate_mgr.tokens
                print(f"[{elapsed:6.1f}s] Published! Tokens left: {tokens_left:.1f}")

        # Status every 5 seconds
        if now - last_status > 5:
            status = rate_mgr.get_status()

            # Calculate actual rate
            recent_publishes = [t for t in publish_times if t > now - 60]
            actual_rate = len(recent_publishes)

            print(f"\n[{elapsed:6.1f}s] Status: {status}")
            print(f"         Actual rate: {actual_rate}/minute")
            last_status = now

        # Test burst mode at 15 seconds
        if elapsed > 15 and elapsed < 16 and not rate_mgr.burst_mode:
            print(f"\n[{elapsed:6.1f}s] SIMULATING CRITICAL EVENT - Requesting burst mode")
            if rate_mgr.request_burst_mode(duration=10, reason="pH spike detected"):
                print("         Burst mode approved! Publishing rapidly...")

        # Test rate change at 60 seconds
        if elapsed > 60 and elapsed < 61 and rate_mgr.publishes_per_minute == 20:
            print(f"\n[{elapsed:6.1f}s] CHANGING TO PRODUCTION RATE")
            rate_mgr.set_rate(2)  # Switch to 2/minute

        # End test at 90 seconds
        if elapsed > 90:
            print(f"\n[{elapsed:6.1f}s] Test complete!")
            print(f"Total publishes: {rate_mgr.tokens_consumed}")
            print(f"Publishes denied: {rate_mgr.tokens_denied}")
            break

        time.sleep(0.1)  # 100ms loop


if __name__ == "__main__":
    main()