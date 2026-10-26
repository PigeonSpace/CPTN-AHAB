import serial
from serial.tools import list_ports 
from datetime import datetime, timezone
import os
import time

FEATHER_ID = 0x239A #Adafruit vendor ID for the radiofeather
BAUD = 115200
LOG_DIR = os.path.expanduser("~/Documents/AHAB/Flight Logs/RAW")
RETRY_SECONDS = 2

def find_feather():
    for port in list_ports.comports():
        if port.vid == FEATHER_ID:
            return port.device
    return None

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def write_log(text): #timestamps every line, prints to terminal, and writes to disk immediately
    stamped = f"{utc_now()} {text}"
    print(stamped)
    try:
        with open (log_path, "a") as f:
            f.write(stamped + "\n")
            f.flush()
            os.fsync(f.fileno())
    except OSError as error:
        print(f"Log write failed: {error}")

#create the log folder if it doesn't already exist

os.makedirs(LOG_DIR, exist_ok=True)

filenamecounter=1
while True:
    log_path = os.path.join(LOG_DIR, f"groundlog{filenamecounter}.log")
    try:
        with open(log_path, "x") as f:
            f.write(f"Log file created at: {utc_now()}\n")
        print(f"Log file created at: {log_path}")
        break
    except FileExistsError:
        filenamecounter += 1

ser = None
feather_port = None

while True:
    try:  #searching for the feather whenever it isn't connected
        if ser is None:
            feather_port = find_feather()
            if feather_port is None:
                print("Waiting for Feather...")
                time.sleep(RETRY_SECONDS)
                continue
            ser = serial.Serial(feather_port, BAUD, timeout=1)
            write_log(f"---Connected to port {feather_port}---")

        raw = ser.readline()
        if not raw:
            continue #if nothing is there, timeout
        text = raw.decode("ascii", errors="replace").strip()
        if text:
            write_log(text)

    except (serial.SerialException, OSError) as error:
        write_log(f"---disconnected: {error}---")
        if ser is not None:
            try:
                ser.close()
            except (serial.SerialException, OSError):
                pass #the port's dead, jim.
        ser = None
        feather_port = None
        time.sleep(RETRY_SECONDS)

    except KeyboardInterrupt:
        if ser is not None:
            ser.close()
        write_log("---logger stopped---")
        break






