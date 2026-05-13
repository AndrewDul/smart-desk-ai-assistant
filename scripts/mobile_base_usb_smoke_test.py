#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.devices.mobile_base import DEFAULT_BAUDRATE, DEFAULT_TIMEOUT_SEC, choose_serial_port

CONFIRM_TEST_ENV_VAR = "CONFIRM_NEXA_MOBILE_BASE_TEST"
CONFIRM_TEST_ENV_VALUE = "RUN"
STOP_PAYLOAD = {"T": 13, "X": 0.0, "Z": 0.0}


def _json_line(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safe USB smoke test for NeXa mobile base STOP command.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--send-stop-only", action="store_true")
    parser.add_argument("--port", type=str, default=None)
    parser.add_argument("--baudrate", type=int, default=DEFAULT_BAUDRATE)
    parser.add_argument("--timeout-sec", type=float, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--stop-repeat", type=int, default=2)
    parser.add_argument("--stop-interval-sec", type=float, default=0.03)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.dry_run and not args.send_stop_only:
        print("[ERROR] Refusing hardware smoke test without --send-stop-only.")
        print("Use --send-stop-only for a STOP-only hardware smoke test.")
        return 2

    repeat = max(1, int(args.stop_repeat))

    if args.dry_run:
        print("[DRY-RUN] Mobile base USB smoke test will not open hardware serial.")
        for _ in range(repeat):
            print("[DRY-RUN]", _json_line(STOP_PAYLOAD).decode("utf-8").strip())
        print("[OK] STOP-only smoke test completed.")
        return 0

    if os.environ.get(CONFIRM_TEST_ENV_VAR) != CONFIRM_TEST_ENV_VALUE:
        print(f"[ERROR] Hardware gate is closed. Set {CONFIRM_TEST_ENV_VAR}={CONFIRM_TEST_ENV_VALUE}.")
        return 2

    try:
        import serial
    except Exception as error:
        print(f"[ERROR] pyserial is required: {error}")
        return 3

    port = choose_serial_port(explicit_port=args.port)
    print(f"[INFO] Selected port: {port}")

    with serial.Serial(port, baudrate=int(args.baudrate), timeout=float(args.timeout_sec)) as ser:
        for _ in range(repeat):
            line = _json_line(STOP_PAYLOAD)
            print("[WRITE]", line.decode("utf-8").strip())
            ser.write(line)
            ser.flush()
            time.sleep(max(0.0, float(args.stop_interval_sec)))

    print("[OK] STOP-only smoke test completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
