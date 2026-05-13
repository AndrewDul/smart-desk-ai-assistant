#!/usr/bin/env python3
"""Send a safe STOP sequence to the NeXa mobile base."""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT_SEC = 0.1
HARDWARE_GATE_ENV = "CONFIRM_NEXA_MOBILE_BASE_TEST"
HARDWARE_GATE_VALUE = "RUN"

STOP_PAYLOADS: list[dict[str, Any]] = [
    {"T": 13, "X": 0.0, "Z": 0.0},
    {"T": 1, "L": 0.0, "R": 0.0},
    {"T": 11, "L": 0, "R": 0},
]


def _detect_ports() -> list[str]:
    ports: list[str] = []

    for pattern in (
        "/dev/serial/by-id/*",
        "/dev/ttyACM*",
        "/dev/ttyUSB*",
    ):
        ports.extend(sorted(glob.glob(pattern)))

    try:
        from serial.tools import list_ports

        for item in list_ports.comports():
            if item.device not in ports:
                ports.append(item.device)
    except Exception:
        pass

    return ports


def _choose_port(explicit_port: str | None) -> str:
    if explicit_port:
        return explicit_port

    ports = _detect_ports()
    if not ports:
        raise SystemExit("No serial port detected. Pass --port explicitly.")

    if len(ports) > 1:
        print("[INFO] Detected serial ports:")
        for port in ports:
            real = str(Path(port).resolve()) if port.startswith("/dev/serial/by-id/") else port
            print(f"  - {port} real={real}")
        raise SystemExit("Multiple serial ports detected. Pass --port explicitly.")

    return ports[0]


def _line(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":")) + "\n"


def _send_stop_dry_run(stop_repeat: int) -> None:
    print("[DRY-RUN] STOP will not open hardware serial.")
    for _ in range(stop_repeat):
        for payload in STOP_PAYLOADS:
            print("[DRY-RUN]", _line(payload).strip())
    print("[OK] Mobile base STOP completed.")


def _send_stop_hardware(
    *,
    port: str,
    baudrate: int,
    timeout_sec: float,
    stop_repeat: int,
    read_seconds: float,
) -> None:
    if os.environ.get(HARDWARE_GATE_ENV) != HARDWARE_GATE_VALUE:
        raise SystemExit(
            f"Hardware gate is closed. Set {HARDWARE_GATE_ENV}={HARDWARE_GATE_VALUE}."
        )

    import serial

    print(f"[INFO] Selected port: {port}")
    print(f"[INFO] Baudrate: {baudrate}")
    print("[INFO] Command: STOP sequence only")

    with serial.Serial(port, baudrate=baudrate, timeout=timeout_sec) as ser:
        for _ in range(stop_repeat):
            for payload in STOP_PAYLOADS:
                line = _line(payload)
                print("[WRITE]", line.strip())
                ser.write(line.encode("utf-8"))
                ser.flush()
                time.sleep(0.03)

        if read_seconds > 0:
            deadline = time.monotonic() + read_seconds
            while time.monotonic() < deadline:
                raw = ser.readline()
                if raw:
                    print("[READ]", raw.decode("utf-8", errors="replace").strip())

    print("[OK] Mobile base STOP completed.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send STOP to NeXa mobile base.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list-ports", action="store_true")
    parser.add_argument("--port", default=None)
    parser.add_argument("--baudrate", type=int, default=DEFAULT_BAUDRATE)
    parser.add_argument("--timeout-sec", type=float, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument("--stop-repeat", type=int, default=3)
    parser.add_argument("--read-seconds", type=float, default=0.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_ports:
        ports = _detect_ports()
        if not ports:
            print("[INFO] No serial ports detected.")
            return 0
        print("[INFO] Detected serial ports:")
        for port in ports:
            real = str(Path(port).resolve()) if port.startswith("/dev/serial/by-id/") else port
            print(f"  - {port} real={real}")
        return 0

    if args.dry_run:
        _send_stop_dry_run(stop_repeat=max(1, int(args.stop_repeat)))
        return 0

    try:
        selected_port = _choose_port(args.port)
        _send_stop_hardware(
            port=selected_port,
            baudrate=int(args.baudrate),
            timeout_sec=float(args.timeout_sec),
            stop_repeat=max(1, int(args.stop_repeat)),
            read_seconds=max(0.0, float(args.read_seconds)),
        )
    except SystemExit as error:
        print(str(error))
        return int(error.code) if isinstance(error.code, int) else 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
