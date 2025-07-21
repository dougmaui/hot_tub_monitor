# sensor_handler.py - Sensor UART Handler for Infrastructure Board
# Target Board: ESP32-S3 8MB (Infrastructure/WiFi Board)
# Rev: 1.1 - Fixed send_command method
# Date: 2024-01-25
"""
Handles UART communication with sensor board
Designed to integrate cleanly with existing infrastructure executive
Receives temperature data from sensor board via UART JSON protocol
"""

import time
import board
import busio
from uart_json import UARTProtocol


class SensorHandler:
    """Manages communication with sensor board"""
    
    def __init__(self):
        """Initialize UART communication"""
        self.enabled = False
        self.uart = None
        self.protocol = None
        
        # Sensor data storage
        self.latest_temp_c = None
        self.latest_temp_f = None
        self.rtd_mode = None
        self.last_sensor_update = 0
        self.sensor_timeout = 10.0  # Consider sensor offline after 10s
        
        # Command tracking
        self.last_command_time = 0
        self.command_interval = 30.0  # Send status request every 30s
        
        # Statistics
        self.messages_received = 0
        self.messages_sent = 0
        self.parse_errors = 0
        
        print("SENSOR: Handler initialized (disabled by default)")
        
    def initialize(self):
        """Initialize UART hardware and protocol"""
        try:
            # Initialize UART at 115200 baud
            self.uart = busio.UART(board.TX, board.RX, baudrate=115200, timeout=0.1)
            self.protocol = UARTProtocol(self.uart, role="infrastructure")
            self.enabled = True
            
            print("SENSOR: UART initialized successfully")
            print(f"SENSOR: TX pin: {board.TX}, RX pin: {board.RX}")
            return True
            
        except Exception as e:
            print(f"SENSOR: Failed to initialize UART: {e}")
            self.enabled = False
            return False
            
    def tick(self):
        """Non-blocking update cycle"""
        if not self.enabled:
            return
            
        # Process incoming messages
        try:
            messages = self.protocol.process_rx()
            for msg in messages:
                self._handle_message(msg)
        except Exception as e:
            print(f"SENSOR: Error processing messages: {e}")
            self.parse_errors += 1
            
        # Send periodic status requests
        now = time.monotonic()
        if now - self.last_command_time > self.command_interval:
            self._send_status_request()
            self.last_command_time = now
            
    def _handle_message(self, msg):
        """Process received message from sensor"""
        self.messages_received += 1
        
        if msg.get('type') == 'status':
            # Update sensor readings
            sensors = msg.get('sensors', {})
            self.latest_temp_c = sensors.get('temp_c')
            self.latest_temp_f = sensors.get('temp_f')
            self.rtd_mode = sensors.get('rtd_mode')
            self.last_sensor_update = time.monotonic()
            
            # Log significant updates (every 10th message to reduce spam)
            if self.messages_received % 10 == 1:
                print(f"SENSOR: Temp: {self.latest_temp_c:.2f}°C / {self.latest_temp_f:.1f}°F, Mode: {self.rtd_mode}")
                
    def _send_status_request(self):
        """Send GET_STATUS command to sensor"""
        try:
            # Use the send_command method from uart_json.py
            self.protocol.send_command("GET_STATUS")
            self.messages_sent += 1
        except Exception as e:
            print(f"SENSOR: Failed to send status request: {e}")
            
    def is_sensor_online(self):
        """Check if sensor is responding"""
        if not self.enabled or self.last_sensor_update == 0:
            return False
            
        age = time.monotonic() - self.last_sensor_update
        return age < self.sensor_timeout
        
    def get_temperature(self):
        """Get latest temperature reading"""
        if self.is_sensor_online():
            return self.latest_temp_c, self.latest_temp_f
        return None, None
        
    def get_status(self):
        """Get handler status for monitoring"""
        online = self.is_sensor_online()
        age = None
        if self.last_sensor_update > 0:
            age = int(time.monotonic() - self.last_sensor_update)
            
        return {
            "enabled": self.enabled,
            "online": online,
            "temp_c": self.latest_temp_c,
            "temp_f": self.latest_temp_f,
            "rtd_mode": self.rtd_mode,
            "last_update_age": age,
            "messages_received": self.messages_received,
            "messages_sent": self.messages_sent,
            "parse_errors": self.parse_errors
        }
        
    def cleanup(self):
        """Clean up UART resources"""
        if self.uart:
            try:
                self.uart.deinit()
                print("SENSOR: UART cleaned up")
            except:
                pass
        self.enabled = False


# Test code
def main():
    """Test sensor handler standalone"""
    print("Testing Sensor Handler...")
    print("=" * 50)
    
    handler = SensorHandler()
    
    # Initialize UART
    if not handler.initialize():
        print("Failed to initialize handler")
        return
        
    print("\nWaiting for sensor data...")
    print("Press Ctrl+C to stop\n")
    
    last_status = time.monotonic()
    
    try:
        while True:
            handler.tick()
            
            # Print status every 5 seconds
            if time.monotonic() - last_status > 5:
                status = handler.get_status()
                print(f"\nHandler Status: {status}")
                
                temp_c, temp_f = handler.get_temperature()
                if temp_c is not None:
                    print(f"Current temp: {temp_c:.2f}°C / {temp_f:.1f}°F")
                else:
                    print("No temperature data available")
                    
                last_status = time.monotonic()
                
            time.sleep(0.05)  # 50ms tick
            
    except KeyboardInterrupt:
        print("\n\nTest stopped by user")
        handler.cleanup()
        

if __name__ == "__main__":
    main()