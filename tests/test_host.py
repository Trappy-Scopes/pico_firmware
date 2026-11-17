"""End-to-end host test: does the loop survive a link that breaks and stays broken?

The old script's failure mode was not an exception -- it was a blocking serial
read reached from the render function, so the whole process stopped with no
traceback. This drives the real control script against a pumpset whose calls
BLOCK (not raise) after N calls, and asserts the loop keeps rendering, bounds its
memory, and reaches a terminal DOWN state instead of retrying forever.
"""
import os, sys, threading, time, gc, tracemalloc

HERE = os.path.dirname(os.path.abspath(__file__))
import paths
## Repo first, fake LAST -- insert(0) means the last insert wins, and the
## stubbed hive/expframework must shadow the real ones (which need rich,
## a camera stack, and a scope).
sys.path.insert(0, paths.HOST)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake"))

from hive.assembly import ScopeAssembly
import actuators.pumps.supervisor as sup_mod

## The fake Experiment lives at fake/expframework/experiment.py, deliberately
## mirroring the REAL module path. An earlier version of this suite put it at
## fake/experiment.py -- which matched a wrong import in the script under test,
## so the test passed and the script failed on the rig with
## ModuleNotFoundError: No module named 'experiment'. A test double named after
## the bug validates the bug. Guard it explicitly as well:


# --------------------------------------------------------------- fake hardware
class FakePump:
    def __init__(self, n, board): self.n=n; self.b=board
    def __getattr__(self, name):
        def call(*a, **k):
            self.b.tick()
            self.b.settings.setdefault(self.n, {})[name] = a[0] if len(a)==1 else a
            return True
        return call

class FakeBoard:
    """A pump board that can wedge. break_after=None means healthy."""
    def __init__(self, break_after=None, block_s=0.0, heal_after=None):
        self.calls=0; self.break_after=break_after; self.block_s=block_s
        self.heal_after=heal_after; self.settings={}
        self.relinks=0
        self._st = {n: {"name": n, "speed": 0.0, "mode": "idle",
                        "fast_speed": 0.5 if n<3 else 1.0,
                        "slow_limits": (0.03,0.20) if n<3 else (0.45,1.0),
                        "pulse_duty": (5,55) if n<3 else None,
                        "continuous": n==3, "kick": (0.0,0) if n<3 else (1.0,1000),
                        "percent": 30, "level": 0.35, "dir": 1}
                    for n in (1,2,3)}
    def broken(self):
        if self.break_after is None: return False
        if self.heal_after is not None and self.relinks >= self.heal_after: return False
        return self.calls >= self.break_after
    def tick(self):
        self.calls += 1
        if self.broken():
            if self.block_s:
                time.sleep(self.block_s)      # the real failure: it BLOCKS
            raise IOError("timeout waiting for first EOF reception")
    def state(self):
        self.tick(); return {n: dict(s) for n,s in self._st.items()}
    def command(self, line):
        self.tick()
        parts = line.split()
        n = int(parts[1])
        if parts[2]=="POWER": self._st[n]["mode"]="fast" if parts[3]=="ON" else "idle"
        if parts[2]=="SPEED": self._st[n]["percent"]=int(parts[3])
        return True
    def stop_all(self):
        self.tick()
        for s in self._st.values(): s["mode"]="idle"; s["speed"]=0.0
        return True
    def numbers(self): return [1,2,3]
    def __getitem__(self, n): return FakePump(n, self)

class FakeKeypad:
    def __init__(self): self.queue=[]; self.synced=0
    def lines(self):
        out, self.queue = self.queue, []
        return out
    def sync(self, states): self.synced += 1; return sorted(states)
    def snapshot_lines(self): return []
    def stop_all(self): return True

board = FakeBoard()
keypad = FakeKeypad()
ScopeAssembly.current.pumpset = board
ScopeAssembly.current.kp = keypad

# Point RemotePumpSet and KeypadLink at the fakes.
import actuators.pumps.remote as remote
import actuators.pumps.keypadlink as kpl
remote.RemotePumpSet._remote = lambda self: ScopeAssembly.current.pumpset
remote.RemotePumpSet.__getitem__ = lambda self, n: ScopeAssembly.current.pumpset[n]
kpl.kp = lambda name="kp": ScopeAssembly.current.kp
def _fake_repair(self):
    board.relinks += 1
    ok = not board.broken()
    if not ok: self._last_error = "relink: still desynchronised"
    return ok
