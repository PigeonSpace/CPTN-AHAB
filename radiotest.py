import board, busio, digitalio
import adafruit_rfm9x

spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
cs = digitalio.DigitalInOut(board.CE1)      # GPIO7
reset = digitalio.DigitalInOut(board.D25)   # GPIO25

rfm9x = adafruit_rfm9x.RFM9x(spi, cs, reset, 433.0)
print("Radio found at", rfm9x.frequency_mhz, "MHz")