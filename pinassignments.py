import board


if board.circuit_id == "4ch_pwm_sc1":
    light = {
        "red_pin"   : 9,
        "green_pin" : 10,
        "blue_pin"  : 12,
        "white_pin" : 16,
    }
    
    beacon = 14

    sensors = {
        "tandh"  : 15
    }