sup_mod.LinkSupervisor._repair_once = _fake_repair
sup_mod.BACKOFF_S = (0.05, 0.05, 0.05, 0.05, 0.05)   # keep the test quick

SRC = paths.CONTROL

## Guard the import path itself. Every other script in trappyscopes uses
## expframework.experiment; there is no top-level `experiment` module. An earlier
## version of this suite kept its Experiment double at fake/experiment.py, which
## matched a WRONG import in the script -- so the test passed and the rig failed
## with ModuleNotFoundError. A double named after the bug validates the bug.
_src = open(SRC).read()
assert "from expframework.experiment import Experiment" in _src, \
        "must import Experiment from expframework.experiment"
assert "\nfrom experiment import" not in _src, \
        "bare 'from experiment import' -- no such module in this repo"
g = {"__name__": "__main__"}
exec(compile(open(SRC).read(), SRC, "exec"), g)

# ---------------------------------------------------------------- happy path
g["create_exp"]()
assert g["connect"]() is not None, "connect() refused a healthy rig"
LINK = g["LINK"]
assert LINK.status() == "up", LINK.summary()
assert board.settings[3]["set_fast_speed"] == 1.0, board.settings[3]
assert board.settings[1]["set_slow_limits"] == (0.03, 0.20)
# limits must be pushed BEFORE the speed (set_slow_speed clamps into the band)
order = list(board.settings[1])
assert order.index("set_slow_limits") < order.index("set_slow_speed"), order
print("connect + envelope push OK; push order:", order)

assert g["preflight"](verbose=False) is True
keypad.queue = ["PUMP 1 POWER ON", "PUMP 1 SPEED 45", "PUMP 2 LIMIT MAX", "junk"]

def run_start(**kw):
    t = threading.Thread(target=g["start"], kwargs=kw, daemon=True)
    t.start(); return t

t = run_start(duration_min=None, fps=30, poll_s=0.01, state_s=0.05)
time.sleep(0.5)
assert g["RUNNING"], "loop did not start"
assert board._st[1]["mode"] == "fast", board._st[1]
assert board._st[1]["percent"] == 45
assert g["exp"].keypress.rows[0]["verb"] == "POWER"
## The LED mirror is GONE from the live loop (Yatharth, 26 Aug): while start()
## owns the terminal nothing can drive the pumps through the REPL, so the keypad
## is the only source of change and it already knows what it sent. Mirroring was
## reflecting the keypad's own commands back at it, at the cost of a round trip
## on a second board.
assert keypad.synced == 0, \
        "the live loop is still mirroring state to the keypad (%d syncs)" % keypad.synced
print("live loop applied keypad commands OK; 0 mirrors, as intended")

# ---------------------------------------------------------------- break it
# Every board call from here BLOCKS for 0.2 s and then fails. The old code called
# relink() from _frame(), so this is where the process stopped.
board.break_after = board.calls
board.block_s = 0.2
deadline = time.time() + 20
while LINK.status() != "down" and time.time() < deadline:
    time.sleep(0.1)
assert LINK.status() == "down", "link never reached a terminal state: " + LINK.summary()
assert board.relinks <= sup_mod.MAX_REPAIR_ATTEMPTS, \
        "unbounded retry: %d attempts" % board.relinks
t.join(timeout=10)
assert not t.is_alive(), "start() HUNG on a dead link -- the original bug"
assert not g["RUNNING"]
print("link death handled OK: %d repair attempts, then DOWN, loop exited cleanly"
      % board.relinks)
print("  ", LINK.summary())

# incidents are bounded, and exp.logs is not O(n^2)
assert len(LINK.incidents()) <= sup_mod.INCIDENTS_MAX
assert len(g["exp"].logs["link_incidents"]) <= 200
print("incidents bounded OK: %d kept" % len(LINK.incidents()))

# ---------------------------------------------------------------- recover
board.heal_after = board.relinks + 1
g["resume"]()
deadline = time.time() + 10
while LINK.status() != "up" and time.time() < deadline:
    time.sleep(0.1)
assert LINK.status() == "up", "resume() did not recover: " + LINK.summary()
board.break_after = None; board.block_s = 0.0
print("resume() recovered OK:", LINK.summary())

