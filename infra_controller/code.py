# Version: 2.3

from time import sleep, monotonic
import wifi
import os
import array
import math

# Configuration
START_HOURS, START_MINUTES, START_SECONDS = 0, 0, 0  # Start time: 00:00:00
BUFFER_SECONDS = 60  # Store last 60 seconds of RSSI and channel
DIAG_INTERVAL = 240  # Diagnostics every 1 minute (240 cycles at 0.25 s)
SAMPLE_INTERVAL = 0.25  # Sample every 0.25 seconds (4 Hz)
BUFFER_SIZE = int(BUFFER_SECONDS / SAMPLE_INTERVAL)  # 240 entries for 60 seconds
RSSI_OUTLIER_THRESHOLD = 5  # dBm deviation for outlier detection

# Circular buffers for RSSI, channel, and timestamps
rssi_buffer = array.array("i", [0] * BUFFER_SIZE)  # Signed int for RSSI
channel_buffer = array.array("i", [0] * BUFFER_SIZE)  # Signed int for channel
buffer_timestamps = array.array("f", [0.0] * BUFFER_SIZE)  # Float for monotonic()
buffer_index = 0

# Variability tracking
rssi_samples = []  # Store valid RSSI for variability calculation
RSSI_WINDOW = BUFFER_SIZE  # 240 samples for 60 seconds
outlier_count = 0  # Count RSSI outliers (>5 dBm from mean)

start_time = monotonic()


# Function to add seconds to time
def add_seconds_direct(hours, minutes, seconds, n):
    total_seconds = hours * 3600 + minutes * 60 + seconds + n
    new_hours = total_seconds // 3600
    total_seconds %= 3600
    new_minutes = total_seconds // 60
    new_seconds = total_seconds % 60
    return f"{new_hours:02d}:{new_minutes:02d}:{new_seconds:02d}"


# Function to dump buffer
def dump_buffer(current_time, cycle_count, pre_dropout_start=None):
    print(
        f"[{current_time}] Cycle {cycle_count}: Buffer contents (last {BUFFER_SECONDS} seconds):"
    )
    if pre_dropout_start is not None:
        start_cycle = pre_dropout_start
    else:
        start_cycle = cycle_count - BUFFER_SIZE + 1
    data = [
        {
            "cycle": start_cycle + i,
            "time": add_seconds_direct(
                START_HOURS, START_MINUTES, START_SECONDS, int(t - start_time)
            ),
            "rssi": r,
            "channel": c,
        }
        for i, (t, r, c) in enumerate(
            zip(buffer_timestamps, rssi_buffer, channel_buffer)
        )
        if r != -999 and c != 0
    ]
    for entry in data:
        print(
            f"  Cycle {entry['cycle']}: {entry['time']}: RSSI {entry['rssi']} dBm, Channel {entry['channel']}"
        )
    print(f"[{current_time}] Printed {len(data)} values")
    return len(data)


# Connect to Wi-Fi
try:
    wifi.radio.enabled = True
    wifi.radio.connect(os.getenv("WIFI_SSID"), os.getenv("WIFI_PASSWORD"))
    print("Wi-Fi connected")
except Exception as e:
    print(f"Wi-Fi connection failed: {e}")

# Print initial info
print("IP:", wifi.radio.ipv4_address or "Not connected")

cycle_count = 0
last_connected = True
dropout_detected = False
in_simulated_dropout = False
pre_dropout_cycle = None

