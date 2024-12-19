import picokeypad
import time


		
	def update(self):
		button_states = self.get_button_states()
		if self.last_button_states != button_states:
			self.last_button_states = button_states
			if button_states > 0:
				
				## Isolate single button presses
				for button in range(0, Keypad.no_pads):
					# check if this button is pressed and no other buttons are pressed
					#if button_states & 0x01 > 0:
				## --------------------------------
					if (button_states & (1 << button)) != 0:
						if button in self.buttons:
							self.buttons[button].on_trigger_color()
							time.sleep(0.1)
							self.buttons[button].on_trigger_action()
							self.buttons[button].on_relax()
							time.sleep(0.5)
							#button_states = self.keypad.get_button_states()
							
							if self.buttons[button].mode == "oneshot":
								self.buttons.pop(button)
							else:
								self.buttons[button].on_standby()

		
		
if __name__ == "__main__":
	keypad = Keypad()
	from machine import Pin
	keypad.set_button(4, ">>>motor1.start()", "M1")
	keypad.set_button(0, ">>>motor1.start()", "M2", trigger="purple", standby="blue")
	
	keypad.set_button(0xf, ">>>motor3.start()", "M3")
	
	while True:
		keypad.update()
	print("done!")
		
	
