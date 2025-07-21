# test_uart_json.py - Test JSON protocol with real RTD data
"""
Simple test of UART JSON protocol sending real temperature data
"""

import board
import busio
import digitalio
import time
import gc
from uart_json import UARTProtocol
from rtd_sensor import RTDSensor

print("Starting UART JSON Protocol Test with RTD")
print("=" * 50)

# Initialize hardware
spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
uart = busio.UART(board.TX, board.RX, baudrate=115200, timeout=0.1)

# Initialize modules
rtd = RTDSensor(spi, board.D10)
protocol = UARTProtocol(uart, role="sensor")

print(f"Free memory: {gc.mem_free()} bytes")
print("\nSending temperature data every 2 seconds...")
print("Listening for commands...\n")

# Timing
last_status = time.monotonic()
status_interval = 2.0  # Send status every 2 seconds

try:
    while True:
        # Tick the RTD sensor
        rtd.tick()

        # Process any incoming commands
        messages = protocol.process_rx()
        for msg in messages:
            msg_type = msg.get("type")

            if msg_type == "command":
                cmd = msg.get("cmd")
                print(f"\n>>> Received command: {cmd}")

                if cmd == "GET_STATUS":
                    # Get RTD status
                    status = rtd.get_status()
                    print(f"    RTD Mode: {rtd.mode}")
                    print(f"    Success rate: {status['success_rate']}%")

                elif cmd == "SET_MODE":
                    # Change RTD mode
                    new_mode = msg.get("params", {}).get("rtd_mode", "MONITOR")
                    rtd.set_mode(new_mode)
                    print(f"    Mode changed to: {new_mode}")

        # Send periodic status
        now = time.monotonic()
        if now - last_status >= status_interval:
            # Get temperature
            temp_c, source = rtd.get_temperature()

            if temp_c is not None:
                temp_f = temp_c * 9/5 + 32

                # Send status
                protocol.send_status(temp_c, temp_f, rtd.mode)

                # Local display
                print(f"[{now:.1f}s] Sent: {temp_c:.3f}°C / {temp_f:.3f}°F - Mode: {rtd.mode}")
            else:
                print(f"[{now:.1f}s] No temperature reading available")

            last_status = now

        # Small delay
        time.sleep(0.05)

except KeyboardInterrupt:
    print("\n\nTest stopped by user")
    print(f"Free memory: {gc.mem_free()} bytes")