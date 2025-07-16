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
    MEMORY_WARNING = 50000  # Memory warning threshold (bytes)

    # Watchdog settings
    CONNECTION_WATCHDOG_TIMEOUT = 3600  # 1 hour default
    RETRY_BACKOFF_MAX = 300  # Max 5 minutes between retries

    # Connection quality thresholds
    LOW_RSSI_DISCONNECT_TIME = 10  # Seconds of low RSSI before disconnect
    LOW_RSSI_WARNING_TIME = 8  # Seconds before disconnect to warn MQTT


class NTPConfig:
    """NTP Sync configuration constants"""

    # NTP Server
    NTP_SERVER = "pool.ntp.org"  # Default NTP server
    NTP_PORT = 123  # Standard NTP port

    # Timing constants (seconds)
    SYNC_INTERVAL = 3600  # How often to sync when stable (1 hour)
    SYNC_TIMEOUT = 5.0  # Maximum time for sync attempt
    INITIAL_RETRY_DELAY = 30  # First retry after failure (30 seconds)
    MAX_RETRY_DELAY = 300  # Maximum retry delay (5 minutes)

    # NTP Protocol
    NTP_EPOCH_OFFSET = 2208988800  # Seconds between 1900 and 1970
    NTP_PACKET_SIZE = 48  # Standard NTP packet size
