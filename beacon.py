from rp2 import PIO, StateMachine, asm_pio
from machine import Pin
import time

class Beacon:

    def __init__(self, pin_no):
        self.pin_no = pin_no
        self.pin = Pin(pin_no)
        self.sm1 = None
        self.sm2 = None
        self.pin.value(False)
        
        @asm_pio(set_init=PIO.OUT_LOW)
        def led_off():
            set(pins, 0)

        @asm_pio(set_init=PIO.OUT_LOW)
        def led_on():
            set(pins, 1)

        self.off_fn = StateMachine(1, led_off, freq=10000, set_base=self.pin)
        self.on_fn = StateMachine(2, led_on, freq=10002, set_base=self.pin)
        
    def blink(self):
        self.off_fn.active(1)
        self.on_fn.active(1)

    def on(self):
        self.off_fn.active(0)
        self.on_fn.active(1)

    def off(self):
        self.off_fn.active(1)
        self.on_fn.active(0)