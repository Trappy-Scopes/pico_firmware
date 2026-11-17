# discrete_spectrometer_adafruit_as7314_v1_proto.py

import sys
from time import sleep_ms
from machine import I2C, SoftI2C, Pin

from pico_firmware.sensors.spectrometer.adafruit_as7314 import *


## Configuration function for the spectrometer
def __configure_spectrometer__(sensor, measure_mode=AS7341_MODE_SPM, 
							atime=29, astep=599, again=8):
	sensor.set_measure_mode(measure_mode)
	sensor.set_atime(atime)                # 30 ASTEPS
	sensor.set_astep(astep)                # 1.67 ms
	sensor.set_again(again)                # factor 8 (with pretty much light)

	print("Channel 2", sensor.get_channel_data(2))
	print("Integration time:", sensor.get_integration_time(), "msec")

## Read function for the spectrometer
def __read_spectrometer__(sensor):
	result = {(405, 425): None,  # F1
			  (435, 455): None,	 # F2
			  (470, 490): None,	 # F3
			  (505, 525): None,	 # F4
			  (545, 565): None,	 # F5
			  (580, 600): None,	 # F6
			  (620, 640): None,	 # F7
			  (670, 690): None,	 # F8
			  "nir"     : None,
			  "clear"   : None,
			  "flicker" : None}

	## Measure -> Mux state 1
	sensor.start_measure("F1F4CN")
	result[(405, 425)], result[(435, 455)], result[(470, 490)], result[(505, 525)], result["clr"], result["nir"] = sensor.get_spectral_data()

	## Measure -> Mux state 2
	sensor.start_measure("F5F8CN")
	result[(545, 565)], result[(580, 600)], result[(620, 640)], result[(670, 690)], clear_, nir_ = sensor.get_spectral_data()

	## Measure -> Mux state 3
	sensor.start_measure("FD")
	result["flicker"] = sensor.get_spectral_data()

	#return result.update(sensor.config) ## Add configuration to the result
	return result


pins = {"scl":15, "sda": 14}

# i2c = SoftI2C(scl=Pin(25), sda=Pin(26))
i2c_ = I2C(1, scl=Pin(pins["scl"]), sda=Pin(pins["sda"]), freq=100000)
print("Detected devices at I2C-addresses:",
	  " ".join(["0x{:02X}".format(x) for x in i2c_.scan()]))


from pico_firmware.hive.detector import Detector

#class Spectrometer(AS7341, AbstractDetector):
#	def __init__(self, i2c_, configure, read):
#		
#
#		AbstractDetector.__init__(self, configure, read)

__as7341__ = AS7341(i2c_)
if not __as7341__.isconnected():
	print("Failed to contact AS7341 Spectrometer!")
spectrometer = Detector.Construct(__as7341__, configure=__configure_spectrometer__, read=__read_spectrometer__)



#spectrometer.config = {}
#test encoding:
#for i in (2000, 800, 128, 8, 2, 2, 0.7, 0.5, 0.3, 0):
#    spectrometer.set_again_factor(i)
#    print("factor in:", i, "code", spectrometer.get_again(), " result:", spectrometer.get_again_factor())
