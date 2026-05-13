#!/usr/bin/env python3
"""Install repo-side files for NeXa Drive Runtime autostart.

This repair script is idempotent. It writes a drive-ready voice launcher and a
systemd unit template into the repository. The actual enable/start step remains
explicit and is done with sudo after reviewing the generated unit.
"""

from __future__ import annotations

import getpass
import os
import shlex
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SERIAL_PORT = "/dev/serial/by-id/usb-1a86_USB_Single_Serial_5A36029146-if00"
SERVICE_NAME = "nexa-drive-runtime.service"


START_LAUNCHER = '''#!/usr/bin/env python3
"""Start NeXa in real voice mode with mobile-base drive mode prepared."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_PORT = "/dev/serial/by-id/usb-1a86_USB_Single_Serial_5A36029146-if00"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start NeXa with real wake-word listening and drive mode prepared."
    )
    parser.add_argument("--enable-movement", action="store_true")
    parser.add_argument("--port", default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--http-port", type=int, default=8768)
    parser.add_argument("--command-profile", default="wheel", choices=["ros", "wheel", "pwm"])
    parser.add_argument("--linear-speed-mps", type=float, default=0.18)
    parser.add_argument("--angular-speed-rad-s", type=float, default=0.65)
    parser.add_argument("--wheel-turn-speed-mps", type=float, default=0.26)
    parser.add_argument("--no-auto-open", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = Path(__file__).resolve().parents[1]
    main_py = project_root / "main.py"
    if not main_py.exists():
        raise SystemExit(f"main.py not found: {main_py}")

    env = os.environ.copy()
    env["NEXA_REQUIRE_REAL_VOICE_INPUT"] = "1"
    env["NEXA_REQUIRE_REAL_WAKE_GATE"] = "1"
    env["NEXA_RUNTIME_MODE"] = "voice_drive_runtime"
    env["NEXA_MOBILE_BASE_SERIAL_PORT"] = str(args.port)
    env["NEXA_DRIVE_MODE_HOST"] = str(args.host)
    env["NEXA_DRIVE_MODE_HTTP_PORT"] = str(int(args.http_port))
    env["NEXA_DRIVE_MODE_FORCE_RESTART"] = "1"
    env["NEXA_DRIVE_MODE_COMMAND_PROFILE"] = str(args.command_profile)
    env["NEXA_DRIVE_MODE_LINEAR_SPEED_MPS"] = f"{float(args.linear_speed_mps):.3f}"
    env["NEXA_DRIVE_MODE_ANGULAR_SPEED_RAD_S"] = f"{float(args.angular_speed_rad_s):.3f}"
    env["NEXA_DRIVE_MODE_WHEEL_TURN_SPEED_MPS"] = f"{float(args.wheel_turn_speed_mps):.3f}"

    if args.no_auto_open:
        env.pop("NEXA_DRIVE_MODE_AUTO_OPEN", None)
    else:
        env["NEXA_DRIVE_MODE_AUTO_OPEN"] = "1"

    if args.enable_movement:
        env["CONFIRM_NEXA_MOBILE_BASE_TEST"] = "RUN"
        env["CONFIRM_NEXA_MOBILE_BASE_MOVE"] = "RUN"
        env["NEXA_DRIVE_MODE_ENABLE_MOVEMENT"] = "1"
        env.pop("NEXA_DRIVE_MODE_DRY_RUN", None)
        print("[START] Drive mode hardware movement gate: enabled")
    else:
        env.pop("CONFIRM_NEXA_MOBILE_BASE_MOVE", None)
        env.pop("NEXA_DRIVE_MODE_ENABLE_MOVEMENT", None)
        env["NEXA_DRIVE_MODE_DRY_RUN"] = "1"
        print("[START] Drive mode dry-run: enabled")

    print("[START] Real microphone/wake gate required: yes")
    print(f"[START] Project root: {project_root}")
    print(f"[START] Serial port: {env['NEXA_MOBILE_BASE_SERIAL_PORT']}")
    print(f"[START] Drive profile: {env['NEXA_DRIVE_MODE_COMMAND_PROFILE']}")
    print(f"[START] Drive panel host: {env['NEXA_DRIVE_MODE_HOST']}:{env['NEXA_DRIVE_MODE_HTTP_PORT']}")
    print("[START] Launching main.py")
    return subprocess.call([sys.executable, str(main_py)], cwd=str(project_root), env=env)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''


CHECK_SCRIPT = '''#!/usr/bin/env python3
"""Check NeXa Drive Runtime autostart installation state."""

from __future__ import annotations

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICE_NAME = "nexa-drive-runtime.service"


