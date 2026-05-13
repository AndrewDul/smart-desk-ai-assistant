from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

CONFIRM_TEST_ENV_VAR = "CONFIRM_NEXA_MOBILE_BASE_TEST"
CONFIRM_TEST_ENV_VALUE = "RUN"

DRIVE_MODE_DRY_RUN_ENV = "NEXA_DRIVE_MODE_DRY_RUN"
DRIVE_MODE_ENABLE_MOVEMENT_ENV = "NEXA_DRIVE_MODE_ENABLE_MOVEMENT"
DRIVE_MODE_SERIAL_PORT_ENV = "NEXA_MOBILE_BASE_SERIAL_PORT"
DRIVE_MODE_FORCE_RESTART_ENV = "NEXA_DRIVE_MODE_FORCE_RESTART"


@dataclass(frozen=True, slots=True)
class DriveModeLaunchConfig:
    project_root: Path
    host: str
    http_port: int
    dry_run: bool
    serial_port: str
    movement_requested: bool
    enable_movement: bool
    force_restart: bool
    auto_open: bool
    command_profile: str
    linear_speed_mps: str
    angular_speed_rad_s: str
    wheel_turn_speed_mps: str
    env: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class DriveModeLaunchResult:
    ok: bool
    url: str
    dry_run: bool
    movement_enabled: bool
    command_profile: str
    pid: int | None = None
    error: str | None = None
    status: str = "unknown"
    message: str = ""


def build_drive_mode_launch_config_from_env(
    *,
    env: Mapping[str, str] | None = None,
    project_root: Path | None = None,
) -> DriveModeLaunchConfig:
    source = dict(os.environ if env is None else env)
    root = Path(project_root or Path(__file__).resolve().parents[3])
    movement_requested = source.get(DRIVE_MODE_ENABLE_MOVEMENT_ENV) == "1"

    return DriveModeLaunchConfig(
        project_root=root,
        host=source.get("NEXA_DRIVE_MODE_HOST", "127.0.0.1"),
        http_port=int(source.get("NEXA_DRIVE_MODE_HTTP_PORT", "8768")),
        dry_run=source.get(DRIVE_MODE_DRY_RUN_ENV) == "1",
        serial_port=source.get(DRIVE_MODE_SERIAL_PORT_ENV, "auto"),
        movement_requested=movement_requested,
        enable_movement=movement_requested and source.get("CONFIRM_NEXA_MOBILE_BASE_MOVE") == "RUN",
        force_restart=source.get(DRIVE_MODE_FORCE_RESTART_ENV, "1") != "0",
        auto_open=source.get("NEXA_DRIVE_MODE_AUTO_OPEN", "1") == "1",
        command_profile=source.get("NEXA_DRIVE_MODE_COMMAND_PROFILE", "wheel").strip().lower() or "wheel",
        linear_speed_mps=source.get("NEXA_DRIVE_MODE_LINEAR_SPEED_MPS", "0.18"),
        angular_speed_rad_s=source.get("NEXA_DRIVE_MODE_ANGULAR_SPEED_RAD_S", "0.65"),
        wheel_turn_speed_mps=source.get("NEXA_DRIVE_MODE_WHEEL_TURN_SPEED_MPS", "0.26"),
        env=source,
    )


def build_drive_mode_launch_command(config: DriveModeLaunchConfig) -> list[str]:
    command = [
        sys.executable,
        str(config.project_root / "scripts" / "mobile_base_drive_mode.py"),
        "--host",
        config.host,
        "--http-port",
        str(config.http_port),
        "--command-profile",
        config.command_profile,
        "--linear-speed-mps",
        config.linear_speed_mps,
        "--angular-speed-rad-s",
        config.angular_speed_rad_s,
        "--wheel-turn-speed-mps",
        config.wheel_turn_speed_mps,
    ]

    if config.dry_run:
        command.append("--dry-run")
    else:
        command += ["--port", config.serial_port]

    if config.enable_movement:
        command.append("--enable-movement")

    if config.auto_open:
        command.append("--auto-open")

    return command


class DriveModeVoiceLauncher:
    def __init__(self, *, config: DriveModeLaunchConfig | None = None) -> None:
        self.config = config or build_drive_mode_launch_config_from_env()

    def launch(self) -> DriveModeLaunchResult:
        config = self.config
        url = f"http://{config.host}:{config.http_port}/"

        if not config.dry_run and config.env.get(CONFIRM_TEST_ENV_VAR) != CONFIRM_TEST_ENV_VALUE:
            message = f"Hardware gate is closed. Set {CONFIRM_TEST_ENV_VAR}={CONFIRM_TEST_ENV_VALUE}."
            return DriveModeLaunchResult(
                ok=False,
                url=url,
                dry_run=config.dry_run,
                movement_enabled=config.enable_movement,
                command_profile=config.command_profile,
                error=message,
                status="hardware_gate_closed",
                message=message,
            )

        if config.force_restart:
            subprocess.run(
                ["pkill", "-f", "scripts/mobile_base_drive_mode.py"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            subprocess.run(
                ["fuser", "-k", f"{config.http_port}/tcp"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )

        log = config.project_root / "var/log/mobile_base_drive_mode_voice.log"
        log.parent.mkdir(parents=True, exist_ok=True)

        try:
            proc = subprocess.Popen(
                build_drive_mode_launch_command(config),
                cwd=str(config.project_root),
                stdout=log.open("a", encoding="utf-8"),
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except Exception as error:
            return DriveModeLaunchResult(
                ok=False,
                url=url,
                dry_run=config.dry_run,
                movement_enabled=config.enable_movement,
                command_profile=config.command_profile,
                error=str(error),
                status="launch_failed",
                message=str(error),
            )

        return DriveModeLaunchResult(
            ok=True,
            url=url,
            dry_run=config.dry_run,
            movement_enabled=config.enable_movement,
            command_profile=config.command_profile,
            pid=proc.pid,
            status="started",
            message="Drive mode started.",
        )


def launch_drive_mode_from_environment(*, project_root: Path | None = None) -> DriveModeLaunchResult:
    return DriveModeVoiceLauncher(
        config=build_drive_mode_launch_config_from_env(project_root=project_root)
    ).launch()
