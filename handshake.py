import board
from machine import RTC

rtc = RTC()
class Handshake:

    def intro():
        return "device: {}, uuid: {}, circuit: {}, rtc: {}".format( \
               board.name, board.uuid, board.circuit_id, rtc.datetime())

    def handshake():
        print(f"Hello I am {board.name}! At your service.")