from __future__ import annotations

import logging
import time

import numpy as np
import spidev
from gpiozero import DigitalInputDevice, DigitalOutputDevice, PWMOutputDevice

LOGGER = logging.getLogger(__name__)


class RaspberryPi:
    """
    Low-level Waveshare LCD GPIO/SPI helper.

    This keeps the vendor-facing hardware surface isolated under the display
    vendor package so the higher product layers remain clean.
    """

    def __init__(
        self,
        *,
        spi: spidev.SpiDev | None = None,
        spi_port: int = 0,
        spi_device: int = 0,
        spi_freq: int = 40_000_000,
        rst: int = 27,
        dc: int = 25,
        bl: int = 18,
        bl_freq: int = 1000,
    ) -> None:
        self.np = np
        self.INPUT = False
        self.OUTPUT = True

        self.SPEED = int(spi_freq)
        self.BL_freq = int(bl_freq)

        self.RST_PIN = self.gpio_mode(rst, self.OUTPUT)
        self.DC_PIN = self.gpio_mode(dc, self.OUTPUT)
        self.BL_PIN = self.gpio_pwm(bl)
        self.bl_DutyCycle(0)

        self.SPI = spi if spi is not None else spidev.SpiDev(spi_port, spi_device)
        self.SPI.max_speed_hz = self.SPEED
        self.SPI.mode = 0b00

    def gpio_mode(self, pin: int, mode: bool, pull_up=None, active_state: bool = True):
        if mode:
            return DigitalOutputDevice(pin, active_high=True, initial_value=False)
        return DigitalInputDevice(pin, pull_up=pull_up, active_state=active_state)

    @staticmethod
    def digital_write(pin, value: bool) -> None:
        if value:
            pin.on()
        else:
            pin.off()

    @staticmethod
    def digital_read(pin):
        return pin.value

    @staticmethod
    def delay_ms(delaytime: int) -> None:
        time.sleep(delaytime / 1000.0)

    def gpio_pwm(self, pin: int):
        return PWMOutputDevice(pin, frequency=self.BL_freq)

    def spi_writebyte(self, data: list[int]) -> None:
        self.SPI.writebytes(data)

    def bl_DutyCycle(self, duty: int) -> None:
        self.BL_PIN.value = max(0, min(100, duty)) / 100.0

    def bl_Frequency(self, freq: int) -> None:
        self.BL_PIN.frequency = freq

    def module_init(self) -> int:
        self.SPI.max_speed_hz = self.SPEED
        self.SPI.mode = 0b00
        return 0

    def module_exit(self) -> None:
        LOGGER.debug("Waveshare LCD SPI close.")
        try:
            self.SPI.close()
        except Exception:
            pass

        LOGGER.debug("Waveshare LCD GPIO cleanup.")
        try:
            self.digital_write(self.RST_PIN, True)
            self.digital_write(self.DC_PIN, False)
        except Exception:
            pass

        try:
            self.BL_PIN.close()
        except Exception:
            pass

        time.sleep(0.001)