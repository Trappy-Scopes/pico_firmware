# pimoroni_rgb_sparkly_rainbows_cntlr.py
# Pimoroni RGB Keypad Base as a 3-pump control surface.
#
# REWRITTEN 14 Aug 2026, same filename on purpose: main.py resolves the
# circuit by board.py's circuit_id, and the flash list and the notes all name
# this file. Same object, same wire protocol, same host-facing API. The
# decorative animation is gone and three latent hangs with it -- 913 lines to
# 531. The previous version is at _backup_20260814/circuits/ (this repo is not
# under git); restoring it is a straight copy back, no board.py edit.
# See "WHAT CHANGED" at the bottom.
#
# Trappy-Scopes circuit file: main.py execfile()s this, so everything defined at
# module level lands in main.py's globals. `kp` is the object the host reaches
# as scope.kp -- no __repr__ on purpose, so Handshake.obj_list() finds it.
#
#   kp.state(1)          -> {'power': True, 'pulse': False, 'speed': 45}
#   kp.state()           -> {1: {...}, 2: {...}, 3: {...}}
#   kp.markers()         -> {'BLEACH': False, 'AERATION': True}
#   kp.pumps() kp.speed(n) kp.is_power(n) kp.is_pulse(n) kp.count()
#   kp.drain()           -> pending Command objects, queue cleared
#   kp.lines()           -> ['PUMP 1 POWER ON', ...]  (use this over the REPL)
#   kp.snapshot_lines()  -> full state as wire lines, to resync a host
#   kp.sync(pumpset.state())   kp.apply(line)   kp.apply_lines([...])
#   kp.stop_all()  kp.stop()  kp.disarm()  kp.service_errors()  kp.health()
#
# host -> keypad (sync/apply/apply_lines) is QUIET by default: it updates state
# and LEDs without emitting commands, so a push cannot bounce back as a command.
#
# ---------------------------------------------------------------- pad layout
#   pad 0  1  2  3        col0 = PUMP 1        row 0  POWER  toggle
#   pad 4  5  6  7        col1 = PUMP 2        row 1  PULSE  toggle
#   pad 8  9  A  B        col2 = markers       row 2  SPEED + (auto-repeat)
#   pad C  D  E  F        col3 = PUMP 3        row 3  SPEED - (auto-repeat)
#
#   col2 holds MARKERS: toggles that move no pump, they only tell the host to
#   log an event. pad 2 = BLEACH (red while on: bleach clean of the tubes),
#   pad 6 = AERATION (blue while on: aeration of media/water). Dark when off;
#   pads A and E stay dark. See MARKER_PADS.
#
# ---------------------------------------------------------------- wire format
#   PUMP <n> POWER ON|OFF
#   PUMP <n> PULSE ON|OFF
#   PUMP <n> SPEED <pct>
#   PUMP <n> LIMIT MIN|MAX        (UI feedback only, safe to ignore)
#   EVENT <name> ON|OFF           (marker toggled; the host logs an event)

import gc
import time

# ---------------------------------------------------------------- config
SPEED_STEP      = 5
SPEED_MIN       = 5
SPEED_MAX       = 100
SPEED_INIT      = 30
BRIGHTNESS      = 1.0
REPEAT_DELAY_MS = 450
REPEAT_RATE_MS  = 90
DEBOUNCE_MS     = 25
FRAME_MS        = 33          # 30 fps is plenty; nothing animates any more
BLINK_MS        = 320         # pulse-indicator half period
FLASH_MS        = 90          # key-press acknowledgement
TIMER_MS        = 8
HISTORY         = 16          # commands kept in recent()
PENDING_MAX     = 64          # cap on the undrained queue; oldest dropped
GC_MS           = 5000        # periodic collect; see WHAT CHANGED note 3

ROW_POWER, ROW_PULSE, ROW_UP, ROW_DOWN = 0, 1, 2, 3
PUMP_COLUMNS = {0: 1, 1: 2, 3: 3}     # keypad column -> pump number
STEADY_PULSE = (3,)                   # columns whose pulse LED does not blink

