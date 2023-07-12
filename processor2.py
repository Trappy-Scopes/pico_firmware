from dtsync import dt_sync_callback
import urequests

global processor2_stop, device_status_str
processor2_stop = False
device_status_str = ""

def processor2():
    global processor2_stop, push_not_flag, buzzer, wifi, device_status_str, rtc
    
    wifi_reconn_counter = 0

    not_counter = 0
    max_not_counter = int(60 * 0.1)

    while True:
        if not wifi.connected:
            wifi_reconn_counter = wifi_reconn_counter + 1
            import secrets
            print(f"Wifi Reconnection counter: {counter}.")
            wifi.connect(secrets)
            time.sleep(0.5)
            if wifi.connected:
                Log.write("out", f"On Processor 2, wifi connected: {wifi.info()}.")
                dt_sync_callback(True)            
            else:
                if wifi_reconn_counter == 5: # Reset Device - if counter exceeds 5.
                    buzzer.buzz()
                    Log.write("out", "Unable to connect to Wifi. Auto-Reseting device.")
                    machine.reset()          
        else:
            time.sleep(0.5)

            # Process other requests



            # Push device status - Periodic Notificationss
            #message = f"RTC:{rtc.datetime()}"
            if not_counter >= max_not_counter:
            	not_counter = 0
            	message = device_status_str
            	message = str(rtc.datetime())
                title = "Trappy-Systems-Generic-Device"
                req = "https://api.pushover.net/1/messages.json?token={}&user={}&title={}&message={}".format(\
                	  secrets.not_token, secrets.not_user_key, title, message)
                response = urequests.post(req)
                print(response)
            else:
            	not_counter += 1





