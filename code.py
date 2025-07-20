# code.py - Temporary executive for sensor board testing
"""
Temporary executive module for ESP32-S3 Sensor Board
This will eventually coordinate RTD, pH, dosing, and UART
For now, it just runs the RTD test
"""

import time
import gc

# Import and run the RTD test
print("ESP32-S3 Sensor Board Starting...")
print(f"Free memory: {gc.mem_free()} bytes")
print("")

# Run the RTD module test
from test_rtd_module import main

# Start the test
main()