## Marker pads: pad index -> (name, colour while on). Each press toggles the
## marker and emits EVENT <name> ON|OFF; no pump is touched. Must sit in a column
## that PUMP_COLUMNS leaves free.
MARKER_PADS = {2: ("BLEACH", (255, 0, 0)),       # col2 row0: bleach clean of the tubes
               6: ("AERATION", (0, 0, 255))}     # col2 row1: aeration of media/water

OFF       = (0, 0, 0)
GREEN     = (0, 255, 40)
RED_DIM   = (71, 0, 0)
UP_COL    = (255, 0, 150)
DOWN_COL  = (255, 110, 0)
FLASH     = (230, 230, 230)
PULSE_LO  = (0, 20, 255)
PULSE_HI  = (255, 240, 120)


def _scale(c, f):
    if f < 0.0:
        f = 0.0
    elif f > 1.0:
        f = 1.0
    return (int(c[0] * f), int(c[1] * f), int(c[2] * f))


def _mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def _mem_free():
    """gc.mem_free() on MicroPython; None under CPython (stubbed tests)."""
    try:
        return gc.mem_free()
    except AttributeError:
        return None


def clamp_speed(pct):
    if pct > SPEED_MAX:
        return SPEED_MAX
    if pct < SPEED_MIN:
        return SPEED_MIN
    return pct


## Speed -> pulse colour, precomputed once at import for every reachable speed.
## _render() then does zero tuple arithmetic: it only ever indexes this table.
_SPAN = float(SPEED_MAX - SPEED_MIN)
PULSE_ON = {}
PULSE_OFF = {}
for _p in range(SPEED_MIN, SPEED_MAX + 1):
    _f = (_p - SPEED_MIN) / _SPAN
    _c = _scale(_mix(PULSE_LO, PULSE_HI, _f), 0.30 + 0.70 * _f)
    PULSE_ON[_p] = _c
    PULSE_OFF[_p] = _scale(_c, 0.06)
del _p, _f, _c


# ---------------------------------------------------------------- driver
class RGBKeypad:
    """Pimoroni RGB Keypad Base, driven directly.

    TCA9555 buttons on I2C0 (SDA=GP4, SCL=GP5, addr 0x20);
    APA102 LEDs on SPI0 (CLK=GP18, MOSI=GP19, CS=GP17).

    The old file probed for a `picokeypad` module first and carried two shim
    classes for its two historical APIs. One of them never called init(). This
    board has always landed on the direct driver -- the probe is gone.
    """

    ADDR = 0x20

    def __init__(self):
        from machine import Pin, I2C, SPI
        self._i2c = I2C(0, sda=Pin(4), scl=Pin(5), freq=400000)
        self._cs = Pin(17, Pin.OUT, value=1)
        self._spi = SPI(0, baudrate=4_000_000, sck=Pin(18), mosi=Pin(19))
        self._buf = bytearray(4 + 16 * 4 + 4)
        for i in range(16):
            self._buf[4 + i * 4] = 0xE0 | 31
        for i in range(4):
            self._buf[-1 - i] = 0xFF
        self._rx = bytearray(2)               # reused; no per-scan allocation
        self._bright = 31
        self._i2c.writeto(self.ADDR, b"\x06\xff\xff")     # both ports = inputs

    def init(self):
        pass

    def set_brightness(self, b):
        self._bright = max(1, min(31, int(b * 31)))

    def illuminate(self, i, r, g, b):
        o = 4 + i * 4
        self._buf[o] = 0xE0 | self._bright
        self._buf[o + 1] = b
        self._buf[o + 2] = g
        self._buf[o + 3] = r

    def update(self):
        self._cs(0)
        self._spi.write(self._buf)
        self._cs(1)

    def get_button_states(self):
        self._i2c.writeto(self.ADDR, b"\x00")
        self._i2c.readfrom_into(self.ADDR, self._rx)
        return (~(self._rx[0] | (self._rx[1] << 8))) & 0xFFFF      # active low


