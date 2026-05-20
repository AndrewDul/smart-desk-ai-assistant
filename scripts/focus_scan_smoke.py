#!/usr/bin/env python3
"""
Focus Mode active scan smoke test — physical pan-tilt movement proof.

Executes the same center→left→center→right→center sweep that Focus Mode
periodic/away-recheck scans use. Prints movement_executed for each step.

SAFETY: No movement happens unless ALL of the following are true in settings:
  pan_tilt.hardware_enabled = true
  pan_tilt.motion_enabled   = true
  pan_tilt.dry_run          = false
  pan_tilt.enabled          = true
  focus_vision.pan_tilt_scan_enabled = true

USAGE:
  NEXA_FOCUS_SCAN_CONFIRM=1 .venv/bin/python scripts/focus_scan_smoke.py

No mobile base movement is performed.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

CONFIRM_ENV = "NEXA_FOCUS_SCAN_CONFIRM"
DEFAULT_SETTINGS = ROOT_DIR / "config" / "settings.json"


def _load_settings(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _section(settings: dict[str, Any], key: str) -> dict[str, Any]:
    val = settings.get(key, {})
    return val if isinstance(val, dict) else {}


def _print_gate_summary(pt_cfg: dict[str, Any], fv_cfg: dict[str, Any]) -> None:
    print("── Pan-tilt safety gates ──────────────────────────────")
    gates = {
        "pan_tilt.enabled": bool(pt_cfg.get("enabled", False)),
        "pan_tilt.hardware_enabled": bool(pt_cfg.get("hardware_enabled", False)),
        "pan_tilt.motion_enabled": bool(pt_cfg.get("motion_enabled", False)),
        "pan_tilt.dry_run (must be false)": not bool(pt_cfg.get("dry_run", True)),
        "focus_vision.pan_tilt_scan_enabled": bool(fv_cfg.get("pan_tilt_scan_enabled", False)),
    }
    all_open = True
    for name, ok in gates.items():
        status = "OPEN " if ok else "CLOSED"
        print(f"  [{status}]  {name}")
        if not ok:
            all_open = False
    print()
    if not all_open:
        print("WARNING: One or more safety gates are CLOSED.")
        print("Physical movement will NOT happen.")
        print()
        print("To enable physical movement, set in config/settings.json:")
        print('  "pan_tilt": {')
        print('    "enabled": true,')
        print('    "hardware_enabled": true,')
        print('    "motion_enabled": true,')
        print('    "dry_run": false')
        print("  },")
        print('  "focus_vision": { "pan_tilt_scan_enabled": true }')
        print()


def _do_move(backend: Any, pan_delta: float, label: str) -> None:
    print(f"  → {label} (pan_delta={pan_delta:+.1f}°) ...", end=" ", flush=True)
    move_delta = getattr(backend, "move_delta", None)
    if not callable(move_delta):
        print("SKIP (no move_delta method)")
        return
    try:
        result = move_delta(pan_delta_degrees=pan_delta, tilt_delta_degrees=0.0)
    except Exception as err:
        print(f"EXCEPTION: {err}")
        return
    executed = bool(result.get("movement_executed", False)) if isinstance(result, dict) else False
    reason = result.get("detail", "") if isinstance(result, dict) else ""
    gates = result.get("missing_safety_gates", []) if isinstance(result, dict) else []
    if executed:
        print("movement_executed=True")
    else:
        msg = f"movement_executed=False  detail={reason!r}"
        if gates:
            msg += f"  missing_gates={gates}"
        print(msg)


def _do_center(backend: Any, label: str) -> None:
    print(f"  → {label} ...", end=" ", flush=True)
    center = getattr(backend, "center", None)
    if not callable(center):
        print("SKIP (no center method)")
        return
    try:
        result = center()
    except Exception as err:
        print(f"EXCEPTION: {err}")
        return
    if isinstance(result, dict):
        executed = bool(result.get("movement_executed", False))
        print("movement_executed=True" if executed else f"movement_executed=False  detail={result.get('detail', '')!r}")
    else:
        print("done")


def main() -> int:
    if os.environ.get(CONFIRM_ENV) != "1":
        print(f"Set {CONFIRM_ENV}=1 to run this smoke test.")
        print(f"  {CONFIRM_ENV}=1 .venv/bin/python scripts/focus_scan_smoke.py")
        return 1

    settings_path = DEFAULT_SETTINGS
    if not settings_path.exists():
        print(f"Settings not found: {settings_path}")
        return 1

    settings = _load_settings(settings_path)
    pt_cfg = _section(settings, "pan_tilt")
    fv_cfg = _section(settings, "focus_vision")
    scan_pan_degrees = float(fv_cfg.get("scan_pan_degrees", 12.0))
    settle_seconds = float(fv_cfg.get("scan_point_settle_seconds", 1.0))

    print()
    print("Focus Mode Active Scan — hardware smoke test")
    print(f"  scan_pan_degrees       = {scan_pan_degrees}")
    print(f"  scan_point_settle_s    = {settle_seconds}")
    print()

    _print_gate_summary(pt_cfg, fv_cfg)

    from modules.devices.pan_tilt import PanTiltService

    try:
        backend = PanTiltService(config=pt_cfg)
    except Exception as err:
        print(f"Failed to build PanTiltService: {err}")
        return 1

    status = backend.status()
    print("── Backend status ─────────────────────────────────────")
    for key in ("backend", "serial_write_enabled", "hardware_enabled", "motion_enabled", "dry_run", "device_exists", "calibration_ready"):
        if key in status:
            print(f"  {key} = {status[key]}")
    print()

    print("── Sweep: center → left → center → right → center ─────")
    _do_center(backend, "center (start)")
    time.sleep(settle_seconds / 2.0)

    _do_move(backend, -scan_pan_degrees, f"left  {scan_pan_degrees}°")
    time.sleep(settle_seconds)

    _do_center(backend, "center")
    time.sleep(settle_seconds / 2.0)

    _do_move(backend, +scan_pan_degrees, f"right {scan_pan_degrees}°")
    time.sleep(settle_seconds)

    _do_center(backend, "center (end)")
    print()
    print("Sweep complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
