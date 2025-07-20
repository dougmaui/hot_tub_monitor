# mqtt_publisher_v1.py - MQTT Publisher Module (Phase 1: Basic State Machine)
"""
MQTT Publisher Module for ESP32-S3 CircuitPython
Phase 1: Basic structure with state machine and mock publishing
"""

import time
import gc


class MQTTPublisher:
    """Manages MQTT publishing with queue and rate limiting"""

    # State constants
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    PUBLISHING = "PUBLISHING"

    # Message priorities
    CRITICAL = 2  # System status
    NORMAL = 1    # Telemetry
    LOW = 0       # Future use

    def __init__(self, broker, port, client_id, max_queue_size=20):
        """Initialize MQTT Publisher"""
        # Connection info
        self.broker = broker
        self.port = port
        self.client_id = client_id

        # State management
        self.state = self.DISCONNECTED
        self._connect_time = 0
        self._last_publish_time = 0
        self._connected_at = None

        # Queue (simple list for Phase 1)
        self.queue = []
        self.max_queue_size = max_queue_size

        # Statistics
        self.messages_sent = 0
        self.messages_queued = 0
        self.messages_dropped = 0

        # Memory monitoring
        self._last_gc = time.monotonic()
        self._initial_memory = gc.mem_free()

        # Coordination flags
        self.publishing = False

        print(f"MQTT: Publisher initialized for {broker}:{port}")
        print(f"MQTT: Client ID: {client_id}")
        print(f"MQTT: Max queue size: {max_queue_size}")
        print(f"MQTT: Free memory: {gc.mem_free()} bytes")

    def tick(self):
        """Main update cycle - non-blocking"""
        # Memory check every 10 seconds
        now = time.monotonic()
        if now - self._last_gc > 10:
            self._check_memory()
            self._last_gc = now

        # State machine
        if self.state == self.DISCONNECTED:
            # Simulate connection attempt every 5 seconds
            if self._should_connect(now):
                self.state = self.CONNECTING
                self._connect_time = now
                print(f"MQTT: Starting connection to {self.broker}...")

        elif self.state == self.CONNECTING:
            # Simulate connection delay
            if now - self._connect_time > 2:  # 2 second mock connection
                self.state = self.CONNECTED
                self._connected_at = now
                print(f"MQTT: Connected! Ready to publish.")

        elif self.state == self.CONNECTED:
            # Check if we have messages to publish
            if len(self.queue) > 0 and self._can_publish(now):
                self.state = self.PUBLISHING
                self.publishing = True
                self._last_publish_time = now

        elif self.state == self.PUBLISHING:
            # Simulate publish delay
            if now - self._last_publish_time > 0.5:  # 500ms mock publish
                # Get highest priority message
                msg = self._get_next_message()
                if msg:
                    print(f"MQTT: Published [{msg['topic']}] = {msg['payload']} (priority: {msg['priority']})")
                    self.messages_sent += 1

                self.publishing = False
                self.state = self.CONNECTED

    def publish_status(self, status_dict, priority=None):
        """Queue a status message for publishing"""
        if priority is None:
            priority = self.CRITICAL

        # For Phase 1, just convert dict to string
        payload = str(status_dict)
        return self._queue_message("status", payload, priority)

    def publish_metric(self, topic, value, priority=None):
        """Queue a metric for publishing"""
        if priority is None:
            priority = self.NORMAL

        return self._queue_message(topic, str(value), priority)

    def _queue_message(self, topic, payload, priority):
        """Add message to queue"""
        # Check queue size
        if len(self.queue) >= self.max_queue_size:
            # Drop lowest priority message
            self._drop_lowest_priority()

        message = {
            "topic": topic,
            "payload": payload,
            "priority": priority,
            "queued_at": time.monotonic()
        }

        self.queue.append(message)
        self.messages_queued += 1

        # Sort by priority (highest first)
        self.queue.sort(key=lambda x: x["priority"], reverse=True)

        return True

    def _drop_lowest_priority(self):
        """Drop the lowest priority message from queue"""
        if not self.queue:
            return

        # Find lowest priority
        min_priority = min(msg["priority"] for msg in self.queue)

        # Find oldest message with that priority
        for i, msg in enumerate(self.queue):
            if msg["priority"] == min_priority:
                dropped = self.queue.pop(i)
                self.messages_dropped += 1
                print(f"MQTT: Dropped message [{dropped['topic']}] to make room")
                return

    def _get_next_message(self):
        """Get highest priority message from queue"""
        if self.queue:
            return self.queue.pop(0)  # Already sorted by priority
        return None

    def _should_connect(self, now):
        """Check if we should attempt connection"""
        # For Phase 1, try every 5 seconds when disconnected
        return self._connected_at is None or (now - self._connect_time) > 5

    def _can_publish(self, now):
        """Check if we can publish (rate limiting placeholder)"""
        # For Phase 1, publish at most once per second
        return (now - self._last_publish_time) > 1

    def _check_memory(self):
        """Monitor memory usage"""
        free = gc.mem_free()
        used = self._initial_memory - free

        if free < 30000:
            print(f"MQTT: WARNING - Low memory: {free} bytes free")
            # Could trigger emergency flush here

    def is_connected(self):
        """Check if connected"""
        return self.state in [self.CONNECTED, self.PUBLISHING]

    def is_overloaded(self):
        """Check if queue is getting full"""
        return len(self.queue) > (self.max_queue_size * 0.8)

    def get_status(self):
        """Get current status"""
        uptime = None
        if self._connected_at:
            uptime = int(time.monotonic() - self._connected_at)

        return {
            "state": self.state,
            "connected": self.is_connected(),
            "queue_size": len(self.queue),
            "messages_sent": self.messages_sent,
            "messages_dropped": self.messages_dropped,
            "uptime": uptime,
            "memory_free": gc.mem_free()
        }

    def get_queue_info(self):
        """Get queue breakdown by priority"""
        info = {0: 0, 1: 0, 2: 0}
        for msg in self.queue:
            info[msg["priority"]] += 1
        return {"by_priority": info}


