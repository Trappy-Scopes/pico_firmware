import dht
import machine
import utime

TEMP_HUM_PIN = 14
def get_temp_humidy():
    d = dht.DHT11(machine.Pin(TEMP_HUM_PIN))
    d.measure()
    return {"temp": d.temperature(), "humidity":d.humidity()}