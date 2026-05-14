from __future__ import annotations

import os
import fcntl
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TemperatureReading:
    """Temperature reading prepared for Visual Shell rendering."""

    value_c: int
    raw_value_c: float
    source: str


@dataclass(frozen=True, slots=True)
class BatteryReading:
    """Battery percentage reading prepared for Visual Shell rendering."""

    percent: int
    source: str
    voltage_v: float | None = None
    raw_percent: float | None = None


@dataclass(slots=True)
class VisualShellSystemMetricsProvider:
    """Reads local system metrics for Visual Shell metric glyph states.

    Godot only renders values. Python owns the hardware/system queries.
    """

    thermal_zone_path: Path = Path("/sys/class/thermal/thermal_zone0/temp")
    power_supply_root: Path = Path("/sys/class/power_supply")
    x1206_i2c_device: Path = Path("/dev/i2c-1")
    x1206_i2c_address: int = 0x36
    vcgencmd_path: str = "vcgencmd"
    command_timeout_sec: float = 0.2

    def read_temperature(self) -> TemperatureReading | None:
        sysfs_reading = self._read_temperature_from_sysfs()
        if sysfs_reading is not None:
            return sysfs_reading

        return self._read_temperature_from_vcgencmd()

    def read_battery(self) -> BatteryReading | None:
        env_reading = self._read_battery_from_environment()
        if env_reading is not None:
            return env_reading

        x1206_reading = self._read_battery_from_x1206_i2c()
        if x1206_reading is not None:
            return x1206_reading

        return self._read_battery_from_power_supply()

    def _read_temperature_from_sysfs(self) -> TemperatureReading | None:
        try:
            raw_value = self.thermal_zone_path.read_text(encoding="utf-8").strip()
            millidegrees_c = int(raw_value)
            raw_celsius = millidegrees_c / 1000.0

            return TemperatureReading(
                value_c=round(raw_celsius),
                raw_value_c=raw_celsius,
                source=str(self.thermal_zone_path),
            )

        except (OSError, ValueError):
            return None

    def _read_temperature_from_vcgencmd(self) -> TemperatureReading | None:
        try:
            result = subprocess.run(
                [self.vcgencmd_path, "measure_temp"],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.command_timeout_sec,
            )

        except (OSError, subprocess.TimeoutExpired):
            return None

        if result.returncode != 0:
            return None

        match = re.search(r"temp=([0-9]+(?:\.[0-9]+)?)", result.stdout)
        if not match:
            return None

        raw_celsius = float(match.group(1))

        return TemperatureReading(
            value_c=round(raw_celsius),
            raw_value_c=raw_celsius,
            source="vcgencmd measure_temp",
        )

    def _read_battery_from_environment(self) -> BatteryReading | None:
        raw_value = os.environ.get("NEXA_BATTERY_PERCENT", "").strip()
        if not raw_value:
            return None

        try:
            percent = self._clamp_percent(int(raw_value))
        except ValueError:
            return None

        return BatteryReading(
            percent=percent,
            source="NEXA_BATTERY_PERCENT",
        )

    def _read_battery_from_x1206_i2c(self) -> BatteryReading | None:
        """Read real battery state from the X1206 MAX17040 fuel gauge.

        Unit tests often pass a temporary power_supply_root. In that case this
        provider must not read the real Raspberry Pi I2C device, otherwise tests
        that expect fake /sys/class/power_supply data would be polluted by the
        real UPS state.
        """

        if self.power_supply_root != Path("/sys/class/power_supply"):
            return None

        try:
            soc_raw = self._x1206_read_word(register=0x04)
            vcell_raw = self._x1206_read_word(register=0x02)
        except OSError:
            return None
        except PermissionError:
            return None

        raw_percent = float((soc_raw >> 8) + ((soc_raw & 0xFF) / 256.0))
        percent = self._clamp_percent(round(raw_percent))

        # MAX17040 VCELL is a 12-bit value left-aligned in a 16-bit register.
        # Each step is 1.25 mV.
        voltage_v = float(((vcell_raw >> 4) * 1.25) / 1000.0)

        return BatteryReading(
            percent=percent,
            source=f"{self.x1206_i2c_device}@0x{self.x1206_i2c_address:02x}:MAX17040",
            voltage_v=round(voltage_v, 3),
            raw_percent=round(raw_percent, 2),
        )

    def _x1206_read_word(self, *, register: int) -> int:
        i2c_slave_ioctl = 0x0703

        with self.x1206_i2c_device.open("r+b", buffering=0) as device:
            fcntl.ioctl(device.fileno(), i2c_slave_ioctl, self.x1206_i2c_address)
            device.write(bytes([register]))
            data = device.read(2)

        if len(data) != 2:
            raise OSError(f"Short I2C read from register 0x{register:02x}")

        return (data[0] << 8) | data[1]

    def _read_battery_from_power_supply(self) -> BatteryReading | None:
        try:
            power_supplies = sorted(self.power_supply_root.iterdir())
        except OSError:
            return None

        for power_supply in power_supplies:
            capacity_path = power_supply / "capacity"
            if not capacity_path.is_file():
                continue

            try:
                percent = self._clamp_percent(
                    int(capacity_path.read_text(encoding="utf-8").strip())
                )
            except (OSError, ValueError):
                continue

            return BatteryReading(
                percent=percent,
                source=str(capacity_path),
            )

        return None

    @staticmethod
    def _clamp_percent(percent: int) -> int:
        return max(0, min(100, percent))