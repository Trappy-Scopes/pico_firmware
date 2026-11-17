from machine import RTC, Timer
from neopixel import NeoPixel

from pico_firmware._logger import Logger as Log

"""
TODO
----

1. Implement Finite Cycles
2. Possibility of having multiple schedules. Name based file assignments.
3. Status sheet for LCD display
"""

class CircadianScheduler:
    """
    Sets up Circadium Rhythm Scheduler.
    lightmatrix: Neopixel Array to control
    buzzer: used for auditary feedback on processes.
    """
    ## Set by the circuit file on a watchdog reset, shown in the 30 s status line.
    boot_tag = ""

    ## Set by the circuit file's heartbeat: filesystem headroom.
    fs_tag = ""

    def __init__(self, lightmatrix, name=None, day_start=[8,0], night_start=[20,0],
                 lightmap={"day" :[255, 255, 255], "night" :[0, 0, 0]},
                    bomdia=None, bonnoite=None, buzzer=None

                 ):
        
        self.name = name
        self.lightmatrix = lightmatrix
        ## Is a list now -> this means that multiple displays can be updated.
        self.partitions = []


        ## Assume infinite cycles or that the object has to be stopped.
        self.lightmap = lightmap
        self.day_start   = day_start   # hh, mm
        self.night_start = night_start # hh, mm
        
        if not bomdia:
            self.bomdia = lambda lightmatrix: lightmatrix.fill(self.lightmap["day"])
        else:
            self.bomdia = bomdia
        if not bonnoite:
            self.bonnoite = lambda lightmatrix: lightmatrix.fill(self.lightmap["night"])
        else:
            self.bonnoite = bonnoite

        self.rtc = RTC()
        self.timer = Timer()
        ## Pass buzzer= explicitly; otherwise fall back to the old PIO Beacon.
        if buzzer is not None:
            self.buzzer = buzzer
        else:
            from pico_firmware.beacon import Beacon
            self.buzzer = Beacon.current
        
        self.is_active = True
        self.phase_map = {"day": 0, "night": 1}
        

        ## Status
        self.status = {"phase": "day", "active": True}

        
        
        # Bookeeping and Interrupt Usage
        self.last_day_callback = (0,0,0,0,0,0,0,0)
        self.last_night_callback = (0,0,0,0,0,0,0,0)
        
        ### If we assume that the incubator divides the y
        self.time_based(self.day_start, self.night_start)
          
    
    def time_based(self, day_start, night_start, cycles=0):
        """
        Set a time based Schedule.
        Input [hours, minute]s in 24 hour format.
        cycles = 0 : Run cycle forever.
        """
        self.last_day_callback = (0,0,0,0,0,0,0,0)
        self.last_night_callback = (0,0,0,0,0,0,0,0)
        
        #--------
        def str_to_time(string):
            # Format should be hh:mm
            if isinstance(string, list):
                return string
            
            
            string = string.strip(" ").split(",")
            time_ = [int(t) for t in string]
            return time_[:2]
        
        def is_valid_time(time):
            return (time[0] >= 0 and time[0] <= 23) and \
                   (time[1] >= 0 and time[1] <= 60)
        #--------

        day_start = str_to_time(day_start)
        night_start = str_to_time(night_start)
      
        if is_valid_time(day_start) and is_valid_time(night_start):
            self.day_start   = day_start
            self.night_start = night_start
            self.cycles      = cycles
            self.remaining_cycles = self.cycles
            if self.cycles == 0:
                self.remaining_cycles = 2000
            Log.write("out", f"Set Circadium Scheduler: {self.day_start}, {self.night_start}, {self.cycles}")
        else:
            Log.write("out", "Invalid time entry!")
            self.buzzer(count=10)
            return
          
        #with open("/vault/circadium.config") as file:
        #    file.write(f"{day_start}\n{night_start}\n{cycles}\n")
        #    self.is_active = True
            
        # Set the current state as per the time
        now = self.rtc.datetime()
        if self.phase_detect(now) == "day":
            Log.write("out", "Phase detection: day")
            self.__set_day__(now)
        elif self.phase_detect(now) == "night":
            Log.write("out", "Phase detection: night")
            self.__set_night__(now)
        else:
            Log.write("out", "Could not detect phase.")
    
    
    def set_from_config(self):
        """
        Sets time values from the circadium.config state file.
        """
        data = None
        with open("/vault/circadium.config") as file:
            data = file.read()
        data.rstrip("\n")
        
        lines = data.split("\n")
        lines = [line.lstrip("[").rstrip("]") for line in lines]
        self.time_based(lines[0], lines[1], cycles=int(lines[2]))
        

            

    # ------------
    def __set_day__(self, now):    
        print("Bom Dia!")
        if self.buzzer:
            try:
                self.buzzer.pulse(5)
            except BaseException as e:
                print("buzzer failed:", e)
        
        self.bomdia(self.lightmatrix)

        self.lightmatrix.write()
        self.phase = "day"
        Log.write("out", f"Transitioning to day light conditions: {self.lightmap['day']}")
        self.last_day_callback = now
        self.remaining_cycles = float(self.remaining_cycles) - 0.5
        
    def __set_night__(self, now):
        #print("diff", self.__minute_diff__(now, self.last_night_callback))
        print("Boa Noite!")
        if self.buzzer:
            try:
                self.buzzer.pulse(5)
            except BaseException as e:
                print("buzzer failed:", e)
        
        self.bonnoite(self.lightmatrix)
        
        self.lightmatrix.write()
        self.phase = "night"
        Log.write("out", f"Transitioning to night light conditions: {self.lightmap['night']}")
        self.last_night_callback = now
        self.remaining_cycles = float(self.remaining_cycles) - 0.5
        
    def desired_phase(self, now):
        """The phase the wall clock implies right now.

        Pure function of the time: no memory, no edges, no windows. This is
        what makes the scheduler self-healing - a callback that arrives late,
        or a board that reboots at 03:00, still computes the right answer.
        """
        mins = now[4] * 60 + now[5]
        day = self.day_start[0] * 60 + self.day_start[1]
        night = self.night_start[0] * 60 + self.night_start[1]

        if day == night:
            return "day"
        if day < night:
            ## Daylight window sits inside one calendar day.
            if day <= mins < night:
                return "day"
            return "night"
        ## Daylight window wraps past midnight.
        if mins >= day or mins < night:
            return "day"
        return "night"

    def phase_detect(self, now):
        return self.desired_phase(now)
            
     
    def __minute_diff__(self, t1, t2):
        """
        Outputs t1 - t2 in minutes.Only [hh,mm]'s difference is calculated.
        time values can be machine.RTC() datetime tuple or [hh,mm].
        """
        def selector(time):
            if len(time) == 2:
                return time
            else: # Assume machine.RTC() datetime tuple
                return (time[4], time[5])
        t1 = selector(t1)
        t2 = selector(t2)
        
        diff = ((t2[0]*60)+t2[1]) - ((t1[0]*60)+t1[1])
        
        hours_diff = (t1[0] - t2[0] + 24) % 24
        min_diff = (t1[1] - t2[1] + 60) % 60
        #return (hours_diff * 60) + min_diff
        #print(diff)
        return diff
    
    
    def set_timers(self, mode="short"):
        """
        Set a timer to query scheduler state.
        mode == "short" : queries state every config.cs_callback_s seconds.
        mode == "long"  : executes two callbacks every single cycle based on
                           precise time calculations. [TODO]
        """
        if mode == "short":
            self.timer.init(mode=Timer.PERIODIC, period=30*1000, callback=self.short_callback)
            Log.write("out", f"Timer for Circadium Scheduler set: {self.timer}")
        
        elif mode == "long":
            
            # Determine what mode it is now
            # Flick the phase switch
            # setup timer
            
            Log.write("out", "CircadiumScheduler: Timer mode long is not implemented.")
            return
            

    def short_callback(self, timer):
        """Level-triggered: compare wanted phase to applied phase, correct.

        The previous version was edge-triggered - it only acted if a callback
        happened to land in the single minute containing a transition. On
        2026-08-26 the 20:00 tick was missed and the lights stayed on for
        10h24m, until a chance reboot. Here a missed tick costs 30 seconds.
        """
        now = self.rtc.datetime()
        print("to day: %d min | to night: %d min%s%s" % (
            self.__minute_diff__(now, self.day_start),
            self.__minute_diff__(now, self.night_start),
            self.fs_tag, self.boot_tag))

        if not self.is_active:
            return

        want = self.desired_phase(now)
        if want != getattr(self, "phase", None):
            if want == "day":
                self.__set_day__(now)
            else:
                self.__set_night__(now)

        if self.remaining_cycles <= 0:
            self.is_active = False
