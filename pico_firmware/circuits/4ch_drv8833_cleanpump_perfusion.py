## 4ch_drv8833_cleanpump_perfusion
##
## Four peristaltic perfusion / cleaning pumps on two Adafruit DRV8833 breakouts.
## Replaces 8ch_drv6833_pumpctrl_proto.py, whose CleaningPump was a stub.
##
##   pump1, pump2  -- board1  (A and B channels)
##   pump3, pump4  -- board2  (A and B channels)
##
## Each pump has three modes, in priority order:
##
##   DEEP  : alternating 6 s forward / 2 s reverse at 3x, coasting between the
##           direction changes. Reversing the flow is what makes it a deep clean.
##           REFUSED unless bench_mode() has been called -- it will destroy a
##           microfluidic device. Tube cleaning only, with the chip disconnected.
##   FAST  : continuous forward at fast_speed.
##   PULSE : duty-cycled forward dosing at the same rate, 5 s in every 60.
##
## RATE accepts 0.0 - 1.0 with no ceiling. There is exactly one interlock on this
## board and it is on deep clean, because that is the mode that reverses.
##
## Host-facing wire protocol (the touchscreen deck speaks exactly this):
##
##   PUMP <n> POWER ON|OFF        PUMP <n> RATE <0.0-1.0>
##   PUMP <n> PULSE ON|OFF        PUMP <n> CLEAN ON|OFF
##
## Interlock:  lock_deep()   refuses deep clean (the boot state)
##             unlock_deep() permits it, chip disconnected only
##
## Runtime:
##   pump1.deep_on()  pump1.deep_on(cycles=5)  pump1.deep_off()
##   pump1.set_deep_profile(6, 2)   pump1.set_deep_mult(3.0)
##   pumpset.command("PUMP 3 CLEAN ON")   pumpset.state()   stop()
##
## NOTE: delete the hardcoded `# cid : 3` block in pico_firmware/main.py before
## using this file. That block builds motor1/motor2 on GP2/3 and GP6/7, and GP6/7
## are board1's AIN1/AIN2 here -- two PWM owners on one pin pair.

from pico_firmware.controllers.adafruit_drv8633 import DRV6833
from pico_firmware.actuators.cleaning import CleaningPump, CleaningPumpSet
from pico_firmware.actuators.peristaltic import _read_state_file
from pico_firmware.beacon import Beacon

## Adafruit DRV8833 breakout. nSLEEP is driven high by DRV6833.__init__.
## https://learn.adafruit.com/adafruit-drv8833-dc-stepper-motor-driver-breakout-board
pins = {"buzzer": 26,
		"board1": {"ain1": 6, "ain2": 7, "bin1": 9, "bin2": 8, "slp": 10},
		"board2": {"ain1": 12, "ain2": 13, "bin1": 15, "bin2": 14, "slp": 11}}

## Operating envelope -- edit here, or call the set_* functions at runtime.
##
## Plain DC peristaltic heads, no controller of their own. The working rate is low
## because that is what the rig wants, NOT because anything is clamped: RATE
## accepts the full 0.0 - 1.0 and the operator decides.
FAST_SPEED = 0.12          ## the rig's working rate
PULSE_ON_S = 5             ## seconds running per dosing cycle
PULSE_PERIOD_S = 60
PULSE_OFF_S = PULSE_PERIOD_S - PULSE_ON_S

## No stiction kick: a 0.4 burst at the top of every dosing cycle is a pressure
## transient into the chip, which is the thing that breaks. Not configured here at
## all -- the base class defaults to no kick.
##
## PWM stays at DCMotor's 10 Hz. It is what these heads have always run at on
## this rig; raising it was tried and made low-duty behaviour worse. Not a knob.

## Deep clean. DEEP_BASE is pinned rather than inherited from the speed slider,
## so the button means the same thing every time -- and it is set to 0.33 for a
## reason: 0.33 * 3 = 0.99, so the reverse stroke is a real 3x instead of being
## clipped at full duty. Raise DEEP_BASE and you lose the multiplier, not gain
## flow.
DEEP_BASE = 0.33
DEEP_MULT = 3.0
DEEP_FWD_S = 6
DEEP_REV_S = 2
DEEP_GAP_MS = 250          ## coast between direction changes -- protects the bridge
DEEP_MAX_CYCLES = 0        ## 0 = until stopped; the deck sends CLEAN OFF

## Deep clean is INTERLOCKED OFF at boot. It drives the head to 0.99 and reverses
## it, which no microfluidic device downstream will survive -- it is a
## tube-cleaning mode, to be used with the chip disconnected. The interlock is a
## state the pumps hold, so it survives a stray REPL command as well as a stray
## fingertip; bench_mode() is the only way past it.
DEEP_ALLOWED_AT_BOOT = False


## trappyscopes runs main.py on every connect, so this file is re-executed often.
## Retire the previous build's timers or two cycle machines fight over one motor.
## The PWM outputs are untouched, so a perfusion does not stutter through a
## rebuild -- and the commanded state is read back and handed to each pump.
try:
	pumpset.deinit()
