import machine
import utime
from pico_lcd import *

setUpLCD()
rs.value(1)
for x in 'Hello World!':
    send2LCD8(ord(x))
    utime.sleep_ms(100)