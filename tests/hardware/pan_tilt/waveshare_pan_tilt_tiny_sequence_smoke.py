#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.devices.pan_tilt.waveshare_protocol import (
    build_tiny_smoke_sequence,
    compact_json_line,
)


def _auto_detect_port() -> str | None:
    candidates: list[Path] = []
    candidates.extend(sorted(Path("/dev/serial/by-id").glob("*")))
    candidates.extend(sorted(Path("/dev").glob("ttyUSB*")))
    candidates.extend(sorted(Path("/dev").glob("ttyACM*")))
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _read_available_lines(serial_port: Any, *, seconds: float) -> list[str]:
    lines: list[str] = []
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        raw = serial_port.readline()
        if raw:
            lines.append(raw.decode("utf-8", errors="replace").strip())
    return lines


def _print_plan(commands: list[dict[str, Any]], *, port: str, baudrate: int, pause: float) -> None:
    print("## Waveshare pan-tilt tiny sequence smoke test")
    print(f"port={port}")
    print(f"baudrate={baudrate}")
    print(f"pause_seconds={pause}")
    print("sequence=right -> center -> left -> center -> up -> center -> down -> center")
    print("safety=small configured angle only; no sweeps; no mechanical extremes; steady mode off")
    print()
    for index, command in enumerate(commands, start=1):
        print(f"{index:02d}. {compact_json_line(command).strip()}")


def _confirm() -> None:
    expected = "MOVE TINY PAN TILT"
    print()
    print("This will physically move the pan-tilt by a small configured angle.")
    print("Keep cables clear and keep a hand near the power switch.")
    answer = input(f"Type {expected!r} to continue: ").strip()
    if answer != expected:
        raise SystemExit("Aborted before hardware movement.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a conservative Waveshare pan-tilt tiny movement smoke test.")
    parser.add_argument("--port", default="/dev/serial0", help="Serial port path, normally /dev/serial0 for Waveshare GPIO UART.")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--degrees", type=float, default=5.0, help="Tiny step angle, limited to 0.1..10.0.")
    parser.add_argument("--speed", type=int, default=80, help="Waveshare speed. Must be >0 because 0 is fastest.")
    parser.add_argument("--acceleration", type=int, default=80, help="Waveshare acceleration. Must be >0 because 0 is fastest.")
    parser.add_argument("--pause", type=float, default=1.0, help="Delay after each command.")
    parser.add_argument("--read-seconds", type=float, default=0.25)
    parser.add_argument("--dry-run", action="store_true", help="Print commands without opening serial port.")
    parser.add_argument("--yes", action="store_true", help="Skip interactive confirmation.")
    args = parser.parse_args()

    port = _auto_detect_port() if args.port == "auto" else args.port
    if not port and args.dry_run:
        port = "auto-not-found-dry-run"
    if not port:
        raise SystemExit("ERROR: No serial port found. Use --port /dev/serial0 for GPIO UART or verify wiring.")

    commands = build_tiny_smoke_sequence(
        degrees=args.degrees,
        speed=args.speed,
        acceleration=args.acceleration,
    )
    _print_plan(commands, port=port, baudrate=args.baudrate, pause=args.pause)

    if args.dry_run:
        print("DRY RUN: no serial port opened and no movement commands sent.")
        return 0

    if not args.yes:
        _confirm()

    try:
        import serial
    except ImportError as error:
        raise SystemExit("ERROR: pyserial is missing. Install it with: python -m pip install pyserial") from error

    with serial.Serial(port, args.baudrate, timeout=max(0.01, args.read_seconds)) as serial_port:
        time.sleep(1.0)
        serial_port.reset_input_buffer()
        for command in commands:
            line = compact_json_line(command)
            print(f"SEND: {line.strip()}")
            serial_port.write(line.encode("utf-8"))
            serial_port.flush()
            for response in _read_available_lines(serial_port, seconds=args.read_seconds):
                print(f"RECV: {response}")
            time.sleep(max(0.0, args.pause))

    print("Done. Final command was stop after returning to center.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