# Test code
def main():
    """Test MQTT Publisher standalone"""
    print("Starting MQTT Publisher test...")
    print("This is a mock implementation - no actual network connection")
    print()

    # Create publisher - using a public test broker
    mqtt = MQTTPublisher("broker.hivemq.com", 1883, "esp32_hottub_test")

    # Test message counter
    message_count = 0
    last_status = time.monotonic()
    last_telemetry = time.monotonic()
    test_start_time = time.monotonic()  # Track when test started
    overflow_tested = False  # Only test once

    while True:
        mqtt.tick()

        now = time.monotonic()

        # Queue a status message every 5 seconds
        if now - last_status > 5:
            status = {
                "timestamp": f"{int(now)}",
                "rssi": -67,
                "ph": 7.2,
                "temp": 98.6,
                "free_mem": gc.mem_free()
            }
            mqtt.publish_status(status)
            print(f"MQTT: Queued status message (queue size: {len(mqtt.queue)})")
            last_status = now

        # Queue telemetry every 2 seconds
        if now - last_telemetry > 2:
            message_count += 1

            # Rotate through different metrics
            if message_count % 4 == 0:
                mqtt.publish_metric("sensors/ph", 7.2 + (message_count % 10) * 0.01)
            elif message_count % 4 == 1:
                mqtt.publish_metric("sensors/temp_f", 98.6 + (message_count % 5) * 0.1)
            elif message_count % 4 == 2:
                mqtt.publish_metric("sensors/temp_c", 37.0 + (message_count % 5) * 0.05)
            else:
                mqtt.publish_metric("sensors/rssi", -65 - (message_count % 10))

            last_telemetry = now

        # Print full status every 10 seconds
        if int(now) % 10 == 0 and int(now) != int(now - 0.05):
            status = mqtt.get_status()
            queue_info = mqtt.get_queue_info()
            print(f"\n{'='*50}")
            print(f"MQTT Status: {status}")
            print(f"Queue Info: {queue_info}")
            print(f"{'='*50}\n")

        # Test queue overflow after 30 seconds from start
        if not overflow_tested and (now - test_start_time) > 30:
            print("\nTEST: Flooding queue to test overflow handling...")
            for i in range(25):
                mqtt.publish_metric(f"test/metric_{i}", i, priority=0)  # LOW priority
            print(f"Queue size after flood: {len(mqtt.queue)}")
            print(f"Messages dropped: {mqtt.messages_dropped}\n")
            overflow_tested = True

        time.sleep(0.05)  # 50ms tick


if __name__ == "__main__":
    main()