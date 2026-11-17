"""DEAD. Do not restore a module here.

The Experiment double now lives at fake/expframework/experiment.py, mirroring the
real module path (`from expframework.experiment import Experiment`).

It used to live here, at fake/experiment.py -- which happened to match a WRONG
import in keypad_pump_control.py (`from experiment import Experiment`). The test
suite therefore passed while the script failed on the rig with
ModuleNotFoundError: No module named 'experiment'. A test double named after the
bug validates the bug.

This file raises so that mistake cannot be made again quietly.
"""

raise ImportError(
    "There is no top-level 'experiment' module in trappyscopes. "
    "Use `from expframework.experiment import Experiment`. "
    "See fake/experiment.py for why this file exists.")
