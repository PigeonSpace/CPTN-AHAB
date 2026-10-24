import time
import board
import busio
import csv
import adafruit_gps
import adafruit_mcp9600
import serial
import json
import os

#gps build function

def connect_gps():
    uart = None
    try:
        uart = serial.Serial("/dev/ttyS0", baudrate=9600, timeout=2)
        gps = adafruit_gps.GPS(uart, debug=False) 
        gps.send_command(b"PMTK314,0,1,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
        gps.send_command(b"PMTK220,1000")
        print("GPS serial connection initialized")
        return gps, uart
    
    except (serial.SerialException, OSError) as error:
        print(f"GPS startup failed: {error}. Terminating. ")

        if uart is not None and uart.is_open:
            uart.close()

        return None, None

#initialize gps communication and return status. Terminate if unable to initialize

gps, uart = connect_gps()

if gps is None:
    raise RuntimeError("Gps failed to initialize")

last_print = time.monotonic()
GPS_RETRY_SECONDS = 5
next_gps_retry = 0

#Temp sensor error handling variables

TEMP_RETRY_SECONDS = 10
HARDWARE_ERRORS = (OSError, RuntimeError, ValueError)

#gps close function

def close_gps(uart):
    if uart is not None:
        try:
            uart.close()
        except (serial.SerialException, OSError) as error:
            print(f"Error closing GPS: {error}")
    return None, None


#i2c bus connection function

def connect_i2c():
    try:
        new_i2c = busio.I2C(board.SCL, board.SDA)
        print("I2C bus connected")
        return new_i2c

    except HARDWARE_ERRORS as error:
        print(f"I2C bus unable to connect: {error}")
        return None
    
#close i2c bus function

def close_i2c(i2c):
    if i2c is not None:
        try:
            i2c.deinit()
        except HARDWARE_ERRORS as error:
            print(f"Error while closing I2C bus: {error}")
    return None

#Temp sensor connection function. Returns None if sensor drops from bus

def connect_temp_sensor(i2c, address, name):
    if i2c is None:
        return None
    
    try:
        sensor = adafruit_mcp9600.MCP9600( i2c, address=address,)
        print(f"{name} connected at {hex(address)}")
        return sensor
    
    except HARDWARE_ERRORS as error:
        print(f"{name} not detected: {error}")
        return None


i2c = connect_i2c()
temp_top = connect_temp_sensor(i2c, address=0x66, name="Temp_Top")
temp_bottom = connect_temp_sensor(i2c, address=0x67, name="Temp_Bottom")
next_temp_retry = time.monotonic() + TEMP_RETRY_SECONDS

#Filename settings 

filenamecounter = 1
csv_filename = "flightlog" + str(filenamecounter)
csv_header = ['uptime_s', 'timestamp', 'sat_num', 'fix_quality', 'latitude', 'longitude', 'altitude', 'speed', 'track_angle', 'horizontal_dilution', 'height_geoid', 'exterior_temp', 'interior_temp', 'battery_temp']

#CSV file creation

print("AHAB startup complete. Once GPS fix is acquired, log file will be created. " + str(csv_filename) + ".csv")

GPS_PARSE_ERROR_LIMIT = 15
FIX_WAIT_TIMEOUT = 120
fix_wait_start = time.monotonic()

while not gps.has_fix:
    current = time.monotonic()

    if current - fix_wait_start >= FIX_WAIT_TIMEOUT:
        print("Fix wait timed out. Beginning logging without fix.")
        break

    try:
        gps.update()

    except (serial.SerialException, OSError) as error:
        print(f"GPS error while waiting for fix: {error}. Starting logging and attempting GPS reconnection")
        gps, uart = close_gps(uart)
        break

    except (UnicodeDecodeError, ValueError) as error:
        print(f"GPS parse error while waiting for fix: {error}")
    
    if current - last_print >= 1.0:
        last_print = current

        if gps.satellites is not None:
            print(f"Waiting for GPS fix. {gps.satellites} satellites currently visible")
        else:
            print("Waiting for fix. No satellites currently visible OR waiting for download.")

    time.sleep(0.1)
    
if gps is not None and gps.has_fix:
    print("GPS fix acquired. Creating log file...")
else: 
    print("Proceeding without fix. Creating log file...")

while True:
    csv_filename = f"flightlog{filenamecounter}.csv"

    try:
        with open(csv_filename, "x", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(csv_header)

        print(f"Log file created: {csv_filename}")
        break

    except FileExistsError:
        print(f"{csv_filename} already exists, trying the next filename.")
        filenamecounter += 1

print("Log file created. Logging...")
print("===================================")
print("\033[s", end="", flush=True) #saves this cursor position 

consecutive_errors = 0
gps_parse_errors = 0



while True:
    try:
        current = time.monotonic()

        if gps is not None:
            try: 
                gps.update()

            except (serial.SerialException, OSError) as error:
                print(f"GPS communication error: {error}")
                gps, uart = close_gps(uart)
                next_gps_retry = current + GPS_RETRY_SECONDS
                gps_parse_errors = 0
            except (UnicodeDecodeError, ValueError) as error:
                gps_parse_errors += 1
                print(f"GPS parse error: {error}")

                if gps_parse_errors >= GPS_PARSE_ERROR_LIMIT:
                    print("Persistent GPS parse errors. Reconnecting GPS.")
                    gps, uart = close_gps(uart)
                    next_gps_retry = current + GPS_RETRY_SECONDS
                    gps_parse_errors = 0
                    
            else: gps_parse_errors = 0

        elif current >= next_gps_retry:
            gps, uart = connect_gps()
            next_gps_retry = current + GPS_RETRY_SECONDS
    
        if current - last_print >= 1.0:

            last_print = current
            print("\033[u\033[J", end="") #returns to saved line and clears everything below it

            if current >= next_temp_retry:

                if i2c is None:
                    i2c = connect_i2c()

                if i2c is not None:
                    if temp_top is None:    
                        temp_top = connect_temp_sensor(i2c, address=0x66, name="Temp_Top")

                    if temp_bottom is None:    
                        temp_bottom = connect_temp_sensor(i2c, address=0x67, name="Temp_Bottom")
                    
                    if temp_top is None and temp_bottom is None:
                        print("Both temp sensors unresponsive. Resetting I2C.")
                        i2c = close_i2c(i2c)

                next_temp_retry = current + TEMP_RETRY_SECONDS

            gps_connected = gps is not None
            gps_has_fix = gps_connected and gps.has_fix

            exterior_temp = None
            interior_temp = None
            battery_temp = None
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
            
            if gps_connected:
                sat_num = gps.satellites
                fix_quality = gps.fix_quality

            if gps_connected and gps.timestamp_utc is not None:
                timestamp = "{}/{}/{} {:02}:{:02}:{:02}".format(
                    gps.timestamp_utc.tm_mon,
                    gps.timestamp_utc.tm_mday,
                    gps.timestamp_utc.tm_year,
                    gps.timestamp_utc.tm_hour,
                    gps.timestamp_utc.tm_min,
                    gps.timestamp_utc.tm_sec,
            )

            if gps_has_fix:
                latitude = gps.latitude
                longitude = gps.longitude
                altitude = gps.altitude_m
                speed = gps.speed_kmh
                track_angle = gps.track_angle_deg
                horizontal_dilution = gps.horizontal_dilution
                height_geoid = gps.height_geoid

            if temp_top is not None:
                try:
                    exterior_temp = temp_top.temperature
                    interior_temp = temp_top.ambient_temperature

                except HARDWARE_ERRORS as error:
                    print(f"Temperature sense error, temp_top: {error}")
                    temp_top = None
                    next_temp_retry = current + TEMP_RETRY_SECONDS

            if temp_bottom is not None:
                try:
                    battery_temp = temp_bottom.temperature

                except HARDWARE_ERRORS as error:
                    print(f"Temperature sense error, temp_bottom: {error}")
                    temp_bottom = None
                    next_temp_retry = current + TEMP_RETRY_SECONDS

            try:        
                with open(csv_filename, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([round(current, 1), timestamp, sat_num, fix_quality, latitude, longitude, altitude, speed, track_angle, horizontal_dilution, height_geoid, exterior_temp, interior_temp, battery_temp])
            except OSError as error:
                print(f"Log row write failed: {error}")

            status = {"uptime_s": round(current, 1),
                      "timestamp": timestamp,
                      "fix_quality": fix_quality,
                      "latitude": latitude,
                      "longitude": longitude,
                      "altitude_m": altitude,
                      "speed":speed,
                      "track_angle":track_angle,
                      "horizontal_dilution":horizontal_dilution,
                      "height_geoid":height_geoid,
                      "sat_num": sat_num,
                      "exterior_temp":exterior_temp,
                      "interior_temp": interior_temp,
                      "battery_temp": battery_temp,
            }
            try:
                with open("/dev/shm/latest.json.tmp", "w") as f:
                    json.dump(status, f)
                os.replace("/dev/shm/latest.json.tmp", "/dev/shm/latest.json")
            except OSError as error:
                print(f"Status file write failed: {error}")

            print(timestamp)
            print(f"Number of Satellites: {sat_num}")
            print(f"Fix quality: {fix_quality}")
            print(f"Lat: {latitude}")
            print(f"Long: {longitude}")
            print(f"Altitude: {altitude}m")
            print(f"Speed: {speed} km/h")
            print(f"Exterior Temperature: {exterior_temp}C")
            print(f"Interior Temperature: {interior_temp}C")
            print(f"Battery Temperature: {battery_temp}C")
            print("===================================")
        time.sleep(0.05)
        consecutive_errors = 0
    except Exception:
        consecutive_errors += 1
        print(f"Unexpected error in main loop: {consecutive_errors} in a row")

        if consecutive_errors >= 15:
            print("Persistent errors. Resetting all hardware.")
            gps, uart = close_gps(uart)
            i2c = close_i2c(i2c)
            temp_top = None
            temp_bottom = None
            next_gps_retry = 0
            next_temp_retry = 0
            consecutive_errors = 0
            gps_parse_errors = 0
        time.sleep(1)
