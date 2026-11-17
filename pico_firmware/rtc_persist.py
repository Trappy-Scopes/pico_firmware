"""
rtc_persist - keep the RP2040 RTC across a watchdog reset.

A machine.WDT timeout resets the RESETS block, which resets the RTC peripheral,
so the clock falls back to 2021-01-01. The watchdog block itself is NOT reset by
a watchdog event, so WATCHDOG_SCRATCH0..7 survive it. Snapshot the time there
once a second, restore it on boot.

Costs up to ~1 s of accuracy per reset, and the error accumulates. This is a
bridge until a real sync (NTP / PCF85063), not a replacement for one.

Scratch registers survive: watchdog reset, soft reset.
Scratch registers are cleared by: power-on, RUN pin.

SCRATCH4..7 are reserved by the pico-sdk / bootrom reboot path. We use 0 and 1.

Offsets verified against pico-sdk hardware/regs/watchdog.h:
    CTRL 0x00   LOAD 0x04   REASON 0x08   SCRATCH0..7 0x0c..0x28   TICK 0x2c
"""

from machine import RTC, mem32
import time

WATCHDOG_BASE = 0x40058000          # RP2040. RP2350 is 0x400d8000.
SCRATCH0 = WATCHDOG_BASE + 0x0C     # magic marker
SCRATCH1 = WATCHDOG_BASE + 0x10     # epoch seconds

MAGIC = 0x7AC10C4B                  # "is there a real time in SCRATCH1?"

rtc = RTC()


def save():
    """Snapshot the current RTC into the scratch registers. Call ~1 Hz."""
    y, m, d, wd, hh, mm, ss, us = rtc.datetime()
    secs = time.mktime((y, m, d, hh, mm, ss, 0, 0))
    mem32[SCRATCH1] = secs
    mem32[SCRATCH0] = MAGIC          # magic written last, so it is never
    return secs                      # set while SCRATCH1 is stale


def has_checkpoint():
    return mem32[SCRATCH0] == MAGIC


def restore():
    """Set the RTC from the scratch registers. Returns the tuple, or None."""
    if not has_checkpoint():
        return None
    secs = mem32[SCRATCH1]
    if secs <= 0:
        return None
    y, m, d, hh, mm, ss, wd, yd = time.localtime(secs)
    rtc.datetime((y, m, d, wd, hh, mm, ss, 0))
    return rtc.datetime()


def clear():
    mem32[SCRATCH0] = 0
    mem32[SCRATCH1] = 0
