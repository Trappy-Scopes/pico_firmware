import board
import rtc

rtc = RTC()
class Handshake:

    def intro():
        return "device: {}, uuid: {}, rtc: {}".format( \
               board.name, board.uuid, rtc.datetime())

    def handshake():
        print(f"Hello I am {board.name}! At your service.")