# mqtt_publisher.py - MQTT Publisher Module (Phase 4: Adafruit IO Connection)
"""
MQTT Publisher Module for ESP32-S3 CircuitPython
Phase 4: Real MQTT connection to Adafruit IO
"""

import time
import gc
import wifi
import socketpool
import ssl
import adafruit_minimqtt.adafruit_minimqtt as MQTT
from rate_manager import RateManager


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

    def __init__(self, broker, port, username, key, max_queue_size=20, publishes_per_minute=20):
        """Initialize MQTT Publisher with Adafruit IO credentials"""
        # Connection info
        self.broker = broker
        self.port = port
        self.username = username
        self.key = key

        # State management
        self.state = self.DISCONNECTED
        self._connect_time = 0
        self._last_publish_attempt = 0
        self._connected_at = None
        self._publish_start_time = 0
        self._last_ping = 0

        # Queue (simple list for now)
        self.queue = []
        self.max_queue_size = max_queue_size

        # Rate Manager
        self.rate_manager = RateManager(publishes_per_minute)

        # Statistics
        self.messages_sent = 0
        self.messages_queued = 0
        self.messages_dropped = 0
        self.messages_rate_limited = 0
        self.publish_failures = 0

        # Memory monitoring
        self._last_gc = time.monotonic()
        self._initial_memory = gc.mem_free()

        # Coordination flags
        self.publishing = False

        # MQTT client setup
        self.mqtt_client = None
        self._socket_pool = None
        self._current_message = None  # Track message being published

        print(f"MQTT: Publisher initialized for {broker}:{port}")
        print(f"MQTT: Username: {username}")
        print(f"MQTT: Max queue size: {max_queue_size}")
        print(f"MQTT: Publish rate: {publishes_per_minute}/minute")
        print(f"MQTT: Free memory: {gc.mem_free()} bytes")

    def _setup_mqtt_client(self):
        """Set up MQTT client with callbacks"""
        try:
            # Create socket pool if needed
            if self._socket_pool is None:
                self._socket_pool = socketpool.SocketPool(wifi.radio)

            # Create MQTT client
            self.mqtt_client = MQTT.MQTT(
                broker=self.broker,
                port=self.port,
                username=self.username,
                password=self.key,
                socket_pool=self._socket_pool,
                ssl_context=ssl.create_default_context() if self.port == 8883 else None,
                keep_alive=60,  # Adafruit IO requires keepalive
            )

            # Set up callbacks
            self.mqtt_client.on_connect = self._on_connect
            self.mqtt_client.on_disconnect = self._on_disconnect
            self.mqtt_client.on_publish = self._on_publish

            print("MQTT: Client configured")
            return True

        except Exception as e:
            print(f"MQTT: Client setup error: {e}")
            return False

    def _on_connect(self, client, userdata, flags, rc):
        """Callback for successful connection"""
        print(f"MQTT: Connected with result code {rc}")
        self.state = self.CONNECTED
        self._connected_at = time.monotonic()

    def _on_disconnect(self, client, userdata, rc):
        """Callback for disconnection"""
        print(f"MQTT: Disconnected with result code {rc}")
        self.state = self.DISCONNECTED
        self._connected_at = None

    def _on_publish(self, client, userdata, topic, pid):
        """Callback for successful publish"""
        # This is called when QoS > 0 and broker confirms receipt
        pass

    def tick(self):
        """Main update cycle - non-blocking"""
        # Memory check every 10 seconds
        now = time.monotonic()
        if now - self._last_gc > 10:
            self._check_memory()
            self._last_gc = now

        # State machine
        if self.state == self.DISCONNECTED:
            # Try to connect
            if self._should_connect(now):
                self.state = self.CONNECTING
                self._connect_time = now
                print(f"MQTT: Connecting to {self.broker}...")

                # Set up client if needed
                if self.mqtt_client is None:
                    if not self._setup_mqtt_client():
                        self.state = self.DISCONNECTED
                        return

                # Attempt connection
                try:
                    print(f"MQTT: Attempting connection to {self.broker}:{self.port}")
                    print(f"MQTT: Using username: {self.username}")
                    print(f"MQTT: Free memory before connect: {gc.mem_free()}")
                    self.mqtt_client.connect()
                except Exception as e:
                    print(f"MQTT: Connection failed: {e}")
                    if "memory" in str(e).lower():
                        print("MQTT: Possible memory issue - collecting garbage")
                        gc.collect()
                        print(f"MQTT: Free memory after GC: {gc.mem_free()}")
                    self.state = self.DISCONNECTED
                    self._connect_time = now  # For retry delay

        elif self.state == self.CONNECTING:
            # Check if connected (callback will change state)
            if now - self._connect_time > 10:  # 10 second timeout
                print("MQTT: Connection timeout")
                self.state = self.DISCONNECTED
                try:
                    self.mqtt_client.disconnect()
                except:
                    pass

        elif self.state == self.CONNECTED:
            # Handle keepalive
            if now - self._last_ping > 30:  # Ping every 30 seconds
                try:
                    self.mqtt_client.ping()
                    self._last_ping = now
                except Exception as e:
                    print(f"MQTT: Ping failed: {e}")
                    self.state = self.DISCONNECTED
                    return

            # Check if we have messages and tokens to publish
            if len(self.queue) > 0:
                # Check rate limit
                if self.rate_manager.can_publish():
                    self.state = self.PUBLISHING
                    self.publishing = True
                    self._publish_start_time = now
                    self._current_message = self._get_next_message()
                else:
                    # Rate limited - check if we should warn about queue buildup
                    if now - self._last_publish_attempt > 2:  # Only log every 2 seconds
                        wait_time = self.rate_manager.get_wait_time()
                        print(f"MQTT: Rate limited. Next token in {wait_time:.1f}s. Queue: {len(self.queue)}")
                        self._last_publish_attempt = now
                        self.messages_rate_limited += 1

        elif self.state == self.PUBLISHING:
            # Try to publish
            if self._current_message:
                try:
                    # Consume token first
                    if self.rate_manager.consume():
                        # Build Adafruit IO topic
                        topic = f"{self.username}/feeds/{self._current_message['topic']}"

                        # Publish with QoS 1 (at least once delivery)
                        self.mqtt_client.publish(topic, self._current_message['payload'], qos=1)

                        # Log success
                        rate_info = self.rate_manager.get_status()
                        print(f"MQTT: Published [{self._current_message['topic']}] = {self._current_message['payload'][:50]}{'...' if len(self._current_message['payload']) > 50 else ''}")
                        #print(f"      Priority: {self._current_message['priority']}, Tokens left: {rate_info['tokens']:.1f}")

                        self.messages_sent += 1
                    else:
                        print(f"MQTT: ERROR - Token disappeared during publish!")

                except Exception as e:
                    print(f"MQTT: Publish failed: {e}")
                    self.publish_failures += 1
                    # Put message back in queue if it was important
                    if self._current_message['priority'] >= self.CRITICAL:
                        self.queue.insert(0, self._current_message)
                        print("MQTT: Re-queued CRITICAL message")

                self._current_message = None
                self.publishing = False
                self.state = self.CONNECTED

    def publish_status(self, status_dict, priority=None):
        """Queue a status message for publishing"""
        if priority is None:
            priority = self.CRITICAL

        # For Adafruit IO, we might want to use their group publish
        # For now, publish to a 'status' feed as JSON
        import json
        payload = json.dumps(status_dict)
        return self._queue_message("hottub.status", payload, priority)

    def publish_metric(self, topic, value, priority=None):
        """Queue a metric for publishing"""
        if priority is None:
            priority = self.NORMAL

        # Ensure topic is clean for Adafruit IO (alphanumeric, dash, underscore)
        clean_topic = topic.replace("/", "-").replace(" ", "_").lower()
        return self._queue_message(f"hottub-{clean_topic}", str(value), priority)

    def request_burst_mode(self, reason, duration=30):
        """Request burst mode for critical events"""
        success = self.rate_manager.request_burst_mode(duration, reason)
        if success:
            print(f"MQTT: Burst mode activated - {reason}")
            # Immediately try to publish any queued CRITICAL messages
            critical_count = sum(1 for msg in self.queue if msg['priority'] == self.CRITICAL)
            if critical_count > 0:
                print(f"MQTT: {critical_count} CRITICAL messages in queue, publishing immediately")
        return success

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

        # Check for queue warnings
        if len(self.queue) > self.max_queue_size * 0.8:
            print(f"MQTT: WARNING - Queue {len(self.queue)}/{self.max_queue_size} full")

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
        # Retry every 10 seconds when disconnected
        return self._connected_at is None or (now - self._connect_time) > 10

    def _check_memory(self):
        """Monitor memory usage"""
        free = gc.mem_free()

        if free < 30000:
            print(f"MQTT: WARNING - Low memory: {free} bytes free")
            # Could trigger emergency flush here

    def set_rate(self, publishes_per_minute):
        """Change publish rate (for dev/prod modes)"""
        self.rate_manager.set_rate(publishes_per_minute)
        print(f"MQTT: Publish rate changed to {publishes_per_minute}/minute")

    def disconnect(self):
        """Cleanly disconnect from broker"""
        if self.mqtt_client and self.state != self.DISCONNECTED:
            try:
                self.mqtt_client.disconnect()
                print("MQTT: Disconnected cleanly")
            except Exception as e:
                print(f"MQTT: Disconnect error: {e}")
        self.state = self.DISCONNECTED

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

        rate_status = self.rate_manager.get_status()

        return {
            "state": self.state,
            "connected": self.is_connected(),
            "queue_size": len(self.queue),
            "messages_sent": self.messages_sent,
            "messages_dropped": self.messages_dropped,
            "messages_rate_limited": self.messages_rate_limited,
            "publish_failures": self.publish_failures,
            "uptime": uptime,
            "memory_free": gc.mem_free(),
            "rate": rate_status["rate"],
            "tokens": rate_status["tokens"]
        }

    def get_queue_info(self):
        """Get queue breakdown by priority"""
        info = {0: 0, 1: 0, 2: 0}
        for msg in self.queue:
            info[msg["priority"]] += 1
        return {"by_priority": info}


