from machine import Pin

SPECTRO_SDA_PIN = 16
SPECTRO_SCL_PIN = 17

i2c = machine.I2C(0,
                  scl=machine.Pin(SPECTRO_SCL_PIN),
                  sda=machine.Pin(SPECTRO_SDA_PIN),
                  freq=4000)

from time import sleep
#import board
from adafruit_as7341 import AS7341

#i2c = board.I2C()
sensor = AS7341(i2c)