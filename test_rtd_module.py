# test_rtd_module.py - Test harness for RTD sensor module
"""
Test program for RTD sensor module
Provides visual feedback without modifying the production module
"""

import board
import busio
import digitalio
import time
import gc
from rtd_sensor import RTDSensor


def format_status_line(status):
    """Format a concise status line"""
    if status['temp_c'] is not None:
        temp_str = str(round(status['temp_c'], 3)) + "C"
    else:
        temp_str = "----.---C"

    if status['temp_f'] is not None:
        temp_f_str = str(round(status['temp_f'], 1)) + "F"
    else:
        temp_f_str = "---.-F"

    health_map = {
        'healthy': 'OK',
        'warning': 'WARN',
        'degraded': 'DEGR',
        'error': 'ERR'
    }
    health_indicator = health_map.get(status['health'], '?')

    line = temp_str + " " + temp_f_str + " | "
    line += "State: " + status['state'] + " | "
    line += "Mode: " + status['mode'] + " | "
    line += "Health: " + health_indicator + " | "
    line += "Success: " + str(status['success_rate']) + "%"

    return line


def main():
    """Test RTD Sensor module with visual feedback"""
    print("RTD Sensor Module Test")
    print("=" * 80)
    print("Prime number sampling intervals active")
    print("Will switch modes every 30 seconds to demonstrate")
    print("-" * 80)

    # Initialize SPI
    spi = busio.SPI(board.SCK, board.MOSI, board.MISO)

    # Create sensor instance
    rtd = RTDSensor(spi, board.D10)

    # Test control
    start_time = time.monotonic()
    last_display = 0
    display_interval = 1.0  # Update display every second

    mode_switch_interval = 30  # Switch modes every 30 seconds
    next_mode_switch = start_time + mode_switch_interval
    current_test_mode = 0

    # Temperature tracking for change detection
    last_temp = None
    temp_readings = []

    print("\nTime     Temperature        State      Mode      Health  Success")
    print("-" * 80)

    try:
        while True:
            # Tick the sensor
            rtd.tick()

            now = time.monotonic()
            elapsed = now - start_time

            # Mode switching for demonstration
            if now >= next_mode_switch:
                current_test_mode = (current_test_mode + 1) % 2
                if current_test_mode == 1:
                    new_mode = RTDSensor.MEASUREMENT_MODE
                else:
                    new_mode = RTDSensor.MONITOR_MODE
                rtd.set_mode(new_mode)
                print("\n[" + str(round(elapsed, 1)) + "s] Mode switched to: " + new_mode)
                print("-" * 80)
                next_mode_switch = now + mode_switch_interval

            # Display updates
            if now - last_display >= display_interval:
                status = rtd.get_status()

                # Track temperature changes
                if status['temp_c'] is not None:
                    temp_readings.append(status['temp_c'])
                    if len(temp_readings) > 60:
                        temp_readings.pop(0)

                    # Calculate statistics
                    if len(temp_readings) > 1:
                        temp_min = min(temp_readings)
                        temp_max = max(temp_readings)
                        temp_range = temp_max - temp_min
                        temp_avg = sum(temp_readings) / len(temp_readings)
                    else:
                        temp_range = 0
                        if temp_readings:
                            temp_avg = temp_readings[0]
                        else:
                            temp_avg = 0

                # Format and display
                line = format_status_line(status)
                elapsed_str = "[" + str(round(elapsed, 1)) + "s] "
                print(elapsed_str + line)

                # Show statistics every 20 seconds
                if int(elapsed) % 20 == 0 and len(temp_readings) > 0:
                    print("\nStats: Avg=" + str(round(temp_avg, 3)) + "C, Range=" + str(round(temp_range, 3)) + "C, " +
                          "Samples=" + str(len(temp_readings)) + ", Memory=" + str(gc.mem_free()) + " bytes")

                    # Show interval pattern
                    if status['mode'] == 'MEASURE':
                        interval_ms = rtd.FAST_PRIME_INTERVALS_MS
                    else:
                        interval_ms = rtd.PRIME_INTERVALS_MS
                    current_interval = interval_ms[status['interval_index']]
                    print("Current interval: " + str(current_interval) + "ms (index " + str(status['interval_index']) + ")")
                    print("-" * 80)

                last_display = now

            # Maintain 50ms tick rate
            time.sleep(0.05)

    except KeyboardInterrupt:
        elapsed_final = time.monotonic() - start_time
        print("\n\nTest completed after " + str(round(elapsed_final, 1)) + " seconds")

        # Final statistics
        final_status = rtd.get_status()
        print("\nFinal Status:")
        print("   Total reads: " + str(final_status['total_reads']))
        print("   Successful: " + str(final_status['successful_reads']))
        print("   Errors: " + str(final_status['error_count']))
        print("   Success rate: " + str(final_status['success_rate']) + "%")
        if final_status['last_error']:
            print("   Last error: " + str(final_status['last_error']))
        else:
            print("   Last error: None")

        if temp_readings:
            avg_temp = sum(temp_readings) / len(temp_readings)
            min_temp = min(temp_readings)
            max_temp = max(temp_readings)
            range_temp = max_temp - min_temp

            print("\nTemperature Statistics:")
            print("   Average: " + str(round(avg_temp, 3)) + "C")
            print("   Min: " + str(round(min_temp, 3)) + "C")
            print("   Max: " + str(round(max_temp, 3)) + "C")
            print("   Range: " + str(round(range_temp, 3)) + "C")


if __name__ == "__main__":
    main()