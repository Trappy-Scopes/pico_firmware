import ntptime
from logger import Logger as Log
from machine import RTC
from wifi import Wifi

# Clock synchronisation ----------------------------------------------    T2   ||  Timer 0
def dt_sync_callback(timer):
    global rtc
    if Wifi.connected:
        Log.write("dtsync", "Local time before synchronization：%s" %str(rtc.datetime()))
        ntptime.settime()
        now = list(rtc.datetime())
        now[4] = (now[4] + 1) %24 #UTC+1 Timezone correction
        rtc.datetime(now)
        print("Local time after synchronization：%s" %str(rtc.datetime()))
        Log.write("dtsync", "RTC synchronized by NTP server.")
