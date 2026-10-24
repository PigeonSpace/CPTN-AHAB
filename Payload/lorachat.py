import sys
import select
import board, busio, digitalio
import adafruit_rfm9x

CALLSIGN = "KM7HZC"
FREQUENCY_MHZ = 433.0
SPREADING_FACTOR = 12
BANDWIDTH = 125000

spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
cs = digitalio.DigitalInOut(board.CE1)       # GPIO7
reset = digitalio.DigitalInOut(board.D25)    # GPIO25

rfm9x = adafruit_rfm9x.RFM9x(spi, cs, reset, FREQUENCY_MHZ)
rfm9x.signal_bandwidth = BANDWIDTH
rfm9x.spreading_factor = SPREADING_FACTOR
rfm9x.coding_rate = 8
rfm9x.tx_power = 20
rfm9x.xmit_timeout = 10.0   

# RadioHead (the Feathers) turns low-data-rate-optimize on automatically when
# a symbol lasts longer than 16 ms (SF11 and SF12 at 125 kHz). This library
# doesn't, so set it the same way here or the two ends can't decode each other.
rfm9x.low_datarate_optimize = (2 ** SPREADING_FACTOR / BANDWIDTH) > 0.016


def prompt():
    print("Send: ", end="", flush=True)


print("Type a message and press Enter to send. Ctrl+C to quit.")
rfm9x.listen()
prompt()

while True:
    # Wait up to 0.1 s for a typed line. select() sleeps while it waits,
    # so the loop doesn't burn CPU.
    typed, _, _ = select.select([sys.stdin], [], [], 0.1)

    if typed:
        line = sys.stdin.readline()
        if line == "":           # Ctrl+D
            break
        text = line.strip()
        if text:
            message = f"{CALLSIGN}: {text}"
            # The Feather sketches print text up to a null byte, so end with one.
            data = message.encode("ascii", errors="replace") + b"\x00"
            ok = rfm9x.send(data, keep_listening=True)   # back to listening after
            print("Sent" if ok else "TIMED OUT")
        prompt()

    # rx_done() only reads a status register, so checking it never
    # interrupts a packet that's still arriving.
    if rfm9x.rx_done():
        packet = rfm9x.receive(timeout=0)
        if packet is None:
            print("\rReceived a corrupted packet (failed CRC)")
        else:
            text = packet.decode("ascii", errors="replace").rstrip("\x00")
            print(f"\rReceived: {text}  (RSSI {rfm9x.last_rssi} dBm, SNR {rfm9x.last_snr} dB)")
        prompt()
