import board
from machine import RTC
import machine
import ubinascii


rtc = RTC()
class Handshake:
    uuid = ubinascii.hexlify(machine.unique_id()).decode()

    def intro():
        return "device: {}, uuid: {}, circuit: {}, rtc: {}".format( \
               board.name, Handshake.uuid, board.circuit_id, rtc.datetime())

    def hello():
        print(f"Hello I am {board.name}! - [{Handshake.uuid}]")
        
    def obj_list():        
        all_ = globals()
        objects = [obj for obj in all_ \
                   if  "class" in str(all_[obj])]
        exclusion_list = ['__thonny_helper']
        for obj in exclusion_list:
            if obj in objects:
                objects.remove(obj)
        return objects