from pathlib import Path

from modules.presentation.visual_shell.service import (
    BatteryReading,
    TemperatureReading,
    VisualShellSystemMetricsProvider,
)


def test_system_metrics_provider_reads_temperature_from_sysfs(tmp_path: Path) -> None:
    temperature_file = tmp_path / "thermal_zone0_temp"
    temperature_file.write_text("57321\n", encoding="utf-8")

    provider = VisualShellSystemMetricsProvider(
        thermal_zone_path=temperature_file,
        power_supply_root=tmp_path / "missing_power_supply",
    )

    reading = provider.read_temperature()

    assert reading == TemperatureReading(
        value_c=57,
        raw_value_c=57.321,
        source=str(temperature_file),
    )


def test_system_metrics_provider_returns_none_when_temperature_is_unavailable(
    tmp_path: Path,
) -> None:
    provider = VisualShellSystemMetricsProvider(
        thermal_zone_path=tmp_path / "missing_temp",
        power_supply_root=tmp_path / "missing_power_supply",
        vcgencmd_path="/definitely/missing/vcgencmd",
    )

    assert provider.read_temperature() is None


def test_system_metrics_provider_reads_battery_from_power_supply(
    tmp_path: Path,
) -> None:
    battery_dir = tmp_path / "BAT0"
    battery_dir.mkdir()
    capacity_file = battery_dir / "capacity"
    capacity_file.write_text("82\n", encoding="utf-8")

    provider = VisualShellSystemMetricsProvider(
        thermal_zone_path=tmp_path / "missing_temp",
        power_supply_root=tmp_path,
    )

    reading = provider.read_battery()

    assert reading == BatteryReading(
        percent=82,
        source=str(capacity_file),
    )


def test_system_metrics_provider_clamps_battery_percentage(tmp_path: Path) -> None:
    battery_dir = tmp_path / "BAT0"
    battery_dir.mkdir()
    capacity_file = battery_dir / "capacity"
    capacity_file.write_text("141\n", encoding="utf-8")

    provider = VisualShellSystemMetricsProvider(
        thermal_zone_path=tmp_path / "missing_temp",
        power_supply_root=tmp_path,
    )

    reading = provider.read_battery()

    assert reading == BatteryReading(
        percent=100,
        source=str(capacity_file),
    )


def test_system_metrics_provider_returns_none_when_battery_is_unavailable(
    tmp_path: Path,
) -> None:
    provider = VisualShellSystemMetricsProvider(
        thermal_zone_path=tmp_path / "missing_temp",
        power_supply_root=tmp_path,
    )

    assert provider.read_battery() is None