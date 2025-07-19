# display_text_test.py - Test text display for hot tub monitor
import board
import busio
import displayio
import fourwire
import busdisplay
import terminalio
import time
import gc
import digitalio

# Release any existing displays
displayio.release_displays()

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

# Initialize hardware
print("Initializing display...")

# Backlight on
bl = digitalio.DigitalInOut(board.D10)
bl.direction = digitalio.Direction.OUTPUT
bl.value = True

# SPI setup
spi = busio.SPI(board.SCK, board.MOSI)
display_bus = fourwire.FourWire(spi, command=board.D6, chip_select=board.D5, reset=board.D11)

# Create display
display = busdisplay.BusDisplay(display_bus, _INIT_SEQUENCE, width=320, height=480)

print(f"Display initialized. Free memory: {gc.mem_free()} bytes")

# Create main display group
main_group = displayio.Group()

# Deep blue background
bg_bitmap = displayio.Bitmap(320, 480, 1)
bg_palette = displayio.Palette(1)
bg_palette[0] = 0x000080  # Deep blue
bg = displayio.TileGrid(bg_bitmap, pixel_shader=bg_palette)
main_group.append(bg)

# Import text support
from adafruit_display_text import label

# Create text labels
font = terminalio.FONT

# pH display (larger) - centered
ph_label = label.Label(font, text="pH:  7.234", color=0xFFFFFF, scale=3)
ph_label.x = 80  # More centered
ph_label.y = 80

# Temperature display - centered
temp_label = label.Label(font, text="24.567 C  102.345 F", color=0xFFFFFF, scale=2)
temp_label.x = 60  # More centered
temp_label.y = 140

# Add a horizontal dashed line between temp and wifi
line_group = displayio.Group()
dash_length = 10
gap_length = 5
y_position = 180  # Between temp and wifi
for x in range(10, 310, dash_length + gap_length):
    dash_bitmap = displayio.Bitmap(dash_length, 1, 1)
    dash_palette = displayio.Palette(1)
    dash_palette[0] = 0xFFFFFF  # White
    dash = displayio.TileGrid(dash_bitmap, pixel_shader=dash_palette, x=x, y=y_position)
    line_group.append(dash)

# System info - moved down by ~35 pixels (one line at scale=2)
wifi_label = label.Label(font, text="WiFi: -67dBm Ch:6 EF", color=0xFFFFFF, scale=2)
wifi_label.x = 50
wifi_label.y = 245  # Was 210

mqtt_label = label.Label(font, text="MQTT: OK Q:0  5/min", color=0xFFFFFF, scale=2)
mqtt_label.x = 50
mqtt_label.y = 280  # Was 245

mem_label = label.Label(font, text="Mem: 45KB  Up: 3.2h", color=0xFFFFFF, scale=2)
mem_label.x = 50
mem_label.y = 315  # Was 280

# Time/date at very bottom with scale=2 - now includes date
time_label = label.Label(font, text="2024-01-15 12:34:56 CEST", color=0xFFFFFF, scale=2)
time_label.x = 10  # Left margin
time_label.y = 460  # Near bottom (480 - 20 for some margin)

# Add all labels to group
main_group.append(ph_label)
main_group.append(temp_label)
main_group.append(line_group)  # Add the dashed line
main_group.append(wifi_label)
main_group.append(mqtt_label)
main_group.append(mem_label)
main_group.append(time_label)  # Time at bottom

# Show on display
display.root_group = main_group

print("Display showing hot tub monitor layout")
print(f"Free memory after setup: {gc.mem_free()} bytes")

# Keep running
while True:
    time.sleep(1)