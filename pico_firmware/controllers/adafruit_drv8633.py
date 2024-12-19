from machine import Pin

from pico_firmware.actuators.dcmotor import DCMotor

class DRV6833:

	def __init__(self, ain1, ain2, bin1, bin2, sleep):
		self.motors = [DCMotor(ain1, ain2), DCMotor(bin1, bin2)]

		self.sleep = Pin(sleep, Pin.OUT)

		## Enable board
		self.sleep.on()