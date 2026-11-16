import utime
from machine import I2C, Pin

# Register addresses
TSL2561_Control = 0x80
TSL2561_Timing = 0x81
TSL2561_Interrupt = 0x86
TSL2561_Channel0L = 0x8C
TSL2561_Channel0H = 0x8D
TSL2561_Channel1L = 0x8E
TSL2561_Channel1H = 0x8F

TSL2561_Address = 0x29  # 7-bit device address

# Constants for lux calculation
LUX_SCALE = 14
RATIO_SCALE = 9
CH_SCALE = 10
CHSCALE_TINT0 = 0x7517
CHSCALE_TINT1 = 0x0fe7

# T Package coefficients
K1T = 0x0040; B1T = 0x01f2; M1T = 0x01be
K2T = 0x0080; B2T = 0x0214; M2T = 0x02d1
K3T = 0x00c0; B3T = 0x023f; M3T = 0x037b
K4T = 0x0100; B4T = 0x0270; M4T = 0x03fe
K5T = 0x0138; B5T = 0x016f; M5T = 0x01fc
K6T = 0x019a; B6T = 0x00d2; M6T = 0x00fb
K7T = 0x029a; B7T = 0x0018; M7T = 0x0012
K8T = 0x029a; B8T = 0x0000; M8T = 0x0000

# CS Package coefficients (not used here but kept for reference)
K1C = 0x0043; B1C = 0x0204; M1C = 0x01ad
K2C = 0x0085; B2C = 0x0228; M2C = 0x02c1
K3C = 0x00c8; B3C = 0x0253; M3C = 0x0363
K4C = 0x010a; B4C = 0x0282; M4C = 0x03df
K5C = 0x014d; B5C = 0x0177; M5C = 0x01dd
K6C = 0x019a; B6C = 0x0101; M6C = 0x0127
K7C = 0x029a; B7C = 0x0037; M7C = 0x002b
K8C = 0x029a; B8C = 0x0000; M8C = 0x0000

