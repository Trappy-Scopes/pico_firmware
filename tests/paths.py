"""Where the real files live, resolved from this test directory.

tests/ sits in Trappy-Scopes/pico_firmware/; the host package lives in
~/trappyscopes. Keep every path in one place so the suite survives a move.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FW   = os.path.dirname(HERE)                       ## .../pico_firmware
HOST = os.path.expanduser("~/trappyscopes")
if not os.path.isdir(HOST):
    ## the Cowork bridge mounts the folders side by side rather than in $HOME
    HOST = os.path.normpath(os.path.join(FW, "..", "..", "trappyscopes"))

KEYPAD_NEW = os.path.join(FW, "pico_firmware", "circuits",
                          "pimoroni_rgb_sparkly_rainbows_cntlr.py")
KEYPAD_OLD = os.path.join(FW, "_backup_20260814", "circuits",
                          "pimoroni_rgb_sparkly_rainbows_cntlr.py")
PUMPDECK   = os.path.join(FW, "host", "pumpdeck.py")
RESERVOIRS = os.path.join(FW, "host", "reservoirs.py")
CONTROL    = os.path.join(HOST, "scripts", "chambertests", "keypad_pump_control.py")
LIVETRACK  = os.path.join(HOST, "scripts", "celltracking", "livetrack.py")
