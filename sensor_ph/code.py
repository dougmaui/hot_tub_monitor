# code.py - Sensor board executive (JSON test mode)
"""
Back to running the full JSON protocol test with RTD
"""
import time
import gc

print("ESP32-S3 Sensor Board Starting...")
print(f"Free memory: {gc.mem_free()} bytes")
print("")

# Run the UART JSON test with RTD
print("Starting UART JSON protocol test...")
exec(open("test_uart_json.py").read())