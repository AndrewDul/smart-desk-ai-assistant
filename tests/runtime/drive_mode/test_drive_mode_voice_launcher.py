from __future__ import annotations

from pathlib import Path

from modules.runtime.drive_mode.voice_launcher import (
    CONFIRM_TEST_ENV_VAR,
    CONFIRM_TEST_ENV_VALUE,
    DRIVE_MODE_DRY_RUN_ENV,
    DRIVE_MODE_ENABLE_MOVEMENT_ENV,
    DRIVE_MODE_SERIAL_PORT_ENV,
    DRIVE_MODE_FORCE_RESTART_ENV,
    DriveModeVoiceLauncher,
    build_drive_mode_launch_command,
    build_drive_mode_launch_config_from_env,
)


def test_voice_launcher_builds_dry_run_command_without_movement(tmp_path: Path) -> None:
    config = build_drive_mode_launch_config_from_env(env={DRIVE_MODE_DRY_RUN_ENV: "1"}, project_root=tmp_path)
    command = build_drive_mode_launch_command(config)
    assert "--dry-run" in command
    assert "--enable-movement" not in command
    assert str(tmp_path / "scripts" / "mobile_base_drive_mode.py") in command


def test_voice_launcher_requires_movement_env_gate(tmp_path: Path) -> None:
    config = build_drive_mode_launch_config_from_env(env={DRIVE_MODE_ENABLE_MOVEMENT_ENV: "1", DRIVE_MODE_SERIAL_PORT_ENV: "/dev/ttyACM0"}, project_root=tmp_path)
    command = build_drive_mode_launch_command(config)
    assert config.movement_requested is True
    assert config.enable_movement is False
    assert "--enable-movement" not in command


def test_voice_launcher_allows_movement_only_when_gate_is_open(tmp_path: Path) -> None:
    config = build_drive_mode_launch_config_from_env(env={DRIVE_MODE_ENABLE_MOVEMENT_ENV: "1", "CONFIRM_NEXA_MOBILE_BASE_MOVE": "RUN", DRIVE_MODE_SERIAL_PORT_ENV: "/dev/ttyACM0"}, project_root=tmp_path)
    command = build_drive_mode_launch_command(config)
    assert config.enable_movement is True
    assert "--enable-movement" in command
    assert "/dev/ttyACM0" in command


def test_voice_launcher_reports_closed_hardware_gate_without_starting(tmp_path: Path) -> None:
    config = build_drive_mode_launch_config_from_env(env={DRIVE_MODE_SERIAL_PORT_ENV: "/dev/ttyACM0"}, project_root=tmp_path)
    result = DriveModeVoiceLauncher(config=config).launch()
    assert result.ok is False
    assert result.status == "hardware_gate_closed"
    assert CONFIRM_TEST_ENV_VAR in result.message
    assert CONFIRM_TEST_ENV_VALUE in result.message


def test_voice_launcher_force_restart_is_enabled_by_default(tmp_path: Path) -> None:
    config = build_drive_mode_launch_config_from_env(env={DRIVE_MODE_DRY_RUN_ENV: "1"}, project_root=tmp_path)
    assert config.force_restart is True


def test_voice_launcher_force_restart_can_be_disabled(tmp_path: Path) -> None:
    config = build_drive_mode_launch_config_from_env(
        env={DRIVE_MODE_DRY_RUN_ENV: "1", DRIVE_MODE_FORCE_RESTART_ENV: "0"},
        project_root=tmp_path,
    )
    assert config.force_restart is False
