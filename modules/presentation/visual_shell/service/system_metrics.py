from __future__ import annotations

import os
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


@dataclass(slots=True)
class VisualShellSystemMetricsProvider:
    """Reads local system metrics for Visual Shell metric glyph states.

    Godot only renders values. Python owns the hardware/system queries.
    """

    thermal_zone_path: Path = Path("/sys/class/thermal/thermal_zone0/temp")
    power_supply_root: Path = Path("/sys/class/power_supply")
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