## 2ch_peristat_kitroniks_vx_shield
##
## Three peristaltic pumps driven by the Pimoroni RGB keypad through the host:
##   pump1, pump2 -- Kitronik Compact Motor Driver shield (GP2/3, GP6/7)
##   pump3        -- DFRobot DFR0523, PPM on GP1, own 5-6 V supply
##
##   FAST  mode : continuous run at fast_speed (default 0.5). All pumps.
##   PULSE mode : pump1/2 -- 5 s on / 55 s off, starting at 0.083, adjustable in
##                           0.03 - 0.2.
##                pump3   -- CONTINUOUS, 0.10 - 0.30, starting at 0.15. No duty
##                           cycle. A kick at the start breaks stiction; the
##                           running speed itself stays low.
##
## Both pumps and the limits are retunable at runtime from the host:
##
##   pump1.fast_on()             pump1.toggle_pulse()
##   pump1.set_fast_speed(0.6)   pump1.set_slow_limits(0.05, 0.25)
##   pump1.set_pulse_duty(5, 55) pump1.set_percent(40)
##   pump1.state()               pumpset.state()
##
## Keypad wire lines are applied directly, so the host can forward whatever the
## keypad queued without translating anything:
##
##   pumpset.command("PUMP 1 POWER ON")
##   pumpset.commands(["PUMP 2 PULSE ON", "PUMP 2 SPEED 40"])
##
## NOTE: delete the hardcoded `# cid : 3` block in pico_firmware/main.py before
## using this file -- otherwise that block builds motor1/motor2 on these same
## pins first and this circuit re-PWMs them.

from pico_firmware.actuators.dcmotor import DCMotor
from pico_firmware.actuators.dfr0523 import DFR0523
from pico_firmware.actuators.peristaltic import PeristalticPump, PumpSet

## Kitronik Compact Motor Driver shield for Pico
## https://resources.kitronik.co.uk/pdf/5331-compact-motor-driver-raspberry-pi-pico-datasheet.pdf
## pump3 is a DFRobot DFR0523 on its own 5-6 V supply: one PPM signal pin, with
## the supply ground tied back to Pico GND.
pins = {"m1": {"fwd": 2, "rev": 3},
		"m2": {"fwd": 6, "rev": 7},
		"m3": {"ppm": 1},
		"potentiometer": 26}

## Operating envelope -- edit here for a different default, or call the
## set_* functions at runtime.
FAST_SPEED = 0.5           ## fast mode, continuous
SLOW_MIN   = 0.03          ## slowest the pulse mode may run
SLOW_MAX   = 0.2           ## fastest the pulse mode may run
PULSE_ON_S = 5             ## seconds running per cycle
PULSE_PERIOD_S = 60        ## one pulse per minute -> 5 s on / 55 s off
PULSE_OFF_S = PULSE_PERIOD_S - PULSE_ON_S
SLOW_START = 0.083         ## perfusion pulse-mode speed on a fresh boot (31% of the band).
                           ## A board with a saved pumpstate.txt restores its own speed instead.

## pump3 (DFR0523, aeration) does not pulse: its "slow mode" runs continuously.
##
## It is driven HARD, and deliberately. The DFR0523 is a slow pump by design
## (<=85 ml/min flat out), and its head needs real torque to turn against the
## tube occlusion -- at low drive the motor hums and the rotor stays put, which
## looks like a control fault but is simply not enough torque. There is no
## reason to throttle a pump whose maximum is already the rate we want.
## Halved after the pump head was replaced: the old figures were compensating
## for a damaged head that stalled, and are far too fast with a sound one.
P3_FAST_SPEED = 0.275
P3_SLOW_MIN = 0.10
P3_SLOW_MAX = 0.30
P3_SLOW_START = 0.15       ## where the continuous rate sits on boot
P3_KICK_SPEED = 0.4        ## break stiction at the start of every run
P3_KICK_MS = 500


## trappyscopes runs main.py on every connect, so this file is re-executed
## often. Two things follow, and both are handled here:
##
##   the previous build's timers are still armed -- retire them, or two pulse
##   cycles end up fighting over the same motor. The PWM outputs are untouched,
##   so the pumps keep running through the rebuild.
##
##   whatever was commanded before must come back -- so the saved state is read
##   once and handed to each pump as it is constructed.
try:
	pumpset.deinit()
