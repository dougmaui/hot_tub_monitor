# display_module.py - Display Module for ESP32-S3 Hot Tub Monitor
"""
Display Module for Waveshare 3.5" IPS LCD (ST7796S)
Follows established module patterns - tick-based, non-blocking
"""

import time
import board
import busio
import displayio
import fourwire
import busdisplay
import terminalio
import gc
import digitalio
from adafruit_display_text import label
from config import DisplayConfig


class DisplayModule:
    """Manages the IPS LCD display with system status"""

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
        if not DisplayConfig.ENABLE_DISPLAY:
            print("Display: Disabled by configuration")
            self.enabled = False
            return

        self.enabled = True
        self._last_update = 0
        self._update_count = 0

        # Track previous values to minimize updates
        self._prev_ph = None
        self._prev_temp_c = None
        self._prev_temp_f = None
        self._prev_rssi = None
        self._prev_channel = None
        self._prev_bssid = None
        self._prev_mqtt_state = None
        self._prev_queue = None
        self._prev_rate = None
        self._prev_memory = None
        self._prev_uptime = None
        self._prev_timestamp = None

        # Initialize display
        try:
            self._init_display()
            self._create_layout()
            print(f"Display: Module initialized. Free memory: {gc.mem_free()} bytes")
        except Exception as e:
            print(f"Display: FATAL init error: {e}")
            print("Display: Triggering reset...")
            import microcontroller
            microcontroller.reset()

    def _init_display(self):
        """Initialize the hardware"""
        # Release any existing displays
        displayio.release_displays()

        # Set up backlight using string pin name from config
        bl_pin = getattr(board, DisplayConfig.BL_PIN)
        self.backlight = digitalio.DigitalInOut(bl_pin)
        self.backlight.direction = digitalio.Direction.OUTPUT
        self.backlight.value = True

        # Set up SPI
        self.spi = busio.SPI(board.SCK, board.MOSI)

        # Get pins from config strings
        cs_pin = getattr(board, DisplayConfig.CS_PIN)
        dc_pin = getattr(board, DisplayConfig.DC_PIN)
        rst_pin = getattr(board, DisplayConfig.RST_PIN)

        # Create display bus
        self.display_bus = fourwire.FourWire(
            self.spi,
            command=dc_pin,
            chip_select=cs_pin,
            reset=rst_pin
        )

        # Create display
        self.display = busdisplay.BusDisplay(
            self.display_bus,
            self._INIT_SEQUENCE,
            width=DisplayConfig.WIDTH,
            height=DisplayConfig.HEIGHT
        )

    def _create_layout(self):
        """Create the display layout with all text elements"""
        # Create main display group
        self.main_group = displayio.Group()

        # Deep blue background
        bg_bitmap = displayio.Bitmap(DisplayConfig.WIDTH, DisplayConfig.HEIGHT, 1)
        bg_palette = displayio.Palette(1)
        bg_palette[0] = DisplayConfig.BACKGROUND_COLOR
        bg = displayio.TileGrid(bg_bitmap, pixel_shader=bg_palette)
        self.main_group.append(bg)

        # Font
        font = terminalio.FONT

        # Create all text labels
        # pH display (larger) - centered
        self.ph_label = label.Label(font, text="pH: --.-", color=DisplayConfig.TEXT_COLOR, scale=3)
        self.ph_label.x = 80
        self.ph_label.y = 80

        # Temperature display - centered
        self.temp_label = label.Label(font, text="--.- C  --.- F", color=DisplayConfig.TEXT_COLOR, scale=2)
        self.temp_label.x = 60
        self.temp_label.y = 140

        # Create dashed line
        self._create_dashed_line()

        # System info
        self.wifi_label = label.Label(font, text="WiFi: --- Ch:-- --", color=DisplayConfig.TEXT_COLOR, scale=2)
        self.wifi_label.x = 50
        self.wifi_label.y = 245

        self.mqtt_label = label.Label(font, text="MQTT: --- Q:- -/min", color=DisplayConfig.TEXT_COLOR, scale=2)
        self.mqtt_label.x = 50
        self.mqtt_label.y = 280

        self.mem_label = label.Label(font, text="Mem: --KB Up: -.--h", color=DisplayConfig.TEXT_COLOR, scale=2)
        self.mem_label.x = 50
        self.mem_label.y = 315

        # Time/date at bottom
        self.time_label = label.Label(font, text="----/--/-- --:--:-- ---", color=DisplayConfig.TEXT_COLOR, scale=2)
        self.time_label.x = 10
        self.time_label.y = 460

        # Add all labels to group
        self.main_group.append(self.ph_label)
        self.main_group.append(self.temp_label)
        self.main_group.append(self.line_group)
        self.main_group.append(self.wifi_label)
        self.main_group.append(self.mqtt_label)
        self.main_group.append(self.mem_label)
        self.main_group.append(self.time_label)

        # Show on display
        self.display.root_group = self.main_group

    def _create_dashed_line(self):
        """Create a horizontal dashed line"""
        self.line_group = displayio.Group()
        dash_length = 10
        gap_length = 5
        y_position = 180

        for x in range(10, 310, dash_length + gap_length):
            dash_bitmap = displayio.Bitmap(dash_length, 1, 1)
            dash_palette = displayio.Palette(1)
            dash_palette[0] = DisplayConfig.TEXT_COLOR
            dash = displayio.TileGrid(dash_bitmap, pixel_shader=dash_palette, x=x, y=y_position)
            self.line_group.append(dash)

    def tick(self, wifi_mgr=None, ntp=None, mqtt=None):
        """Update display if needed - called from executive loop"""
        if not self.enabled:
            return

        # Check update interval
        now = time.monotonic()
        if now - self._last_update < DisplayConfig.UPDATE_INTERVAL:
            return

        # Don't update during critical operations
        if wifi_mgr and (wifi_mgr.measuring or wifi_mgr.will_be_unavailable()):
            return
        if mqtt and mqtt.publishing:
            return

        # Update the display
        try:
            self._update_display(wifi_mgr, ntp, mqtt)
            self._last_update = now
            self._update_count += 1
        except Exception as e:
            print(f"Display: Update error: {e}")
            # On any display error, trigger reset per requirements
            print("Display: Fatal error, resetting...")
            import microcontroller
            microcontroller.reset()

    def _update_display(self, wifi_mgr, ntp, mqtt):
        """Update display elements that have changed"""
        # Get sensor values (mock for now)
        # TODO: Replace with real sensor readings
        ph = 7.234
        temp_c = 24.567
        temp_f = 102.345

        # Update pH if changed
        if ph != self._prev_ph:
            self.ph_label.text = f"pH: {ph:.3f}"
            self._prev_ph = ph

        # Update temperature if changed
        if temp_c != self._prev_temp_c or temp_f != self._prev_temp_f:
            self.temp_label.text = f"{temp_c:.3f} C  {temp_f:.3f} F"
            self._prev_temp_c = temp_c
            self._prev_temp_f = temp_f

        # Update WiFi info if available
        if wifi_mgr:
            status = wifi_mgr.get_status()
            rssi = status['rssi']
            channel = status['channel']
            bssid_suffix = wifi_mgr.current_bssid[-2:] if wifi_mgr.current_bssid else "--"

            if rssi != self._prev_rssi or channel != self._prev_channel or bssid_suffix != self._prev_bssid:
                if rssi == 0:
                    self.wifi_label.text = "WiFi: Disconnected"
                else:
                    self.wifi_label.text = f"WiFi: {rssi}dBm Ch:{channel} {bssid_suffix}"
                self._prev_rssi = rssi
                self._prev_channel = channel
                self._prev_bssid = bssid_suffix

        # Update MQTT info if available
        if mqtt:
            mqtt_status = mqtt.get_status()
            state = "OK" if mqtt_status['connected'] else "OFF"
            queue = mqtt_status['queue_size']
            rate = mqtt_status['rate']

            if state != self._prev_mqtt_state or queue != self._prev_queue or rate != self._prev_rate:
                self.mqtt_label.text = f"MQTT: {state} Q:{queue} {rate}/min"
                self._prev_mqtt_state = state
                self._prev_queue = queue
                self._prev_rate = rate
        else:
            if self._prev_mqtt_state != "N/A":
                self.mqtt_label.text = "MQTT: Disabled"
                self._prev_mqtt_state = "N/A"

        # Update memory and uptime
        free_mem = gc.mem_free() // 1024  # Convert to KB
        uptime_seconds = int(time.monotonic())
        uptime_hours = uptime_seconds / 3600

        if free_mem != self._prev_memory or uptime_hours != self._prev_uptime:
            self.mem_label.text = f"Mem: {free_mem}KB Up: {uptime_hours:.2f}h"
            self._prev_memory = free_mem
            self._prev_uptime = uptime_hours

        # Update time display
        if wifi_mgr:
            timestamp = wifi_mgr.get_timestamp()
            # Check if we have a full date/time from NTP
            if ntp and ntp.is_synced():
                # Get timezone from config
                from config import is_dst, get_local_offset
                real_timestamp = ntp.get_real_timestamp_us() / 1000000
                tz_name = "CEST" if is_dst(real_timestamp) else "CET"

                # For now, just show time with timezone
                # TODO: Add full date formatting when needed
                time_str = f"{timestamp} {tz_name}"
            else:
                time_str = f"{timestamp} (manual)"

            if time_str != self._prev_timestamp:
                self.time_label.text = time_str
                self._prev_timestamp = time_str

    def get_status(self):
        """Get display module status"""
        return {
            "enabled": self.enabled,
            "updates": self._update_count,
            "memory_used": gc.mem_alloc() - gc.mem_free() if self.enabled else 0
        }


# Test code
def main():
    """Test display module standalone"""
    print("Testing Display Module...")
    print(f"Free memory at start: {gc.mem_free()} bytes")

    display = DisplayModule()

    if not display.enabled:
        print("Display disabled in config")
        return

    print(f"Free memory after init: {gc.mem_free()} bytes")

    # Simulate updates
    last_status = time.monotonic()

    while True:
        # Update display
        display.tick()

        # Status every 5 seconds
        if time.monotonic() - last_status > 5:
            status = display.get_status()
            print(f"Display status: {status}")
            last_status = time.monotonic()

        time.sleep(0.05)  # 50ms loop


if __name__ == "__main__":
    main()