# config.py - Configuration constants for WiFi Manager and NTP Sync
"""
Configuration file for Network Services Modules
Centralizes all tunable parameters
"""


class WiFiConfig:
    """WiFi Manager configuration constants"""

    # Signal strength thresholds (dBm)
    RSSI_THRESHOLD = -75  # Minimum acceptable signal
    RSSI_GOOD = -70  # Good signal threshold

    # Timing constants (seconds)
    SCAN_TIMEOUT = 5.0  # Maximum scan duration
    CONNECT_TIMEOUT = 10.0  # Connection attempt timeout
    TICK_INTERVAL = 0.05  # Main loop interval

    # Memory management
    MEMORY_WARNING = 10000 # Memory warning threshold (bytes)

    # Watchdog settings
    CONNECTION_WATCHDOG_TIMEOUT = 3600  # 1 hour default
    RETRY_BACKOFF_MAX = 300  # Max 5 minutes between retries

    # Connection quality thresholds
    LOW_RSSI_DISCONNECT_TIME = 10  # Seconds of low RSSI before disconnect
    LOW_RSSI_WARNING_TIME = 8  # Seconds before disconnect to warn MQTT

    # Better AP switching parameters
    BETTER_AP_MARGIN = 10  # dB improvement needed to consider switching
    BETTER_AP_CHECK_INTERVAL = 45  # Check for better APs every minute
    BETTER_AP_STABLE_TIME = 30  # Seconds better AP must remain stable before switching


class NTPConfig:
    """NTP Sync configuration constants"""

    # NTP Server
    NTP_SERVER = "pool.ntp.org"  # Default NTP server
    NTP_PORT = 123  # Standard NTP port
    TIMEZONE_OFFSET = 1  # PST is UTC-8
    USE_DST = True  # Enable Daylight Saving Time calculation
    DST_OFFSET = 1  # DST adds 1 hour

    # Timing constants (seconds)
    SYNC_INTERVAL = 3600  # How often to sync when stable (1 hour)
    SYNC_TIMEOUT = 5.0  # Maximum time for sync attempt
    INITIAL_RETRY_DELAY = 30  # First retry after failure (30 seconds)
    MAX_RETRY_DELAY = 300  # Maximum retry delay (5 minutes)

    # NTP Protocol
    NTP_EPOCH_OFFSET = 2208988800  # Seconds between 1900 and 1970
    NTP_PACKET_SIZE = 48  # Standard NTP packet size

class MQTTConfig:
    """MQTT Publisher configuration"""
    # Connection
    BROKER = "io.adafruit.com"
    PORT = 1883  # Non-SSL for production (change to 8883 for SSL)

    # Publishing rates
    PUBLISH_RATE_DEV = 20   # Development: 20/minute
    PUBLISH_RATE_PROD = 5   # Production: 5/minute

    # Bucket size - for burst capacity
    MIN_BUCKET_SIZE = 20    # Minimum tokens for emergencies

    # Queue settings
    MAX_QUEUE_SIZE = 20

    # Publishing intervals
    HEALTH_PUBLISH_INTERVAL = 60  # Publish every 60 seconds

    # Memory thresholds
    MIN_MEMORY_PUBLISH = 15000   # Don't publish below this
    MIN_MEMORY_WARNING = 15000   # Warning threshold
    MIN_MEMORY_CRITICAL = 10000  # Critical threshold

    # Set to False to disable MQTT
    ENABLED = True


class DisplayConfig:
    # SPI pins (using ESP32-S3 defaults - as strings)
    # These will be converted to actual pins in the display module
    
    # Display control pins (your connections)
    CS_PIN = "D5"     # LCD_CS - Chip Select
    DC_PIN = "D6"     # LCD_DC - Data/Command
    RST_PIN = "D11"    # LCD_RST - Reset
    BL_PIN = "D10"    # LCD_BL - Backlight control
    
    # Display settings
    WIDTH = 320
    HEIGHT = 480
    ROTATION = 0  # Adjust if display is oriented wrong
    BACKGROUND_COLOR = 0x000080  # Deep blue
    TEXT_COLOR = 0xFFFFFF  # White
    
    # Update settings
    UPDATE_INTERVAL = 1.0  # Minimum seconds between updates
    MEMORY_LIMIT = 15000  # Maximum bytes for display
    
    # Failure management
    SPI_TIMEOUT = 1.0  # Seconds before declaring SPI hung
    ENABLE_DISPLAY = True  # Can be set False for headless operation


def is_dst(timestamp):
    """Simple DST check for US - DST is approximately April through October"""
    if not NTPConfig.USE_DST:
        return False

    try:
        days_since_epoch = int(timestamp // 86400)
        month = ((days_since_epoch % 365) // 30) + 1
        return 4 <= month <= 10
    except:
        return False


def get_local_offset(timestamp):
    """Get the local time offset from UTC in seconds"""
    base_offset = NTPConfig.TIMEZONE_OFFSET * 3600
    if is_dst(timestamp):
        return base_offset + (NTPConfig.DST_OFFSET * 3600)
    return base_offset
