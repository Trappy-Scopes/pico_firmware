import _thread
from processor2 import processor2
import secrets

from lights import LightSelector
from wifi import Wifi

## Wifi
wifi = Wifi(secrets)
beacon = Beacon()

## Start Processor 2 thread
processor2_thread = _thread.start_new_thread(processor2, ())


## Light
lit = LightSelector(deviceid)


## TandH
if tandh in deviceid:
	tandh = TandHSensor(pinassignments.sensors.tandh, "dh11")