## !!! Changes sync globally across all devices
## !!! Do not block the REPL for long

"""
Stand main executable for all standard pico devices.
"""


import os
from machine import Pin, PWM
from time import sleep
from pico_firmware.handshake import Handshake

## 0. Print welcome message
print("Executing default main.py: pico_firmware/main.py")

### 1. Verify required files -----------------------------
### Construct boot and webrepl config
if "boot.py" not in os.listdir("/"):
    with open("boot.py", "w") as f:
        f.write("import webrepl\nwebrepl.start()\n") 

if "webrepl_cfg.py" not in os.listdir("/"):
    with open("webrepl_cfg.py", "w") as f:
        f.write("PASS = \'trappy_cr\'\n")

if "board.py" not in os.listdir("/"):
    with open("board.py", "w") as f:
        f.write('name = \"picodev\" \ncircuit_id = \"idle_device_that_blinks\"')

### -----------------------------------------------------
import board
import pico_firmware.pinassignments as pins


### 2. processor-2 instruction execution-----------------
import _thread
#processor2_thread = _thread.start_new_thread(processor2, ())      
# -------------------------------------------------------        

### 3. Common Resources ---------------------------------
#from sensor import Sensor
#sensors = Sensor()
#--------------------------------------------------------

## 4. Device Initalisation ------------------------------

# cid : 0
if board.circuit_id == "idle_device_that_blinks":
    print("main.py : Device initalised as : idle_device_that_blinks")
    led = Pin("LED", Pin.OUT)
    i = 0
    while i < 10:
        led.toggle()
        sleep(0.5)
        i = i + 1

# cid : 1

if "4ch_voltctrl_pwm_v1_proto" in board.circuit_id:
    if "cc" in board.circuit_id:
        # Common Cathode Mode
        print("main.py : Device initalised as : 4ch_voltctrl_pwm_v1_proto_cc")
        from peripherals.lights.cc_pwm_rgb_led import CcPwmRgbLed
        lit = CcPwmRgbLed(pins.light["red_pin"], pins.light["green_pin"], \
                          pins.light["blue_pin"])
    else:
        # Common Anode Mode
        print("main.py : Device initalised as : 4ch_voltctrl_pwm_v1_proto_ca")
        from peripherals.lights.ca_pwm_rgb_led import CaPwmRgbLed
        lit = CaPwmRgbLed(pins.light["red_pin"], pins.light["green_pin"], \
                          pins.light["blue_pin"])
    
    from beacon import Beacon
    beacon = Beacon(pins.beacon)
    
    from sensors.tandhsensor import TandHSensor
    tandh = TandHSensor(pins.sensors["tandh"], "dh11")
    
    #sensors.append(tandh)

# cid : 2   
if board.circuit_id == "4_6_clustcontrol_v1_proto":
    rpi1 = RPiController(pins.rpictrl[1]["RUN"], pins.rpictrl[1]["GLOBAL_EN"])
    rpi2 = RPiController(pins.rpictrl[2]["RUN"], pins.rpictrl[2]["GLOBAL_EN"])
    rpi3 = RPiController(pins.rpictrl[3]["RUN"], pins.rpictrl[3]["GLOBAL_EN"])
    rpi4 = RPiController(pins.rpictrl[4]["RUN"], pins.rpictrl[4]["GLOBAL_EN"])
    rpis = {}
    rpis[1] = rpi1; rpis[2] = rpi2; rpis[3] = rpi3; rpis[4] = rpi4
    from beacon import Beacon
    beacon = Beacon(pins.buzzer)
    
    from sensors.tandhsensor import TandHSensor
    tandh = TandHSensor(pins.sensors["tandh"], "dh11")
    
# cid : 3
if board.circuit_id == "2ch_peristat_kitroniks_vx_shield":
    
    ## Motor object
    from actuators.dcmotor import DCMotor
    motor = DCMotor(pins.fwdpin, pins.revpin)
    ## TODO motor 2
    motor.set_speed_controller(pin.potentiometer)
    motor1 = motor
    motor2 = None
    motors = [motor1, motor2]

   
if board.circuit_id == "4ch_peristatpump_v1_proto":
    pass
#---------------------------------------------------------



### ---- Test stuff

#from processor2 import processor2
#import secrets


#from lights import LightSelector
#from wifi import Wifi

## Wifi
#wifi = Wifi(secrets)
#beacon = Beacon(14)

## Start Processor 2 thread
#processor2_thread = _thread.start_new_thread(processor2, ())


## Light
#lit = LightSelector(deviceid)


## TandH
#if tandh in deviceid:
#	tandh = TandHSensor(pinassignments.sensors.tandh, "dh11")

from pico_firmware.beacon import Beacon
beacon = Beacon(14)
beacon.blink()
from machine import Pin
power = Pin(17, mode=Pin.OUT)
power.on()
#beacon.pulse(15)
beacon2 = Beacon(16)
#beacon3 = Beacon(12)
beacon2.blink()
