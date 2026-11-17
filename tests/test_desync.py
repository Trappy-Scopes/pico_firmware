"""The 19-23 Aug failure, reproduced: a desynchronised raw REPL.

pyboard raises PyboardError("could not enter raw repl") from exec_raw_no_follow's
opening `read_until(1, b">")` -- a prompt check run before EVERY command. Once
the stream is off by one reply that check fails forever. This models a fake
pyboard with a byte stream and asserts the supervisor's repair actually
resynchronises it -- WITHOUT soft-resetting the board.
"""
import os, sys, time, threading
import paths
import paths
## Repo first, fake LAST -- insert(0) means the last insert wins, and the
## stubbed hive/expframework must shadow the real ones (which need rich,
## a camera stack, and a scope).
sys.path.insert(0, paths.HOST)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake"))

from hive.assembly import ScopeAssembly
import actuators.pumps.supervisor as sup_mod
import actuators.pumps.remote as remote

class PyboardError(Exception): pass

class FakeSerial:
    """A byte stream that can be left with stale data in it."""
    def __init__(self): self.buf = b""; self.timeout=None; self.write_timeout=None
    def inWaiting(self): return len(self.buf)
    def read(self, n):
        out, self.buf = self.buf[:n], self.buf[n:]
        return out
    def write(self, data): pass

class FakePyboard:
    """Models the prompt check that actually fails on the rig."""
    def __init__(self):
        self.serial = FakeSerial()
        self.synced = True
        self.soft_resets = 0
        self.reboots_would_have_stopped_pumps = 0
    def _prompt_check(self):
        if not self.synced:
            raise PyboardError("could not enter raw repl")
    def exec(self, cmd):
        self._prompt_check()
        return b"{1: {'speed': 0.0}}"
    def exit_raw_repl(self):
        self.serial.buf += b"\r\nMicroPython v1.22\r\n>>> "   # friendly-REPL banner
    def enter_raw_repl(self, soft_reset=True):
        if soft_reset:
            self.soft_resets += 1
            self.reboots_would_have_stopped_pumps += 1
            ## a soft reset re-runs main.py; the circuit rebuild floods the port
            self.serial.buf += b"MPY: soft reboot\r\n" + b"circuit banner\r\n" * 50
            raise PyboardError("could not enter raw repl")   # what the rig logs
        ## resync only works if the caller cleared the backlog first
        if self.serial.inWaiting():
            raise PyboardError("could not enter raw repl")
        self.synced = True

board = FakePyboard()

class Dev:
    def __init__(self): self.device = board
    def __call__(self, cmd):
        board._prompt_check()
        return 2 if cmd == "1+1" else None

dev = Dev()
remote.pump_device = lambda name="pumpset": dev

class PS:
    def numbers(self): return [1,2,3]
    def state(self): return {1: {"speed": 0.0}} if _ok() else _boom()
    def command(self, line): return True if _ok() else _boom()
    def stop_all(self): return True
def _ok(): return board.synced
def _boom(): raise PyboardError("could not enter raw repl")

sup_mod.BACKOFF_S = (0.05,)*5
sup = sup_mod.LinkSupervisor(PS()).start()
assert sup.arm_serial_timeout() is True
assert board.serial.timeout == sup_mod.SERIAL_TIMEOUT_S
print("port armed: read %.1fs / write %.1fs" % (board.serial.timeout, board.serial.write_timeout))
assert sup.state() == {1: {"speed": 0.0}}
print("healthy:", sup.summary())

# ---- desynchronise, exactly as the rig does, and leave junk in the stream
board.synced = False
board.serial.buf = b"garbage from a late reply\r\n" * 20
print("desynced; %d stale bytes queued" % board.serial.inWaiting())

## Drive the loop the way start() does. The link must fail, be noticed, be
## repaired, and come back -- all without anyone touching the board by hand.
deadline = time.time() + 20
failed = False
while time.time() < deadline:
    sup.state()
    if sup.status() != "up":
        failed = True
    elif failed:
        break                      # went down, came back
    time.sleep(0.05)

assert failed, "the supervisor never even noticed the desync"
assert sup.status() == "up", "repair never resynchronised the link: " + sup.summary()
assert board.soft_resets == 0, \
        "repair soft-reset the board %d time(s) -- that reboots the pumps" % board.soft_resets
assert board.serial.inWaiting() == 0, "stale bytes left in the stream"
print("recovered without rebooting the board:", sup.summary())
print("   soft resets: %d   (the 19-23 Aug code did one per attempt, 5 per incident)"
      % board.soft_resets)

# ---- a repair in progress must not be reported as a stuck call
# The lock must be held by ANOTHER thread: RLock is reentrant, so a same-thread
# acquire would just succeed and prove nothing.
def hold(sup, holder, seconds=3.0):
    started = threading.Event()
    def run():
        with sup._lock:
            sup._holder = holder
            started.set()
            time.sleep(seconds)
        sup._holder = None
    t = threading.Thread(target=run, daemon=True); t.start()
    started.wait(2)
    return t

sup_mod.LOCK_WAIT_S = 0.2          # keep the test quick

sup2 = sup_mod.LinkSupervisor(PS())
hold(sup2, ("repair", time.monotonic() - 3))
ok, _ = sup2.call("state", lambda: None)
assert ok is False, "call succeeded while the lock was held elsewhere"
assert "in flight" not in (sup2._last_error or ""), \
        "a repair was reported as a stuck call: " + sup2._last_error
assert sup2.status() != "repairing", \
        "an ordinary repair escalated the status"
print("repair-in-progress is not mislabelled as a stuck call")

# ---- a genuinely stuck CALL still is an error
sup3 = sup_mod.LinkSupervisor(PS())
hold(sup3, ("call:state", time.monotonic() - 30))
sup3.call("state", lambda: None)
assert "in flight" in sup3._last_error, sup3._last_error
print("a stuck call still reports as one:", sup3._last_error)

# ---- skip logging is rate limited
import logging
sup4 = sup_mod.LinkSupervisor(PS())
sup4._holder = ("repair", time.monotonic())
recs = []
class H(logging.Handler):
    def emit(self, r): recs.append(r)
h = H(); h.setLevel(logging.DEBUG)
root = logging.getLogger(); root.addHandler(h)
prev = root.level; root.setLevel(logging.DEBUG)
try:
    for _ in range(12):
        sup4._blocked("state")
finally:
    root.removeHandler(h); root.setLevel(prev)
skips = [r for r in recs if "skipped" in r.getMessage()]
assert len(skips) <= 2, "%d skip lines from 12 skips -- not rate limited" % len(skips)
print("skip logging rate limited: 12 skips -> %d log line(s) "
      "(the rig logged hundreds)" % len(skips))

sup.stop()
print("\nALL DESYNC TESTS PASSED")