class TSL2561:
    def __init__(self, i2c_bus, sda_pin, scl_pin):
        self.i2c = I2C(i2c_bus, sda=Pin(sda_pin), scl=Pin(scl_pin))
        self.address = TSL2561_Address
        self.debug = False
        self.cooldown = 0.005  # seconds
        self.packageType = 0   # 0 = T package
        self.gain = 0          # 0=1x, 1=16x
        self.timing = 2        # 0=13.7ms, 1=101ms, 2=402ms
        self.gain_m = 1
        self.timing_ms = 402
        self.ch0 = 0
        self.ch1 = 0
        self.sch0 = 0
        self.sch1 = 0

    def write_register(self, reg, value):
        """Write a byte to the specified register"""
        self.i2c.writeto_mem(self.address, reg, bytearray([value]))
        utime.sleep(self.cooldown)

    def read_register(self, reg):
        """Read a byte from the specified register"""
        result = self.i2c.readfrom_mem(self.address, reg, 1)
        utime.sleep(self.cooldown)
        return result[0]

    def read_register16(self, reg):
        """Read two bytes from consecutive registers (low byte first)"""
        data = self.i2c.readfrom_mem(self.address, reg, 2)
        utime.sleep(self.cooldown)
        return data[0] | (data[1] << 8)

    def power_up(self):
        self.write_register(TSL2561_Control, 0x03)

    def power_down(self):
        self.write_register(TSL2561_Control, 0x00)

    def set_timing_gain(self):
        """Set integration time and gain"""
        if self.gain == 0:
            self.gain_m = 1
        else:
            self.gain_m = 16

        if self.timing == 0:
            self.timing_ms = 13.7
        elif self.timing == 1:
            self.timing_ms = 101
        else:
            self.timing_ms = 402

        # Write configuration to timing register
        self.write_register(TSL2561_Timing, self.timing | (self.gain << 4))

    def read_channels(self):
        """Read both sensor channels"""
        utime.sleep(self.timing_ms / 1000 + 0.001)
        self.ch0 = self.read_register16(TSL2561_Channel0L)
        self.ch1 = self.read_register16(TSL2561_Channel1L)

    def read_visible_lux(self):
        """Read visible light intensity in lux"""
        self.power_up()
        self.set_timing_gain()
        self.read_channels()

        # Dynamic adjustment of gain and timing
        if self.ch0 < 500:
            if self.timing == 0:
                self.timing = 1
            elif self.timing == 1:
                self.timing = 2
            elif self.gain == 0:
                self.gain = 1
            self.set_timing_gain()
            self.read_channels()

        if self.ch0 > 20000 or self.ch1 > 20000:
            if self.gain == 1:
                self.gain = 0
            elif self.timing == 2:
                self.timing = 1
            elif self.timing == 1:
                self.timing = 0
            self.set_timing_gain()
            self.read_channels()

        self.power_down()
        return self.calculate_lux(self.ch0, self.ch1)

    def calculate_lux(self, ch0, ch1):
        """Calculate lux from raw channel values"""
        # Scaling based on timing
        if self.timing == 0:       # 13.7ms
            ch_scale = CHSCALE_TINT0
        elif self.timing == 1:     # 101ms
            ch_scale = CHSCALE_TINT1
        else:                      # 402ms
            ch_scale = 1 << CH_SCALE

        # Apply gain scaling
        if self.gain == 0:
            ch_scale <<= 4  # Scale from 1x to 16x

        # Scale channel values
        self.sch0 = (ch0 * ch_scale) >> CH_SCALE
        self.sch1 = (ch1 * ch_scale) >> CH_SCALE

        # Calculate ratio
        ratio = 0
        if self.sch0 != 0:
            ratio = (self.sch1 << (RATIO_SCALE + 1)) // self.sch0
        ratio = (ratio + 1) >> 1

        # Determine coefficients (T package)
        if ratio <= K1T:
            b, m = B1T, M1T
        elif ratio <= K2T:
            b, m = B2T, M2T
        elif ratio <= K3T:
            b, m = B3T, M3T
        elif ratio <= K4T:
            b, m = B4T, M4T
        elif ratio <= K5T:
            b, m = B5T, M5T
        elif ratio <= K6T:
            b, m = B6T, M6T
        elif ratio <= K7T:
            b, m = B7T, M7T
        else:
            b, m = B8T, M8T

        # Calculate lux
        temp = (self.sch0 * b) - (self.sch1 * m)
        if temp < 0:
            temp = 0
        lux = (temp + (1 << (LUX_SCALE - 1))) >> LUX_SCALE
        return lux

    def init_sensor(self):
        """Initialize sensor with default settings"""
        self.power_up()
        self.set_timing_gain()
        self.write_register(TSL2561_Interrupt, 0x00)
        self.power_down()

# Example usage
if __name__ == "__main__":
    # Initialize I2C on bus 0, SDA=GP0, SCL=GP1 (Pico default I2C0 pins)
    class TSL2591:
        def __init__(self):
            self.sensor = TSL2561(1, 26, 27)
            self.sensor.init_sensor()
            
            self.sensor.gain = 1
            self.sensor.timing = 1
    
        def read(self):
            self.sensor.power_up()
            self.sensor.set_timing_gain()
            self.sensor.read_channels()
            #(sensor.ch0*550)/(257.5*1.24)
            #print(f"[full={sensor.ch0}, Gain={sensor.gain_m}x, Timing={sensor.timing_ms}]")
            #print(f"Lux: {lux} [Vis+IR={sensor.ch0}, IR={sensor.ch1} @ Gain={sensor.gain_m}x, Timing={sensor.timing_ms}ms]")
            #utime.sleep(0.2)
            value = self.sensor.ch0
            self.sensor.power_down()
            return value
    sensor = TSL2591()

