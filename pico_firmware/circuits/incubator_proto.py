# LCD-Vcc is connected to the USB bus - 5V.
 # LCD-GND is connected to GND pin B8.

### Pin assignments
pins = {
        "buzzer" : 2,
        "lcd" : {"din":  11, "clk":10, "cs":9, "dc":12, "rst":13},
        "lm1" : 0,    						## DC connections need to be aditionally grounded to the board -> DC1- to LM1-GND.
        "rtc" : {"scl":17, "sda":16}}


## Boot record --------------------------------------------------------------
## Recover the clock BEFORE the first log line, so the BOOT record is dated.

import machine
import pico_firmware.rtc_persist as rtc_persist
from pico_firmware._logger import Logger as Log

reset_cause = machine.reset_cause()

CAUSE_NAMES = {}
for _name in ("PWRON_RESET", "HARD_RESET", "WDT_RESET", "DEEPSLEEP_RESET", "SOFT_RESET"):
    _val = getattr(machine, _name, None)
    if _val is not None:
        CAUSE_NAMES[_val] = _name.replace("_RESET", "")

cause_name = CAUSE_NAMES.get(reset_cause, str(reset_cause))
banner = ""

if reset_cause == getattr(machine, "WDT_RESET", -1):
    banner = "  *** AUTO-RESET (WDT) ***"
    recovered = rtc_persist.restore()
    if recovered:
        banner += f" clock restored: {recovered}"
    else:
        banner += " clock NOT restored - no checkpoint"

Log.write("out", f"BOOT reset_cause={reset_cause} ({cause_name}){banner}")


## Watchdog -----------------------------------------------------------------
## Armed FIRST, before anything that sleeps.
##
## An RP2040 watchdog survives the reset it causes, so every boot after a WDT
## fire starts with the deadline already running. Arming this at the bottom of
## the file meant beacon.pulse(3) + the init transition's pulse(5) - 4 s of
## blocking sleep - had to fit inside the window before the first feed. Overrun
## once and the board boot-loops with USB never staying up long enough to
## connect. Feeder first, then everything else runs under a fed watchdog.
##
## 8 s, near the RP2040 maximum (~8.39 s). The feeder is a soft timer, so it
## stops exactly when the scheduler dies - which is the failure we are catching.
## The feeder also checkpoints the clock, so the RTC comes back after a fire.
##
## NOTE: once armed the WDT cannot be switched off. To recover a looping board,
## PULL THE USB - a power-on clears the watchdog, a reset does not.

from machine import Timer
import time

## <<<< SET THIS TO False TO DISABLE THE WATCHDOG >>>>
WDT_ENABLE = False
WDT_MS = 8000

wdt = None
wdt_timer = Timer()

def wdt_feed(timer):
    if wdt is not None:
        try:
            wdt.feed()
        except BaseException:
            pass
    try:
        rtc_persist.save()
    except BaseException:
        pass

if WDT_ENABLE:
    wdt = machine.WDT(timeout=WDT_MS)
    wdt_timer.init(mode=Timer.PERIODIC, period=1000, callback=wdt_feed)
    Log.write("out", f"WDT armed {WDT_MS} ms, fed 1 Hz, clock checkpointed 1 Hz")
else:
    wdt_timer.init(mode=Timer.PERIODIC, period=1000, callback=wdt_feed)
    Log.write("out", "WDT DISABLED (WDT_ENABLE=False); clock still checkpointed 1 Hz")


from pico_firmware.actuators.dumbbeacon import DumbBeacon as Beacon
beacon = Beacon(pins["buzzer"])
beacon.pulse(3)
buzzer = beacon
status = beacon.devicestatus


## Define light resources ---------------------------------------------------

#from pico_firmware.peripherals.lcd import LCD_0inch96
#lcd = LCD_0inch96(pins["lcd"])
#lcd.intro_seq()


## Define two light matrices
from pico_firmware.actuators.lightmatrix import LightMatrix
lm1 = LightMatrix(pins["lm1"], size=[11,12])

## Define circadian cycler
from pico_firmware.controllers.circadian_cycle_controller import CircadianScheduler
if banner:
    CircadianScheduler.boot_tag = "   [AUTO-RESET]"

cs1 = CircadianScheduler(lm1, buzzer=beacon, day_start=[8,0], night_start=[20,0])
cs1.set_timers(mode="short")

## Both of them need to be turned on -----------------------------------------


## Heartbeat ----------------------------------------------------------------
## One line to out.txt every 10 minutes, so a dead board can be dated
## afterwards. uptime_ms is monotonic and survives the RTC resetting.

