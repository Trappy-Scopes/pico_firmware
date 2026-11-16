"""
TSL2561 light-to-digital converter (TAOS / ams), and the LightMeter used by lux1.

The register map and the lux constants (LUX_SCALE, CHSCALE_TINT0, K1T ...) follow
the example code in the TAOS TSL2560/TSL2561 datasheet (TAOS059N). The TSL2561
class is unchanged from circuits/tsl2561.py as found on lux1 (2025-08-01).
"""

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



## ---------------------------------------------------------------------------
## LightMeter -- AI Generated (Claude, Anthropic), 2026-11-16, with Yatharth.
## Replaces the wrapper that was called TSL2591 although it built a TSL2561.
## ---------------------------------------------------------------------------

import json
import os
import time
import hashlib
import machine
import ubinascii

GAIN_CODES = {1: 0, 16: 1}
INTEGRATION_CODES = {13.7: 0, 101: 1, 402: 2}
INTEGRATION_FROM_CODE = {0: 13.7, 1: 101, 2: 402}
FULL_SCALE = {13.7: 5047, 101: 37177, 402: 65535}     # datasheet, note 6
PACKAGES = {0x0: "TSL2560CS", 0x1: "TSL2561CS", 0x4: "TSL2560T/FN/CL", 0x5: "TSL2561T/FN/CL"}
SATURATION = 0.99           # a reading at or above this fraction of full scale is flagged
RECORD = "/vault/lightmeter.json"
DRIVER = "/pico_firmware/sensors/tsl2561.py"


class LightMeter:
    """Raw TSL2561 counts at a fixed gain and integration time.

    read()          one conversion: {"ch0", "ch1", "saturated"}
    configure()     set gain (1 or 16) and integration time (13.7, 101 or 402 ms)
    get_config()    identity and settings, read back from the chip, plus the record
    save_record()   replace vault/lightmeter.json, the sensor's own record

    The gain and integration time are written once, in configure(). read() does
    not rewrite them: the old wrapper wrote them 5 ms after powering the chip up,
    so after any change of settings the first reading mixed old and new settings
    (about 5% off, measured on 2026-11-16).
    """

    def __init__(self, i2c_bus=1, sda=26, scl=27, gain=16, integration_ms=101):
        self.chip = TSL2561(i2c_bus, sda, scl)
        self.config = {}
        self.record = self._load_record()
        self._driver_sha256 = self._sha256(DRIVER)
        self.configure(gain, integration_ms)

    def configure(self, gain=16, integration_ms=101):
        if gain not in GAIN_CODES:
            raise ValueError("gain must be 1 or 16")
        if integration_ms not in INTEGRATION_CODES:
            raise ValueError("integration_ms must be 13.7, 101 or 402")
        chip = self.chip
        chip.gain, chip.timing = GAIN_CODES[gain], INTEGRATION_CODES[integration_ms]
        chip.power_up()
        chip.set_timing_gain()
        chip.power_down()
        self.config = {"gain": gain, "integration_ms": integration_ms,
                       "full_scale": FULL_SCALE[integration_ms]}
        return self.config

    def read(self):
        chip = self.chip
        if self._timing_register() != chip.timing | (chip.gain << 4):
            self.configure(self.config["gain"], self.config["integration_ms"])   # chip was reset
        chip.power_up()
        ## The chip's clock may run up to ~6% slow, so wait 10% past the nominal time.
        time.sleep_ms(int(self.config["integration_ms"] * 1.1) + 2)
        ch0 = chip.read_register16(TSL2561_Channel0L)
        ch1 = chip.read_register16(TSL2561_Channel1L)
        chip.power_down()
        limit = SATURATION * self.config["full_scale"]
        return {"ch0": ch0, "ch1": ch1, "saturated": ch0 >= limit or ch1 >= limit}

    def get_config(self):
        timing = self._timing_register()
        chip_id = self.chip.read_register(0x8A)
        integration_ms = INTEGRATION_FROM_CODE.get(timing & 0x03)
        try:
            import board
            name, circuit = board.name, board.circuit_id
        except ImportError:
            name = circuit = None
        return {"board": name, "circuit": circuit,
                "duid": ubinascii.hexlify(machine.unique_id()).decode(),
                "chip": PACKAGES.get(chip_id >> 4, "unknown"),
                "chip_id": "0x%02x" % chip_id,
                "gain": 16 if timing & 0x10 else 1,
                "integration_ms": integration_ms,
                "full_scale": FULL_SCALE.get(integration_ms),
                "driver": DRIVER, "driver_sha256": self._driver_sha256,
                "record": self.record}

    def save_record(self, record):
        """Write the record to a temporary file, then rename it over the old one.
        The rename is atomic, so a power cut never leaves a half-written record."""
        tmp = RECORD + ".tmp"
        with open(tmp, "w") as f:
            json.dump(record, f)
        os.rename(tmp, RECORD)
        self.record = record
        return record

    def _timing_register(self):
        return self.chip.read_register(TSL2561_Timing)

    @staticmethod
    def _load_record():
        try:
            with open(RECORD) as f:
                return json.load(f)
        except OSError:
            return {}
        except ValueError:
            return {"error": "unreadable " + RECORD}

    @staticmethod
    def _sha256(path):
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(512)
                    if not chunk:
                        break
                    h.update(chunk)
        except OSError:
            return None
        return ubinascii.hexlify(h.digest()).decode()
