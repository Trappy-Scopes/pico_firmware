from machine import Pin
import pinassignments

class Action:
    def __init__(self, pin, callback, trigger=Pin.IRQ_FALLING, debounce_ms=300):
        self.callback = callback
        self.debounce_ms = debounce_ms
        self.pin = pin
        
        self._blocked = False
        self._next_call = time.ticks_ms() + self.debounce_ms

        pin.irq(trigger=trigger, handler=self.debounce_handler)

    def __call__(self, pin):
        self.callback(pin)

    def debounce_handler(self, pin):
        if time.ticks_ms() > self._next_call:
            self._next_call = time.ticks_ms() + self.debounce_ms
            self.__call__(pin)
        #else:
        #    print("debounce: %s" % (self._next_call - time.ticks_ms()))
    
class BinaryAction:
    def __init__(self, pin, callback, trigger=Pin.IRQ_FALLING, debounce_ms=300):
        self.callback = callback
        self.debounce_ms = debounce_ms
        self.pin = pin
        
        self._blocked = False
        self._next_call = time.ticks_ms() + self.debounce_ms

        pin.irq(trigger=trigger, handler=self.debounce_handler)

    def __call__(self, pin):
        self.callback(pin)

    def debounce_handler(self, pin):
        if time.ticks_ms() > self._next_call:
            self._next_call = time.ticks_ms() + self.debounce_ms
            self.__call__(pin)
        #else:
        #    print("debounce: %s" % (self._next_call - time.ticks_ms()))
    
if __name__ == "__main__":
    buzzer = Pin(pinassigments.buzzer, Pin.IN)
    relay = Action(Pin(pinassignments.sw2), lambda: buzzer.toggle())