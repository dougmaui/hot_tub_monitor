# display_test.py - Minimal hardware verification for ST7796S
import board
import busio
import displayio
import fourwire
import busdisplay
import time
import gc
import digitalio

# Release any existing displays
displayio.release_displays()

# ST7796S initialization sequence - with command unlock!
_INIT_SEQUENCE = (
    b"\x01\x80\x96"  # Software reset and delay 150ms
    b"\x11\x80\x96"  # Sleep out and delay 150ms
    
    # CRITICAL: Unlock extended commands
    b"\xF0\x01\xC3"  # Enable extension command 2 part I
    b"\xF0\x01\x96"  # Enable extension command 2 part II
    
    # Memory Access Control - 0x48 for RGB
    b"\x36\x01\x48"  # MY=0, MX=1, MV=0, ML=0, BGR=0, MH=0
    
    # Interface Pixel Format
    b"\x3A\x01\x55"  # 16-bit/pixel (RGB565)
    
    # Display on
    b"\x29\x80\x14"  # Display on and delay 20ms
)

# Set up backlight
bl = digitalio.DigitalInOut(board.D10)
bl.direction = digitalio.Direction.OUTPUT
bl.value = True  # Turn on backlight

# Create SPI bus
spi = busio.SPI(board.SCK, board.MOSI)

# Create display bus using raw pins
display_bus = fourwire.FourWire(spi, command=board.D6, chip_select=board.D5, reset=board.D11)

# Initialize display
display = busdisplay.BusDisplay(display_bus, _INIT_SEQUENCE, width=320, height=480)

# Create a simple color bitmap
bitmap = displayio.Bitmap(320, 480, 4)
palette = displayio.Palette(4)
# Test with standard colors
palette[0] = 0x000000  # Black
palette[1] = 0xFF0000  # Red (24-bit)
palette[2] = 0x00FF00  # Green (24-bit)  
palette[3] = 0x0000FF  # Blue (24-bit)

# Fill horizontal bands with different colors
for y in range(120):
    for x in range(320):
        bitmap[x, y] = 0  # Black
for y in range(120, 240):
    for x in range(320):
        bitmap[x, y] = 1  # Red
for y in range(240, 360):
    for x in range(320):
        bitmap[x, y] = 2  # Green
for y in range(360, 480):
    for x in range(320):
        bitmap[x, y] = 3  # Blue

# Create a TileGrid and Group
tile_grid = displayio.TileGrid(bitmap, pixel_shader=palette)
group = displayio.Group()
group.append(tile_grid)

# Show on display
display.root_group = group

print("Display should show 4 vertical bands: Black, Red, Green, Blue")
print("Tell me what colors you see from left to right")
print(f"Free memory: {gc.mem_free()} bytes")

# Keep running
while True:
    time.sleep(1)