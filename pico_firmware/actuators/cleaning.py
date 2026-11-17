## cleaning.py -- one-directional cleaning pump with a reversing DEEP CLEAN mode.
##
## A cleaning pump is a PeristalticPump that normally only ever runs forward:
## same FAST / PULSE modes, same wire protocol, same persistence. On top of that
## it gains a third mode which outranks both:
##
##   DEEP CLEAN : alternate forward and reverse indefinitely --
##                  forward  deep_fwd_s  seconds at the base speed
##                  coast    deep_gap_ms
##                  reverse  deep_rev_s  seconds at base * deep_mult (3x)
##                  coast    deep_gap_ms
##                ...and repeat. Reversing the flow periodically is the point:
##                a steady laminar flow polishes one streamline and leaves the
##                rest of the bore alone, whereas a flow that stops, turns over
##                and restarts at 3x sweeps the whole cross-section and lifts
##                deposits a monotonic flow never touches.
##
## Priority is DEEP > FAST > PULSE. Deep clean remembers the mode it interrupted
## and puts it back when it ends, so you can deep-clean a channel mid-perfusion
## and the perfusion resumes on its own.
##
## Runtime API, all functions, no attribute poking:
##
##   pump1.deep_on()                 ## until stopped
##   pump1.deep_on(cycles=5)         ## five fwd/rev cycles, then back to before
##   pump1.deep_off()
##   pump1.set_deep_profile(6, 2)    ## 6 s forward, 2 s reverse
##   pump1.set_deep_mult(3.0)        ## reverse speed multiplier
##   pump1.set_deep_base(0.4)        ## pin the base speed; None = use current
##   pump1.deep_state()
##
## Wire protocol, two new verbs on the existing four-token grammar:
##
##   PUMP <n> CLEAN ON|OFF
##   PUMP <n> RATE <0.0-1.0>          one unit speed, DCMotor's own units
##
## ---------------------------------------------------------------------------
## THREE THINGS THAT MATTER ON THE HARDWARE
##
## 1. The coast gap is not optional. Slamming an H-bridge from full forward to
##    3x reverse in one PWM period asks the driver to absorb the motor's stored
##    energy plus a reversed drive current at the same instant. On a DRV8833
##    (1.5 A per channel, 2 A peak) with a loaded peristaltic head that is how
##    you find the overcurrent limiter, and the failure looks like a pump that
##    "randomly stops". release() for a moment first and the field collapses
##    before the reverse drive arrives.
##
## 2. base * 3 is clamped to 1.0. A cleaning pump at fast_speed 0.5 gives a 1.5
##    request, which is not a thing; it becomes full duty. If you want a real 3x
##    on the reverse stroke, set the base at or below 0.33.
##
## 3. Every duration quantises up to PULSE_TICK_MS (250 ms), because that is the
##    tick this rides on. deep_rev_s=2 is exact; deep_gap_ms=150 becomes 250.

from pico_firmware.actuators.peristaltic import PeristalticPump, PumpSet, \
		PULSE_TICK_MS

DEEP_MULT = 3.0            ## reverse speed = base * this, clamped to 1.0
DEEP_FWD_S = 6             ## seconds forward per cycle
DEEP_REV_S = 2             ## seconds reverse per cycle
DEEP_GAP_MS = 250          ## coast between direction changes -- see note 1
DEEP_MAX_CYCLES = 0        ## 0 = run until stopped


