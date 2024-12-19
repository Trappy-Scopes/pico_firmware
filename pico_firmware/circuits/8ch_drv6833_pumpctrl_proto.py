## 8ch_drv6833_pumpctrl_proto


from pico_firmware.controllers.adafruit_drv8633 import DRV6833
from pico_firmware.idioms.actionset import ActionSet
from pico_firmware.beacon import Beacon

pins = { "buzzer" : 26,
		 "board1": {"ain1": 6, "ain2": 7, "bin1": 9, "bin2": 8, "slp":10},
		 "board2": {"ain1": 12, "ain2": 13, "bin1": 15, "bin2": 14, "slp":11}
}

buzzer = Beacon(pins["buzzer"])

board1 = DRV6833(pins["board1"]["ain1"], pins["board1"]["ain2"], 
				 pins["board1"]["bin1"], pins["board1"]["bin2"],
				 pins["board1"]["slp"])


board2 = DRV6833(pins["board2"]["ain1"], pins["board2"]["ain2"], 
				 pins["board2"]["bin1"], pins["board2"]["bin2"],
				 pins["board2"]["slp"])

#board3 = DRV6833()
#board4 = DRV6833()


motorset = ActionSet([board1.motors[0], board1.motors[1], board2.motors[0], board2.motors[1]])
motor1 = motorset[0]
motor2 = motorset[1]
motor3 = motorset[2]
motor4 = motorset[3]


class CleaningPump:


	def __init__(self, motor, speed, pump_duty = [5, 55]):
		self.motor = motor
		self.pump_duty = pump_duty


