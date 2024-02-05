from machine import PWM, Pin, ADC
import math

# Will return a integer
def convert(x, in_min, in_max, out_min, out_max):
    return (x - in_min) * (out_max - out_min) // (in_max - in_min) + out_min

class DCMotor:
    
    def __init__(fwdpin, revpin):
        self.pin_no = {"fwd": fwdpin, "rev":revpin}
        self.fwdpin = PWM(Pin(fwdpin))
        self.fwdpin = PWM(Pin(revpin))
        
        self.fwdpin.freq = 1000 #1k Hertz
        self.revpin.freq = 1000
        
        self.dir = +1
        self.duty = 0 # range: 0-65535
        self.speed_ = 0 #Here, defined only when self.duty == 0.
        self.fwdpin.duty_u16(self.duty)
        self.revpin.duty_u16(self.duty)
        
    def speed():
        return self.dir * self.speed_
        
    def speed(unit_speed):
        unit_speed = math.fabs(unit_speed)
        unit_speed = unit_speed * (unit_speed <= 1.0) + 1 * (unit_speed > 1.0)
        
        ## Map speed and set
        self.speed_ = unit_speed
        self.duty = convert(unit_speed, 0.0, 1.0, 0, 65535)
        if self.dir == 1:
            self.revpin.duty_u16(0)
            self.fwdpin.duty_u16(self.duty)
        elif self.dir == -1:
            self.fwd.duty_u16(self.duty)
            self.revpin.duty_u16(0)
        
    def min_speed(speed):
        self.set_speed(0.05)
        
    def max_speed(speed):
        self.set_speed(1.0)
        
    def fwd(speed=None):
        self.dir = 1
        if speed:
            self.set_speed(speed)
            
    def rev(speed=None):
        self.dir = -1
        if speed:
            self.set_speed(speed)
            
    def hold():
        self.fwdpin.duty_u16(65535)
        self.revpin.duty_u16(65535)
        
    def release():
        self.fwdpin.duty_u16(0)
        self.revpin.duty_u16(0)
        
    def set_speed_controller(pot_pin):
        self.pot = ADC(Pin(potpin, PIN.IN))
        def speedcontrol():
            read = self.pot.read_u16()
            self.set_speed(convert(read))
        self.feedback = Timer(period=100, mode=Timer.PERIODIC, \
                                    callback=speedcontrol)
    
    def unset_speed_controller():
        self.feedback.deinit()
        