class CleaningPump(PeristalticPump):
	"""A PeristalticPump with a reversing deep-clean mode layered on top."""

	def __init__(self, motor, name="cleanpump",
					deep_mult=DEEP_MULT,
					deep_fwd_s=DEEP_FWD_S, deep_rev_s=DEEP_REV_S,
					deep_gap_ms=DEEP_GAP_MS,
					deep_max_cycles=DEEP_MAX_CYCLES,
					deep_base=None,
					**kw):
		## Set before super().__init__ -- the base constructor calls __apply__,
		## which is overridden here and reads every one of these.
		self.deep_mult_ = max(1.0, float(deep_mult))
		self.deep_fwd_s_ = max(0, int(deep_fwd_s))
		self.deep_rev_s_ = max(0, int(deep_rev_s))
		self.deep_gap_ms_ = max(0, int(deep_gap_ms))
		self.deep_max_cycles_ = max(0, int(deep_max_cycles))
		self.deep_base_ = None if deep_base is None else float(deep_base)

		self.deep_ = False
		self.deep_phase_ = "idle"      ## fwd | gap_to_rev | rev | gap_to_fwd
		self.deep_ticks_ = 0
		self.deep_cycles_ = 0
		self.deep_target_ = 0          ## cycles to run this session, 0 = forever
		self.deep_run_base_ = 0.0      ## base speed frozen at deep_on()
		self.deep_from_ = (False, False)
		self.deep_allowed_ = True

		super().__init__(motor, name=name, **kw)

		## One speed knob, in DCMotor's own units. Seeded from whatever fast
		## speed the circuit passed so a pump built without a rate still runs.
		self.set_rate(self.fast_speed_)

	## -- speed, as a unit speed ---------------------------------------------------
	## The stock pump carries two coordinate systems for one number: a slow band
	## plus a 0-1 level inside it, plus a separate fast speed. DCMotor already
	## speaks unit speed, 0.0 - 1.0, so this collapses the lot into ONE knob and
	## propagates it rather than mapping it again:
	##
	##   set_rate(0.12) -> fast mode runs at 0.12, and so does the pulse burst.
	##
	## The band is pinned to the rate (min == max == rate) so the inherited
	## slow_speed() keeps working and set_percent / set_level stay harmless.
	def set_rate(self, unit_speed):
		"""The one speed this pump runs at, 0.0 - 1.0. Used by fast and pulse.

		No ceiling beyond the hardware's own 0-1: these are plain DC heads and the
		operator decides how hard to drive them. The only interlock in this class
		is on deep clean, which reverses the flow.
		"""
		self.rate_ = min(1.0, max(0.0, float(unit_speed)))
		self.fast_speed_ = self.rate_
		self.slow_min_ = self.rate_
		self.slow_max_ = self.rate_
		self.__apply__()
		return self.rate_

	def rate(self):
		return self.rate_

	def rate_up(self, step=0.01):
		return self.set_rate(self.rate_ + step)

	def rate_down(self, step=0.01):
		return self.set_rate(self.rate_ - step)

	## -- tunables ---------------------------------------------------------------
	def set_deep_mult(self, mult):
		"""Reverse-stroke speed multiplier. 1.0 = same speed both ways."""
		self.deep_mult_ = max(1.0, float(mult))
		self.__apply__()
		return self.deep_mult_

	def deep_mult(self):
		return self.deep_mult_

	def set_deep_profile(self, fwd_s, rev_s, gap_ms=None, mult=None):
		"""Seconds forward and reverse per cycle. Quantised to 250 ms ticks."""
		self.deep_fwd_s_ = max(0, int(fwd_s))
		self.deep_rev_s_ = max(0, int(rev_s))
		if gap_ms is not None:
			self.deep_gap_ms_ = max(0, int(gap_ms))
		if mult is not None:
			self.deep_mult_ = max(1.0, float(mult))
		self.deep_ticks_ = 0
		return self.deep_profile()

	def deep_profile(self):
		return (self.deep_fwd_s_, self.deep_rev_s_, self.deep_gap_ms_,
				self.deep_mult_)

	def set_deep_base(self, speed):
		"""Pin the forward speed deep clean uses. None = whatever is running.

		Pinning it is the reproducible choice: otherwise the same DEEP CLEAN tap
		means different things depending on where the speed slider happened to
		be. Takes effect at the next deep_on().
		"""
		self.deep_base_ = None if speed is None else min(1.0, max(0.0, float(speed)))
		return self.deep_base_

	def deep_base(self):
		return self.deep_base_

	def set_deep_max_cycles(self, cycles):
		"""Default cycle count for deep_on(). 0 = run until stopped."""
		self.deep_max_cycles_ = max(0, int(cycles))
		return self.deep_max_cycles_

	## -- mode ---------------------------------------------------------------------
	def allow_deep(self, flag):
		"""Interlock. False makes deep_on() refuse -- for when a chip is connected.

		A deep clean drives the head to 0.99 and reverses it; that is a pressure
		transient a microfluidic device will not survive. The interlock is here so
		"chip connected" is a state the pump itself knows, not a habit of the
		person tapping the screen.
		"""
		self.deep_allowed_ = bool(flag)
		if not self.deep_allowed_ and self.deep_:
			self.deep_off()
		return self.deep_allowed_

	def deep_allowed(self):
		return getattr(self, "deep_allowed_", True)

	def deep_on(self, cycles=None):
		"""Start deep clean. Remembers the mode it interrupts.

		cycles=None uses deep_max_cycles (0 = until stopped). The base speed is
		frozen here, so a speed change mid-clean does not shift the strokes
		underneath the cycle.
		"""
		if not self.deep_allowed():
			return False                    ## interlocked -- a chip is connected
		if not self.deep_:
			self.deep_from_ = (self.fast_, self.pulse_)
		self.deep_run_base_ = self.__deep_base_now__()
		self.deep_target_ = self.deep_max_cycles_ if cycles is None else max(0, int(cycles))
		self.deep_ = True
		self.deep_cycles_ = 0
		self.deep_ticks_ = 0
		self.deep_phase_ = "fwd" if self.deep_fwd_s_ > 0 else "rev"
		self.__apply__()
		return True

	def deep_off(self):
		"""Stop deep clean and restore the mode that was running before it."""
		if not self.deep_:
			return False
		self.__deep_end__()
		return False

	def set_deep(self, on, cycles=None):
		return self.deep_on(cycles) if on else self.deep_off()

	def toggle_deep(self):
		return self.set_deep(not self.deep_)

	def is_deep(self):
		return self.deep_

	def deep_cycles(self):
		return self.deep_cycles_

	def deep_seconds_left(self):
		"""Seconds left in the current deep-clean stroke. 0 when not deep."""
		if not self.deep_:
			return 0
		if self.deep_phase_ == "fwd":
			total = self.deep_fwd_s_
		elif self.deep_phase_ == "rev":
			total = self.deep_rev_s_
		else:
			return 0
		return max(0, total - int(self.deep_ticks_ * PULSE_TICK_MS / 1000))

	def deep_state(self):
		return {"deep": self.deep_,
				"phase": self.deep_phase_,
				"cycles": self.deep_cycles_,
				"target": self.deep_target_,
				"base": round(self.deep_run_base_, 4),
				"mult": self.deep_mult_,
				"profile": self.deep_profile(),
				"seconds_left": self.deep_seconds_left(),
				"restores_to": self.deep_from_}

	## -- overrides ----------------------------------------------------------------
	def mode(self):
		if self.deep_:
			return "deep"
		return PeristalticPump.mode(self)

	def speed(self):
		"""Unit speed magnitude being written right now. Direction is separate."""
		if self.deep_:
			if self.deep_phase_ == "rev":
				return min(1.0, self.deep_run_base_ * self.deep_mult_)
			if self.deep_phase_ == "fwd":
				return self.deep_run_base_
			return 0.0                     ## coasting between strokes
		return PeristalticPump.speed(self)

	def state(self):
		st = PeristalticPump.state(self)
		st["rate"] = round(self.rate_, 4)
		st["deep"] = self.deep_
		st["deep_phase"] = self.deep_phase_
		st["deep_cycles"] = self.deep_cycles_
		st["deep_target"] = self.deep_target_
		st["deep_mult"] = self.deep_mult_
		st["deep_profile"] = self.deep_profile()
		st["deep_seconds_left"] = self.deep_seconds_left()
		st["deep_allowed"] = self.deep_allowed()
		return st

	def stop(self):
		"""Everything off, deep clean included. The safe state."""
		self.deep_ = False
		self.deep_phase_ = "idle"
		self.deep_ticks_ = 0
		self.deep_from_ = (False, False)
		PeristalticPump.stop(self)

	def __apply__(self):
		"""Push resolved speed AND direction. Deep outranks fast outranks pulse."""
		if not self.deep_:
			return PeristalticPump.__apply__(self)
		speed = self.speed()
		if speed <= 0.0:
			self.motor.release()
			self.motor.speed_ = 0.0
		elif self.deep_phase_ == "rev":
			self.motor.rev(speed)
		else:
			self.motor.fwd(speed)

	def __tick_body__(self):
		"""Soft-IRQ. Same contract as the base: never raise, never print.

		No flash writes here either -- so a cycle count reached in the timer
		does NOT persist itself. The host picks the change up from state().
		"""
		if self.deep_:
			return self.__deep_tick__()
		return PeristalticPump.__tick_body__(self)

	## -- internals ----------------------------------------------------------------
	def __deep_base_now__(self):
		"""Forward speed for the strokes: pinned, else whatever runs now."""
		if self.deep_base_ is not None:
			return self.deep_base_
		s = PeristalticPump.speed(self)         ## the un-deep view of the pump
		return s if s > 0.0 else self.fast_speed_

	def __deep_goto__(self, phase):
		self.deep_phase_ = phase
		self.deep_ticks_ = 0
		self.__apply__()

	def __deep_end__(self):
		"""Leave deep clean, restore the interrupted mode, face forward again."""
		self.deep_ = False
		self.deep_phase_ = "idle"
		self.deep_ticks_ = 0
		self.fast_, self.pulse_ = self.deep_from_
		if self.pulse_:
			## re-enter the duty cycle at the top of an ON phase rather than
			## halfway through a phase that elapsed while we were reversing
			self.phase_ = "on"
			self.ticks_ = 0
		self.motor.release()                    ## coast before facing forward
		self.motor.dir = 1
		self.__apply__()

	def __deep_tick__(self):
		self.deep_ticks_ += 1
		elapsed_ms = self.deep_ticks_ * PULSE_TICK_MS

		if self.deep_phase_ == "fwd":
			if elapsed_ms >= self.deep_fwd_s_ * 1000:
				self.__deep_goto__("gap_to_rev" if self.deep_gap_ms_ else "rev")

		elif self.deep_phase_ == "gap_to_rev":
			if elapsed_ms >= self.deep_gap_ms_:
				self.__deep_goto__("rev")

		elif self.deep_phase_ == "rev":
			if elapsed_ms >= self.deep_rev_s_ * 1000:
				self.__deep_goto__("gap_to_fwd" if self.deep_gap_ms_ else "fwd")
				if not self.deep_gap_ms_:
					self.__deep_cycle_done__()

		elif self.deep_phase_ == "gap_to_fwd":
			if elapsed_ms >= self.deep_gap_ms_:
				self.__deep_goto__("fwd")
				self.__deep_cycle_done__()

		else:
			self.__deep_goto__("fwd")

	def __deep_cycle_done__(self):
		self.deep_cycles_ += 1
		if self.deep_target_ and self.deep_cycles_ >= self.deep_target_:
			self.__deep_end__()


