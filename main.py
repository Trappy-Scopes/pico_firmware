from lights import Lights
from temphumidity import get_temp_humidy
import utime

# Pins
d1_redPIN = 16
d1_greenPIN = 18
d1_bluePIN = 15

d2_redPIN = 22
d2_greenPIN = 27
d2_bluePIN = 28

print(get_temp_humidy())
l1 = Lights(d1_redPIN, d1_greenPIN, d1_bluePIN)
l2 = Lights(d2_redPIN, d2_greenPIN, d2_bluePIN)

#while True:
 #   print(get_temp_humidy())
  #  utime.sleep(0.1)