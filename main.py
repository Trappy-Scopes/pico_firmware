import os


### Construct boot and webrepl config
if "boot.py" not in os.listdir("/"):
    with open("boot.py", "w") as f:
        f.write("import webrepl\nwebrepl.start()\n") 

if "webrepl_cfg.py" not in os.listdir("/"):
    with open("webrepl_cfg.py", "w") as f:
        f.write("PASS = \'pico2TERA\'\n")



### ---- Test stuff
import _thread
#from processor2 import processor2
import secrets


#from lights import LightSelector
#from wifi import Wifi

## Wifi
#wifi = Wifi(secrets)
#beacon = Beacon(14)

## Start Processor 2 thread
#processor2_thread = _thread.start_new_thread(processor2, ())


## Light
#lit = LightSelector(deviceid)


## TandH
#if tandh in deviceid:
#	tandh = TandHSensor(pinassignments.sensors.tandh, "dh11")

from pico_firmware.beacon import Beacon
beacon = Beacon(14)
beacon.blink()
from machine import Pin
power = Pin(17, mode=Pin.OUT)
power.on()
#beacon.pulse(15)
beacon2 = Beacon(16)
#beacon3 = Beacon(12)
beacon2.blink()