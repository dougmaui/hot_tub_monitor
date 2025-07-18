# bssid_range_test.py - Comprehensive BSSID Control Test
"""
Test the full range of BSSID control capabilities
"""

import wifi
import time
import os
import microcontroller

# Get credentials
SSID = os.getenv("WIFI_SSID", "TestNetwork")
PASSWORD = os.getenv("WIFI_PASSWORD", "testpass")

print("COMPREHENSIVE BSSID CONTROL TEST")
print(f"Target SSID: {SSID}")
print("=" * 60)


# Helper function to get current connection info
def get_connection_info():
    if wifi.radio.connected and wifi.radio.ap_info:
        bssid = ":".join(["%02X" % b for b in wifi.radio.ap_info.bssid])
        return {
            "connected": True,
            "bssid": bssid,
            "rssi": wifi.radio.ap_info.rssi,
            "channel": wifi.radio.ap_info.channel,
        }
    return {"connected": False}


# Step 1: Initial scan
print("\n1. INITIAL SCAN")
print("-" * 40)
networks = []
for network in wifi.radio.start_scanning_networks():
    if network.ssid == SSID:
        bssid_str = ":".join(["%02X" % b for b in network.bssid])
        networks.append(
            {
                "ssid": network.ssid,
                "rssi": network.rssi,
                "channel": network.channel,
                "bssid": network.bssid,
                "bssid_str": bssid_str,
            }
        )
wifi.radio.stop_scanning_networks()

# Sort by signal strength
networks.sort(key=lambda x: x["rssi"], reverse=True)

print(f"Found {len(networks)} access points:")
for i, ap in enumerate(networks):
    print(f"  #{i+1}: Ch{ap['channel']:2d} RSSI:{ap['rssi']:3d} {ap['bssid_str']}")

if len(networks) < 2:
    print("\nNeed at least 2 APs for this test!")
    raise SystemExit

# Step 2: Connect to WEAKEST on fresh boot
print("\n2. TEST: Connect to WEAKEST from fresh boot")
print("-" * 40)
weakest = networks[-1]
print(f"Target: AP #{len(networks)} - {weakest['bssid_str']} (RSSI: {weakest['rssi']})")

try:
    wifi.radio.connect(
        SSID, PASSWORD, channel=weakest["channel"], bssid=weakest["bssid"]
    )
    time.sleep(3)
    info = get_connection_info()
    if info["connected"]:
        print(f"Connected to: {info['bssid']} (RSSI: {info['rssi']})")
        if info["bssid"] == weakest["bssid_str"]:
            print("✓ SUCCESS: Can connect to weakest signal!")
        else:
            print("✗ FAILED: Connected to different AP")
except Exception as e:
    print(f"Connect error: {e}")

# Step 3: Try to switch to strongest while connected
print("\n3. TEST: Switch to STRONGEST while connected")
print("-" * 40)
strongest = networks[0]
print(f"Target: AP #1 - {strongest['bssid_str']} (RSSI: {strongest['rssi']})")

# Try multiple connection attempts
for attempt in range(3):
    print(f"\nAttempt {attempt + 1}:")
    try:
        wifi.radio.connect(
            SSID, PASSWORD, channel=strongest["channel"], bssid=strongest["bssid"]
        )
        time.sleep(2)
        info = get_connection_info()
        if info["connected"]:
            print(f"  Connected to: {info['bssid']} (RSSI: {info['rssi']})")
            if info["bssid"] == strongest["bssid_str"]:
                print("  ✓ SUCCESS: Switched to strongest!")
                break
            else:
                print("  ✗ Still on same AP")
    except Exception as e:
        print(f"  Error: {e}")

# Step 4: Try connect with longer delay
print("\n4. TEST: Connect with 5 second delay")
print("-" * 40)
middle = networks[1] if len(networks) > 2 else networks[0]
print(f"Target: {middle['bssid_str']} (RSSI: {middle['rssi']})")
print("Waiting 5 seconds before connect...")
time.sleep(5)

try:
    wifi.radio.connect(SSID, PASSWORD, channel=middle["channel"], bssid=middle["bssid"])
    time.sleep(3)
    info = get_connection_info()
    if info["connected"]:
        print(f"Connected to: {info['bssid']} (RSSI: {info['rssi']})")
        if info["bssid"] == middle["bssid_str"]:
            print("✓ SUCCESS: Delay helped switch!")
        else:
            print("✗ Delay didn't help")
except Exception as e:
    print(f"Error: {e}")

# Step 5: Try rescan then connect
print("\n5. TEST: Rescan then connect to different AP")
print("-" * 40)
print("Performing new scan while connected...")

# Do a fresh scan
scan_results = []
for network in wifi.radio.start_scanning_networks():
    if network.ssid == SSID:
        bssid_str = ":".join(["%02X" % b for b in network.bssid])
        scan_results.append(
            {
                "rssi": network.rssi,
                "bssid": network.bssid,
                "bssid_str": bssid_str,
                "channel": network.channel,
            }
        )
wifi.radio.stop_scanning_networks()

print(f"Scan found {len(scan_results)} APs")

# Try to connect to a different one
current = get_connection_info()
if current["connected"]:
    print(f"Currently connected to: {current['bssid']}")

    # Find a different AP to target
    target = None
    for ap in scan_results:
        if ap["bssid_str"] != current["bssid"]:
            target = ap
            break

    if target:
        print(
            f"Attempting to switch to: {target['bssid_str']} (RSSI: {target['rssi']})"
        )
        try:
            wifi.radio.connect(
                SSID, PASSWORD, channel=target["channel"], bssid=target["bssid"]
            )
            time.sleep(3)
            new_info = get_connection_info()
            if new_info["connected"]:
                print(
                    f"Now connected to: {new_info['bssid']} (RSSI: {new_info['rssi']})"
                )
                if new_info["bssid"] == target["bssid_str"]:
                    print("✓ SUCCESS: Rescan enabled switching!")
                else:
                    print("✗ Rescan didn't help - still on same AP")
        except Exception as e:
            print(f"Error: {e}")

# Step 6: Test reset behavior
print("\n5. TEST: Reset and check connection")
print("-" * 40)
print("Will reset in 3 seconds...")
print("After reset, the device should connect to strongest signal")
print("Check serial output after reset to verify!")
time.sleep(3)

# Do the reset
print("Resetting NOW...")
microcontroller.reset()
