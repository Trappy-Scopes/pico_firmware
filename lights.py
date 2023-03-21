from machine import Pin, PWM
import utime
# The same PWM output can be selected on two GPIO pins; the same signal
# will appear on each GPIO.



# GPIO Pin numbers not board numbers
d1_redPIN = 16
d1_greenPIN = 18
d1_bluePIN = 15


class Lights:
    
    def __init__(self, redPIN, greenPIN, bluePIN):
        self.pin_map = {'r': redPIN, 'g': greenPIN, 'b': bluePIN}
        self.ch_map = {'r': None, 'g': None, 'b': None}
        self.turn_on('r')
        self.turn_on('g')
        self.turn_on('b')
        
        self.sweep_ch()
        self.setVs(0,0,0)

    def turn_off(self, channel):
        """
        Turns off the PWM channel by setting the pin to GPIO.HIGH mode.
        """
        if channel in ['r', 'g', 'b']:
            if isinstance(ch_map[channel], PWM):
                self.ch_map[channel].deinit()
                print(isinstance(self.ch_map[channel], PWM))
            self.ch_map[channel] = Pin(self.pin_map[channel], mode=Pin.OUT)
            self.ch_map[channel].on()
    
    def turn_on(self, channel):
        """
        Initializes the PWM channel on the given channel and sets the frequency.
        """
        if channel in ['r', 'g', 'b']:
            self.ch_map[channel] = PWM(Pin(self.pin_map[channel], mode=Pin.OUT))
            self.ch_map[channel].freq(int(30*1e5))
            self.setV(channel, 0)
            #ch_map[channel].freq(int(10))


    def setV(self, channel, volt):
        """
        Sets the channel voltage in inverse PWM gating mode.
        """
        if channel in ['r', 'g', 'b']:
            dutycycle_u16 =  65535 - int(float(volt)/3.3*65535)
            self.ch_map[channel].duty_u16(int(dutycycle_u16))
        
    def sweep_ch(self):
        for channel in ['r', 'g', 'b']:
            i = 0
            while i <= 3.3: 
                self.setV(channel, i)
                utime.sleep(0.05)
                i = i + 0.1
                
            while i >= 0:
                self.setV(channel, i)
                utime.sleep(0.05)
                i = i - 0.1
            
    def set_max(self, channel):
        if channel in ['r', 'g', 'b']:
            self.turn_off(channel)
            self.ch_map[channel].off()
        
        
    def setVs(self, rV, gV, bV):
        self.setV('r', rV)
        self.setV('g', gV)
        self.setV('b', bV)
    
        
if __name__ == '__main__':
    turn_on('r')
    turn_on('g')
    turn_on('b')
    print(get_temp_humidy())

    
    
    
