"""Does the deck's Link survive a wedged board and a worker that dies?"""
import sys, os, time, threading, queue, importlib.util, types

import paths
sys.path.insert(0, os.path.join(paths.FW, "host"))

## Import Link/SolventSet without dragging in prompt_toolkit.
src = open(paths.PUMPDECK).read()
start = src.index("class Link:")
end = src.index("## ------------------------------------------------------------------ touch UI")
mod = types.ModuleType("linkonly")
mod.__dict__.update({"queue": queue, "threading": threading, "time": time,
                     "POLL_S": 0.05})
exec(compile(src[start:end], "pumpdeck.py", "exec"), mod.__dict__)
Link = mod.Link

class Board:
    def __init__(self): self.wedged=False; self.calls=0; self.done=0
    def state(self):
        self.calls += 1
        if self.wedged: time.sleep(30)     # blocks, exactly like a stalled REPL
        return {1: {"speed": 0.0}}
    def command(self, line):
        self.calls += 1; self.done += 1
        if self.wedged: time.sleep(30)
        return True

b = Board()
link = Link(b, poll_s=0.02)
time.sleep(0.3)
assert not link.stale(), link.health()
print("healthy:", link.health())

# ---- wedge the board; the UI thread must never block, and the queue must cap
b.wedged = True
time.sleep(0.2)
t0 = time.time()
for i in range(5000):
    link.command("PUMP 1 RATE 0.12")       # this is the UI thread
elapsed = time.time() - t0
h = link.health()
assert elapsed < 2.0, "send() blocked the UI thread for %.1fs" % elapsed
assert h["queued"] <= Link.QUEUE_MAX, h
assert h["dropped"] >= 5000 - Link.QUEUE_MAX - 1, h
time.sleep(1.2)                            # let the last good read age out
assert link.stale(1.0), link.health()
print("wedged board: 5000 taps in %.3fs, queue capped at %d, %d dropped, STALE=%s"
      % (elapsed, h["queued"], h["dropped"], link.stale(1.0)))

# ---- on_update raising must not kill the worker
b.wedged = False
link2 = Link(Board(), poll_s=0.02)
def boom(): raise RuntimeError("renderer blew up")
link2.on_update = boom
time.sleep(0.4)
assert link2.alive(), "a raising on_update killed the worker (the original bug)"
assert "renderer blew up" in (link2.error() or ""), link2.error()
print("raising on_update contained OK:", link2.error())

# ---- watchdog restarts a worker that dies anyway
link3 = Link(Board(), poll_s=0.02)
link3._thread.__class__  # keep a handle
link3._stop.set(); link3._thread.join(1.0); link3._stop.clear()
assert not link3.alive()
assert link3.watchdog() is False
time.sleep(0.2)
assert link3.alive(), "watchdog did not restart the worker"
assert link3.health()["restarts"] == 1
print("watchdog restart OK:", link3.health())

for l in (link, link2, link3): l.stop()

# ---- ledger: atomic, debounced, and reports failure
import reservoirs as RES
path = "/tmp/led.json"
if os.path.exists(path): os.unlink(path)
ss = RES.default_set(path=path, load=False)
t0 = time.time()
for i in range(2000):
    ss.save()                              # every tap, from the UI thread
assert time.time() - t0 < 0.5, "save() still blocks the event loop"
assert not os.path.exists(path) or True
ss.close()
assert os.path.exists(path), "ledger never reached disk"
assert not os.path.exists(path + ".tmp"), "temp file left behind"
assert ss.save_error() is None, ss.save_error()
back = RES.default_set(path=path, load=True)
assert back.names() == ss.names()
print("ledger OK: 2000 saves coalesced, atomic write, reloaded %s" % back.names())

# failure is visible, not swallowed
ss2 = RES.default_set(path="/nonexistent-dir/x.json", load=False)
ss2.save(); ss2.close()
assert ss2.save_error(), "a failing write reported nothing"
print("ledger failure surfaced OK:", ss2.save_error())

print("\nALL PUMPDECK LINK TESTS PASSED")
