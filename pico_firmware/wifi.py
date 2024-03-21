"""
Wireless connection code.
"""


import time
import network
from machine import Pin
import secrets
import ubinascii
import urequests
import gc

class Wifi:
    def __init__(self):
        pass
    def connect(self, ssid, password):
        pass
    def disconnect(self):
        pass
    def reconnect(self, delay=0):
        pass
    
    
    def info(self):
        return {"ssid": self.ssid, "ip":self.ip, "mac": self.mac, 
               "connected": self.connected, 
               "elapsed_ms": time.ticks_ms() - self.connected_ms_tick
               }

    def list_nets(self):
        """
        Lists all wifi networks that can be detected by the pico board.
        """
        nets = self.wlan.scan()
        return nets
        
    def ifconfig(self):
        return self.wlan.ifconfig()