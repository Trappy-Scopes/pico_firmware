import sys, os, gc, tracemalloc
sys.path.insert(0, os.path.dirname(__file__))
import mptime as mtime
sys.modules["time"] = mtime
import machine

def run(src, label, ticks=200_000):
    machine.Timer.instances.clear()
    mtime.set_ms(0)
    g = {"__name__": "circuit"}
    exec(compile(open(src).read(), src, "exec"), g)
    kp = g["kp"]; t = machine.Timer.instances[-1]
    for _ in range(200):                      # get past any boot animation
        mtime.advance(8); t.cb(t)
    spi = kp._kp._spi; spi.writes = 0
    gc.collect(); tracemalloc.start()
    s0 = tracemalloc.take_snapshot()
    n0 = len(gc.get_objects())
    for _ in range(ticks):
        mtime.advance(8); t.cb(t)
    s1 = tracemalloc.take_snapshot()
    grown = sum(x.size_diff for x in s1.compare_to(s0, "filename"))
    tracemalloc.stop()
    print("%-14s %8d SPI writes  %+9d B heap  %+7d live objects  %d errors"
          % (label, spi.writes, grown, len(gc.get_objects()) - n0,
             kp.service_errors()))
    return spi.writes

import paths
OLD = paths.KEYPAD_OLD
NEW = paths.KEYPAD_NEW
print("idle, 200k timer ticks = 8 ms x 200k = ~27 minutes\n")
o = run(OLD, "old (913 L)")
n = run(NEW, "new (531 L)")
print("\nSPI/LED bus traffic: %.0fx less" % (o / max(n, 1)))