import os

HB_PERIOD_MS     = 10 * 60 * 1000
HB_BYTES         = 70                 # measured length of one HB record
HB_PER_DAY       = 86400000 // HB_PERIOD_MS
HB_BYTES_PER_DAY = HB_BYTES * HB_PER_DAY

## statvfs is not usable here: littlefs computes free blocks as
## f_blocks - lfs_fs_size(), and lfs_fs_size() counts metadata pairs more than
## once, so on 2026-08-24 it returned f_bfree = -52 out of 212 blocks while a
## file walk showed 314 KB used of 848 KB. Watch the one file that actually
## grows instead.

LOG_FILE     = "out.txt"
LOG_WARN_KB  = 150      # start warning on the status line
LOG_STOP_KB  = 300      # stop heartbeating; transitions keep logging

## OFF as of 2026-08-28. The heartbeat was added to catch the missed
## transition; the scheduler is now level-triggered, so it no longer
## earns the flash it costs. fs_update() still runs every HB_PERIOD_MS
## and keeps the 30 s status line, it just does not write a record.
## Set back to True when you next need uptime evidence.
hb_enabled = False

def log_size_kb():
    """Size of out.txt in KB, or None if it cannot be read."""
    try:
        return os.stat(LOG_FILE)[6] // 1024
    except OSError:
        try:
            return os.stat("/" + LOG_FILE)[6] // 1024
        except OSError:
            return None

def fs_update():
    """Refresh the cached log size and the 30 s status field.

    A reading we cannot trust must NEVER switch the heartbeat off - the
    heartbeat is the instrument, and losing it is worse than a big log file.
    """
    global hb_enabled
    kb = log_size_kb()

    if kb is None:
        CircadianScheduler.fs_tag = " | log: ?"
        return None, None

    days = (LOG_STOP_KB - kb) * 1024 // HB_BYTES_PER_DAY
    if kb >= LOG_STOP_KB:
        if hb_enabled:
            hb_enabled = False
            Log.write("out", "LOG %s KB - HEARTBEAT OFF, COLLECT LOGS" % kb)
        CircadianScheduler.fs_tag = " | log: %s KB - HB OFF, COLLECT LOGS" % kb
    elif kb >= LOG_WARN_KB:
        CircadianScheduler.fs_tag = " | log: %s KB (%s d) LOW" % (kb, days)
    else:
        CircadianScheduler.fs_tag = " | log: %s KB (%s d)" % (kb, days)
    return kb, days

hb_timer = Timer()

def heartbeat(timer):
    try:
        free, days = fs_update()
        if hb_enabled:
            up = time.ticks_ms()
            ph = getattr(cs1, "phase", "?")
            kb = "?" if free is None else free
            Log.write("out", "HB uptime_ms=%s phase=%s fs_kb=%s" % (up, ph, kb))
    except BaseException:
        pass

hb_timer.init(mode=Timer.PERIODIC, period=HB_PERIOD_MS, callback=heartbeat)

## Boot reading, so it is visible the moment you connect. The raw tuple goes
## in too - a negative free-space figure on 2026-08-24 came from trusting the
## derived number without ever having seen what statvfs actually returns.
_st = os.statvfs("/")
Log.write("out", "FS statvfs=%s  (f_bfree is unreliable on littlefs)" % (_st,))
_kb, _days = fs_update()
if _kb is None:
    Log.write("out", "LOG size unknown - heartbeat left ON")
else:
    Log.write("out", "LOG %s KB of %s KB cap, HB room ~%s days at %s min"
                     % (_kb, LOG_STOP_KB, _days, HB_PERIOD_MS // 60000))
    if _kb >= LOG_WARN_KB:
        beacon.pulse(2)


## Init extra rtc
from machine import RTC
#rtc2 = RTC_PCF85063TP(scl=pins["rtc"]["scl"], sda=pins["rtc"]["sda"])
#global rtc
#rtc = RTC()
#def rtc2_write():
#    now = rtc.datetime()
#    rtc2.write(now)
#    print(f"Updated RTC2: {now}")


"""
To be added later.
lcd.rect(0,0, 80,50, lcd.RED, True)
lcd.update()
lcd.display()
lcd.rect(0,0, 50,80, lcd.RED, True)
lcd.display()
lcd.update()
lcd.rect(50,0, 50,80, lcd.GREEN, True)
lcd.display()
lcd.rect(100,0, 50,80, lcd.WHITE, True)
lcd.display()
"""
