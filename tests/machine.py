"""Minimal stub of MicroPython's machine module for host-side testing."""
class Pin:
    OUT = 1
    def __init__(self, n, mode=None, value=None): self.n=n; self.v=value
    def __call__(self, v=None):
        if v is None: return self.v
        self.v=v

class I2C:
    def __init__(self, *a, **k): self.buttons = 0xFFFF  # active low: no press
    def writeto(self, addr, data): pass
    def readfrom(self, addr, n): return bytes([self.buttons & 0xFF, self.buttons >> 8])
    def readfrom_into(self, addr, buf):
        buf[0] = self.buttons & 0xFF; buf[1] = (self.buttons >> 8) & 0xFF

class SPI:
    def __init__(self, *a, **k): self.writes = 0
    def write(self, buf): self.writes += 1

class Timer:
    PERIODIC = 1
    instances = []
    def __init__(self, id=-1): self.cb=None; self.alive=True; Timer.instances.append(self)
    def init(self, period=None, mode=None, callback=None): self.cb=callback; self.period=period
    def deinit(self): self.alive=False; self.cb=None
