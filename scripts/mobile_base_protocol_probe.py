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

from modules.devices.mobile_base import (  # noqa: E402
    DEFAULT_BAUDRATE,
    DEFAULT_TIMEOUT_SEC,
    DEFAULT_MOVEMENT_CONFIRM_ENV,
    DEFAULT_MOVEMENT_CONFIRM_VALUE,
    choose_serial_port,
    detect_serial_ports,
)

CONFIRM_TEST_ENV_VAR = "CONFIRM_NEXA_MOBILE_BASE_TEST"
CONFIRM_TEST_ENV_VALUE = "RUN"

ROS_STOP = {"T": 13, "X": 0.0, "Z": 0.0}
WHEEL_STOP = {"T": 1, "L": 0.0, "R": 0.0}


def _json_line(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


def _hardware_gate_is_open() -> bool:
    return os.environ.get(CONFIRM_TEST_ENV_VAR) == CONFIRM_TEST_ENV_VALUE


def _movement_gate_is_open() -> bool:
    return os.environ.get(DEFAULT_MOVEMENT_CONFIRM_ENV) == DEFAULT_MOVEMENT_CONFIRM_VALUE


def _print_ports() -> None:
    ports = detect_serial_ports()
    if not ports:
        print("[PROBE] No serial ports detected.")
        return
    print("[PROBE] Serial ports:")
    for port in ports:
        data = port.as_dict()
        print(
            "  - "
            f"device={data['device']} real={data['real_device']} "
            f"description={data['description'] or 'n/a'} source={data['source'] or 'n/a'}"
        )


def _payload_for_mode(mode: str, *, linear_speed_mps: float, angular_speed_rad_s: float, wheel_speed_mps: float) -> dict[str, Any]:
    if mode == "stop-only":
        return ROS_STOP.copy()
    if mode == "ros-forward":
        return {"T": 13, "X": abs(float(linear_speed_mps)), "Z": 0.0}
    if mode == "ros-backward":
        return {"T": 13, "X": -abs(float(linear_speed_mps)), "Z": 0.0}
    if mode == "ros-rotate-left":
        return {"T": 13, "X": 0.0, "Z": abs(float(angular_speed_rad_s))}
    if mode == "ros-rotate-right":
        return {"T": 13, "X": 0.0, "Z": -abs(float(angular_speed_rad_s))}
    if mode == "wheel-forward":
        return {"T": 1, "L": abs(float(wheel_speed_mps)), "R": abs(float(wheel_speed_mps))}
    if mode == "wheel-backward":
        return {"T": 1, "L": -abs(float(wheel_speed_mps)), "R": -abs(float(wheel_speed_mps))}
    if mode == "wheel-rotate-left":
        return {"T": 1, "L": -abs(float(wheel_speed_mps)), "R": abs(float(wheel_speed_mps))}
    if mode == "wheel-rotate-right":
        return {"T": 1, "L": abs(float(wheel_speed_mps)), "R": -abs(float(wheel_speed_mps))}
    raise ValueError(f"Unsupported mode: {mode}")


def _stop_payloads_for_mode(mode: str) -> list[dict[str, Any]]:
    if mode.startswith("wheel-"):
        return [WHEEL_STOP.copy(), ROS_STOP.copy()]
    return [ROS_STOP.copy(), WHEEL_STOP.copy()]


def _write_payload(ser: Any, payload: dict[str, Any]) -> None:
    line = _json_line(payload)
    print(f"[PROBE WRITE] {line.decode('utf-8').strip()}")
    ser.write(line)
    ser.flush()


def _read_available(ser: Any, *, duration_sec: float) -> None:
    if duration_sec <= 0:
        return
    deadline = time.monotonic() + float(duration_sec)
    while time.monotonic() < deadline:
        raw = ser.readline()
        if not raw:
            continue
        print(f"[PROBE READ] {raw.decode('utf-8', errors='replace').strip()}")


def _send_repeated_stop(ser: Any, *, mode: str, repeat: int, interval_sec: float) -> None:
    print("[PROBE] Sending repeated STOP.")
    for _ in range(max(1, int(repeat))):
        for payload in _stop_payloads_for_mode(mode):
            _write_payload(ser, payload)
            time.sleep(max(0.0, float(interval_sec)))


def _run_probe(args: argparse.Namespace) -> int:
    _print_ports()

    if not _hardware_gate_is_open():
        print(f"[PROBE ERROR] Set {CONFIRM_TEST_ENV_VAR}={CONFIRM_TEST_ENV_VALUE} before opening hardware serial.")
        return 2

    movement_mode = str(args.mode) != "stop-only"
    if movement_mode:
        if not bool(args.enable_movement):
            print("[PROBE ERROR] Movement mode requested, but --enable-movement is missing.")
            return 3
        if not _movement_gate_is_open():
            print(f"[PROBE ERROR] Movement gate is closed. Set {DEFAULT_MOVEMENT_CONFIRM_ENV}={DEFAULT_MOVEMENT_CONFIRM_VALUE}.")
            return 4

    selected_port = choose_serial_port(explicit_port=args.port)
    payload = _payload_for_mode(
        str(args.mode),
        linear_speed_mps=float(args.linear_speed_mps),
        angular_speed_rad_s=float(args.angular_speed_rad_s),
        wheel_speed_mps=float(args.wheel_speed_mps),
    )

    print(f"[PROBE] Selected port: {selected_port}")
    print(f"[PROBE] Mode: {args.mode}")
    print(f"[PROBE] Payload: {json.dumps(payload, separators=(',', ':'))}")
    print(f"[PROBE] Duration: {float(args.duration_sec):.3f} sec")
    print(f"[PROBE] Rate: {float(args.rate_hz):.1f} Hz")
    print(f"[PROBE] Hardware gate: {CONFIRM_TEST_ENV_VAR}={os.environ.get(CONFIRM_TEST_ENV_VAR, '<unset>')}")
    print(f"[PROBE] Movement gate: {DEFAULT_MOVEMENT_CONFIRM_ENV}={os.environ.get(DEFAULT_MOVEMENT_CONFIRM_ENV, '<unset>')}")

    try:
        import serial
    except Exception as error:
        print(f"[PROBE ERROR] pyserial is required: {error}")
        return 5

    ser = serial.Serial(
        selected_port,
        baudrate=int(args.baudrate),
        timeout=max(0.0, float(args.timeout_sec)),
        write_timeout=max(0.0, float(args.timeout_sec)),
    )
    try:
        reset_input = getattr(ser, "reset_input_buffer", None)
        if callable(reset_input):
            reset_input()

        _send_repeated_stop(ser, mode=str(args.mode), repeat=int(args.stop_repeat), interval_sec=float(args.stop_interval_sec))
        _read_available(ser, duration_sec=float(args.read_seconds))

        if not movement_mode:
            print("[PROBE OK] STOP-only protocol probe completed.")
            return 0

        period_sec = 1.0 / max(1.0, float(args.rate_hz))
        deadline = time.monotonic() + float(args.duration_sec)
        print("[PROBE] Sending movement burst now. Keep wheels raised.")
        while time.monotonic() < deadline:
            _write_payload(ser, payload)
            time.sleep(period_sec)

        _send_repeated_stop(ser, mode=str(args.mode), repeat=int(args.stop_repeat), interval_sec=float(args.stop_interval_sec))
        _read_available(ser, duration_sec=float(args.read_seconds))
        print("[PROBE OK] Movement protocol probe completed.")
        return 0
    finally:
        try:
            _send_repeated_stop(ser, mode=str(args.mode), repeat=max(3, int(args.stop_repeat)), interval_sec=float(args.stop_interval_sec))
        finally:
            ser.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe Waveshare mobile base serial movement protocols safely.")
    parser.add_argument("--port", type=str, default=None)
    parser.add_argument("--baudrate", type=int, default=DEFAULT_BAUDRATE)
    parser.add_argument("--timeout-sec", type=float, default=DEFAULT_TIMEOUT_SEC)
    parser.add_argument(
        "--mode",
        choices=[
            "stop-only",
            "ros-forward",
            "ros-backward",
            "ros-rotate-left",
            "ros-rotate-right",
            "wheel-forward",
            "wheel-backward",
            "wheel-rotate-left",
            "wheel-rotate-right",
        ],
        default="stop-only",
    )
    parser.add_argument("--enable-movement", action="store_true")
    parser.add_argument("--linear-speed-mps", type=float, default=0.15)
    parser.add_argument("--angular-speed-rad-s", type=float, default=0.30)
    parser.add_argument("--wheel-speed-mps", type=float, default=0.12)
    parser.add_argument("--duration-sec", type=float, default=0.8)
    parser.add_argument("--rate-hz", type=float, default=10.0)
    parser.add_argument("--read-seconds", type=float, default=0.5)
    parser.add_argument("--stop-repeat", type=int, default=4)
    parser.add_argument("--stop-interval-sec", type=float, default=0.04)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run_probe(args)
    except KeyboardInterrupt:
        print("[PROBE] Interrupted by user.")
        return 130
    except Exception as error:
        print(f"[PROBE ERROR] {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
