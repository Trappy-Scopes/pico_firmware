import dht
import machine
import utime
from pins import *

def get_temp_humidy():
    d = dht.DHT11(machine.Pin(TEMP_HUM_PIN))
    d.measure()
    return {"temp": d.temperature(), "humidity":d.humidity()}