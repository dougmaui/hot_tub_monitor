# uart_json.py - Minimal JSON UART Protocol Handler
"""
Simple JSON message protocol for UART communication
Handles basic send/receive with newline delimiters
"""
import json
import time


class UARTProtocol:
    """Handles JSON messaging over UART"""

    def __init__(self, uart, role="sensor"):
        """Initialize protocol handler
        
        Args:
            uart: CircuitPython UART object
            role: "sensor" or "infrastructure"
        """
        self.uart = uart
        self.role = role
        self.rx_buffer = ""
        self.message_count = 0

        print(f"UART Protocol initialized as {role}")

    def send_status(self, temp_c, temp_f, rtd_mode="MONITOR"):
        """Send a status message (sensor side)"""
        message = {
            "type": "status",
            "timestamp": time.monotonic(),  # Simple timestamp for now
            "sensors": {
                "temp_c": round(temp_c, 3),
                "temp_f": round(temp_f, 3),
                "rtd_mode": rtd_mode
            }
        }

        self._send_message(message)

    def send_command(self, cmd, params=None):
        """Send a command (infrastructure side)"""
        self.message_count += 1
        message = {
            "type": "command",
            "id": f"cmd_{self.message_count}",
            "cmd": cmd
        }
        if params:
            message["params"] = params

        self._send_message(message)

    def _send_message(self, message):
        """Internal: Send a message over UART"""
        try:
            # Convert to JSON and add newline
            json_str = json.dumps(message) + "\n"

            # Send over UART
            self.uart.write(json_str.encode('utf-8'))

            # Debug print removed for quiet operation
            # print(f"TX: {json_str.strip()}")

        except Exception as e:
            print(f"Send error: {e}")

    def process_rx(self):
        """Check for received messages
        
        Returns:
            List of parsed messages (can be empty)
        """
        messages = []

        # Read available data
        if self.uart.in_waiting > 0:
            try:
                # Read up to 256 bytes at a time
                data = self.uart.read(256)
                if data:
                    self.rx_buffer += data.decode('utf-8')

            except Exception as e:
                print(f"RX decode error: {e}")
                # Clear buffer on decode error
                self.rx_buffer = ""

        # Look for complete messages (newline terminated)
        while '\n' in self.rx_buffer:
            line, self.rx_buffer = self.rx_buffer.split('\n', 1)

            # Skip empty lines
            if not line.strip():
                continue

            # Try to parse JSON
            try:
                message = json.loads(line)
                messages.append(message)

                # Debug print removed for quiet operation
                # print(f"RX: {line}")

            except json.JSONDecodeError as e:
                print(f"JSON parse error: {e}")
                print(f"Bad line: {line}")

        # Prevent buffer from growing too large
        if len(self.rx_buffer) > 1024:
            print("RX buffer overflow - clearing")
            self.rx_buffer = ""

        return messages


# Test function for standalone testing
def test_protocol():
    """Test the protocol handler standalone"""
    import board
    import busio

    # Set up UART
    uart = busio.UART(board.TX, board.RX, baudrate=115200, timeout=0.1)

    # Create protocol handler
    protocol = UARTProtocol(uart, role="sensor")

    print("Testing UART JSON Protocol")
    print("Sending test status message...")

    # Send a test status
    protocol.send_status(27.543, 81.6, "MONITOR")

    # Check for incoming
    print("\nWaiting for incoming messages...")
    start = time.monotonic()
    while time.monotonic() - start < 10:
        messages = protocol.process_rx()
        for msg in messages:
            print(f"\nReceived message:")
            print(f"  Type: {msg.get('type')}")
            print(f"  Content: {msg}")

        time.sleep(0.1)

    print("\nTest complete")


if __name__ == "__main__":
    test_protocol()