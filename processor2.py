from dtsync import dt_sync_callback
import urequests

"""
Processor 2 standard operations
"""

from machine import Pin
import gc
import math
import time
import webrepl

def processor2():
    tick_duration_ms = 500
    total_ms_ticks_in_a_day = 86,400,000
    
    ## Resource Setup
    onboardled = Pin('LED', mode=Pin.OUT)
    onboardled.on()
    gc.enable()
    
    processor_2_stop = False
    global buzzer, wifi, rtc, device_status_str
    
    
    ## Establish Wifi connection
    wifi_reconn_counter = 0
    global wifi
    import secrets
    wifi.connect(secrets)
    
    if wifi.connected:
        print(wifi.info())
        dt_sync_callback(True)
        webrepl.start()
    ########
    
    while not processor2_stop:
        start_time = time.ticks_ms()
        
        # LED Blink Counter
        if not wifi.connected:
            onboardled.on()
        else:
            onboardled.toggle()
        
        ### Attempt LED Reconnection
        if not wifi.connected:
            wifi_reconn_counter = wifi_reconn_counter + 1
            print(f"Wifi Reconnection counter: {counter}.")
            wifi.connect(secrets)
            
            if wifi.connected:
                Log.write("out", f"On Processor 2, wifi connected: {wifi.info()}.")
                dt_sync_callback(True)
                webrepl.start()
            else:
                if wifi_reconn_counter == 5: # Reset Device - if counter exceeds 5.
                    buzzer.blink()
                    Log.write("out", "Unable to connect to Wifi. Auto-Reseting device.")
                    machine.reset()
        
        ### Date Time Synchronisation Callback
        if dtsync_callback_flag == True:
            try:
                dt_sync_callback(True)
            except:
              Log.write("out", f"On Processor 2, DTSync Failed.")  

        

        ### Garbage Collection
        gc.collect()
        ###
        
        
        ### Process Requests
        #TODO
        ###
        
        ### Appropriate Tick dealy
        end_time = time.ticks_ms()
        if not end_time - start_time >= tick_duration_ms:
            time.sleep(tick_duration_ms - math.fabs(end_time - start_time))


