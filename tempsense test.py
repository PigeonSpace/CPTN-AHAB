import time

import board
import busio

import adafruit_mcp9600

i2c = busio.I2C(board.SCL, board.SDA, frequency=20000)
mcpa = adafruit_mcp9600.MCP9600(i2c, address=0x66)
mcpb = adafruit_mcp9600.MCP9600(i2c, address=0x67)


while True:
    print("Top")
    print((mcpa.ambient_temperature, mcpa.temperature, mcpa.delta_temperature))
    print("Bottom")
    print((mcpb.ambient_temperature, mcpb.temperature, mcpb.delta_temperature))
    time.sleep(1)