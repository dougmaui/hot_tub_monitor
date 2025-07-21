# test_sensor_handler.py - Test sensor handler before integration
# Target Board: ESP32-S3 8MB (Infrastructure/WiFi Board)
# Rev: 1.0 - Initial test harness
# Date: 2024-01-25
"""
Simple test to verify UART communication with sensor board
Run this BEFORE integrating into production code.py
Tests UART without affecting stable WiFi/MQTT/NTP operation
"""

import time
import gc
from sensor_handler import SensorHandler

print("🧪 Testing Sensor Handler Integration")
print("=" * 50)
print("This test verifies UART communication without")
print("affecting your stable infrastructure code")
print("")

# Create handler
handler = SensorHandler()

# Initialize UART
print("Initializing UART...")
if not handler.initialize():
    print("❌ Failed to initialize UART - check connections")
    print("   - Is sensor board powered on?")
    print("   - Are TX/RX properly crossed?")
    print("   - Is ground connected?")
else:
    print("✅ UART initialized successfully")
    print("")
    print("Waiting for sensor data...")
    print("(Sensor should send status every 2 seconds)")
    print("")
    
    # Run for 30 seconds
    start_time = time.monotonic()
    last_display = 0
    
    while time.monotonic() - start_time < 30:
        # Tick the handler
        handler.tick()
        
        # Display status every 2 seconds
        now = time.monotonic()
        if now - last_display > 2:
            # Get current state
            temp_c, temp_f = handler.get_temperature()
            status = handler.get_status()
            
            # Display
            elapsed = int(now - start_time)
            if temp_c is not None:
                print(f"[{elapsed:2d}s] 🌡️  {temp_c:.2f}°C / {temp_f:.1f}°F - "
                      f"Messages: {status['messages_received']}")
            else:
                print(f"[{elapsed:2d}s] ⏳ Waiting for sensor... "
                      f"Messages: {status['messages_received']}")
                      
            # Memory check
            if elapsed % 10 == 0:
                print(f"      💾 Free memory: {gc.mem_free()} bytes")
                
            last_display = now
            
        time.sleep(0.05)  # 50ms tick
        
    # Final report
    print("")
    print("Test Complete!")
    print("=" * 50)
    final_status = handler.get_status()
    print(f"Messages received: {final_status['messages_received']}")
    print(f"Messages sent: {final_status['messages_sent']}")
    print(f"Parse errors: {final_status['parse_errors']}")
    
    if final_status['messages_received'] > 0:
        print("✅ UART communication successful!")
        print("   Ready for integration into code.py")
    else:
        print("❌ No messages received from sensor")
        print("   Check sensor board is running test_uart_json.py")
        
    # Cleanup
    handler.cleanup()
    
print("\nTest finished - restore your code.py to resume normal operation")