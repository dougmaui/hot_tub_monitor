# config.py - Configuration constants for WiFi Manager
"""
Configuration file for WiFi Manager Module
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
