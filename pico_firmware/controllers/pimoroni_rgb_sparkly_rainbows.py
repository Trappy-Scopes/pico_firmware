import picokeypad
import time

from pico_firmware.peripherals.gui import GUI


colors = {"red"    : (255, 0, 0),
		  "green"  : (0, 255, 0),
		  "blue"   : (0, 0, 255),
		  "yellow" : (255, 255, 0),
		  "orange" : (255, 64, 0),
		  "purple" : (255, 0, 255),
		  "white"  : (255,255,255),
		  "cyan"   : (0, 255, 255)
		  }
keys = {0:hex(0), 1:hex(1), 2:hex(2), 3:hex(3), 4:hex(4),
		 5:hex(5), 6:hex(6), 6:hex(7), 8:hex(8), 9:hex(9), "a":hex(10),
		"b":hex(11), "c":hex(12), "d":hex(13), "e":hex(14), "f":hex(15)}
inv_keys = {v:k for k, v in keys.items()}


class Button:
	"""
	Represents single button.
	"""
	def __init__(self, addr, keypad):
		self.addr = addr
		self.keypad = keypad


		self.mode = None
		self.debounce_period = 0.2
		
		self.on_standby = lambda: print(f"{self.addr} -> on_standby")
		self.on_trigger = lambda: print(f"{self.addr} -> on_trigger")
		
		self.on_relax_color = lambda: None
		self.on_relax_action = lambda: print(f"{self.addr} -> on_relax")
		
		self.on_trigger_action = None
		self.on_trigger_color = None

		self.buzzer = self.keypad.buzzer

	def __color__(self, color):
		def paint():
			self.keypad.illuminate(self.addr, *colors[color])
			self.keypad.update()
		return paint
	
	def __blink__(self, color, cycles=3):
		for i in range(cycles):
			self.keypad.illuminate(self.addr, *colors[color])
			self.keypad.update()
			time.sleep(0.2)
			self.keypad.illuminate(self.addr, 0, 0, 0)
			self.keypad.update()
			time.sleep(0.2)

	def set_button(self, standby="green", trigger=None, trigger_color="red", 
						 relax="yellow", mode="continuous"):
		"""
		mode: "oneshot" or "continuous"
		"""
		self.on_standby = self.__color__(standby)
		
		self.on_trigger_color = self.__color__(trigger_color)

		if trigger is None:
			self.on_trigger_action = lambda: print(f"{self.addr} -> on_trigger")
		elif isinstance(trigger, str):
			self.on_trigger_action = lambda:print(trigger)
		else:
			self.on_trigger_action = trigger
		
		self.on_relax_color = self.__color__(relax)    
		
		self.__blink__("red")
		self.on_standby()

	def trigger(self):
		self.on_trigger_color()
		self.on_trigger_action()

	def relax(self):
		self.on_relax_color()
		self.on_relax_action()
		time.sleep(self.debounce_period)
		self.on_standby()

class Keypad(picokeypad.PicoKeypad, GUI):
	no_pads = 16
		
	def __init__(self, buzzer):
		super().__init__()
		self.no_pads = self.get_num_pads()
		self.set_brightness(0.2)
		self.last_button_states = None
		self.buzzer = buzzer
		
		self.guilist = {"all": None, "clear": None}
		
		
	def clear(self):
		super().clear()
		self.update()
	
	def all(self, color="white"):
		if isinstance(color, str):
			color = colors[color]
		for i in range(self.no_pads):
				self.illuminate(i, *color)
		self.update()
		 
	def brightness(self, b):
		self.set_brightness(b)
		self.update()
		
	def poll(self, buttons):
		button_states = self.get_button_states()
		if self.last_button_states != button_states:
			self.last_button_states = button_states
			if button_states > 0:
				
				## Isolate single button presses
				for button in range(0, self.no_pads):
					# check if this button is pressed and no other buttons are pressed
					#if button_states & 0x01 > 0:
				## --------------------------------
					if (button_states & (1 << button)) != 0:
						if button in buttons:
							buttons[button].on_trigger_color()
							time.sleep(0.1)
							buttons[button].on_trigger_action()
							buttons[button].on_relax()
							time.sleep(0.5)
							#button_states = self.keypad.get_button_states()
							
							if buttons[button].mode == "oneshot":
								buttons.pop(button)
							else:
								buttons[button].on_standby()
		
	def __initseq__(self):
		### Init sequence
		for i in range(self.no_pads):
			self.illuminate(i, *colors["white"])
			time.sleep(0.2)
			self.update()
		time.sleep(0.5)
		for color in ["red", "green", "blue"]:
			for i in range(Keypad.no_pads):
				self.illuminate(i, *colors[color])
				self.update()
			time.sleep(0.5)
		self.clear()
		self.update()
		
		## Draw T
		for key in [0,1,2,3,5,6,9,10,13,14]:
			self.illuminate(key, *colors["cyan"])
		self.update()
		time.sleep(0.5)
		
		## Draw S
		self.clear()
		self.update()
		for key in [3,2,1,0,5, 10, 15, 14, 13, 12]:
			self.illuminate(key, *colors["cyan"])
		self.update()
		time.sleep(0.5)
		
		self.clear()
		self.update()
		