# ---------------------------------------------------------------- leak test
t = run_start(fps=60, poll_s=0.001, state_s=0.01)
time.sleep(0.5)
gc.collect(); tracemalloc.start()
s0 = tracemalloc.take_snapshot(); n0 = len(gc.get_objects())
c0 = board.calls
SECONDS = 12
for i in range(SECONDS * 20):
    keypad.queue.append("PUMP %d SPEED %d" % (1 + i % 3, 10 + i % 80))
    time.sleep(0.05)
s1 = tracemalloc.take_snapshot()
grown = sum(x.size_diff for x in s1.compare_to(s0, "filename"))
objs = len(gc.get_objects()) - n0
tracemalloc.stop()
rate = (board.calls - c0) / float(SECONDS)
print("after %ds hot loop: heap %+d B, %+d live objects, %.0f round trips/s"
      % (SECONDS, grown, objs, rate))
assert grown < 2_000_000, "heap grew %d B in %ds" % (grown, SECONDS)
assert objs < 5000, "%d objects leaked" % objs

# ---------------------------------------------------------------- THE REAL ONE
# The experiment records show the board call BLOCKS rather than raising: zero
# ERROR records in any logs.yaml, including a run that sat frozen for 22 hours.
# So exception handling is irrelevant -- what matters is that a render loop can
# still draw, and still quit, while a call is stuck in a read that never returns.
g["RUNNING"] = False
time.sleep(0.3)
board.break_after = None; board.block_s = 0.0
LINK.resume()
time.sleep(0.5)

frames = [0]
_real_frame = g["BOARD"].frame
def counting_frame(*a, **k):
    frames[0] += 1
    return _real_frame(*a, **k)
g["BOARD"].frame = counting_frame

class Wedged:
    """A pumpset whose calls never return and never raise. The real failure."""
    def __init__(self): self.entered = threading.Event()
    def numbers(self): return [1,2,3]
    def state(self): self.entered.set(); time.sleep(600)
    def command(self, line): self.entered.set(); time.sleep(600)
    def stop_all(self): time.sleep(600)

# stall one call in a background thread, holding the supervisor's lock
wedged = Wedged()
LINK._ps = wedged
threading.Thread(target=lambda: LINK.call("state", wedged.state), daemon=True).start()
assert wedged.entered.wait(3), "the wedged call never started"
time.sleep(0.5)

t = run_start(fps=20, poll_s=0.05, state_s=0.2)
time.sleep(sup_mod.LOCK_WAIT_S + 3)
assert g["RUNNING"], "the loop died instead of drawing a stale frame"
assert frames[0] > 3, "the loop stopped rendering behind the stuck call (%d frames)" % frames[0]
assert LINK.blocked_s() > 2, "a stuck call was not visible: %s" % LINK.health()
assert "BLOCKED" in LINK.summary(), LINK.summary()
print("stuck read: loop still rendering (%d frames), and it SAYS SO:" % frames[0])
print("   ", LINK.summary())

# and it must still be quittable
g["RUNNING"] = False
LINK._status = "down"
t.join(timeout=15)
assert not t.is_alive(), "start() could not exit while a call was stuck -- THE ORIGINAL BUG"
print("loop exited cleanly with a board call still wedged")

# the port timeout is the actual fix -- assert it gets armed
class FakeSerial:
    def __init__(self):
        self.timeout = None          # pyserial's default: block forever
        self.write_timeout = None
ser = FakeSerial()
class FakeDev:
    class device: pass
FakeDev.device.serial = ser
import actuators.pumps.remote as _r
_r.pump_device = lambda name="pumpset": FakeDev()
sup2 = sup_mod.LinkSupervisor(board)
assert sup2.arm_serial_timeout() is True
assert ser.timeout == sup_mod.SERIAL_TIMEOUT_S, ser.timeout
assert ser.write_timeout == sup_mod.SERIAL_WRITE_TIMEOUT_S, ser.write_timeout
print("serial timeouts armed at connect: read %.1fs / write %.1fs "
      "(pyserial default is None = forever, which is what froze it)"
      % (ser.timeout, ser.write_timeout))

# and if there is no port to arm, that must be LOUD, not silent
_r.pump_device = lambda name="pumpset": None
assert sup_mod.LinkSupervisor(board).arm_serial_timeout() is False
print("unarmable port reports False rather than pretending")

g["shutdown"]()
import _thread
threading.Thread(target=lambda: None).start()
# stop the loop
g["RUNNING"] = False
print("\nALL HOST TESTS PASSED")
os._exit(0)
