# uart_json.py - Minimal JSON UART Protocol Handler (with pH support)
"""
Simple JSON message protocol for UART communication
Handles basic send/receive with newline delimiters
Updated to include pH in status messages
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

    def send_status(self, temp_c, temp_f, rtd_mode="MONITOR", ph=None):
        """Send a status message (sensor side)
        
        Args:
            temp_c: Temperature in Celsius
            temp_f: Temperature in Fahrenheit
            rtd_mode: RTD operating mode
            ph: pH value (optional)
        """
        message = {
            "type": "status",
            "timestamp": time.monotonic(),
            "sensors": {
                "temp_c": round(temp_c, 3) if temp_c is not None else None,
                "temp_f": round(temp_f, 3) if temp_f is not None else None,
                "rtd_mode": rtd_mode
            }
        }

        # Add pH if provided
        if ph is not None:
            message["sensors"]["ph"] = round(ph, 3)

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

            except ValueError as e:  # CircuitPython uses ValueError not JSONDecodeError
                print(f"JSON parse error: {e}")
                print(f"Bad line: {line}")

        # Prevent buffer from growing too large
        if len(self.rx_buffer) > 1024:
            print("RX buffer overflow - clearing")
            self.rx_buffer = ""

        return messages