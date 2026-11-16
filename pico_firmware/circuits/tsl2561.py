## lux1: TSL2561 light meter (Seeed Grove - Digital Light Sensor) on I2C1, SDA GP26, SCL GP27.
## The scope sees it as scope.lightmeter. Driver: pico_firmware/sensors/tsl2561.py.
from pico_firmware.sensors.tsl2561 import LightMeter

lightmeter = LightMeter(i2c_bus=1, sda=26, scl=27)