# Test code
def main():
    """Test MQTT Publisher with Adafruit IO"""
    import os

    print("Starting MQTT Publisher test with Adafruit IO...")
    print("=" * 60)

    # Check if WiFi is connected
    if not wifi.radio.connected:
        print("ERROR: WiFi not connected!")
        print("This module requires WiFi to be connected first.")
        print("Run the executive module (code.py) instead.")
        return

    print(f"WiFi connected. IP: {wifi.radio.ipv4_address}")

    # Get credentials from environment
    aio_username = os.getenv("AIO_USERNAME")
    aio_key = os.getenv("AIO_KEY")

    if not aio_username or not aio_key:
        print("ERROR: Set AIO_USERNAME and AIO_KEY in settings.toml")
        print("Example:")
        print('AIO_USERNAME = "your_username"')
        print('AIO_KEY = "your_key"')
        return

    # Create publisher at development rate
    mqtt = MQTTPublisher("io.adafruit.com", 8883, aio_username, aio_key,
                        publishes_per_minute=20)

    # Test tracking
    test_start = time.monotonic()
    last_status = time.monotonic()
    last_telemetry = time.monotonic()
    message_count = 0

    print("\nStarting test - will publish real data to Adafruit IO!")
    print("Press Ctrl+C to stop\n")

    while True:
        mqtt.tick()

        now = time.monotonic()
        elapsed = now - test_start

        # Only publish if connected
        if mqtt.is_connected():
            # Queue a status message every 10 seconds
            if now - last_status > 10:
                status = {
                    "timestamp": int(now),
                    "rssi": -67,
                    "ph": 7.2,
                    "temp_f": 98.6,
                    "memory": gc.mem_free()
                }
                mqtt.publish_status(status)
                print(f"[{elapsed:.0f}s] Queued status message")
                last_status = now

            # Queue telemetry every 3 seconds (slower for real testing)
            if now - last_telemetry > 3:
                message_count += 1

                # Rotate through different metrics
                if message_count % 4 == 0:
                    mqtt.publish_metric("ph", 7.2 + (message_count % 10) * 0.01)
                elif message_count % 4 == 1:
                    mqtt.publish_metric("temp-f", 98.6 + (message_count % 5) * 0.1)
                elif message_count % 4 == 2:
                    mqtt.publish_metric("temp-c", 37.0 + (message_count % 5) * 0.05)
                else:
                    mqtt.publish_metric("rssi", -65 - (message_count % 10))

                last_telemetry = now

        # Print full status every 15 seconds
        if int(elapsed) % 15 == 0 and int(elapsed) != int(elapsed - 0.05):
            status = mqtt.get_status()
            queue_info = mqtt.get_queue_info()
            print(f"\n[{elapsed:.0f}s] {'='*50}")
            print(f"Status: {status}")
            print(f"Queue: {queue_info}")
            print(f"{'='*50}\n")

        # End test after 60 seconds
        if elapsed > 60:
            print(f"\n[{elapsed:.0f}s] Test complete!")
            mqtt.disconnect()
            final_status = mqtt.get_status()
            print(f"Final status: {final_status}")
            break

        time.sleep(0.05)  # 50ms tick


if __name__ == "__main__":
    main()