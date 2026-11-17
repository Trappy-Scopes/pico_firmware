"""
DumbBeacon - a plain GPIO buzzer/beacon.

Drop-in replacement for pico_firmware.beacon.Beacon with the same API
(current / on / off / blink / pulse / devicestatus) but no PIO.

Why: Beacon drove ONE pin from TWO PIO state machines running at 10000 and
10001 Hz and relied on the beat between them to blink. That burns 2 of the
RP2040's 8 state machines and is a lot of machinery for a beeper. This does
the same job with Pin.value() and, for blink(), one soft Timer.

Usage is identical:

    from pico_firmware.actuators.dumbbeacon import DumbBeacon as Beacon
    beacon = Beacon(pins["buzzer"])
    beacon.pulse(3)
"""

from machine import Pin, Timer
import time


class DumbBeacon:

    # Kept for API compatibility: CircadianScheduler does `Beacon.current`.
    current = None

    # Blink rate when blink() is active, milliseconds per half-period.
    BLINK_MS = 500

    def __init__(self, pin_no):
        self.pin_no = pin_no
        self.pin = Pin(pin_no, Pin.OUT)
        self.pin.value(0)

        self._blink_timer = None
        self._blinking = False

        DumbBeacon.current = self

    # -- state ------------------------------------------------------------

    def on(self):
        self.__stop_blink__()
        self.pin.value(1)

    def off(self):
        self.__stop_blink__()
        self.pin.value(0)

    def blink(self):
        """Blink continuously in the background. Non-blocking."""
        if self._blinking:
            return
        self._blinking = True
        self.pin.value(0)
        self._blink_timer = Timer()
        self._blink_timer.init(
            mode=Timer.PERIODIC,
            period=DumbBeacon.BLINK_MS,
            callback=self.__toggle__,
        )

    def __toggle__(self, timer):
        # Timer callbacks must never let an exception escape.
        try:
            self.pin.value(not self.pin.value())
        except BaseException:
            pass

    def __stop_blink__(self):
        if self._blink_timer is not None:
            try:
                self._blink_timer.deinit()
            except BaseException:
                pass
            self._blink_timer = None
        self._blinking = False

    # -- patterns ---------------------------------------------------------

    def pulse(self, no):
        """`no` beeps, 0.25 s on / 0.25 s off. Blocking, as before."""
        self.__stop_blink__()
        for _ in range(no):
            self.pin.value(1)
            time.sleep(0.25)
            self.pin.value(0)
            time.sleep(0.25)

    def tick(self, ms=40):
        """One short chirp. Cheap enough to call from a periodic callback."""
        self.pin.value(1)
        time.sleep_ms(ms)
        self.pin.value(0)

    # -- device status ----------------------------------------------------

    def devicestatus(self, status):
        if status == "standby":
            self.blink()
            return True
        elif status == "off":
            self.off()
            return True
        elif status == "busy":
            self.on()
            return True
        else:
            return False
