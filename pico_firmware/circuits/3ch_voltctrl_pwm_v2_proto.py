## 3ch_voltctrl_pwm_v2_proto.py



## Pin assignements
pins = {"ch": {"red": 9, "green":10, "blue":12},
		"tandh": {"sda":8, "scl":9},
		"beacon" : 14
}



## Device initalization
from pico_firmware.beacon import Beacon
beacon = Beacon(pins["beacon"])
status = beacon.devicestatus

from pico_firmware.actuators.lights.channels.pwm_ca_channel import PwmCAchannel
from pico_firmware.actuators.lights.multichannel_controller import MultiChController

red = PwmCAchannel(pins["ch"]["red"])
green = PwmCAchannel(pins["ch"]["green"])
blue = PwmCAchannel(pins["ch"]["blue"])
lit = MultiChController([red, green, blue])


#from pico_firmware.bookeeping.checkpointer import Checkpointer
#lit.setVs(Checkpointer.read(lit.setVs))


from pico_firmware.sensors.tandhsensor import TandHSensor
#tandh = TandHSensor(pins["tandh"], "dh11")
status("busy")
