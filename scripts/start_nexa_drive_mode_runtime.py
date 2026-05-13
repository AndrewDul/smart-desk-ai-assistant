#!/usr/bin/env python3
"""Start NeXa runtime with mobile-base drive mode gates prepared."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


DEFAULT_PORT = "/dev/serial/by-id/usb-1a86_USB_Single_Serial_5A36029146-if00"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start NeXa with mobile-base drive mode environment prepared."
    )
    parser.add_argument("--enable-movement", action="store_true")
    parser.add_argument("--port", default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
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

    env["NEXA_MOBILE_BASE_SERIAL_PORT"] = str(args.port)
    env["NEXA_DRIVE_MODE_HOST"] = str(args.host)
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

    print(f"[START] Project root: {project_root}")
    print(f"[START] Serial port: {env['NEXA_MOBILE_BASE_SERIAL_PORT']}")
    print(f"[START] Drive profile: {env['NEXA_DRIVE_MODE_COMMAND_PROFILE']}")
    print(f"[START] Linear speed: {env['NEXA_DRIVE_MODE_LINEAR_SPEED_MPS']} m/s")
    print(f"[START] Angular speed: {env['NEXA_DRIVE_MODE_ANGULAR_SPEED_RAD_S']} rad/s")
    print(f"[START] Wheel turn speed: {env['NEXA_DRIVE_MODE_WHEEL_TURN_SPEED_MPS']} m/s")
    print("[START] Launching main.py")

    return subprocess.call([sys.executable, str(main_py)], cwd=str(project_root), env=env)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
