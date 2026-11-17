from machine import RTC
import os


class Logger:
    """File logger that can never take the device down.

    Two rules, both learned the hard way on 2026-08-25 when the flash filled
    and OSError 28 (ENOSPC) was raised from this module's class body, killing
    the import and with it main.py and the light cycle:

      1. Logging is a diagnostic. If it cannot write, it degrades to printing
         and sets Logger.fs_full. It never raises to the caller.
      2. Every file is capped. Writing stops at MAX_KB rather than consuming
         the last block on the device.

    No rotation, deliberately: when a log fills you collect it and clear it.
    Rotation would quietly discard the oldest records and remove the reason to
    go and fetch them.
    """

    channels = ["out", "in", "err", "dtsync"]

    MAX_KB = 64                # per file; the whole device is only 848 KB

    log = str()
    rtc = RTC()
    files = {key: None for key in channels}
    sizes = {key: 0 for key in channels}
    debug = True
    fs_full = False
    dropped = 0
    lcd_ = None
    __lcd_i__ = 1

    for file in channels:
        name = f"{file}.txt"
        try:
            if name not in os.listdir():
                with open(name, "w") as f:
                    pass
            sizes[file] = os.stat(name)[6]
            files[file] = open(name, "a")
            files[file].write(f"{file}\n")
            files[file].flush()
            sizes[file] += len(file) + 1
        except OSError as e:
            # ENOSPC, a read-only mount, a corrupt filesystem - any of them.
            # Carry on with this channel disabled rather than failing import.
            files[file] = None
            fs_full = True
            print("Logger: cannot open", name, "-", e)

    def write(key, log):
        Logger.log = f"{key}, {Logger.rtc.datetime()}, {log}\n"

        if Logger.debug:
            print(Logger.log)

        fh = Logger.files.get(key)
        if fh is None:
            Logger.dropped += 1
            return False

        if Logger.sizes[key] >= Logger.MAX_KB * 1024:
            if not Logger.fs_full:
                Logger.fs_full = True
                print("Logger:", key, "at cap", Logger.MAX_KB,
                      "KB - COLLECT LOGS")
            Logger.dropped += 1
            return False

        try:
            fh.write(Logger.log)
            fh.flush()
            Logger.sizes[key] += len(Logger.log)
            return True
        except OSError as e:
            # Disk full mid-run. Close the handle, stop trying, keep printing.
            Logger.fs_full = True
            Logger.dropped += 1
            try:
                fh.close()
            except OSError:
                pass
            Logger.files[key] = None
            print("Logger: write failed on", key, "-", e)
            return False

    def status():
        """Cheap health line for the circuit's status display."""
        return {
            "fs_full": Logger.fs_full,
            "dropped": Logger.dropped,
            "sizes_kb": {k: v // 1024 for k, v in Logger.sizes.items()},
        }

    def reopen():
        """Retry the channels that are shut, after clearing space by hand."""
        for key in Logger.channels:
            if Logger.files[key] is not None:
                continue
            name = f"{key}.txt"
            try:
                Logger.files[key] = open(name, "a")
                Logger.sizes[key] = os.stat(name)[6]
            except OSError as e:
                print("Logger: reopen failed on", key, "-", e)
        Logger.fs_full = any(f is None for f in Logger.files.values())
        return not Logger.fs_full

    def lcd(text):
        if Logger.lcd_:
            slot = Logger.lcd_.top if Logger.__lcd_i__ % 3 == 1 else Logger.lcd_.middle
            slot(f"{Logger.__lcd_i__}. {text}")
            Logger.__lcd_i__ += 1