class CleaningPumpSet(PumpSet):
	"""PumpSet plus the CLEAN verb, and broadcasts that reach every pump.

	Also repairs two things the stock PumpSet gets wrong:
	  set_kick() assigned kick_speed_ on the SET instead of forwarding it to the
	  pumps, so it silently did nothing; and stop_all() had no notion of deep
	  clean, so a reversing pump survived a "stop everything".
	"""

	def __init__(self, pumps, buzzer=None, **kw):
		PumpSet.__init__(self, pumps, **kw)
		self.buzzer = buzzer            ## a Beacon, or anything with on()/off()
		self.beep_timer = None

	## -- tactile feedback ---------------------------------------------------------
	def beep(self, ms=35):
		"""A short blip on the board buzzer -- tap feedback for the touchscreen.

		One-shot Timer, never a sleep: this is called from the host on every
		button press, and blocking the board for even 35 ms per tap would stall
		the raw REPL and stutter the pulse cycle. Fails silently if no buzzer was
		passed, because tap feedback is never worth an exception.
		"""
		if self.buzzer is None:
			return False
		try:
			from machine import Timer
			self.buzzer.on()
			if self.beep_timer is None:
				self.beep_timer = Timer(-1)
			self.beep_timer.init(period=max(5, int(ms)), mode=Timer.ONE_SHOT,
									callback=self.__beep_off__)
			return True
		except Exception:
			try:
				self.buzzer.off()
			except Exception:
				pass
			return False

	def __beep_off__(self, _t=None):
		try:
			self.buzzer.off()
		except Exception:
			pass

	def command(self, line):
		"""Apply one wire line. Handles CLEAN and RATE, defers the rest upstream.

		RATE is a new verb rather than a redefinition of SPEED: SPEED means
		percent-of-band to the existing keypad, and quietly changing what an old
		command does is how a pump ends up running at 60x the intended rate.
		"""
		parts = str(line).strip().upper().split()
		if len(parts) == 4 and parts[0] == "PUMP" and parts[2] in ("CLEAN", "RATE"):
			try:
				n = int(parts[1])
			except ValueError:
				return None
			pump = self.pumps.get(n)
			if pump is None:
				return None
			if parts[2] == "CLEAN":
				if not hasattr(pump, "deep_on"):
					return None
				pump.set_deep(parts[3] == "ON")
			else:
				if not hasattr(pump, "set_rate"):
					return None
				try:
					pump.set_rate(float(parts[3]))
				except ValueError:
					return None
			self.save()
			return pump.state()
		return PumpSet.command(self, line)

	## -- broadcast ---------------------------------------------------------------
	def stop_all(self):
		for pump in self.pumps.values():
			pump.stop()                     ## CleaningPump.stop clears deep too
		self.save()

	def deep_all(self, cycles=None):
		return [p.set_deep(True, cycles) for p in self.pumps.values()
				if hasattr(p, "deep_on")]

	def deep_off_all(self):
		return [p.deep_off() for p in self.pumps.values() if hasattr(p, "deep_off")]

	def any_deep(self):
		return any(p.is_deep() for p in self.pumps.values() if hasattr(p, "is_deep"))

	def set_rate(self, unit_speed):
		"""One unit speed for every pump, 0.0 - 1.0."""
		return [p.set_rate(unit_speed) for p in self.pumps.values()
				if hasattr(p, "set_rate")]

	def allow_deep(self, flag):
		"""Interlock every pump at once: False = a chip is connected."""
		return [p.allow_deep(flag) for p in self.pumps.values()
				if hasattr(p, "allow_deep")]

	def rates(self):
		return dict((n, p.rate()) for n, p in self.pumps.items()
					if hasattr(p, "rate"))

	def set_deep_profile(self, fwd_s, rev_s, gap_ms=None, mult=None):
		return [p.set_deep_profile(fwd_s, rev_s, gap_ms, mult)
				for p in self.pumps.values() if hasattr(p, "set_deep_profile")]

	def set_deep_mult(self, mult):
		return [p.set_deep_mult(mult) for p in self.pumps.values()
				if hasattr(p, "set_deep_mult")]

	def set_deep_base(self, speed):
		return [p.set_deep_base(speed) for p in self.pumps.values()
				if hasattr(p, "set_deep_base")]

	def set_kick(self, speed, ms=400):
		"""Forward the stiction kick to every pump. The base class kept it."""
		return [p.set_kick(speed, ms) for p in self.pumps.values()]

	def deep_state(self):
		return dict((n, p.deep_state()) for n, p in self.pumps.items()
					if hasattr(p, "deep_state"))
