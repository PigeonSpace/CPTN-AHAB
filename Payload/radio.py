import board
import busio
import digitalio
import adafruit_rfm9x
import time
import json

CALLSIGN = "KM7HZC"

#the json status file is stored in a RAM disk so it isn't competing with the camera for SD card write time
STATUS_PATH = "/dev/shm/latest.json"


FREQUENCY_MHZ = 433.0
SPREADING_FACTOR = 12
BANDWIDTH = 125000
CODING_RATE = 8
TX_POWER = 17 #can be as high as 20 but it's only rated for 1% duty cycle

BEACON_INTERVAL = 30.0 #Beacon transmission interval in seconds
RADIO_RETRY_SECONDS = 5 #How long to wait before retrying to connect to the radio if connection fails

RADIO_ERRORS = (OSError, RuntimeError)

spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
cs = digitalio.DigitalInOut(board.CE1)       # GPIO7
reset = digitalio.DigitalInOut(board.D25)    # GPIO25

#configures radio settings to communicate with ground station
def connect_radio():
    try:
        rfm9x = adafruit_rfm9x.RFM9x(spi, cs, reset, FREQUENCY_MHZ)
        rfm9x.signal_bandwidth = BANDWIDTH
        rfm9x.spreading_factor = SPREADING_FACTOR
        rfm9x.coding_rate = CODING_RATE
        rfm9x.tx_power = TX_POWER
        rfm9x.xmit_timeout = 10.0   
        rfm9x.low_datarate_optimize = (2 ** SPREADING_FACTOR / BANDWIDTH) > 0.016

        #turn radio on and listen for incoming packets
        rfm9x.listen()
        print("Radio Initialized and listening")
        return rfm9x
    except RADIO_ERRORS as error:
        print(f"Radio initialization failed: {error}")
        return None

def update_status():
    try:
        with open(STATUS_PATH) as file:
            status = json.load(file)
    except(OSError, ValueError) as error:
        print(f"Unable to read status file: {error}")
        return None
    uptime = status.get("uptime_s") if isinstance(status, dict) else None
    if uptime is None or uptime > time.monotonic() + 1:
        print("Status file's uptime is not valid: Something is broken. Ignoring.")
        return None
    return status
    
def format_val(value, spec): #defines how to format numbers for the packet, and what to do if the value is None
    if value is None:
        return ""
    try:
        return format(value, spec)
    except (TypeError, ValueError):
        return ""
    
def build_packet(seq, status, last_fix, current): # builds the packet for transmission
    status = status or {}
    lat = long = alt = fix_age = None
    if last_fix is not None:
        lat, long, alt, fix_time = last_fix
        fix_age = max(0, current - fix_time)
    
    data_age = None

    if status.get("uptime_s") is not None:
        data_age = max(0, current - status["uptime_s"])
    
    fields = [
        CALLSIGN,
        str(seq),
        format_val(lat, ".5f"),   # 5 decimals gives about 1m pf accuracy
        format_val(long, ".5f"),
        format_val(alt, ".0f"),
        format_val(fix_age, ".0f"),
        format_val(status.get("sat_num"), "d"),
        format_val(status.get("exterior_temp"), ".1f"),
        format_val(status.get("interior_temp"), ".1f"),
        format_val(status.get("battery_temp"), ".1f"),
        format_val(data_age, ".0f"),
    ]
    return ",".join(fields).encode("ascii", errors="replace") + b"\x00"
    
radio = connect_radio()
next_radio_retry = time.monotonic() + RADIO_RETRY_SECONDS
next_beacon = time.monotonic()
last_fix = None          # (lat, long, alt, uptime_s) of the last good position
seq = 0
consecutive_errors = 0
 
while True:
    try:
        current = time.monotonic()
 
        if radio is None and current >= next_radio_retry:
            radio = connect_radio()
            next_radio_retry = current + RADIO_RETRY_SECONDS
 
        if current >= next_beacon:
            next_beacon += BEACON_INTERVAL
            if next_beacon <= current:           # Something is broken and the next transmission time is in the past. Resetting to now. 
                next_beacon = current + BEACON_INTERVAL
 
            status = update_status()
            if (status is not None and status.get("latitude") is not None
                    and status.get("longitude") is not None):
                last_fix = (status["latitude"], status["longitude"],
                            status.get("altitude_m"), status["uptime_s"])
 
            if radio is not None:
                seq += 1
                packet = build_packet(seq, status, last_fix, current)
                try:
                    ok = radio.send(packet, keep_listening=True)
                    print(f"Beacon {seq} {'sent' if ok else 'TIMED OUT'}: "
                          f"{packet.rstrip(bytes(1)).decode()}")
                except RADIO_ERRORS as error:
                    print(f"Radio send error: {error}")
                    radio = None
                    next_radio_retry = current + RADIO_RETRY_SECONDS
 
        if radio is not None:
            try:
                if radio.rx_done():       # rx_done() only reads a status register, so checking it never interrupts a packet that's still arriving.
                    packet = radio.receive(timeout=0)
                    if packet is None:
                        print("Received a corrupted packet (failed CRC)")
                    else:
                        text = packet.decode("ascii", errors="replace").rstrip("\x00")
                        print(f"Received: {text}  (RSSI {radio.last_rssi} dBm, "
                              f"SNR {radio.last_snr} dB)")
            except RADIO_ERRORS as error:
                print(f"Radio receive error: {error}")
                radio = None
                next_radio_retry = current + RADIO_RETRY_SECONDS
 
        consecutive_errors = 0
        time.sleep(0.05)
 
    except Exception as error:
        consecutive_errors += 1
        print(f"Unexpected error in radio loop ({consecutive_errors} in a row): {error}")
        if consecutive_errors >= 15:
            print("Persistent errors. Resetting radio.")
            radio = None
            next_radio_retry = 0
            consecutive_errors = 0
        time.sleep(1)