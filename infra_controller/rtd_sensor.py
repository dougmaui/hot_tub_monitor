# rtd_sensor.py - RTD Temperature Sensor Module
"""
RTD Sensor Module for ESP32-S3 CircuitPython
Uses MAX31865 amplifier with PT100 probe
Implements prime number sampling to avoid power line interference
"""

import time
import gc
import adafruit_max31865


class RTDSensor:
    """Manages RTD temperature sensor with prime interval sampling"""
    
    # State constants
    INIT = "INIT"
    IDLE = "IDLE"
    READING = "READING"
    ERROR = "ERROR"
    
    # Sensor modes
    MONITOR_MODE = "MONITOR"      # ~1Hz sampling
    MEASUREMENT_MODE = "MEASURE"  # ~10Hz for acid injection
    
    # Prime intervals in milliseconds
    # These average to ~1 second but avoid 50/60Hz harmonics
    PRIME_INTERVALS_MS = [907, 1009, 1103, 997, 1013, 953, 1019, 983, 1021, 967]
    
    # Fast prime intervals for measurement mode (~100ms average)
    FAST_PRIME_INTERVALS_MS = [97, 103, 89, 107, 83, 113, 79, 109, 101, 87]
    
    def __init__(self, spi, cs_pin, rtd_nominal=100.0, ref_resistor=430.0, wires=3):
        """Initialize RTD Sensor
        
        Args:
            spi: SPI bus instance
            cs_pin: Chip select pin
            rtd_nominal: RTD resistance at 0°C (default 100.0 for PT100)
            ref_resistor: Reference resistor value (default 430.0)
            wires: Number of RTD wires (2, 3, or 4)
        """
        # Hardware configuration
        self.spi = spi
        self.cs_pin = cs_pin
        self.rtd_nominal = rtd_nominal
        self.ref_resistor = ref_resistor
        self.wires = wires
        
        # State management
        self.state = self.INIT
        self.mode = self.MONITOR_MODE
        self._init_time = time.monotonic()
        
        # Sampling control
        self.interval_index = 0
        self.next_sample_time = 0
        self._last_read_time = 0
        
        # Temperature data
        self.current_temp_c = None
        self.current_temp_f = None
        self.current_resistance = None
        self.last_temp_c = None
        
        # Statistics
        self.read_count = 0
        self.error_count = 0
        self.successful_reads = 0
        self.total_reads = 0
        
        # MAX31865 instance
        self.rtd = None
        
        # Error tracking
        self.last_error = None
        self.consecutive_errors = 0
        self.max_consecutive_errors = 5
        
        # Module initialized silently
        
    def tick(self):
        """Main update cycle - non-blocking"""
        now = time.monotonic()
        
        if self.state == self.INIT:
            self._initialize_sensor()
            
        elif self.state == self.IDLE:
            # Check if it's time for next reading
            if now >= self.next_sample_time:
                self.state = self.READING
                self._last_read_time = now
                
        elif self.state == self.READING:
            self._read_temperature()
            
        elif self.state == self.ERROR:
            # Attempt recovery after delay
            if now - self._last_read_time > 5.0:  # 5 second recovery delay
                self.state = self.INIT
                self.consecutive_errors = 0
                
    def _initialize_sensor(self):
        """Initialize MAX31865 sensor"""
        try:
            import digitalio
            
            # Create CS pin if needed
            if not hasattr(self.cs_pin, 'direction'):
                cs = digitalio.DigitalInOut(self.cs_pin)
            else:
                cs = self.cs_pin
                
            # Initialize MAX31865
            self.rtd = adafruit_max31865.MAX31865(
                self.spi, 
                cs, 
                wires=self.wires,
                rtd_nominal=self.rtd_nominal,
                ref_resistor=self.ref_resistor
            )
            
            # Clear any existing faults
            self.rtd.clear_faults()
            
            # Test read
            test_temp = self.rtd.temperature
            if -50 < test_temp < 150:  # Sanity check
                self.state = self.IDLE
                self.next_sample_time = time.monotonic() + 0.1  # First reading soon
            else:
                raise ValueError(f"Temperature out of range: {test_temp}")
                
        except Exception as e:
            self.last_error = str(e)
            self.error_count += 1
            self.state = self.ERROR
            
    def _read_temperature(self):
        """Read temperature from sensor"""
        try:
            if not self.rtd:
                self.state = self.INIT
                return
                
            # Read sensor
            temp_c = self.rtd.temperature
            resistance = self.rtd.resistance
            
            # Validate reading
            if -50 < temp_c < 150:
                # Store previous value
                self.last_temp_c = self.current_temp_c
                
                # Update current values
                self.current_temp_c = temp_c
                self.current_temp_f = temp_c * 9/5 + 32
                self.current_resistance = resistance
                
                # Update statistics
                self.successful_reads += 1
                self.total_reads += 1
                self.consecutive_errors = 0
                    
            else:
                raise ValueError(f"Temperature out of range: {temp_c}")
                
            # Schedule next reading using prime interval
            self._schedule_next_reading()
            self.state = self.IDLE
            
        except Exception as e:
            self.error_count += 1
            self.consecutive_errors += 1
            self.last_error = str(e)
            
            if self.consecutive_errors >= self.max_consecutive_errors:
                self.state = self.ERROR
            else:
                # Try again with next interval
                self._schedule_next_reading()
                self.state = self.IDLE
                
    def _schedule_next_reading(self):
        """Schedule next reading using prime interval"""
        # Select interval based on mode
        if self.mode == self.MEASUREMENT_MODE:
            intervals = self.FAST_PRIME_INTERVALS_MS
        else:
            intervals = self.PRIME_INTERVALS_MS
            
        # Get next interval and advance index
        interval_ms = intervals[self.interval_index]
        self.interval_index = (self.interval_index + 1) % len(intervals)
        
        # Schedule next reading
        self.next_sample_time = time.monotonic() + (interval_ms / 1000.0)
        
    def _log_reading(self):
        """Format reading for external logging if needed"""
        if self.current_temp_c is not None:
            delta = ""
            if self.last_temp_c is not None:
                delta = f" Δ{self.current_temp_c - self.last_temp_c:+.3f}°C"
                
            # Return formatted string that caller can use
            return f"{self.current_temp_c:.3f}°C / {self.current_temp_f:.2f}°F ({self.current_resistance:.2f}Ω){delta}"
        return None
            
    def set_mode(self, mode):
        """Change sampling mode"""
        if mode in [self.MONITOR_MODE, self.MEASUREMENT_MODE]:
            old_mode = self.mode
            self.mode = mode
            if old_mode != mode:
                # Reset interval index for consistent behavior
                self.interval_index = 0
                return True
        return False
            
    def get_temperature(self):
        """Get current temperature reading
        
        Returns:
            tuple: (temp_c, temp_f) or (None, None) if no reading
        """
        return (self.current_temp_c, self.current_temp_f)
        
    def get_status(self):
        """Get comprehensive sensor status"""
        uptime = int(time.monotonic() - self._init_time)
        
        success_rate = 0
        if self.total_reads > 0:
            success_rate = (self.successful_reads / self.total_reads) * 100
            
        # Determine health
        if self.state == self.ERROR:
            health = "error"
        elif self.consecutive_errors > 2:
            health = "degraded"
        elif success_rate > 95:
            health = "healthy"
        else:
            health = "warning"
            
        return {
            "state": self.state,
            "mode": self.mode,
            "temp_c": self.current_temp_c,
            "temp_f": self.current_temp_f,
            "resistance": self.current_resistance,
            "health": health,
            "uptime": uptime,
            "total_reads": self.total_reads,
            "successful_reads": self.successful_reads,
            "error_count": self.error_count,
            "success_rate": round(success_rate, 1),
            "last_error": self.last_error,
            "interval_index": self.interval_index
        }
        
    def is_ready(self):
        """Check if sensor is ready with valid data"""
        return (self.state in [self.IDLE, self.READING] and 
                self.current_temp_c is not None)