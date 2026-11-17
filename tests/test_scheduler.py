"""Level-triggered CircadianScheduler: simulate 48 h of 30 s ticks.

Run from pico_firmware/tests:  python3 test_scheduler.py

The failure this guards against is real: on 2026-08-26 the 20:00 transition
never fired and the cells got 10h24m of unintended light.
"""
import sys, os, types

sys.path.insert(0, "stub")
sys.path.insert(0, os.path.abspath(".."))

import machine

## neopixel and the logger are irrelevant here; stub them out before import.
np = types.ModuleType("neopixel")
np.NeoPixel = object
sys.modules["neopixel"] = np

lg = types.ModuleType("pico_firmware._logger")
class _Log:
    @staticmethod
    def write(ch, msg): pass
lg.Logger = _Log
sys.modules["pico_firmware._logger"] = lg

from pico_firmware.controllers import circadian_cycle_controller as ccc
from pico_firmware.controllers.circadian_cycle_controller import CircadianScheduler

## The module did `from machine import RTC` at import time, so rebinding
## machine.RTC is too late - patch the name the module actually holds.
_real_print = print
ccc.print = lambda *a, **k: None


class FakeClock:
    """RTC driven by a minute counter, so ticks can be delayed at will."""
    def __init__(self, minutes=0):
        self.minutes = minutes
    def datetime(self):
        m = self.minutes % 1440
        day = 25 + (self.minutes // 1440)
        return (2026, 8, day, 1, m // 60, m % 60, 0, 0)


class FakeBuzzer:
    def __init__(self): self.pulses = 0
    def pulse(self, n=1): self.pulses += 1


class FakeMatrix:
    def __init__(self): self.colour = None
    def fill(self, c): self.colour = tuple(c)
    def write(self): pass


def build(day_start=[8, 0], night_start=[20, 0], start_min=0):
    clock = FakeClock(start_min)
    lm = FakeMatrix()
    ccc.RTC = lambda: clock
    s = CircadianScheduler(lm, day_start=day_start, night_start=night_start,
                           buzzer=FakeBuzzer())
    return s, clock, lm


FAILS = []

def check(name, cond, detail=""):
    print = _real_print
    if cond:
        print("  ok   ", name)
    else:
        print("  FAIL ", name, detail)
        FAILS.append(name)


# --- 1. desired_phase is a pure function of the clock -----------------------
print("desired_phase")
s, clock, lm = build()
cases = [(0, "night"), (7 * 60 + 59, "night"), (8 * 60, "day"),
         (12 * 60, "day"), (19 * 60 + 59, "day"), (20 * 60, "night"),
         (23 * 60 + 59, "night")]
for m, want in cases:
    got = s.desired_phase((2026, 8, 25, 1, m // 60, m % 60, 0, 0))
    check("%02d:%02d -> %s" % (m // 60, m % 60, want), got == want, "got " + got)

# boundary: 20:00 exactly must be night, not day (old phase_detect said day)
check("20:00 is night, not day",
      s.desired_phase((2026, 8, 25, 1, 20, 0, 0, 0)) == "night")


# --- 2. a wrapping window (night cycle) ------------------------------------
print("wrapping window: day 20:00 -> 06:00")
s2, _, _ = build(day_start=[20, 0], night_start=[6, 0])
for m, want in [(0, "day"), (5 * 60 + 59, "day"), (6 * 60, "night"),
                (19 * 60, "night"), (20 * 60, "day"), (23 * 60, "day")]:
    got = s2.desired_phase((2026, 8, 25, 1, m // 60, m % 60, 0, 0))
    check("%02d:%02d -> %s" % (m // 60, m % 60, want), got == want, "got " + got)


# --- 3. 48 h of clean 30 s ticks: exactly 4 transitions ---------------------
print("48 h of 30 s ticks")
s, clock, lm = build(start_min=0)          # boot at 00:00 -> night
s.set_timers("short")
events = []
prev = s.phase
half = 0
for _ in range(48 * 60 * 2):               # 30 s steps
    half += 1
    clock.minutes = half // 2
    s.timer.tick()
    if s.phase != prev:
        events.append((clock.minutes % 1440, s.phase))
        prev = s.phase
check("4 transitions in 48 h", len(events) == 4, events)
check("transitions at 08:00 / 20:00",
      all(m in (480, 1200) for m, _ in events), events)
check("ends on night (48 h -> 00:00)", s.phase == "night", s.phase)


# --- 4. the 2026-08-26 failure: a tick that skips clean over 20:00 ----------
print("delayed tick across the 20:00 boundary")
s, clock, lm = build(start_min=12 * 60)    # boot at 12:00 -> day
s.set_timers("short")
check("starts in day", s.phase == "day")

clock.minutes = 19 * 60 + 58
s.timer.tick()
check("19:58 still day", s.phase == "day")

## Jump 17 minutes: no callback lands inside the 20:00 minute at all.
## The old edge-triggered code would stay in "day" until the next 20:00.
clock.minutes = 20 * 60 + 15
s.timer.tick()
check("20:15 corrected to night on the very next tick", s.phase == "night",
      s.phase)


# --- 5. hours-long outage, phase recovered in one tick ----------------------
print("multi-hour outage")
s, clock, lm = build(start_min=12 * 60)
s.set_timers("short")
clock.minutes = 12 * 60 + 30
s.timer.tick()
check("day before outage", s.phase == "day")
clock.minutes = (23 * 60) + 45           # 11 h later, transition missed
s.timer.tick()
check("night after outage", s.phase == "night", s.phase)


# --- 6. idempotence: repeated ticks in one phase never re-fire --------------
print("idempotence")
s, clock, lm = build(start_min=10 * 60)
s.set_timers("short")
fired = []
s.bomdia = lambda lm_: fired.append("day")
s.bonnoite = lambda lm_: fired.append("night")
for i in range(200):
    clock.minutes = 10 * 60 + i // 4
    s.timer.tick()
check("no re-fire across 200 ticks inside one phase", fired == [], fired)


# --- 7. reboot mid-phase reapplies the correct lights -----------------------
print("reboot at 03:00")
s, clock, lm = build(start_min=3 * 60)
check("boots into night", s.phase == "night", s.phase)
check("matrix set to night colour", lm.colour == (0, 0, 0), lm.colour)
s, clock, lm = build(start_min=9 * 60)
check("boots into day", s.phase == "day", s.phase)
check("matrix set to day colour", lm.colour == (255, 255, 255), lm.colour)


print()
if FAILS:
    print("%d FAILED: %s" % (len(FAILS), FAILS))
    sys.exit(1)
print("all passed")
