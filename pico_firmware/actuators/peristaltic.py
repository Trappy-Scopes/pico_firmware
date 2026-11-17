## peristaltic.py -- peristaltic pump with fast and pulsed (slow) modes.
##
## Wraps a DCMotor and adds the two operating modes the keypad drives:
##
##   FAST  : continuous run at a single fixed speed (default 0.5).
##   PULSE : repeating duty cycle -- 5 s running, 55 s idle -- where the running
##           speed is adjustable, but only inside a narrow band (0.03 - 0.2) so
##           the pump stays in its slow-dosing regime.
##
## Every limit is changeable at runtime through a function, never by poking an
## attribute, so the host can retune a pump mid-experiment:
##
##   pump1.set_fast_speed(0.6)
##   pump1.set_slow_limits(0.05, 0.25)
##   pump1.set_pulse_duty(5, 55)
##
## The pulse cycle runs off a single PERIODIC machine.Timer ticking every
## PULSE_TICK_MS. The callback only does integer maths and duty writes -- no
## sleeping, no allocation, no printing -- because it runs in soft-IRQ context.
## This replaces the old pattern of time.sleep(5) inside a 60 s timer callback,
## which blocked the interpreter for 5 s out of every 60.

from machine import Timer

PULSE_TICK_MS = 250        ## pulse cycle resolution

## PWM frequency: None means "leave whatever DCMotor set" (10 Hz).
## Raising it was tried and made things worse on this shield -- at low duty the
## Kitronik driver needs the long on-time of a slow PWM period to get the head
## moving at all, so 10 Hz stays. Pass pwm_freq=<hz> per pump to override.
PWM_FREQ_HZ = None


## ---------------------------------------------------------------- persistence
## The pumps must keep running whatever happens to the host, and must come back
## in the same state when the host restarts and re-runs main.py.
##
## Two different survivals, and they need different mechanisms:
##
##   host disconnects / hangs   -- nothing to do. The duty cycle is a board-side
##                                 timer and the PWM is hardware; neither needs
##                                 the host. A pump keeps pumping.
##   board re-runs main.py      -- everything is rebuilt from scratch, so the
##                                 commanded state has to be written down. It is
##                                 saved here, to a small file, and restored when
##                                 the circuit builds its pumps.
##
## Saved on change only, never from the timer callback: a flash write inside a
## soft IRQ is exactly the kind of thing that hangs a board.

STATE_FILE = "pumpstate.txt"


def _read_state_file(path=STATE_FILE):
	try:
		with open(path) as f:
			return eval(f.read())          ## a dict literal; json may be absent
	except Exception:
		return {}


def _write_state_file(data, path=STATE_FILE):
	try:
		with open(path, "w") as f:
			f.write(repr(data))
		return True
	except Exception:
		return False


