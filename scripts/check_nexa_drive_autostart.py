#!/usr/bin/env python3
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
        print("\n".join(status.splitlines()[:25]))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
