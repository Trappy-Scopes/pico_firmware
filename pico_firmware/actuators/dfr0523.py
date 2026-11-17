## dfr0523.py -- DFRobot DFR0523 "Gravity: Digital Peristaltic Pump"
##
## The driver board takes a 50 Hz servo/PPM signal on its D pin:
##     500 -1400 us  forward   (500 us  = max forward)
##    1400 -1600 us  stop      (deadband)
##    1600 -2500 us  reverse   (2500 us = max reverse)
##
## Wiring:  D -> any GPIO (3.3 V logic is accepted)
##          + -> 5-6 V external supply, >= 2 A per pump
##          - -> supply GND, tied to Pico GND
##       M/M- -> the pump motor
## Never power the driver from the Pico's 3V3 pin.
##
## The class deliberately mirrors DCMotor's surface -- fwd/rev/hold/release,
## speed_, dir, fwdpin/revpin -- so PeristalticPump drives it unchanged and the
## keypad cannot tell the two pump kinds apart.

from machine import PWM, Pin

PPM_FREQ_HZ = 50
PERIOD_US   = 1000000 // PPM_FREQ_HZ      ## 20000
FWD_FULL_US = 500
FWD_MIN_US  = 1330        ## slowest commanded forward pulse.
                          ## NOT 1400: the deadband edge itself gives almost no
                          ## drive, and the head stalls against a microfluidic
                          ## load. Pulling the zero-speed end inward to ~1330 us
                          ## means unit speed 0.0 already commands real motion.
                          ## Lower it further if the pump still will not start.
STOP_US     = 1500        ## centre of the deadband
REV_MIN_US  = 1670        ## mirror of FWD_MIN_US on the reverse side
REV_FULL_US = 2500


class DFR0523:
	"""One DFR0523 driver board on one GPIO."""

	def __init__(self, pin, invert=False, fwd_min_us=None, fwd_full_us=None):
		self.fwd_min_us = FWD_MIN_US if fwd_min_us is None else int(fwd_min_us)
		self.fwd_full_us = FWD_FULL_US if fwd_full_us is None else int(fwd_full_us)
		self.pin_no = {"ppm": pin}
		self.pwm = PWM(Pin(pin))
		self.pwm.freq(PPM_FREQ_HZ)

		## DCMotor compatibility: both names point at the single PPM output, so
		## PeristalticPump.set_pwm_freq() and friends do not blow up. Changing
		## the frequency breaks the PPM timing, so it is guarded below.
		self.fwdpin = self
		self.revpin = self

		self.invert = invert
		self.dir = +1
		self.duty = 0
		self.speed_ = 0.0
		self.release()

	## -- pin-like shims so DCMotor-shaped callers keep working -----------------
	def freq(self, hz=None):
		"""PPM must stay at 50 Hz. Reads back; silently refuses to change.

		Deliberately SILENT. A print() here would be unsolicited output on the
		USB CDC, and the host talks to this board over the raw REPL: any stray
		bytes desynchronise pyboard.follow(), which reads until \x04. One stray
		line and every later call reads the wrong output -- the board looks
		unreachable until it is reconnected. Nothing in this class prints.
		"""
		return PPM_FREQ_HZ

	def duty_u16(self, value):
		"""Present for API symmetry only; use speed()."""
		self.pwm.duty_u16(int(value))

	## -- PPM ------------------------------------------------------------------
	def pulse_us(self, unit_speed):
		"""Signed unit speed (-1.0 .. +1.0) -> PPM pulse width.

		The deadband is skipped, so a small non-zero speed already moves the
		pump instead of sitting in the stop window.
		"""
		if unit_speed > 1.0:
			unit_speed = 1.0
		elif unit_speed < -1.0:
			unit_speed = -1.0
		if unit_speed == 0:
			return STOP_US
		if unit_speed > 0:
			return int(self.fwd_min_us - (self.fwd_min_us - self.fwd_full_us) * unit_speed)
		return int(REV_MIN_US + (REV_FULL_US - REV_MIN_US) * (-unit_speed))

	def __write__(self, signed_speed):
		if self.invert:
			signed_speed = -signed_speed
		us = self.pulse_us(signed_speed)
		self.duty = int(us * 65535 // PERIOD_US)
		self.pwm.duty_u16(self.duty)

	## -- DCMotor-compatible verbs ----------------------------------------------
	def speed(self, unit_speed):
		"""Set magnitude 0.0 - 1.0; direction comes from fwd()/rev()."""
		if unit_speed is None:
			unit_speed = self.speed_
		unit_speed = abs(float(unit_speed))
		if unit_speed > 1.0:
			unit_speed = 1.0
		self.speed_ = unit_speed
		self.__write__(unit_speed * self.dir)

	def fwd(self, speed=None):
		self.dir = 1
		if speed:
			self.speed(speed)

	def rev(self, speed=None):
		self.dir = -1
		if speed:
			self.speed(speed)

	def hold(self):
		"""Commanded stop. The DFR0523 has no brake -- this is the deadband."""
		self.speed_ = 0.0
		self.__write__(0)

	def release(self):
		"""Same as hold on this driver: park in the stop window."""
		self.hold()

	def min_speed(self):
		self.speed(0.05)

	def max_speed(self):
		self.speed(1.0)

	def set_deadband(self, fwd_min_us):
		"""Move the zero-speed pulse width. Lower = more drive at low speed."""
		self.fwd_min_us = int(fwd_min_us)
		self.speed(self.speed_)
		return self.fwd_min_us

	def state(self):
		return {"kind": "dfr0523", "fwd_min_us": self.fwd_min_us,
				"pin": self.pin_no["ppm"],
				"dir": self.dir,
				"speed": round(self.speed_, 4),
				"pulse_us": self.pulse_us(self.speed_ * self.dir)}
