import subprocess
import sys
import time
from serial.tools import list_ports
import time

FEATHER_ID = 0x239A #Adafruit vendor ID for the radiofeather
BAUD = 115200

def find_feather():
    for port in list_ports.comports():
        if port.vid == FEATHER_ID:
            return port.device
    return None

feather_port = find_feather()

if feather_port is None:
    print("Feather not found. Check USB or try a different port.")
    while feather_port is None:
        time.sleep(1)
        feather_port = find_feather()

print(f"Feather found at: {feather_port}")

subprocess.run([sys.executable, "-m", "serial.tools.miniterm", feather_port, str(BAUD)])

