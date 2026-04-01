from luma.core.interface.serial import i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306
from time import sleep

serial = i2c(port=1, address=0x3C)
device = ssd1306(serial, width=128, height=64)

with canvas(device) as draw:
    draw.text((0, 0), "Smart Desk AI", fill="white")
    draw.text((0, 16), "OLED test passed", fill="white")
    draw.text((0, 32), "I2C address: 0x3C", fill="white")
    draw.text((0, 48), "31 March 2026", fill="white")

sleep(10)
device.clear()