except NameError:
	pass

_saved = _read_state_file()

buzzer = Beacon(pins["buzzer"])

## Boards are local names only. The motors are never bound at module level: they
## live as pump.motor, which keeps them out of Handshake.obj_list() so the host
## sees pumps rather than half-owned H-bridges and nobody can drive a motor
## behind its pump's back and desync pump.state(). Still reachable for bench
## work as pump1.motor.fwd(0.9) / pump1.motor.release().
_board1 = DRV6833(pins["board1"]["ain1"], pins["board1"]["ain2"],
					pins["board1"]["bin1"], pins["board1"]["bin2"],
					pins["board1"]["slp"])
_board2 = DRV6833(pins["board2"]["ain1"], pins["board2"]["ain2"],
					pins["board2"]["bin1"], pins["board2"]["bin2"],
					pins["board2"]["slp"])

_motors = [_board1.motors[0], _board1.motors[1],
			_board2.motors[0], _board2.motors[1]]


def _build(n, motor):
	pump = CleaningPump(motor, name="pump{}".format(n),
						fast_speed=FAST_SPEED,
						pulse_on_s=PULSE_ON_S, pulse_off_s=PULSE_OFF_S,
						deep_base=DEEP_BASE, deep_mult=DEEP_MULT,
						deep_fwd_s=DEEP_FWD_S, deep_rev_s=DEEP_REV_S,
						deep_gap_ms=DEEP_GAP_MS,
						deep_max_cycles=DEEP_MAX_CYCLES,
						restore=_saved.get(n))
	pump.set_rate(FAST_SPEED)
	pump.allow_deep(DEEP_ALLOWED_AT_BOOT)
	return pump


pump1 = _build(1, _motors[0])
pump2 = _build(2, _motors[1])
pump3 = _build(3, _motors[2])
pump4 = _build(4, _motors[3])

## The buzzer goes to the set so the host can ask for tap feedback with one call.
pumpset = CleaningPumpSet({1: pump1, 2: pump2, 3: pump3, 4: pump4},
							buzzer=buzzer)


## Host-facing helpers --------------------------------------------------------
def command(line):
	"""Apply one wire line, e.g. command("PUMP 1 CLEAN ON")."""
	return pumpset.command(line)


def commands(lines):
	"""Apply a list of wire lines."""
	return pumpset.commands(lines)


def state():
	"""State of all four pumps, keyed by pump number."""
	return pumpset.state()


def stop():
	"""Safe-state everything, deep clean included."""
	pumpset.stop_all()
	return state()


def deep(n=None, cycles=None):
	"""Deep clean one pump, or all of them when n is None."""
	if n is None:
		return pumpset.deep_all(cycles)
	pump = pumpset.get(n)
	return None if pump is None else pump.deep_on(cycles)


def deep_off(n=None):
	if n is None:
		return pumpset.deep_off_all()
	pump = pumpset.get(n)
	return None if pump is None else pump.deep_off()


def lock_deep():
	"""Refuse deep clean. The boot state -- safe with a device connected."""
	pumpset.allow_deep(False)
	return {"deep_allowed": False}


def unlock_deep():
	"""Permit deep clean. Chip disconnected only: it reverses the flow at 3x."""
	pumpset.allow_deep(True)
	return {"deep_allowed": True}


def beep(ms=35):
	"""Blip the buzzer. The deck calls this on every button tap."""
	return pumpset.beep(ms)


def set_rate(unit_speed):
	"""The working rate for ALL pumps, 0.0 - 1.0, clamped to the ceiling."""
	return pumpset.set_rate(unit_speed)


def set_pulse_duty(on_s, off_s):
	"""Pulse duty cycle in seconds for ALL pumps."""
	return pumpset.set_pulse_duty(on_s, off_s)


def set_deep_profile(fwd_s, rev_s, gap_ms=None, mult=None):
	"""Deep-clean stroke profile for ALL pumps."""
	return pumpset.set_deep_profile(fwd_s, rev_s, gap_ms, mult)


def motor(n):
	"""Escape hatch: the raw DCMotor behind pump `n`, for bench debugging.

	Anything done with it is invisible to the pump -- call pump.stop() after to
	resynchronise.
	"""
	pump = pumpset.get(n)
	return None if pump is None else pump.motor


## End -> Indicate end of circuit creation
print("4ch_drv8833_cleanpump_perfusion : pump1..pump4, pumpset ready")
print("  rate {}  duty {}s/{}s  no kick  no ceiling  pwm 10 Hz".format(
		FAST_SPEED, PULSE_ON_S, PULSE_OFF_S))
print("  deep: {}s fwd @ {} / {}s rev @ {} (x{}) gap {}ms -- INTERLOCKED {}".format(
		DEEP_FWD_S, DEEP_BASE, DEEP_REV_S,
		round(min(1.0, DEEP_BASE * DEEP_MULT), 3), DEEP_MULT, DEEP_GAP_MS,
		"OFF (bench_mode() to permit)" if not DEEP_ALLOWED_AT_BOOT else "ON"))
