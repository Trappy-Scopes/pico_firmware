# receiver.py / Tx/Rx => Tx/Rx
import os
import machine
from time import sleep
import _thread
from machine import Pin

global buffer
buffer = []

def start_comms():
    uart = machine.UART(0, 115200)
    print(uart)
    b = None
    msg = ""
    while True:
        sleep(1)
        if uart.any():
            b = uart.readline()
            print(type(b))
            print(b)
            try:
                msg = b.decode('utf-8')
                print(type(msg))
                print("rec>> " + msg)
                buffer.append(msg)
            except:
                pass

if __name__ == "__main__":

    _thread.start_new_thread(start_comms, ())
    print("Thread executed")
    led = Pin("LED", Pin.OUT)
    while True:
        sleep(1)
        led.toggle()
    