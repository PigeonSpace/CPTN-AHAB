import os
import glob
import csv

LOG_DIR = os.path.expanduser("~/Documents/AHAB/Flight Logs/RAW")
PARSED_LOG_DIR = os.path.expanduser("~/Documents/AHAB/Flight Logs/PARSED")
LOG_FRESHNESS_CHECK = 30
CSV_HEADER = ['uptime_s', 'timestamp', 'sat_num', 'fix_quality', 'latitude', 'longitude', 'altitude', 'speed', 'track_angle', 'horizontal_dilution', 'height_geoid', 'exterior_temp', 'interior_temp', 'battery_temp']

uptime_s = None
timestamp = None
sat_num = None
fix_quality = None
latitude = None
longitude = None
altitude = None
speed = None
track_angle = None
horizontal_dilution = None
height_geoid = None
exterior_temp = None
interior_temp = None
battery_temp = None

def newest_log():
    logs = glob.glob(os.path.join(LOG_DIR, "groundlog*.log"))
    if not logs:
        return None
    return max(logs, key=os.path.getmtime)

logfile = newest_log()

filenamecounter=1
while True:
    parsed_log_path = os.path.join(PARSED_LOG_DIR, f"parsedlog{filenamecounter}.csv")
    try:
        with open(parsed_log_path "x", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADER)
        print(f"Parsed Log File created: parsedlog{filenamecounter}.csv")
        break
    except FileExistsError:
        print(f"parsedlog{filenamecounter} already exists. Trying next filename.")
        filenamecounter += 1