except NameError:
	pass

from pico_firmware.actuators.peristaltic import _read_state_file
_saved = _read_state_file()


## Device initalization
## The motor / driver objects are deliberately NOT bound to module-level names. They
## live only as pump1.motor / pump2.motor, which keeps them out of
## Handshake.obj_list() -- the host sees pumps, not half-owned H-bridges, and
## nobody can drive a motor behind its pump's back and desync pump.state().
## They are still reachable for debugging as an attribute chain:
##     pump1.motor.fwd(0.9)      pump1.motor.release()
pump1 = PeristalticPump(DCMotor(pins["m1"]["fwd"], pins["m1"]["rev"]),
						name="pump1",
						fast_speed=FAST_SPEED,
						slow_min=SLOW_MIN, slow_max=SLOW_MAX,
						pulse_on_s=PULSE_ON_S, pulse_off_s=PULSE_OFF_S,
						slow_speed=SLOW_START,
						restore=_saved.get(1))

pump2 = PeristalticPump(DCMotor(pins["m2"]["fwd"], pins["m2"]["rev"]),
						name="pump2",
						fast_speed=FAST_SPEED,
						slow_min=SLOW_MIN, slow_max=SLOW_MAX,
						pulse_on_s=PULSE_ON_S, pulse_off_s=PULSE_OFF_S,
						slow_speed=SLOW_START,
						restore=_saved.get(2))

## pump3: DFRobot DFR0523, continuous slow mode instead of a duty cycle.
pump3 = PeristalticPump(DFR0523(pins["m3"]["ppm"]),
						name="pump3",
						fast_speed=P3_FAST_SPEED,
						slow_min=P3_SLOW_MIN, slow_max=P3_SLOW_MAX,
						continuous=True, slow_speed=P3_SLOW_START,
						restore=_saved.get(3))
pump3.set_kick(P3_KICK_SPEED, P3_KICK_MS)

pumpset = PumpSet({1: pump1, 2: pump2, 3: pump3})


## Host-facing helpers --------------------------------------------------------
def command(line):
	"""Apply one keypad wire line, e.g. command("PUMP 1 POWER ON")."""
	return pumpset.command(line)


def commands(lines):
	"""Apply a list of keypad wire lines."""
	return pumpset.commands(lines)


def state():
	"""State of both pumps, as a dict keyed by pump number."""
	return pumpset.state()


def stop():
	"""Safe-state both pumps."""
	pumpset.stop_all()
	return state()


def set_fast_speed(speed):
	"""Fast-mode speed for BOTH pumps. Per-pump: pump1.set_fast_speed(x)."""
	return pumpset.set_fast_speed(speed)


def set_slow_limits(low, high):
	"""Pulse-mode speed band for BOTH pumps."""
	return pumpset.set_slow_limits(low, high)


def set_pulse_duty(on_s, off_s):
	"""Pulse duty cycle in seconds for BOTH pumps."""
	return pumpset.set_pulse_duty(on_s, off_s)


def motor(n):
	"""Escape hatch: the raw DCMotor behind pump `n`, for bench debugging.

	Anything you do with it is invisible to the pump, so call pump.stop()
	afterwards to resynchronise.
	"""
	pump = pumpset.get(n)
	return None if pump is None else pump.motor


## End -> Indicate end of circuit creation
print("2ch_peristat_kitroniks_vx_shield : pump1, pump2, pump3, pumpset ready")
print("  pump1/2 kitronik : fast {}  slow {}-{}  duty {}s/{}s".format(
		FAST_SPEED, SLOW_MIN, SLOW_MAX, PULSE_ON_S, PULSE_OFF_S))
print("  pump3   dfr0523  : fast {}  slow {}-{} continuous @ {} kick {}/{}ms".format(
		P3_FAST_SPEED, P3_SLOW_MIN, P3_SLOW_MAX, P3_SLOW_START,
		P3_KICK_SPEED, P3_KICK_MS))
