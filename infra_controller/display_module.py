# display_module.py - Display Module for Hot Tub Monitor
# Target Board: ESP32-S3 8MB (Infrastructure/WiFi Board)
# Rev: 1.2 - Working version before timing line
# Date: 2024-01-25
"""
Display module for Waveshare 3.5" IPS LCD (ST7796S)
Shows real-time status from WiFi, NTP, MQTT, and Sensor modules
Non-blocking operation with 1-second update interval
"""

import board
import busio
import displayio
import fourwire
import busdisplay
import terminalio
import time
import gc
import digitalio
from adafruit_display_text import label
from config import DisplayConfig

# Release any existing displays
displayio.release_displays()


class DisplayModule:
    """Manages the IPS display with hot tub monitor layout"""

    # ST7796S initialization sequence for IPS display
    _INIT_SEQUENCE = (
        b"\x01\x80\x96"  # Software reset
        b"\x11\x80\x96"  # Sleep out
        b"\xF0\x01\xC3"  # Enable extension command 2 partI
        b"\xF0\x01\x96"  # Enable extension command 2 partII
        b"\x36\x01\x48"  # Memory Access Control
        b"\x3A\x01\x55"  # Interface Pixel Format - 16 bit
        b"\xB4\x01\x01"  # Column inversion
        b"\xB6\x03\x80\x02\x3B"  # Display Function Control
        b"\x21\x00"      # Display Inversion ON (IPS)
        b"\xF0\x01\x69"  # Disable extension command 2 partI
        b"\xF0\x01\x3C"  # Disable extension command 2 partII
        b"\x29\x80\x14"  # Display ON
    )

    def __init__(self):
        """Initialize display module"""
        self.enabled = False
        self.display = None
        self.main_group = None
        self.last_update = 0
        self.update_count = 0

        # Text labels (will be created during init)
        self.ph_label = None
        self.temp_label = None
        self.wifi_label = None
        self.mqtt_label = None
        self.mem_label = None
        self.date_label = None

        # Try to initialize display
        if DisplayConfig.ENABLE_DISPLAY:
            try:
                self._initialize_display()
                self.enabled = True
            except Exception as e:
                print(f"Display: Failed to initialize - {e}")
                self.enabled = False
        else:
            print("Display: Disabled by configuration")

    def _initialize_display(self):
        """Initialize the display hardware"""
        print("Display: Initializing...")

        # Set up backlight
        bl = digitalio.DigitalInOut(getattr(board, DisplayConfig.BL_PIN))
        bl.direction = digitalio.Direction.OUTPUT
        bl.value = True

        # Initialize SPI
        spi = busio.SPI(board.SCK, board.MOSI)
        display_bus = fourwire.FourWire(
            spi,
            command=getattr(board, DisplayConfig.DC_PIN),
            chip_select=getattr(board, DisplayConfig.CS_PIN),
            reset=getattr(board, DisplayConfig.RST_PIN)
        )

        # Create display
        self.display = busdisplay.BusDisplay(
            display_bus,
            self._INIT_SEQUENCE,
            width=DisplayConfig.WIDTH,
            height=DisplayConfig.HEIGHT
        )

        # Create main display group
        self.main_group = displayio.Group()

        # Deep blue background
        bg_bitmap = displayio.Bitmap(DisplayConfig.WIDTH, DisplayConfig.HEIGHT, 1)
        bg_palette = displayio.Palette(1)
        bg_palette[0] = DisplayConfig.BACKGROUND_COLOR
        bg = displayio.TileGrid(bg_bitmap, pixel_shader=bg_palette)
        self.main_group.append(bg)

        # Create text labels
        font = terminalio.FONT

        # pH display (larger) - at top since no time label
        self.ph_label = label.Label(font, text="pH:  --.---", color=DisplayConfig.TEXT_COLOR, scale=3)
        self.ph_label.x = 80
        self.ph_label.y = 80

        # Temperature display
        self.temp_label = label.Label(font, text="--.--- C  --.--- F", color=DisplayConfig.TEXT_COLOR, scale=2)
        self.temp_label.x = 60
        self.temp_label.y = 140

        # System info
        self.wifi_label = label.Label(font, text="WiFi: --- dBm", color=DisplayConfig.TEXT_COLOR, scale=2)
        self.wifi_label.x = 50
        self.wifi_label.y = 245

        self.mqtt_label = label.Label(font, text="MQTT: ---", color=DisplayConfig.TEXT_COLOR, scale=2)
        self.mqtt_label.x = 50
        self.mqtt_label.y = 280

        self.mem_label = label.Label(font, text="Mem: --- KB  Up: --- h", color=DisplayConfig.TEXT_COLOR, scale=2)
        self.mem_label.x = 50
        self.mem_label.y = 315

        # Date at bottom
        self.date_label = label.Label(font, text="----/--/-- --:--:--", color=DisplayConfig.TEXT_COLOR, scale=2)
        self.date_label.x = 10
        self.date_label.y = 460

        # Add horizontal line
        self._add_dashed_line()

        # Add all labels
        self.main_group.append(self.ph_label)
        self.main_group.append(self.temp_label)
        self.main_group.append(self.wifi_label)
        self.main_group.append(self.mqtt_label)
        self.main_group.append(self.mem_label)
        self.main_group.append(self.date_label)

        # Show on display
        self.display.root_group = self.main_group

        print(f"Display: Module initialized. Free memory: {gc.mem_free()} bytes")

    def _add_dashed_line(self):
        """Add a dashed line separator"""
        line_group = displayio.Group()
        dash_length = 10
        gap_length = 5
        y_position = 180

        for x in range(10, 310, dash_length + gap_length):
            dash_bitmap = displayio.Bitmap(dash_length, 1, 1)
            dash_palette = displayio.Palette(1)
            dash_palette[0] = DisplayConfig.TEXT_COLOR
            dash = displayio.TileGrid(dash_bitmap, pixel_shader=dash_palette, x=x, y=y_position)
            line_group.append(dash)

        self.main_group.append(line_group)

    def tick(self, wifi_mgr, ntp_sync, mqtt_pub, sensor=None):
        """Update display with current status - includes sensor parameter"""
        if not self.enabled:
            return

        # Throttle updates to once per second
        now = time.monotonic()
        if now - self.last_update < DisplayConfig.UPDATE_INTERVAL:
            return

        try:
            # Update temperature from sensor if available
            if sensor and sensor.is_sensor_online():
                temp_c, temp_f = sensor.get_temperature()
                if temp_c is not None:
                    self.temp_label.text = f"{temp_c:.3f} C {temp_f:.3f} F"
                else:
                    self.temp_label.text = "--.--- C --.--- F"

                # Update pH from sensor (CHANGED)
                ph = sensor.get_ph()
                if ph is not None:
                    self.ph_label.text = f"pH: {ph:.3f}"
                else:
                    self.ph_label.text = "pH: -.---"
            else:
                # Fallback to test data if no sensor
                self.temp_label.text = "No Sensor Data"
                self.ph_label.text = "pH: No Data"

            # Update WiFi status
            wifi_status = wifi_mgr.get_status()
            if wifi_status['connected']:
                rssi = wifi_status['rssi']
                ch = wifi_status['channel']
                bssid_short = wifi_mgr.current_bssid[-2:] if wifi_mgr.current_bssid else "--"
                self.wifi_label.text = f"WiFi: {rssi}dBm Ch:{ch} {bssid_short}"
            else:
                self.wifi_label.text = f"WiFi: {wifi_status['state']}"

            # Update MQTT status
            if mqtt_pub:
                mqtt_status = mqtt_pub.get_status()
                if mqtt_status['connected']:
                    q = mqtt_status['queue_size']
                    rate = mqtt_status['rate']
                    self.mqtt_label.text = f"MQTT: OK Q:{q} {rate}/min"
                else:
                    self.mqtt_label.text = f"MQTT: {mqtt_status['state']}"
            else:
                self.mqtt_label.text = "MQTT: Disabled"

            # Update memory and uptime (original working version)
            free_kb = gc.mem_free() // 1024
            uptime_seconds = wifi_status.get('uptime', 0)
            if uptime_seconds:
                hours = uptime_seconds // 3600
                minutes = (uptime_seconds % 3600) // 60
                uptime_str = f"{hours}.{minutes:02d}h"
            else:
                uptime_str = "0.00h"
            self.mem_label.text = f"Mem: {free_kb}KB  Up: {uptime_str}"

            # Update date/time at bottom
            self.date_label.text = f"2024-01-15 {wifi_mgr.get_timestamp()} CEST"

            self.update_count += 1
            self.last_update = now

        except Exception as e:
            print(f"Display: Update error - {e}")

    def get_status(self):
        """Get display module status"""
        return {
            "enabled": self.enabled,
            "updates": self.update_count,
            "last_update": int(time.monotonic() - self.last_update) if self.last_update > 0 else None
        }


# Test code
def main():
    """Test display module standalone"""
    print("Testing Display Module...")
    display = DisplayModule()

    if not display.enabled:
        print("Display not enabled!")
        return

    print("Display initialized. Running for 30 seconds...")

    # Create mock objects for testing
    class MockWiFi:
        def get_timestamp(self):
            return "12:34:56"
        def get_status(self):
            return {"connected": True, "rssi": -67, "channel": 6, "state": "CONNECTED", "uptime": 3600}
        current_bssid = "AA:BB:CC:DD:EE:FF"

    class MockNTP:
        def get_status(self):
            return {"quality": "ntp"}

    class MockMQTT:
        def get_status(self):
            return {"connected": True, "queue_size": 0, "rate": 5, "state": "CONNECTED"}

    class MockSensor:
        def is_sensor_online(self):
            return True
        def get_temperature(self):
            return 25.5, 77.9

    wifi = MockWiFi()
    ntp = MockNTP()
    mqtt = MockMQTT()
    sensor = MockSensor()

    start = time.monotonic()
    while time.monotonic() - start < 30:
        display.tick(wifi, ntp, mqtt, sensor)
        time.sleep(0.1)

    print(f"Test complete. Updates: {display.get_status()['updates']}")


if __name__ == "__main__":
    main()