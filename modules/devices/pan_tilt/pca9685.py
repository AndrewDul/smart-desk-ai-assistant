from __future__ import annotations

from dataclasses import dataclass

from smbus2 import SMBus


@dataclass(slots=True)
class PCA9685Config:
    i2c_bus: int = 1
    i2c_address: int = 0x40
    pwm_frequency_hz: float = 50.0


class PCA9685:
    """Minimal PCA9685 driver for stable servo control on Raspberry Pi."""

    _MODE1 = 0x00
    _MODE2 = 0x01
    _PRESCALE = 0xFE
    _LED0_ON_L = 0x06
    _RESTART = 0x80
    _SLEEP = 0x10
    _ALLCALL = 0x01
    _OUTDRV = 0x04

    def __init__(self, config: PCA9685Config) -> None:
        self.config = config
        self._bus = SMBus(config.i2c_bus)
        self._frequency_hz = float(config.pwm_frequency_hz)
        self._initialize()

    def _initialize(self) -> None:
        self.write_register(self._MODE1, self._ALLCALL)
        self.write_register(self._MODE2, self._OUTDRV)
        self.write_register(self._MODE1, self._ALLCALL)
        self.set_pwm_frequency(self._frequency_hz)

    def write_register(self, register: int, value: int) -> None:
        self._bus.write_byte_data(self.config.i2c_address, register, value & 0xFF)

    def read_register(self, register: int) -> int:
        return int(self._bus.read_byte_data(self.config.i2c_address, register))

    def set_pwm_frequency(self, frequency_hz: float) -> None:
        frequency_hz = max(1.0, float(frequency_hz))
        prescale_value = int(round(25_000_000.0 / (4096.0 * frequency_hz)) - 1)
        old_mode = self.read_register(self._MODE1)
        sleep_mode = (old_mode & 0x7F) | self._SLEEP

        self.write_register(self._MODE1, sleep_mode)
        self.write_register(self._PRESCALE, prescale_value)
        self.write_register(self._MODE1, old_mode)
        self.write_register(self._MODE1, old_mode | self._RESTART)
        self._frequency_hz = frequency_hz

    def set_pwm(self, channel: int, on_count: int, off_count: int) -> None:
        if not 0 <= int(channel) <= 15:
            raise ValueError("PCA9685 channel must be between 0 and 15.")

        base = self._LED0_ON_L + 4 * int(channel)
        self.write_register(base + 0, on_count & 0xFF)
        self.write_register(base + 1, (on_count >> 8) & 0x0F)
        self.write_register(base + 2, off_count & 0xFF)
        self.write_register(base + 3, (off_count >> 8) & 0x0F)

    def set_servo_pulse_us(self, channel: int, pulse_us: float) -> int:
        pulse_us = max(0.0, float(pulse_us))
        counts = int(round((pulse_us * self._frequency_hz * 4096.0) / 1_000_000.0))
        counts = max(0, min(4095, counts))
        self.set_pwm(channel, 0, counts)
        return counts

    def close(self) -> None:
        self._bus.close()