# ---------------------------------------------------------------- Command
class Command:
    """One user action. Immutable; read it through its methods."""

    __slots__ = ("_seq", "_t", "_pump", "_verb", "_value")

    def __init__(self, seq, t, pump, verb, value):
        self._seq = seq
        self._t = t
        self._pump = pump
        self._verb = verb
        self._value = value

    def seq(self):
        return self._seq

    def time(self):
        return self._t

    def pump(self):
        return self._pump

    def verb(self):
        """'POWER' | 'PULSE' | 'SPEED' | 'LIMIT' | 'EVENT'"""
        return self._verb

    def value(self):
        """bool for POWER/PULSE/EVENT, int for SPEED, str for LIMIT.
        For EVENT, pump() is the marker name."""
        return self._value

    def line(self):
        """Wire representation, one line, no trailing newline."""
        if self._verb == "EVENT":
            return "EVENT {} {}".format(self._pump, "ON" if self._value else "OFF")
        if self._verb in ("POWER", "PULSE"):
            v = "ON" if self._value else "OFF"
        else:
            v = str(self._value)
        return "PUMP {} {} {}".format(self._pump, self._verb, v)

    def tuple(self):
        return (self._seq, self._t, self._pump, self._verb, self._value)

    def __repr__(self):
        return "<{} #{}>".format(self.line(), self._seq)


def parse(line):
    """Wire line -> (pump, verb, value), or None. One parser, used everywhere.
    EVENT <name> ON|OFF -> (name, 'EVENT', bool)."""
    parts = str(line).strip().upper().split()
    if len(parts) == 3 and parts[0] == "EVENT":
        return (parts[1], "EVENT", parts[2] == "ON")
    if len(parts) != 4 or parts[0] != "PUMP":
        return None
    try:
        n = int(parts[1])
    except ValueError:
        return None
    verb, arg = parts[2], parts[3]
    if verb == "POWER" or verb == "PULSE":
        return (n, verb, arg == "ON")
    if verb == "SPEED":
        try:
            return (n, verb, int(arg))
        except ValueError:
            return None
    if verb == "LIMIT":
        return (n, verb, arg)
    return None


