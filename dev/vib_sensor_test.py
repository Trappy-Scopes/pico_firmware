from machine import ADC
from utime import sleep


vib = ADC(28)
for i in range(50000):
    print(vib.read_u16())
    sleep(0.05)