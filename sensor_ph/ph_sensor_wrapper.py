# ph_sensor_wrapper.py - Non-blocking pH sensor with I2C recovery
import time
import board
import busio
from ph_sensor import AtlasScientificPH

class PHSensorWrapper:
    """Non-blocking wrapper for Atlas Scientific pH sensor with safety features"""

    # States for non-blocking operation
    IDLE = "IDLE"
    COMMAND_SENT = "COMMAND_SENT"
    WAITING = "WAITING"
    READING = "READING"
    ERROR = "ERROR"

    def __init__(self, i2c_bus=None, address=0x63):
        """Initialize pH sensor wrapper
        
        Args:
            i2c_bus: Existing I2C bus or None to create
            address: I2C address (default 0x63)
        """
        # I2C setup
        if i2c_bus is None:
            self.i2c = busio.I2C(board.SCL, board.SDA)
        else:
            self.i2c = i2c_bus

        # Create wrapped sensor
        try:
            self.sensor = AtlasScientificPH(self.i2c, address)
            print(f"pH: Sensor initialized at address 0x{address:02X}")

            # Get sensor info
            info = self.sensor.get_info()
            print(f"pH: Sensor info: {info}")

        except Exception as e:
            print(f"pH: Initialization error: {e}")
            self.sensor = None

        # State machine
        self.state = self.IDLE
        self.command_time = 0
        self.wait_time = 0
        self.last_ph = None
        self.last_temp_c = None

        # Statistics
        self.read_count = 0
        self.error_count = 0
        self.recovery_count = 0
        self.last_error_time = 0

        # Configuration
        self.max_retries = 3
        self.error_timeout = 5.0  # Don't retry for 5s after error

    def tick(self):
        """Non-blocking update - call frequently"""
        now = time.monotonic()

        if self.state == self.IDLE:
            # Ready for next reading
            if self.sensor is None:
                # Try to recover
                if now - self.last_error_time > self.error_timeout:
                    self._attempt_recovery()
            return

        elif self.state == self.COMMAND_SENT:
            # Waiting for command to process
            if now - self.command_time >= self.wait_time:
                self.state = self.READING

        elif self.state == self.READING:
            # Try to read result
            self._read_result()

        elif self.state == self.ERROR:
            # Error state - wait before retry
            if now - self.last_error_time > self.error_timeout:
                self.state = self.IDLE

    def start_reading(self):
        """Start a new pH reading (non-blocking)"""
        if self.state != self.IDLE or self.sensor is None:
            return False

        try:
            self.sensor.send_command("R")
            self.command_time = time.monotonic()
            self.wait_time = 0.91  # Atlas spec: 910ms for reading
            self.state = self.COMMAND_SENT
            return True

        except Exception as e:
            print(f"pH: Send command error: {e}")
            self._handle_error()
            return False

    def _read_result(self):
        """Read the pH result (internal)"""
        try:
            code, response = self.sensor.read_response(0)  # Don't wait, we already did

            if code == 1:  # Success
                try:
                    ph_value = float(response)

                    # Basic validation
                    if 0 <= ph_value <= 14:
                        self.last_ph = ph_value
                        self.read_count += 1
                        self.state = self.IDLE
                    else:
                        print(f"pH: Value out of range: {ph_value}")
                        self._handle_error()

                except ValueError:
                    print(f"pH: Parse error: {response}")
                    self._handle_error()
            else:
                print(f"pH: Read error code {code}: {response}")
                self._handle_error()

        except Exception as e:
            print(f"pH: Read error: {e}")
            self._handle_error()

    def set_temperature_compensation(self, temp_c):
        """Update temperature compensation (non-blocking)"""
        if self.state != self.IDLE or self.sensor is None:
            return False

        # Only update if temperature changed significantly
        if self.last_temp_c is not None and abs(temp_c - self.last_temp_c) < 0.1:
            return True

        try:
            self.sensor.send_command(f"T,{temp_c:.1f}")
            self.last_temp_c = temp_c
            # Don't change state - temp command is fire-and-forget
            return True

        except Exception as e:
            print(f"pH: Temp compensation error: {e}")
            return False

    def get_ph(self):
        """Get last pH reading"""
        return self.last_ph

    def is_ready(self):
        """Check if ready for new reading"""
        return self.state == self.IDLE and self.sensor is not None

    def get_status(self):
        """Get sensor status"""
        return {
            "state": self.state,
            "last_ph": self.last_ph,
            "temp_compensation": self.last_temp_c,
            "read_count": self.read_count,
            "error_count": self.error_count,
            "recovery_count": self.recovery_count,
            "operational": self.sensor is not None
        }

    def _handle_error(self):
        """Handle errors"""
        self.error_count += 1
        self.last_error_time = time.monotonic()
        self.state = self.ERROR

        # If too many errors, mark sensor as failed
        if self.error_count > 10:
            print("pH: Too many errors, marking sensor as failed")
            self.sensor = None

    def _attempt_recovery(self):
        """Try to recover I2C communication"""
        print("pH: Attempting recovery...")

        try:
            # Try to reinitialize
            self.sensor = AtlasScientificPH(self.i2c, 0x63)
            info = self.sensor.get_info()
            print(f"pH: Recovery successful! Info: {info}")

            self.recovery_count += 1
            self.error_count = 0  # Reset error count
            self.state = self.IDLE

        except Exception as e:
            print(f"pH: Recovery failed: {e}")
            self.last_error_time = time.monotonic()