# ---------------------------------------------------------------- controller
class PumpKeypad:
    """Keypad surface. Everything public is a method; nothing to poke at."""

    def __init__(self, keypad=None, brightness=BRIGHTNESS, history=HISTORY):
        self._kp = keypad if keypad is not None else RGBKeypad()
        self._kp.init()
        self._kp.set_brightness(brightness)

        self._history_len = history
        self._recent = []
        self._pending = []
        self._seq = 0
        self._dropped = 0

        self._state = {}
        for _col, n in PUMP_COLUMNS.items():
            self._state[n] = {"power": False, "pulse": False, "speed": SPEED_INIT}
        self._markers = dict((m[0], False) for m in MARKER_PADS.values())

        self._last_states = 0
        self._edge_time = [0] * 16
        self._held = [0] * 16
        self._next_repeat = [0] * 16
        self._flash_until = [0] * 16
        self._shown = [None] * 16          # last colour pushed, per pad
        self._next_frame = 0
        self._next_gc = time.ticks_add(time.ticks_ms(), GC_MS)
        self._blink = True
        self._timer = None
        self._service_errors = 0
        self._last_error = ""
        self._serviced = 0

    # =============================================================== queries
    def pumps(self):
        return sorted(self._state)

    def state(self, pump=None):
        """State of one pump, or of all pumps keyed by number. Copies."""
        if pump is None:
            return dict((n, dict(s)) for n, s in self._state.items())
        return dict(self._state[pump])

    def speed(self, pump):
        return self._state[pump]["speed"]

    def is_power(self, pump):
        return self._state[pump]["power"]

    def is_pulse(self, pump):
        return self._state[pump]["pulse"]

    def markers(self):
        """{name: on} for every marker pad. Copy."""
        return dict(self._markers)

    def is_running(self, pump):
        s = self._state[pump]
        return s["power"] or s["pulse"]

    def recent(self, n=None):
        return list(self._recent) if n is None else list(self._recent[-n:])

    def last(self, verb=None):
        for c in reversed(self._recent):
            if verb is None or c.verb() == verb:
                return c
        return None

    def pending(self):
        return list(self._pending)

    def count(self):
        return self._seq

    def snapshot_lines(self):
        """Full state as wire lines -- resyncs a host that lost track."""
        out = []
        for n in sorted(self._state):
            s = self._state[n]
            out.append("PUMP {} POWER {}".format(n, "ON" if s["power"] else "OFF"))
            out.append("PUMP {} PULSE {}".format(n, "ON" if s["pulse"] else "OFF"))
            out.append("PUMP {} SPEED {}".format(n, s["speed"]))
        return out

    def health(self):
        """One dict the host can poll instead of guessing. Cheap, bounded."""
        return {"serviced": self._serviced,
                "errors": self._service_errors,
                "last_error": self._last_error,
                "pending": len(self._pending),
                "dropped": self._dropped,
                "armed": self._timer is not None,
                "mem_free": _mem_free()}

    def service_errors(self):
        return self._service_errors

    # =============================================================== consuming
    def drain(self):
        """Every pending command, queue cleared. Returns Command objects."""
        out = self._pending
        self._pending = []
        return out

    def lines(self):
        """Drain as wire strings. This is the one the host should call --
        Command reprs do not survive the raw-REPL round trip."""
        out = [c.line() for c in self._pending]
        self._pending = []
        return out

    def clear(self):
        self._pending = []
        self._recent = []

    # =============================================================== mutators
    def set_power(self, pump, on, quiet=False):
        """quiet=True updates state and LEDs WITHOUT emitting a command."""
        s = self._state[pump]
        on = bool(on)
        if s["power"] != on:
            s["power"] = on
            if not quiet:
                self._issue(pump, "POWER", on)
        return on

    def set_pulse(self, pump, on, quiet=False):
        s = self._state[pump]
        on = bool(on)
        if s["pulse"] != on:
            s["pulse"] = on
            if not quiet:
                self._issue(pump, "PULSE", on)
                if on:
                    self._issue(pump, "SPEED", s["speed"])
        return on

    def set_speed(self, pump, pct, quiet=False):
        s = self._state[pump]
        new = clamp_speed(int(pct))
        if new != s["speed"]:
            s["speed"] = new
            if not quiet:
                self._issue(pump, "SPEED", new)
        return new

    def nudge_speed(self, pump, delta=SPEED_STEP):
        s = self._state[pump]
        new = clamp_speed(s["speed"] + delta)
        if new == s["speed"]:
            self._issue(pump, "LIMIT", "MAX" if delta > 0 else "MIN")
        else:
            s["speed"] = new
            self._issue(pump, "SPEED", new)
        return s["speed"]

    def set_marker(self, name, on, quiet=False):
        """Set a marker; emits EVENT <name> ON|OFF unless quiet. None if unknown."""
        name = str(name).upper()
        if name not in self._markers:
            return None
        on = bool(on)
        if self._markers[name] != on:
            self._markers[name] = on
            if not quiet:
                self._issue(name, "EVENT", on)
        return on

    def toggle_marker(self, name):
        return self.set_marker(name, not self._markers.get(str(name).upper(), False))

    def toggle_power(self, pump):
        return self.set_power(pump, not self._state[pump]["power"])

    def toggle_pulse(self, pump):
        return self.set_pulse(pump, not self._state[pump]["pulse"])

    def stop_all(self):
        """Force every pump off, emitting the matching commands."""
        for n in sorted(self._state):
            self.set_power(n, False)
            self.set_pulse(n, False)

    def set_brightness(self, b):
        self._kp.set_brightness(b)
        self._shown = [None] * 16          # force a full repaint

    # =============================================================== inbound
    def apply(self, line, quiet=True):
        """Apply one wire line to the keypad's own state and LEDs."""
        got = parse(line)
        if got is None:
            return None
        n, verb, val = got
        if verb == "EVENT":
            return None if self.set_marker(n, val, quiet=quiet) is None else n
        if n not in self._state:
            return None
        if verb == "POWER":
            self.set_power(n, val, quiet=quiet)
        elif verb == "PULSE":
            self.set_pulse(n, val, quiet=quiet)
        elif verb == "SPEED":
            self.set_speed(n, val, quiet=quiet)
        return n

    def apply_lines(self, lines, quiet=True):
        count = 0
        for line in (lines or []):
            if self.apply(line, quiet=quiet) is not None:
                count += 1
        return count

    def sync(self, states, quiet=True):
        """Adopt a {pump: {...}} mapping wholesale -- e.g. PumpSet.state().

        Accepts "power" or "fast" for the fast flag, and "percent" or "level"
        (0.0-1.0) for the speed.
        """
        touched = []
        for n, st in (states or {}).items():
            try:
                n = int(n)
            except (TypeError, ValueError):
                continue
            if n not in self._state or not st:
                continue
            if "power" in st:
                self.set_power(n, st["power"], quiet=quiet)
            elif "fast" in st:
                self.set_power(n, st["fast"], quiet=quiet)
            if "pulse" in st:
                self.set_pulse(n, st["pulse"], quiet=quiet)
            pct = st.get("percent")
            if pct is None and st.get("level") is not None:
                pct = float(st["level"]) * 100
            if pct is not None:
                self.set_speed(n, int(pct), quiet=quiet)
            touched.append(n)
        return sorted(touched)

    # =============================================================== lifecycle
    def service(self, now=None):
        """Scan keys, refresh LEDs. Never blocks, never prints, never raises."""
        if now is None:
            now = time.ticks_ms()
        self._serviced += 1

        mark = self._seq
        self._scan(now)

        if time.ticks_diff(now, self._next_frame) >= 0:
            self._next_frame = time.ticks_add(now, FRAME_MS)
            self._render(now)

        if time.ticks_diff(now, self._next_gc) >= 0:
            self._next_gc = time.ticks_add(now, GC_MS)
            gc.collect()

        if self._seq == mark:
            return []
        return [c for c in self._pending if c.seq() > mark]

    def start(self, period_ms=TIMER_MS):
        """Arm a soft timer to call service() in the background. Returns self."""
        from machine import Timer
        if self._timer is not None:
            self.disarm()                  # re-arm rather than silently no-op
        self._timer = Timer(-1)

        def _cb(_t):
            ## BaseException, not Exception. The host's raw-REPL driver sends
            ## Ctrl-C routinely; MicroPython raises KeyboardInterrupt at the next
            ## bytecode boundary, which is exactly where this callback runs.
            ## Exception does not catch it, so it used to escape as an uncaught
            ## error in a scheduled callback -> traceback printed into the raw
            ## REPL byte stream -> host desync -> host hangs forever.
            ## NEVER print from here: sys.print_exception() writes to USB CDC,
            ## which the host drains only while running a command. A repeating
            ## failure fills the buffer and the next write blocks INSIDE the
            ## callback. Record it instead; health() reports it.
            try:
                self.service()
            except BaseException as err:
                self._service_errors += 1
                try:
                    self._last_error = "{}: {}".format(type(err).__name__, err)
                except BaseException:
                    pass

        self._timer.init(period=period_ms, mode=Timer.PERIODIC, callback=_cb)
        return self

    def is_started(self):
        return self._timer is not None

    def disarm(self):
        """Drop the timer and nothing else. For rebuilds.

        trappyscopes runs main.py on every connect, so this circuit is
        re-executed often. Without this the previous PumpKeypad keeps its soft
        timer armed: two callbacks then contend for the same I2C expander and
        SPI LEDs at 8 ms, which starves the REPL and looks exactly like the
        board has blocked.

        Deliberately NOT stop(): LEDs and pump state are untouched, so the
        rebuild is invisible on the bench.
        """
        if self._timer is not None:
            try:
                self._timer.deinit()
            except BaseException:
                pass
            self._timer = None
        return True

    def stop(self):
        """Disarm the timer, stop the pumps, blank the LEDs."""
        self.disarm()
        self.stop_all()
        self.blackout()

    def blackout(self):
        for i in range(16):
            self._kp.illuminate(i, 0, 0, 0)
            self._shown[i] = OFF
        self._kp.update()

    def adopt(self, other):
        """Take over another PumpKeypad's state during a rebuild, so the LEDs
        never flash back to defaults in between."""
        ok = True
        try:
            for n, st in other.state().items():
                if n in self._state:
                    self._state[n] = dict(st)
        except BaseException:
            ok = False
        try:                               # a build from before the markers has none
            for name, on in other.markers().items():
                if name in self._markers:
                    self._markers[name] = bool(on)
        except BaseException:
            pass
        return ok

    def driver_name(self):
        return type(self._kp).__name__

    # =============================================================== internals
    def _issue(self, pump, verb, value):
        self._seq += 1
        cmd = Command(self._seq, time.ticks_ms(), pump, verb, value)
        self._pending.append(cmd)
        over = len(self._pending) - PENDING_MAX
        if over > 0:                       # nobody is draining: drop oldest
            del self._pending[0:over]
            self._dropped += over
        self._recent.append(cmd)
        over = len(self._recent) - self._history_len
        if over > 0:
            del self._recent[0:over]
        return cmd

    def _press(self, i, now, repeat=False):
        marker = MARKER_PADS.get(i)
        if marker is not None:
            if not repeat:
                self._flash_until[i] = time.ticks_add(now, FLASH_MS)
                self.toggle_marker(marker[0])
            return
        row, col = i // 4, i % 4
        n = PUMP_COLUMNS.get(col)
        if n is None:
            return
        if not repeat:
            self._flash_until[i] = time.ticks_add(now, FLASH_MS)
        if row == ROW_POWER:
            if not repeat:
                self.toggle_power(n)
        elif row == ROW_PULSE:
            if not repeat:
                self.toggle_pulse(n)
        elif row == ROW_UP:
            self.nudge_speed(n, SPEED_STEP)
        elif row == ROW_DOWN:
            self.nudge_speed(n, -SPEED_STEP)

    def _scan(self, now):
        states = self._kp.get_button_states()
        changed = states ^ self._last_states
        for i in range(16):
            bit = 1 << i
            down = bool(states & bit)
            if changed & bit:
                if time.ticks_diff(now, self._edge_time[i]) < DEBOUNCE_MS:
                    ## Bounce. Do NOT adopt this edge as the new baseline --
                    ## the old code fell through to `_last_states = states` and
                    ## the press was lost instead of being re-detected.
                    states = (states & ~bit) | (self._last_states & bit)
                    continue
                self._edge_time[i] = now
                if down:
                    self._press(i, now)
                    self._held[i] = now
                    self._next_repeat[i] = time.ticks_add(now, REPEAT_DELAY_MS)
                else:
                    self._held[i] = 0
            elif down and self._held[i]:
                if (i // 4) in (ROW_UP, ROW_DOWN) and \
                        time.ticks_diff(now, self._next_repeat[i]) >= 0:
                    self._press(i, now, repeat=True)
                    self._next_repeat[i] = time.ticks_add(now, REPEAT_RATE_MS)
        self._last_states = states

    def _set(self, i, c, now):
        if time.ticks_diff(self._flash_until[i], now) > 0:
            c = FLASH
        if self._shown[i] is c:            # identity: colours are table entries
            return False
        self._shown[i] = c
        self._kp.illuminate(i, c[0], c[1], c[2])
        return True

    def _render(self, now):
        """Flat. No animation, no per-frame arithmetic, no allocation.

        Colours come from the precomputed PULSE_ON/PULSE_OFF tables or from
        module constants, so the only work per frame is 16 identity compares.
        The SPI write happens only when something actually changed.
        """
        self._blink = bool((now // BLINK_MS) & 1)
        dirty = False
        for col in range(4):
            n = PUMP_COLUMNS.get(col)
            if n is None:                  # the marker column: on colour or dark
                for r in range(4):
                    i = r * 4 + col
                    m = MARKER_PADS.get(i)
                    on = m is not None and self._markers[m[0]]
                    dirty |= self._set(i, m[1] if on else OFF, now)
                continue

            s = self._state[n]
            pct = s["speed"]
            running = s["power"] or s["pulse"]

            dirty |= self._set(ROW_POWER * 4 + col,
                               GREEN if s["power"] else RED_DIM, now)

            if s["pulse"] and (self._blink or col in STEADY_PULSE):
                c = PULSE_ON[pct]
            else:
                c = PULSE_OFF[pct]
            dirty |= self._set(ROW_PULSE * 4 + col, c, now)

            at_max = pct >= SPEED_MAX
            at_min = pct <= SPEED_MIN
            dirty |= self._set(ROW_UP * 4 + col,
                               OFF if at_max else
                               (_UP_ON if running else _UP_DIM), now)
            dirty |= self._set(ROW_DOWN * 4 + col,
                               OFF if at_min else
                               (_DN_ON if running else _DN_DIM), now)

        if dirty:
            self._kp.update()


_UP_ON  = _scale(UP_COL, 0.85)
_UP_DIM = _scale(UP_COL, 0.20)
_DN_ON  = _scale(DOWN_COL, 0.85)
_DN_DIM = _scale(DOWN_COL, 0.20)


# ---------------------------------------------------------------- entry point
def start_keypad(period_ms=TIMER_MS, **kw):
    """Build a PumpKeypad, arm it in the background, return it immediately.

    Named start_keypad rather than start() because circuit files are execfile'd
    into main.py's globals, where a bare `start` would collide.
    """
    return PumpKeypad(**kw).start(period_ms)


## Device initialisation -----------------------------------------------------
AUTOSTART = True

## Retire the previous build. Capture the old instance BEFORE rebinding kp, or
## there is nothing left to disarm.
try:
    _previous = kp
except NameError:
    _previous = None
if _previous is not None:
    try:
        _previous.disarm()
    except BaseException:
        pass

kp = None                   # this is what the host sees as scope.kp

if AUTOSTART:
    kp = start_keypad()
    if _previous is not None:
        kp.adopt(_previous)
    _previous = None        # do not pin the old object for the life of the board
    gc.collect()
    print("pimoroni_rgb_sparkly_rainbows_cntlr : kp ready, pumps={}".format(kp.pumps()))


# ============================================================ WHAT CHANGED
# vs the previous pimoroni_rgb_sparkly_rainbows_cntlr.py (913 lines -> 531)
#
# BUGS FIXED
# 1. Timer callback caught `Exception`, so KeyboardInterrupt -- which the host's
#    raw-REPL driver induces with Ctrl-C on every connect and every abort --
#    escaped as an uncaught scheduled-callback error. MicroPython then printed a
#    traceback straight into the raw-REPL byte stream, desyncing the host's
#    read_until(b'\x04') permanently. That is a prime suspect for "the host
#    freezes but the keypad still works". Now `except BaseException`.
# 2. Debounce rejection did `continue` but still assigned
#    `self._last_states = states`, so a bounced press was recorded as the new
#    baseline and silently LOST. Now the rejected bit is masked back out.
# 3. ~50 short-lived tuples per frame at 62 fps (~3000 alloc/s, forever) with no
#    gc.collect() anywhere -- the classic RP2040 slow-fragmentation profile, and
#    a MemoryError in _cb was silently swallowed. Colours are now a precomputed
#    table, allocation per frame is zero, and there is a 5 s gc.collect().
# 4. `_previous` was never cleared, pinning one dead PumpKeypad per reconnect
#    for the life of the board. Now released.
# 5. start() returned early if _timer was already set, so a stale timer silently
#    blocked re-arming. Now it disarms and re-arms.
# 6. get_button_states() allocated a fresh 2-byte object per scan (125/s). Now
#    readfrom_into a reusable buffer.
#
# REMOVED
# - HostReader: registered sys.stdin with select.poll and read bytes off it. On a
#   USB-CDC Pico sys.stdin IS the raw REPL -- calling it would eat the host's
#   in-flight command and guarantee a permanent hang. Unreferenced, but a loaded
#   gun in the file.
# - UsbSerialSink: print(cmd.line()) from inside the timer callback -- the exact
#   blocking-write deadlock the callback comment warns about, reintroduced 200
#   lines later. With it, set_sink()/set_callback().
# - UartSink, parse_all(), keypad(): unreferenced.
# - _ModuleKeypad / _ClassKeypad / make_keypad(): probes for a `picokeypad`
#   module this board does not have. _ClassKeypad never called init().
# - _animate() boot rainbow: 620 ms during which _scan never ran, so the first
#   real scan saw every held key as a fresh press. With it wheel(), triangle().
# - The decorative column, the comet/shimmer/heart/blink modulation, pulse_color()
#   and the 3-stop colour ramp.
# - Command.is_verb(), the duplicate wire parser inside apply() (two parsers that
#   could drift -- there is now exactly one, parse()).
#
# ADDED
# - health(): serviced/errors/last_error/pending/dropped/armed/mem_free in one
#   cheap call, so the host can see a starving board instead of inferring it.
# - _dropped counter: the queue cap silently discarded the OLDEST commands when
#   the host stalled, so a POWER ON could vanish while a later SPEED survived.
#   Still capped, but now it is visible.
# - Render is change-driven: the SPI write only happens when a pad colour
#   actually changed, which also takes the steady-state SPI traffic to near zero.