while True:
    try:
        cycle_count += 1

        # Calculate uptime
        uptime_seconds = monotonic() - start_time
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        seconds = int(uptime_seconds % 60)
        current_time = add_seconds_direct(
            START_HOURS, START_MINUTES, START_SECONDS, int(uptime_seconds)
        )

        # Read RSSI and channel
        rssi = None
        channel = None
        try:
            ap = wifi.radio.ap_info
            if ap and not in_simulated_dropout:
                rssi = ap.rssi
                channel = ap.channel
                if not last_connected:
                    print(
                        f"[{current_time}] Cycle {cycle_count}: Reconnected after dropout"
                    )
                    dump_buffer(current_time, cycle_count, pre_dropout_cycle)
                    dropout_detected = True
                last_connected = True
            else:
                if last_connected and not in_simulated_dropout:
                    pre_dropout_cycle = cycle_count - 1
                if last_connected:
                    dropout_detected = False
                    last_connected = False
                rssi = None
                channel = None
                print(f"[{current_time}] Cycle {cycle_count}: No active AP")
        except Exception as e:
            if last_connected and not in_simulated_dropout:
                pre_dropout_cycle = cycle_count - 1
            if last_connected:
                dropout_detected = False
                last_connected = False
            rssi = None
            channel = None
            print(f"[{current_time}] Cycle {cycle_count}: AP info error: {e}")

        # Store RSSI and channel in circular buffer (only if connected)
        if last_connected and not in_simulated_dropout:
            rssi_buffer[buffer_index] = rssi if rssi is not None else -999
            channel_buffer[buffer_index] = channel if channel is not None else 0
            buffer_timestamps[buffer_index] = monotonic()
            buffer_index = (buffer_index + 1) % BUFFER_SIZE

        # Track RSSI variability
        if rssi is not None:
            rssi_samples.append(rssi)
            if len(rssi_samples) > RSSI_WINDOW:
                rssi_samples.pop(0)
            if len(rssi_samples) >= RSSI_WINDOW and cycle_count % DIAG_INTERVAL == 0:
                mean_rssi = sum(rssi_samples) / len(rssi_samples)
                variance = sum((x - mean_rssi) ** 2 for x in rssi_samples) / len(
                    rssi_samples
                )
                std_dev = math.sqrt(variance) if variance > 0 else 0
                min_rssi = min(rssi_samples)
                max_rssi = max(rssi_samples)
                outliers = sum(
                    1
                    for x in rssi_samples
                    if abs(x - mean_rssi) > RSSI_OUTLIER_THRESHOLD
                )
                outlier_count += outliers
                print(
                    f"[{current_time}] Cycle {cycle_count}: RSSI Variability (last 60s): Mean {mean_rssi:.1f} dBm, Std Dev {std_dev:.1f} dBm, Min {min_rssi} dBm, Max {max_rssi} dBm, Outliers {outliers}, Total Outliers {outlier_count}"
                )

        # Periodic reconnection with retry
        if not last_connected and cycle_count % 40 == 0 and not in_simulated_dropout:
            for _ in range(3):
                try:
                    wifi.radio.enabled = True
                    wifi.radio.connect(
                        os.getenv("WIFI_SSID"), os.getenv("WIFI_PASSWORD")
                    )
                    sleep(0.5)
                    if wifi.radio.connected:
                        print(f"[{current_time}] Cycle {cycle_count}: Reconnected")
                        if not dropout_detected:
                            print(
                                f"[{current_time}] Cycle {cycle_count}: Reconnected after dropout"
                            )
                            dump_buffer(current_time, cycle_count)
                            dropout_detected = True
                        last_connected = True
                        break
                except Exception as e:
                    print(
                        f"[{current_time}] Cycle {cycle_count}: Reconnect failed: {e}"
                    )
                    sleep(0.5)
            if not last_connected:
                print(
                    f"[{current_time}] Cycle {cycle_count}: All reconnect attempts failed"
                )

        # Debug: Print buffer status before dropout
        if cycle_count == 479:
            print(f"[{current_time}] Cycle {cycle_count}: Pre-dropout buffer status:")
            dump_buffer(current_time, cycle_count)

        # Debug: Print buffer index at cycle 120 and 240
        if cycle_count in (120, 240):
            print(f"[{current_time}] Cycle {cycle_count}: Buffer index: {buffer_index}")

        # Simulate 2-minute dropout
        if cycle_count == 480:  # ~2 minutes (120s / 0.25s = 480 cycles)
            print(f"[{current_time}] Cycle {cycle_count}: Simulating Wi-Fi dropout")
            wifi.radio.enabled = False
            wifi.radio.stop_station()
            in_simulated_dropout = True
        if cycle_count == 960:  # ~4 minutes (240s / 0.25s = 960 cycles)
            print(f"[{current_time}] Cycle {cycle_count}: Ending simulated dropout")
            wifi.radio.enabled = True
            in_simulated_dropout = False
            sleep(0.5)
            for _ in range(3):
                try:
                    wifi.radio.connect(
                        os.getenv("WIFI_SSID"), os.getenv("WIFI_PASSWORD")
                    )
                    sleep(0.5)
                    if wifi.radio.connected:
                        print(
                            f"[{current_time}] Cycle {cycle_count}: Reconnected (post-dropout)"
                        )
                        if not dropout_detected:
                            print(
                                f"[{current_time}] Cycle {cycle_count}: Reconnected after dropout"
                            )
                            dump_buffer(current_time, cycle_count, pre_dropout_cycle)
                            dropout_detected = True
                        last_connected = True
                        break
                except Exception as e:
                    print(
                        f"[{current_time}] Cycle {cycle_count}: Post-dropout reconnect failed: {e}"
                    )
                    sleep(0.5)

        # Diagnostics (every 1 minute)
        if cycle_count % DIAG_INTERVAL == 0:
            print(
                f"[{current_time}] Cycle {cycle_count}: RSSI: {rssi if rssi is not None else 'N/A'} dBm, Channel: {channel if channel is not None else 'N/A'}"
            )

        sleep(SAMPLE_INTERVAL)

    except KeyboardInterrupt:
        print(f"[{current_time}] Cycle {cycle_count}: KeyboardInterrupt detected")
        dump_buffer(current_time, cycle_count)
        raise
    except Exception as e:
        print(f"[{current_time}] Cycle {cycle_count}: ERROR: Unexpected error: {e}")
        dump_buffer(current_time, cycle_count)
        sleep(SAMPLE_INTERVAL)
