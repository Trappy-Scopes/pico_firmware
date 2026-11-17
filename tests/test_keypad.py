import sys, os, gc, tracemalloc
sys.path.insert(0, os.path.dirname(__file__))   # stub machine/time first
import mptime as mtime
sys.modules["time"] = mtime                     # `time` is builtin: force the shim
import machine

import paths
SRC = paths.KEYPAD_NEW
g = {"__name__": "circuit"}
exec(compile(open(SRC).read(), SRC, "exec"), g)

kp = g["kp"]
i2c = kp._kp._i2c
spi = kp._kp._spi
timer = machine.Timer.instances[-1]
assert timer.cb is not None, "timer not armed"
print("armed, pumps =", kp.pumps())

def press(pad, ms=60):
    """Hold pad down for ms, then release, ticking the timer at 8 ms."""
    i2c.buttons = 0xFFFF & ~(1 << pad)
    for _ in range(max(1, ms // 8)):
        mtime.advance(8); timer.cb(timer)
    i2c.buttons = 0xFFFF
    for _ in range(4):
        mtime.advance(8); timer.cb(timer)

# ---- basic behaviour
press(0)                      # col0 row0 -> PUMP 1 POWER
assert kp.is_power(1) is True, kp.state(1)
assert kp.lines() == ["PUMP 1 POWER ON"], "unexpected queue"
press(4)                      # col0 row1 -> PUMP 1 PULSE
assert kp.is_pulse(1) is True
assert kp.lines() == ["PUMP 1 PULSE ON", "PUMP 1 SPEED 30"]
press(8)                      # SPEED +
assert kp.speed(1) == 35, kp.speed(1)
press(12)                     # SPEED -
assert kp.speed(1) == 30
press(3)                      # col3 row0 -> PUMP 3 POWER
assert kp.is_power(3) is True
print("keys OK:", kp.state())

# ---- decorative column is inert
before = kp.count()
press(1 + 8)                  # pad 9 = col1 row2 -> PUMP 2 SPEED+, real
press(2); press(6); press(10); press(14)   # col2 = dead column
assert kp.count() == before + 1, "dead column emitted commands"
print("dead column inert OK")

# ---- auto-repeat on hold
kp.lines()
i2c.buttons = 0xFFFF & ~(1 << 8)
for _ in range(150):          # 1.2 s hold
    mtime.advance(8); timer.cb(timer)
i2c.buttons = 0xFFFF
reps = len(kp.lines())
assert reps > 5, "auto-repeat did not fire (%d)" % reps
print("auto-repeat OK: %d events, speed=%d" % (reps, kp.speed(1)))

# ---- debounce must NOT lose a press
# A press edge that lands inside DEBOUNCE_MS of the previous edge is rejected.
# The old code then still did `self._last_states = states`, adopting the rejected
# level as the new baseline: the key was now "already down", no further edge ever
# arrived, and the press vanished. The finger is still on the key, so a correct
# scan must re-detect it once the window passes.
kp.lines()
mtime.advance(1000); timer.cb(timer)
was = kp.is_power(1)
kp._edge_time[0] = mtime.ticks_ms()   # pretend contact chatter just fired
i2c.buttons = 0xFFFF & ~1             # the real press, inside the window
mtime.advance(8); timer.cb(timer)
assert kp.is_power(1) == was, "press should have been debounced away here"
for _ in range(6):                    # finger stays down past DEBOUNCE_MS
    mtime.advance(8); timer.cb(timer)
assert kp.is_power(1) != was, "bounced press was LOST (the old bug)"
assert len(kp.lines()) == 1, "press registered more than once"
i2c.buttons = 0xFFFF
for _ in range(6): mtime.advance(8); timer.cb(timer)
assert kp.lines() == [], "release emitted a spurious command"
print("debounce-does-not-lose-press OK")

# ---- queue cap and drop accounting
kp.lines()
for i in range(200):
    kp._issue(1, "SPEED", 10 + (i % 80))
assert len(kp.pending()) == g["PENDING_MAX"], len(kp.pending())
assert kp.health()["dropped"] == 200 - g["PENDING_MAX"], kp.health()
print("queue cap OK:", kp.health()["pending"], "pending,", kp.health()["dropped"], "dropped")
kp.lines()

# ---- KeyboardInterrupt inside service() must not escape the callback
real = kp.service
def boom(now=None): raise KeyboardInterrupt()
kp.service = boom
timer.cb(timer)               # would propagate with `except Exception`
kp.service = real
assert kp.service_errors() == 1, kp.service_errors()
assert "KeyboardInterrupt" in kp.health()["last_error"]
print("KeyboardInterrupt contained OK:", kp.health()["last_error"])

# ---- re-exec: old timer must be disarmed, only one live
old = kp
n_before = len(machine.Timer.instances)
g2 = dict(g)
exec(compile(open(SRC).read(), SRC, "exec"), g2)
new = g2["kp"]
assert old._timer is None, "previous build still armed -- two timers on one bus"
assert new._timer is not None
assert new.state() == old.state(), "adopt() lost state"
assert g2["_previous"] is None, "_previous still pinning the dead object"
print("re-exec retire OK; live timers:",
      sum(1 for t in machine.Timer.instances if t.alive and t.cb))

# ---- allocation / SPI churn over a long idle run
kp = new; timer = machine.Timer.instances[-1]
i2c = kp._kp._i2c; spi = kp._kp._spi
gc.collect()
spi.writes = 0
tracemalloc.start()
snap0 = tracemalloc.take_snapshot()
TICKS = 200_000               # 8 ms x 200k = ~27 minutes of idle service()
for _ in range(TICKS):
    mtime.advance(8); timer.cb(timer)
snap1 = tracemalloc.take_snapshot()
grown = sum(s.size_diff for s in snap1.compare_to(snap0, "filename"))
tracemalloc.stop()
print("after %d ticks (~%.0f min): heap delta %+d B, SPI writes %d, errors %d, pending %d"
      % (TICKS, TICKS * 8 / 60000.0, grown, spi.writes, kp.service_errors(), len(kp.pending())))
assert grown < 50_000, "heap grew %d B" % grown
assert kp.service_errors() == 0
assert len(kp.pending()) == 0

# ---- sync / apply round trip
kp.sync({1: {"power": True, "pulse": False, "percent": 55},
         2: {"fast": False, "pulse": True, "level": 0.4},
         3: {"power": False, "pulse": True, "percent": 100}})
assert kp.pending() == [], "sync bounced back as commands"
assert kp.state(1)["speed"] == 55 and kp.state(2)["speed"] == 40
assert kp.snapshot_lines()[0] == "PUMP 1 POWER ON"
assert kp.apply("PUMP 1 POWER OFF") == 1 and kp.is_power(1) is False
assert kp.apply("garbage in") is None
assert kp.apply("PUMP 9 POWER ON") is None
assert kp.apply_lines(["PUMP 2 SPEED 75", "nope"]) == 1
assert kp.pending() == []
print("sync/apply OK:", kp.snapshot_lines())

# ---- ticks wrap (the board runs for weeks)
mtime.set_ms((1 << 30) - 500)
for _ in range(300):
    mtime.advance(8); timer.cb(timer)
assert kp.service_errors() == 0, "wrap broke service(): " + kp.health()["last_error"]
print("ticks_ms wrap OK")

print("\nALL KEYPAD FIRMWARE TESTS PASSED")
