import picokeypad
import time


colors = {"red"    : (255, 0, 0),
          "green"  : (0, 255, 0),
          "blue"   : (0, 0, 255),
          "yellow" : (255, 255, 0),
          "orange" : (255, 64, 0),
          "purple" : (255, 0, 255),
          "white"  : (255,255,255)
          }
keys = {"0":hex(0), "1":hex(1), "2":hex(2), "3":hex(3), "4":hex(4),
         "5":hex(5), "6":hex(6), "7":hex(7), "8":hex(8), "9":hex(9), "a":hex(10),
        "b":hex(11), "c":hex(12), "d":hex(13), "e":hex(14), "f":hex(15)}
inv_keys = {v:k for k, v in keys.items()}


class Button:
	"""
	Represents single button.
	"""
	def __init__(self, addr, keyboard):
		self.addr = addr
		self.keyboard = keyboard


		self.mode = mode
		
		self.on_standby = None
		#self.on_trigger = None
		self.on_relax = None
		self.on_trigger_action = None
		self.on_trigger_color = None

		self.buzzer = self.keypad.buzzer

	def __color__(self, color):
        #def paint():
        #    self.keyboard.illuminate(self.addr, *colors[color])
        #    self.keypad.update()
        #return paint
        pass
    
    def __blink__(self, pos, color, cycles=3):
        for i in range(cycles):
            self.keypad.set_brightness(0.2)
            self.keypad.illuminate(pos, *colors[color])
            self.keypad.update()
            time.sleep(0.2)
            self.keypad.set_brightness(0)
            time.sleep(0.2)
        self.keypad.set_brightness(0.2)
    
class Keypad:
    no_pads = 16
        
    def __init__(self, buzzer):
        self.keypad = picokeypad.PicoKeypad()
        self.keypad.get_num_pads()
        self.keypad.set_brightness(0.2)
        self.last_button_states = None
        self.buttons = {k:b for k, b in keys.keys() \
        				[Button(k, self.keypad for k in keys)]}
        self.buzzer = buzzer