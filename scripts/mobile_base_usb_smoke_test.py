#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Protocol

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.devices.mobile_base.commands import build_stop_sequence, serialize_json_line
from modules.devices.mobile_base.serial_transport import (
    DEFAULT_BAUDRATE,
    DEFAULT_TIMEOUT_SEC,
    DryRunSerialTransport,
    PySerialLineTransport,
    choose_serial_port,
    detect_serial_ports,
)


CONFIRM_ENV_VAR = "CONFIRM_NEXA_MOBILE_BASE_TEST"
CONFIRM_ENV_VALUE = "RUN"


class LineTransport(Protocol):
    def open(self) -> None:
        ...

    def write_line(self, line: str) -> None:
        ...

    def read_available_lines(self, *, duration_sec: float = 0.0) -> list[str]:
        ...

    def close(self) -> None:
        ...


def _hardware_gate_is_open() -> bool:
    return os.environ.get(CONFIRM_ENV_VAR) == CONFIRM_ENV_VALUE


def _print_detected_ports() -> None:
    candidates = detect_serial_ports()
    if not candidates:
        print("[INFO] No serial ports detected.")
        return
    print("[INFO] Detected serial ports:")
    for candidate in candidates:
        data = candidate.as_dict()
        print(
            "  - "
            f"device={data['device']} real={data['real_device']} "
            f"description={data['description'] or '-'} source={data['source'] or '-'}"
        )


def _send_stop_sequence(
    *,
    transport: LineTransport,
    stop_repeat: int,
    stop_interval_sec: float,
) -> list[str]:
    written_lines: list[str] = []
    for command in build_stop_sequence(repeat=stop_repeat):
        line = serialize_json_line(command)
        transport.write_line(line)
        written_lines.append(line.rstrip("\n"))
        if stop_interval_sec > 0.0:
            time.sleep(stop_interval_sec)
    return written_lines


def run_stop_only_smoke(
    *,
    dry_run: bool,
    port: str | None,
    baudrate: int,
    timeout_sec: float,
    read_seconds: float,
    stop_repeat: int,
    stop_interval_sec: float,
) -> int:
    """Run a STOP-only smoke test. No movement commands are sent."""

    if dry_run:
        selected_port = port or "dry-run:auto"
        transport: LineTransport = DryRunSerialTransport()
        print("[DRY-RUN] Mobile base USB smoke test will not open hardware serial.")
    else:
        if not _hardware_gate_is_open():
            print(
                f"[ERROR] Hardware gate is closed. Set {CONFIRM_ENV_VAR}={CONFIRM_ENV_VALUE} "
                "and use --send-stop-only to run the real STOP-only smoke test."
            )
            return 2
        selected_port = choose_serial_port(explicit_port=port)
        transport = PySerialLineTransport(
            port=selected_port,
            baudrate=baudrate,
            timeout_sec=timeout_sec,
        )

    print(f"[INFO] Selected port: {selected_port}")
    print(f"[INFO] Baudrate: {baudrate}")
    print(f"[INFO] STOP repeat: {stop_repeat}")
    print("[INFO] Command profile: Waveshare ROS-style zero velocity, no movement.")

    try:
        transport.open()
        written_lines = _send_stop_sequence(
            transport=transport,
            stop_repeat=stop_repeat,
            stop_interval_sec=stop_interval_sec,
        )
        for line in written_lines:
            prefix = "[DRY-RUN]" if dry_run else "[WRITE]"
            print(f"{prefix} {line}")

        responses = transport.read_available_lines(duration_sec=read_seconds)
        for response in responses:
            print(f"[READ] {response}")

        print("[OK] STOP-only smoke test completed.")
        return 0
    except PermissionError:
        print(
            "[ERROR] Permission denied when opening the serial port. "
            "Use the correct port or add your user to the dialout group."
        )
        return 3
    except KeyboardInterrupt:
        print("[WARN] Interrupted by user. Closing transport after STOP-only attempt.")
        return 130
    except Exception as error:
        print(f"[ERROR] {error}")
        return 4
    finally:
        try:
            transport.close()
        except Exception:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NeXa mobile base USB/serial STOP-only smoke test."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the STOP command sequence without opening the serial port.",
    )
    parser.add_argument(
        "--list-ports",
        action="store_true",
        help="List detected serial ports and exit.",
    )
    parser.add_argument(
        "--send-stop-only",
        action="store_true",
        help="Allow the script to send only repeated STOP commands to hardware.",
    )
    parser.add_argument(
        "--port",
        type=str,
        default=None,
        help="Serial device path, e.g. /dev/ttyACM0 or /dev/serial/by-id/....",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=DEFAULT_BAUDRATE,
        help="Serial baudrate. Waveshare general driver examples use 115200.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=DEFAULT_TIMEOUT_SEC,
        help="Serial read/write timeout in seconds.",
    )
    parser.add_argument(
        "--read-seconds",
        type=float,
        default=0.2,
        help="Optional time window for passive serial feedback after STOP.",
    )
    parser.add_argument(
        "--stop-repeat",
        type=int,
        default=3,
        help="How many STOP commands to send. Allowed range: 1..10.",
    )
    parser.add_argument(
        "--stop-interval-sec",
        type=float,
        default=0.04,
        help="Delay between repeated STOP commands.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_ports:
        _print_detected_ports()
        return 0

    if not args.dry_run and not args.send_stop_only:
        print(
            "[ERROR] Refusing hardware access without --send-stop-only. "
            "This Sprint 1 script never sends movement commands."
        )
        return 2

    return run_stop_only_smoke(
        dry_run=bool(args.dry_run),
        port=args.port,
        baudrate=int(args.baudrate),
        timeout_sec=float(args.timeout_sec),
        read_seconds=max(0.0, float(args.read_seconds)),
        stop_repeat=int(args.stop_repeat),
        stop_interval_sec=max(0.0, float(args.stop_interval_sec)),
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
