import os



### --- Device unique ID ---
import machine
import ubinascii
duid = ubinascii.hexlify(machine.unique_id()).decode()
print("Device Unique ID (DUID):", duid)




### --- resolve main.py file ----
default_main = "execfile(\'pico_firmware/main.py\')"
if "main.py" not in os.listdir("/"):
    print("No specialised main.py file found: executing pico_firmware/main.py")
    with open("main.py", "w") as f:
        f.write(default_main)


### --- start webrepl ----
#import webrepl
#print("boot.py : Starting webrepl")
#webrepl.start()
