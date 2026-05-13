from __future__ import annotations
import os, subprocess, sys
from dataclasses import dataclass
from pathlib import Path
@dataclass(frozen=True, slots=True)
class DriveModeLaunchResult:
    ok: bool; url: str; dry_run: bool; movement_enabled: bool; command_profile: str; pid: int | None = None; error: str | None = None
def launch_drive_mode_from_environment(*, project_root: Path | None = None) -> DriveModeLaunchResult:
    root=Path(project_root or Path(__file__).resolve().parents[3]); host=os.environ.get("NEXA_DRIVE_MODE_HOST","127.0.0.1"); port=int(os.environ.get("NEXA_DRIVE_MODE_HTTP_PORT","8768")); dry=os.environ.get("NEXA_DRIVE_MODE_DRY_RUN")=="1"; move=os.environ.get("NEXA_DRIVE_MODE_ENABLE_MOVEMENT")=="1"; profile=os.environ.get("NEXA_DRIVE_MODE_COMMAND_PROFILE","wheel").strip().lower() or "wheel"
    if os.environ.get("NEXA_DRIVE_MODE_FORCE_RESTART","1") != "0":
        subprocess.run(["pkill","-f","scripts/mobile_base_drive_mode.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False); subprocess.run(["fuser","-k",f"{port}/tcp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    args=[sys.executable, str(root/"scripts/mobile_base_drive_mode.py"), "--host", host, "--http-port", str(port), "--command-profile", profile, "--linear-speed-mps", os.environ.get("NEXA_DRIVE_MODE_LINEAR_SPEED_MPS","0.18"), "--angular-speed-rad-s", os.environ.get("NEXA_DRIVE_MODE_ANGULAR_SPEED_RAD_S","0.65"), "--wheel-turn-speed-mps", os.environ.get("NEXA_DRIVE_MODE_WHEEL_TURN_SPEED_MPS","0.26")]
    if dry: args.append("--dry-run")
    else: args += ["--port", os.environ.get("NEXA_MOBILE_BASE_SERIAL_PORT","auto")]
    if move: args.append("--enable-movement")
    if os.environ.get("NEXA_DRIVE_MODE_AUTO_OPEN","1")=="1": args.append("--auto-open")
    log=root/"var/log/mobile_base_drive_mode_voice.log"; log.parent.mkdir(parents=True, exist_ok=True)
    try: proc=subprocess.Popen(args, cwd=str(root), stdout=log.open("a", encoding="utf-8"), stderr=subprocess.STDOUT, start_new_session=True)
    except Exception as error: return DriveModeLaunchResult(False, f"http://{host}:{port}/", dry, move, profile, error=str(error))
    return DriveModeLaunchResult(True, f"http://{host}:{port}/", dry, move, profile, pid=proc.pid)
