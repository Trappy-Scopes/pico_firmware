
"""
Used to indicate whether power was on in case UV lamp is used.
"""

pins = {"relay" : 14,
        "buzzer" : 20,
        "lightmatrix" : 0, 

        #mosfet : 27
        "tanh1" : 14,
        "tanh2" : 27,

        "sw1" : 15,
        "sw2" : 17,
    }


from pico_firmware.beacon import Beacon
global buzzer
buzzer = Beacon(pins["buzzer"])

buzzer.pulse(3)

