pins = {
		"buzzer" : 14
}



## Device initalization
from pico_firmware.beacon import Beacon
buzzer = Beacon(pins["buzzer"])


from pico_firmware.controllers.pimoroni_rgb_sparkly_rainbows import Keypad, keys, Button, colors
keypad = Keypad(buzzer)
buttons = {k:b for k, b in zip(keys.keys(), [Button(k, keypad) for k in range(16)])}




## End -> Indicate end of circuit creation
keypad.all("white")
import time
time.sleep(0.5)
keypad.clear()
#keypad.__initseq__()

def start():
	for i in range(100):
		print(f">>>print({i}+{i})")
		time.sleep(0.5)
#import _thread
#t = _thread.start_new_thread(start, ())