class PeristalticPump:
	"""One peristaltic pump: fast mode, pulsed slow mode, keypad-facing verbs."""

	def __init__(self, motor, name="pump",
					fast_speed=0.5,
					slow_min=0.03, slow_max=0.2,
					pulse_on_s=5, pulse_off_s=55,
					continuous=False, slow_speed=None, restore=None,
					pwm_freq=PWM_FREQ_HZ):
		self.motor = motor
		self.name = name

		## -- tunables, all reachable through set_* functions ------------------
		self.fast_speed_ = fast_speed
		self.slow_min_ = slow_min
		self.slow_max_ = slow_max
		self.pulse_on_s_ = pulse_on_s
		self.pulse_off_s_ = pulse_off_s
		## Kick start: a short burst at a higher speed at the top of every ON
		## phase, to break stiction before settling to the dosing speed. A 5 s
		## burst that never starts moving delivers nothing, and that failure is
		## silent -- the cycle counter still increments.
		self.kick_speed_ = 0.0     ## 0 disables
		self.kick_ms_ = 400
		## continuous: "pulse mode" runs steadily instead of duty-cycling.
		## Used by pumps whose head cannot tolerate stop/start dosing, e.g. the
		## DFR0523, which is meant to trickle rather than pulse.
		self.continuous_ = continuous

		## -- live state -------------------------------------------------------
		self.fast_ = False         ## fast mode engaged
		self.pulse_ = False        ## pulse mode engaged
		self.level_ = 0.5          ## 0.0 - 1.0 position within the slow band
		self.phase_ = "idle"       ## "idle" | "on" | "off"
		self.ticks_ = 0            ## ticks elapsed in the current phase
		self.cycles_ = 0           ## completed pulse cycles
		self.verbose = False       ## keep False: printing from an IRQ is unsafe
		self.tick_errors_ = 0      ## timer callback failures, see __tick__
		self.tick_last_error_ = 0

		## Leave the motor's PWM frequency alone unless explicitly asked.
		if pwm_freq is not None:
			self.set_pwm_freq(pwm_freq)

		if slow_speed is not None:
			self.set_slow_speed(slow_speed)
		if restore is not None:
			## before the first __apply__, so the first duty written is the
			## restored one and the pump does not blip through zero
			self.restore(restore)

		self.timer = Timer(-1)
		self.timer.init(period=PULSE_TICK_MS, mode=Timer.PERIODIC,
						callback=self.__tick__)
		self.__apply__()

	## -- tunables ---------------------------------------------------------------
	def set_fast_speed(self, speed):
		"""Speed used by fast mode. Clamped to 0.0 - 1.0."""
		self.fast_speed_ = min(1.0, max(0.0, float(speed)))
		self.__apply__()
		return self.fast_speed_

	def fast_speed(self):
		return self.fast_speed_

	def set_slow_limits(self, low, high):
		"""Speed band the pulse mode is allowed to use."""
		low = min(1.0, max(0.0, float(low)))
		high = min(1.0, max(0.0, float(high)))
		if high < low:
			low, high = high, low
		self.slow_min_ = low
		self.slow_max_ = high
		self.__apply__()
		return (self.slow_min_, self.slow_max_)

	def slow_limits(self):
		return (self.slow_min_, self.slow_max_)

	def set_pwm_freq(self, hz):
		"""Change the motor PWM frequency. Default is DCMotor's 10 Hz.

		Raising it did not help on the Kitronik shield -- kept as a knob, not
		used by default.
		"""
		hz = int(hz)
		self.motor.fwdpin.freq(hz)
		self.motor.revpin.freq(hz)
		self.__apply__()
		return hz

	def set_pulse_duty(self, on_s, off_s):
		"""Seconds running and seconds idle per pulse cycle."""
		self.pulse_on_s_ = max(0, int(on_s))
		self.pulse_off_s_ = max(0, int(off_s))
		self.ticks_ = 0
		return (self.pulse_on_s_, self.pulse_off_s_)

	def pulse_duty(self):
		return (self.pulse_on_s_, self.pulse_off_s_)

	def set_kick(self, speed, ms=400):
		"""Speed and duration of the stiction kick at the start of each burst.

		set_kick(0) disables it. Worth a look on the DFR0523 channel and on any
		pump feeding a narrow channel: without it the low end of the band can
		command a pulse the head simply does not respond to.
		"""
		self.kick_speed_ = max(0.0, min(1.0, float(speed)))
		self.kick_ms_ = max(0, int(ms))
		return (self.kick_speed_, self.kick_ms_)

	def kick(self):
		return (self.kick_speed_, self.kick_ms_)

	def set_continuous(self, flag):
		"""True: slow mode runs steadily. False: slow mode duty-cycles."""
		self.continuous_ = bool(flag)
		if self.continuous_ and self.pulse_:
			self.phase_ = "on"
			self.ticks_ = 0
		self.__apply__()
		return self.continuous_

	def is_continuous(self):
		return self.continuous_

	## -- speed within the slow band ---------------------------------------------
	def set_level(self, level):
		"""Position within the slow band, 0.0 (slowest) to 1.0 (fastest)."""
		self.level_ = min(1.0, max(0.0, float(level)))
		self.__apply__()
		return self.level_

	def set_percent(self, pct):
		"""Same as set_level but takes 0 - 100, which is what the keypad sends."""
		return self.set_level(float(pct) / 100.0)

	def level(self):
		return self.level_

	def percent(self):
		return int(round(self.level_ * 100))

	def slow_speed(self):
		"""Actual unit speed the pulse mode will use at the current level."""
		return self.slow_min_ + (self.slow_max_ - self.slow_min_) * self.level_

	def set_slow_speed(self, unit_speed):
		"""Set the slow-mode speed directly, as a unit speed rather than a level.

		Clamped into the current band, so set_slow_speed(0.1) on a 0.05-0.3 band
		lands at level 0.2.
		"""
		span = self.slow_max_ - self.slow_min_
		if span <= 0:
			return self.set_level(0.0)
		return self.set_level((float(unit_speed) - self.slow_min_) / span)

	def speed_up(self, step=0.05):
		return self.set_level(self.level_ + step)

	def speed_down(self, step=0.05):
		return self.set_level(self.level_ - step)

	## -- modes -------------------------------------------------------------------
	def fast_on(self):
		self.fast_ = True
		self.__apply__()
		return True

	def fast_off(self):
		self.fast_ = False
		self.__apply__()
		return False

	def set_fast(self, on):
		return self.fast_on() if on else self.fast_off()

	def toggle_fast(self):
		return self.set_fast(not self.fast_)

	def is_fast(self):
		return self.fast_

	def pulse_on(self):
		"""Start the pulse cycle at the beginning of an ON phase."""
		self.pulse_ = True
		self.phase_ = "on"
		self.ticks_ = 0
		self.__apply__()
		return True

	def pulse_off(self):
		self.pulse_ = False
		self.phase_ = "idle"
		self.ticks_ = 0
		self.__apply__()
		return False

	def set_pulse(self, on):
		return self.pulse_on() if on else self.pulse_off()

	def toggle_pulse(self):
		return self.set_pulse(not self.pulse_)

	def is_pulse(self):
		return self.pulse_

	def stop(self):
		"""Everything off. The safe state."""
		self.fast_ = False
		self.pulse_ = False
		self.phase_ = "idle"
		self.__apply__()

	def prime(self, seconds=5, speed=None):
		"""DEPRECATED -- do not call this over the serial link.

		It blocks the board. pyboard.exec_raw() waits 10 s for the reply and
		then raises, while this board keeps running and emits its output into
		the NEXT command's window -- which desynchronises the raw REPL and makes
		the device look permanently unreachable.

		Use prime_start()/prime_stop() and let the host do the waiting.
		"""
		if seconds > 8:
			return "REFUSED: {} s would block the serial link; use prime_start()".format(
					seconds)
		import time
		was_fast, was_pulse = self.fast_, self.pulse_
		self.fast_ = False
		self.pulse_ = False
		self.motor.fwd(1.0 if speed is None else float(speed))
		time.sleep(seconds)
		self.fast_, self.pulse_ = was_fast, was_pulse
		self.__apply__()
		return True

	def prime_start(self, speed=None):
		"""Begin priming and return immediately. The host times it."""
		self._primed_from = (self.fast_, self.pulse_)
		self.fast_ = False
		self.pulse_ = False
		self.motor.fwd(1.0 if speed is None else float(speed))
		return True

	def prime_stop(self):
		"""End priming and restore whatever mode was running before."""
		was = getattr(self, "_primed_from", (False, False))
		self.fast_, self.pulse_ = was
		self.__apply__()
		return True

	## -- introspection -------------------------------------------------------------
	## No __repr__ on purpose: Handshake.obj_list() discovers globals by looking
	## for "object" in str(value), so a custom repr would hide this pump from the
	## host. Use state() instead.
	def state(self):
		return {"name": self.name,
				"mode": self.mode(),
				"fast": self.fast_,
				"pulse": self.pulse_,
				"phase": self.phase_,
				"level": round(self.level_, 3),
				"percent": self.percent(),
				"speed": round(self.speed(), 4),
				"fast_speed": self.fast_speed_,
				"slow_limits": (self.slow_min_, self.slow_max_),
				"pulse_duty": (self.pulse_on_s_, self.pulse_off_s_),
				"continuous": self.continuous_,
				"kick": (self.kick_speed_, self.kick_ms_),
				"tick_errors": self.tick_errors_,
				"cycles": self.cycles_,
				"dir": self.motor.dir}

	def mode(self):
		if self.fast_:
			return "fast"
		if self.pulse_:
			return "slow" if self.continuous_ else "pulse"
		return "idle"

	def speed(self):
		"""Unit speed being written to the motor right now.

		Note the stock DCMotor has no working speed getter -- its setter shadows
		it -- so the pump keeps its own view of the commanded speed.
		"""
		if self.fast_:
			return self.fast_speed_
		if self.pulse_ and (self.continuous_ or self.phase_ == "on"):
			return self.slow_speed()
		return 0.0

	def running(self):
		return self.speed() > 0.0

	def seconds_left(self):
		"""Seconds remaining in the current pulse phase. 0 when not pulsing."""
		if not self.pulse_ or self.continuous_:
			return 0
		total = self.pulse_on_s_ if self.phase_ == "on" else self.pulse_off_s_
		return max(0, total - int(self.ticks_ * PULSE_TICK_MS / 1000))

	## -- internals -------------------------------------------------------------
	def __apply__(self):
		"""Push the resolved speed to the motor. Fast overrides pulse."""
		speed = self.speed()
		## still inside the kick window at the top of an ON phase?
		if (speed > 0 and not self.fast_ and self.pulse_ and self.phase_ == "on"
				and self.kick_speed_ > speed
				and self.ticks_ * PULSE_TICK_MS < self.kick_ms_):
			speed = self.kick_speed_
		if speed <= 0.0:
			self.motor.release()
			self.motor.speed_ = 0.0
		else:
			self.motor.fwd(speed)

	def __tick__(self, _timer):
		"""Soft-IRQ: advance the pulse cycle. MUST NOT RAISE, MUST NOT PRINT.

		This is the single most dangerous function in the firmware. It runs from
		a soft timer, and MicroPython prints a traceback when a timer callback
		raises. That traceback goes to USB CDC -- which the host only drains
		while it is running a command over the raw REPL. Once the CDC buffer
		fills, the next write BLOCKS INSIDE THIS CALLBACK and the interpreter
		stops: the board hangs, hard, and the host sees "timeout waiting for
		first EOF reception" for ever.

		So everything is swallowed. Failures are counted and surfaced through
		state(), which the host can read, instead of being printed where nobody
		is listening.
		"""
		try:
			self.__tick_body__()
		except Exception:
			## deliberately bare: no print, no re-raise, no traceback
			self.tick_errors_ += 1
			self.tick_last_error_ = 1

	def __tick_body__(self):
		if not self.pulse_ or self.fast_ or self.continuous_:
			return
		self.ticks_ += 1
		elapsed_s = self.ticks_ * PULSE_TICK_MS / 1000
		## the kick expires mid-phase, so the speed has to be rewritten
		if (self.kick_speed_ > 0 and self.phase_ == "on"
				and self.ticks_ * PULSE_TICK_MS >= self.kick_ms_
				and (self.ticks_ - 1) * PULSE_TICK_MS < self.kick_ms_):
			self.__apply__()

		if self.phase_ == "on" and elapsed_s >= self.pulse_on_s_:
			self.phase_ = "off"
			self.ticks_ = 0
			self.cycles_ += 1
			self.__apply__()
		elif self.phase_ == "off" and elapsed_s >= self.pulse_off_s_:
			self.phase_ = "on"
			self.ticks_ = 0
			self.__apply__()

	def snapshot(self):
		"""What has to survive a restart: the commanded mode, nothing else.

		Limits, duty, kick and speeds are NOT saved. main.py re-runs on every
		host connect, so the circuit re-applies its defaults and the host
		re-pushes its envelope every single time -- saving them as well would
		only make a second copy that can go stale.
		"""
		return (self.fast_, self.pulse_, round(self.level_, 4))

	def restore(self, snap):
		"""Reinstate a snapshot. Never raises on a malformed one."""
		try:
			self.fast_ = bool(snap[0])
			self.pulse_ = bool(snap[1])
			self.level_ = float(snap[2])
			self.phase_ = "on" if self.pulse_ else "idle"
			self.ticks_ = 0
			return True
		except Exception:
			return False


	def tick_errors(self):
		"""How many times the timer callback has failed since boot.

		Non-zero means something is wrong that you cannot see any other way --
		the callback cannot report it, because reporting it is what hangs the
		board.
		"""
		return self.tick_errors_

	def deinit(self):
		self.timer.deinit()
		self.stop()


