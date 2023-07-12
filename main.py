import _thread
from processor2 import processor2
import secrets
from wifi import Wifi

wifi = Wifi(secrets)
processor2_thread = _thread.start_new_thread(processor2, ())