def run(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    return proc.returncode, proc.stdout.strip()


def main() -> int:
    print(f"[CHECK] Project root: {PROJECT_ROOT}")
    launcher = PROJECT_ROOT / "scripts" / "start_nexa_drive_voice_runtime.py"
    unit = PROJECT_ROOT / "deploy" / "systemd" / SERVICE_NAME
    print(f"[CHECK] launcher exists: {launcher.exists()} -> {launcher}")
    print(f"[CHECK] unit template exists: {unit.exists()} -> {unit}")

    code, enabled = run(["systemctl", "is-enabled", SERVICE_NAME])
    print(f"[CHECK] systemd enabled: {enabled or 'unknown'}")

    code, active = run(["systemctl", "is-active", SERVICE_NAME])
    print(f"[CHECK] systemd active: {active or 'unknown'}")

    code, status = run(["systemctl", "status", SERVICE_NAME, "--no-pager", "-l"])
    if status:
        print("[CHECK] status excerpt:")
        print("\\n".join(status.splitlines()[:25]))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _write(path: Path, text: str, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if executable:
        path.chmod(0o755)
    print(f"[REPAIR] wrote {path.relative_to(PROJECT_ROOT)}")


def _unit_text(*, project_root: Path, user: str, serial_port: str) -> str:
    python_path = project_root / ".venv" / "bin" / "python"
    launcher_path = project_root / "scripts" / "start_nexa_drive_voice_runtime.py"
    stop_script = project_root / "scripts" / "mobile_base_stop.py"
    command = [
        str(python_path),
        str(launcher_path),
        "--enable-movement",
        "--command-profile",
        "wheel",
        "--linear-speed-mps",
        "0.18",
        "--angular-speed-rad-s",
        "0.65",
        "--wheel-turn-speed-mps",
        "0.26",
        "--no-auto-open",
    ]
    stop_command = (
        f"cd {shlex.quote(str(project_root))} && "
        "CONFIRM_NEXA_MOBILE_BASE_TEST=RUN "
        f"{shlex.quote(str(python_path))} {shlex.quote(str(stop_script))} "
        f"--port {shlex.quote(serial_port)} --read-seconds 0.2 || true"
    )
    return f'''[Unit]
Description=NeXa Drive Runtime - real voice + manual mobile base control
Documentation=file://{project_root}/docs/architecture_notes.md
After=network-online.target sound.target
Wants=network-online.target sound.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
WorkingDirectory={project_root}
User={user}
Group={user}
EnvironmentFile=-{project_root}/config/systemd/nexa-drive.env
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONIOENCODING=utf-8
Environment=NEXA_RUNTIME_MODE=systemd_drive_voice
Environment=CONFIRM_NEXA_MOBILE_BASE_TEST=RUN
Environment=CONFIRM_NEXA_MOBILE_BASE_MOVE=RUN
Environment=NEXA_DRIVE_MODE_ENABLE_MOVEMENT=1
Environment=NEXA_MOBILE_BASE_SERIAL_PORT={serial_port}
Environment=NEXA_DRIVE_MODE_COMMAND_PROFILE=wheel
Environment=NEXA_DRIVE_MODE_LINEAR_SPEED_MPS=0.18
Environment=NEXA_DRIVE_MODE_ANGULAR_SPEED_RAD_S=0.65
Environment=NEXA_DRIVE_MODE_WHEEL_TURN_SPEED_MPS=0.26
ExecStart={shlex.join(command)}
ExecStopPost=/bin/bash -lc {shlex.quote(stop_command)}
Restart=on-failure
RestartSec=3
TimeoutStopSec=25
KillSignal=SIGINT
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
'''


def _env_example(serial_port: str) -> str:
    return f'''# Optional overrides for nexa-drive-runtime.service.
# The service unit already contains safe defaults. Keep these values commented
# unless you intentionally need to override them.

# NEXA_MOBILE_BASE_SERIAL_PORT={serial_port}
# NEXA_DRIVE_MODE_COMMAND_PROFILE=wheel
# NEXA_DRIVE_MODE_LINEAR_SPEED_MPS=0.18
# NEXA_DRIVE_MODE_ANGULAR_SPEED_RAD_S=0.65
# NEXA_DRIVE_MODE_WHEEL_TURN_SPEED_MPS=0.26
'''


def main() -> int:
    user = os.environ.get("SUDO_USER") or getpass.getuser()
    serial_port = os.environ.get("NEXA_MOBILE_BASE_SERIAL_PORT", DEFAULT_SERIAL_PORT)

    _write(PROJECT_ROOT / "scripts" / "start_nexa_drive_voice_runtime.py", START_LAUNCHER, executable=True)
    _write(PROJECT_ROOT / "scripts" / "check_nexa_drive_autostart.py", CHECK_SCRIPT, executable=True)
    _write(PROJECT_ROOT / "config" / "systemd" / "nexa-drive.env.example", _env_example(serial_port))
    _write(
        PROJECT_ROOT / "deploy" / "systemd" / SERVICE_NAME,
        _unit_text(project_root=PROJECT_ROOT, user=user, serial_port=serial_port),
    )

    print("[REPAIR OK] NeXa Drive Runtime autostart files are ready.")
    print("[NEXT] Review deploy/systemd/nexa-drive-runtime.service, then install it with sudo systemctl commands.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