class PumpSet:
	"""Two or more pumps addressed by number, plus the keypad wire protocol.

	The keypad emits lines like "PUMP 1 POWER ON". Feed them straight in:

	    pumpset.command("PUMP 1 POWER ON")

	POWER maps to fast mode, PULSE to the pulsed slow mode, SPEED to the level
	inside the slow band. LIMIT is keypad UI feedback and is ignored.
	"""

	def __init__(self, pumps, persist=True, state_file=STATE_FILE):
		## pumps: dict {1: pump1, 2: pump2}
		self.pumps = pumps
		self.state_file = state_file
		self.persist = persist
		self._written = None

	def __getitem__(self, n):
		return self.pumps[n]

	def get(self, n):
		return self.pumps.get(n)

	def numbers(self):
		return sorted(self.pumps)

	def command(self, line):
		"""Apply one keypad wire line. Returns the pump's state, or None."""
		parts = str(line).strip().upper().split()
		if len(parts) != 4 or parts[0] != "PUMP":
			return None
		try:
			n = int(parts[1])
		except ValueError:
			return None
		pump = self.pumps.get(n)
		if pump is None:
			return None

		verb, arg = parts[2], parts[3]
		if verb == "POWER":
			pump.set_fast(arg == "ON")
		elif verb == "PULSE":
			pump.set_pulse(arg == "ON")
		elif verb == "SPEED":
			try:
				pump.set_percent(int(arg))
			except ValueError:
				return None
		elif verb == "LIMIT":
			return pump.state()          ## UI only, nothing to do
		else:
			return None
		self.save()
		return pump.state()

	def commands(self, lines):
		"""Apply a list of wire lines, e.g. everything the keypad had queued."""
		return [self.command(line) for line in (lines or [])]

	## -- broadcast ---------------------------------------------------------------
	def stop_all(self):
		for pump in self.pumps.values():
			pump.stop()
		self.save()

	def set_fast_speed(self, speed):
		return [p.set_fast_speed(speed) for p in self.pumps.values()]

	def set_slow_limits(self, low, high):
		return [p.set_slow_limits(low, high) for p in self.pumps.values()]

	def set_pulse_duty(self, on_s, off_s):
		return [p.set_pulse_duty(on_s, off_s) for p in self.pumps.values()]

	def set_kick(self, speed, ms=400):
		"""Speed and duration of the stiction kick at the start of each burst.

		set_kick(0) disables it. Worth a look on the DFR0523 channel and on any
		pump feeding a narrow channel: without it the low end of the band can
		command a pulse the head simply does not respond to.
		"""
		self.kick_speed_ = max(0.0, min(1.0, float(speed)))
		self.kick_ms_ = max(0, int(ms))
		return (self.kick_speed_, self.kick_ms_)

	def kick(self):
		return (self.kick_speed_, self.kick_ms_)

	def set_continuous(self, flag):
		return [p.set_continuous(flag) for p in self.pumps.values()]

	def state(self):
		return dict((n, p.state()) for n, p in self.pumps.items())

	## -- surviving a restart -------------------------------------------------
	## main.py re-runs on every host connect, so the whole mechanism is: save
	## when a command changes something, hand the saved state to the pumps when
	## the circuit builds them.

	def snapshot(self):
		return dict((n, p.snapshot()) for n, p in self.pumps.items())

	def save(self):
		"""Persist the commanded modes. No write when nothing changed."""
		if not self.persist:
			return False
		snap = self.snapshot()
		if snap == self._written:
			return False
		if _write_state_file(snap, self.state_file):
			self._written = snap
			return True
		return False

	def forget(self):
		"""Discard the saved state; the next build starts from defaults."""
		self._written = None
		return _write_state_file({}, self.state_file)


	def deinit(self):
		"""Stop the timers. Does NOT stop the pumps or clear the saved state.

		Used when main.py is re-run: the old objects must release their timers,
		but the hardware PWM keeps the pumps running through the rebuild, which
		is the whole point -- a perfusion should not stutter because the host
		restarted.
		"""
		for pump in self.pumps.values():
			try:
				pump.timer.deinit()
			except Exception:
				pass
