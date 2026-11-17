"""MicroPython-flavoured time shim: adds ticks_ms/ticks_diff/ticks_add."""
import time as _t
_MASK = (1 << 30) - 1
_now = [0]
def set_ms(v): _now[0] = v & _MASK
def advance(ms): _now[0] = (_now[0] + ms) & _MASK
def ticks_ms(): return _now[0]
def ticks_add(t, d): return (t + d) & _MASK
def ticks_diff(a, b):
    d = (a - b) & _MASK
    if d > (1 << 29): d -= (1 << 30)
    return d
sleep = _t.sleep
