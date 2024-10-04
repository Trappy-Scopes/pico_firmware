import picokeypad
import time

#import mqtt

class mqtt:
    def transmit(topic, message):
        time.sleep(1)
        print(topic, message)

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
    def __init__(self, mode):
        self.mode = mode
        
        self.on_standby = None
        #self.on_trigger = None
        self.on_relax = None
        self.on_trigger_action = None
        self.on_trigger_color = None

class Keypad:
    no_pads = 16
        
    def __init__(self):
        self.keypad = picokeypad.PicoKeypad()
        self.keypad.get_num_pads()
        self.keypad.set_brightness(0.2)
        self.last_button_states = None
        self.buttons = {}
        
        
        self.__initseq__()
            
    def clear(self):
        self.keypad.clear()
        self.keypad.update()
    
    def all(self, color="white"):
        if isinstance(color, str):
            color = colors[color]
        for i in range(Keypad.no_pads):
                self.keypad.illuminate(i, *color)
        self.keypad.update()
         
    def set_brightness(self, b):
        self.keypad.set_brightness(b)
        self.keypad.update()
        
    def __color__(self, pos, color):
        def paint():
            self.keypad.illuminate(pos, *colors[color])
            self.keypad.update()
        return paint
    
    def __blink__(self, pos, color, cycles=3):
        for i in range(cycles):
            self.keypad.set_brightness(0.2)
            self.keypad.illuminate(pos, *colors[color])
            self.keypad.update()
            time.sleep(0.2)
            self.keypad.set_brightness(0)
            time.sleep(0.2)
        self.keypad.set_brightness(0.2)
    def __initseq__(self):
        ### Init sequence
        for i in range(Keypad.no_pads):
            self.keypad.illuminate(i, *colors["white"])
            time.sleep(0.2)
            self.keypad.update()
        time.sleep(0.5)
        for color in ["red", "green", "blue"]:
            for i in range(Keypad.no_pads):
                self.keypad.illuminate(i, *colors[color])
                self.keypad.update()
            time.sleep(0.5)
        self.keypad.clear()
        self.keypad.update()
    
    def set_button(self, pos, message, topic, standby="green",
                   trigger="red", relax="yellow", mode="continuous"):
        """
        mode: "oneshot" or "continuous"
        """
        
        #if not isinstance(pos, str):
        #    pos = keys[str(pos)]
        button = Button(mode)
        button.on_standby = self.__color__(pos, standby)
        
        button.on_trigger_color = self.__color__(pos, trigger)
        button.on_trigger_action = lambda: mqtt.transmit(message, topic)
        
        button.on_relax = self.__color__(pos, relax)    
        self.buttons[pos] = button
        
        self.__blink__(pos, "red")
        button.on_standby()
        
    def update(self):
        button_states = self.keypad.get_button_states()
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
        
    
