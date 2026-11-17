"""Minimal `machine` stub so firmware modules import under CPython."""


class RTC:
    def datetime(self, t=None):
        return (2026, 8, 25, 1, 10, 0, 0, 0)


class Pin:
    OUT = 1
    IN = 0

    def __init__(self, n, mode=None):
        self.n, self._v = n, 0

    def value(self, v=None):
        if v is None:
            return self._v
        self._v = int(bool(v))

    def init(self, *a, **k):
        pass


class Timer:
    PERIODIC = 1
    ONE_SHOT = 0

    def __init__(self, *a, **k):
        self.cb = None

    def init(self, mode=None, period=None, callback=None):
        self.cb = callback

    def deinit(self):
        self.cb = None

    def tick(self):
        if self.cb:
            self.cb(self)


class WDT:
    def __init__(self, timeout=0):
        self.timeout, self.feeds = timeout, 0

    def feed(self):
        self.feeds += 1


def reset_cause():
    return 1


mem32 = {}
