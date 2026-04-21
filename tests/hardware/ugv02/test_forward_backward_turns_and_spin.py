from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
import termios
import time
from dataclasses import dataclass


RUNNING_UNDER_PYTEST = (
    "PYTEST_CURRENT_TEST" in os.environ
    or os.path.basename(sys.argv[0]).startswith("pytest")
)

if RUNNING_UNDER_PYTEST:
    import pytest

    pytest.skip(
        "Manual hardware test for UGV02. Run directly with python.",
        allow_module_level=True,
    )


DEFAULT_BAUDRATE = 115200
DEFAULT_PORT_PATTERNS = ("/dev/ttyACM*", "/dev/ttyUSB*")


@dataclass(frozen=True)
class MotionSegment:
    name: str
    x_mps: float
    z_rad_s: float
    duration_s: float


@dataclass(frozen=True)
class ScenarioConfig:
    command_refresh_s: float = 0.10
    settle_pause_s: float = 0.35

    linear_speed_mps: float = 0.20
    forward_distance_m: float = 0.10
    backward_distance_m: float = 0.10

    quarter_turn_command_rad_s: float = 0.40
    full_spin_command_rad_s: float = 0.35

    quarter_turn_duration_scale: float = 2.0
    full_spin_duration_scale: float = 2.0

    quarter_turn_rad: float = math.pi / 2
    full_turn_rad: float = math.pi * 2

    def build_segments(self) -> list[MotionSegment]:
        forward_duration_s = self.forward_distance_m / self.linear_speed_mps
        backward_duration_s = self.backward_distance_m / self.linear_speed_mps

        quarter_turn_duration_s = (
            self.quarter_turn_rad / self.quarter_turn_command_rad_s
        ) * self.quarter_turn_duration_scale

        full_spin_duration_s = (
            self.full_turn_rad / self.full_spin_command_rad_s
        ) * self.full_spin_duration_scale

        return [
            MotionSegment(
                name="forward_10cm",
                x_mps=self.linear_speed_mps,
                z_rad_s=0.0,
                duration_s=forward_duration_s,
            ),
            MotionSegment(
                name="backward_10cm",
                x_mps=-self.linear_speed_mps,
                z_rad_s=0.0,
                duration_s=backward_duration_s,
            ),
            MotionSegment(
                name="turn_right_90deg",
                x_mps=0.0,
                z_rad_s=self.quarter_turn_command_rad_s,
                duration_s=quarter_turn_duration_s,
            ),
            MotionSegment(
                name="turn_left_90deg",
                x_mps=0.0,
                z_rad_s=-self.quarter_turn_command_rad_s,
                duration_s=quarter_turn_duration_s,
            ),
            MotionSegment(
                name="spin_in_place_360deg",
                x_mps=0.0,
                z_rad_s=self.full_spin_command_rad_s,
                duration_s=full_spin_duration_s,
            ),
        ]


class SerialJsonLink:
    def __init__(self, port: str, baudrate: int = DEFAULT_BAUDRATE) -> None:
        self._port = port
        self._baudrate = baudrate
        self._fd: int | None = None

    def __enter__(self) -> "SerialJsonLink":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def port(self) -> str:
        return self._port

    def open(self) -> None:
        if self._fd is not None:
            return

        fd = os.open(self._port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        self._configure_port(fd, self._baudrate)
        self._fd = fd

    def close(self) -> None:
        if self._fd is None:
            return
        os.close(self._fd)
        self._fd = None

    def send_json(self, payload: dict[str, object]) -> str:
        if self._fd is None:
            raise RuntimeError("Serial port is not open.")

        line = json.dumps(payload, separators=(",", ":")) + "\n"
        os.write(self._fd, line.encode("utf-8"))
        return line.rstrip("\n")

    @staticmethod
    def _configure_port(fd: int, baudrate: int) -> None:
        if baudrate != 115200:
            raise ValueError("This hardware test currently supports only 115200 baud.")

        attrs = termios.tcgetattr(fd)

        attrs[0] = 0
        attrs[1] = 0
        attrs[2] &= ~(
            termios.PARENB
            | termios.CSTOPB
            | termios.CSIZE
            | getattr(termios, "CRTSCTS", 0)
        )
        attrs[2] |= termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[3] = 0
        attrs[4] = termios.B115200
        attrs[5] = termios.B115200
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0

        termios.tcsetattr(fd, termios.TCSANOW, attrs)


def detect_serial_port() -> str:
    candidates: list[str] = []
    for pattern in DEFAULT_PORT_PATTERNS:
        candidates.extend(glob.glob(pattern))

    unique_candidates = sorted(set(candidates))

    if not unique_candidates:
        raise RuntimeError(
            "No serial device detected. Check /dev/ttyACM* or /dev/ttyUSB*."
        )

    if len(unique_candidates) > 1:
        joined = ", ".join(unique_candidates)
        raise RuntimeError(
            f"Multiple serial devices detected: {joined}. "
            "Run again with --port <device>."
        )

    return unique_candidates[0]


def configure_feedback(link: SerialJsonLink) -> None:
    link.send_json({"T": 131, "cmd": 0})
    link.send_json({"T": 143, "cmd": 1})
    time.sleep(0.05)


def send_motion_command(link: SerialJsonLink, *, x_mps: float, z_rad_s: float) -> None:
    link.send_json(
        {
            "T": 13,
            "X": round(x_mps, 3),
            "Z": round(z_rad_s, 3),
        }
    )


def send_stop(link: SerialJsonLink) -> None:
    for _ in range(3):
        send_motion_command(link, x_mps=0.0, z_rad_s=0.0)
        time.sleep(0.04)


def execute_segment(
    *,
    link: SerialJsonLink,
    segment: MotionSegment,
    refresh_s: float,
) -> None:
    started_at = time.monotonic()

    while True:
        elapsed = time.monotonic() - started_at
        if elapsed >= segment.duration_s:
            break

        send_motion_command(
            link,
            x_mps=segment.x_mps,
            z_rad_s=segment.z_rad_s,
        )
        time.sleep(refresh_s)

    send_stop(link)


def run_scenario(
    *,
    link: SerialJsonLink,
    scenario: ScenarioConfig,
) -> None:
    configure_feedback(link)

    segments = scenario.build_segments()

    print(f"[INFO] Using port: {link.port}")
    print(
        "[INFO] Sequence: forward 10cm, backward 10cm, "
        "turn right 90deg, turn left 90deg, spin 360deg in place."
    )

    for index, segment in enumerate(segments, start=1):
        print(
            f"[STEP {index}/{len(segments)}] {segment.name} "
            f"(X={segment.x_mps:.3f}, Z={segment.z_rad_s:.3f}, "
            f"duration={segment.duration_s:.2f}s)"
        )
        execute_segment(
            link=link,
            segment=segment,
            refresh_s=scenario.command_refresh_s,
        )
        time.sleep(scenario.settle_pause_s)

    print("[INFO] Scenario finished.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="UGV02 forward/backward, 90-degree turns, and spin hardware test."
    )
    parser.add_argument(
        "--port",
        type=str,
        default=None,
        help="Serial device path, e.g. /dev/ttyACM0.",
    )
    parser.add_argument(
        "--linear-speed",
        type=float,
        default=0.20,
        help="Linear speed in m/s for forward/backward motion.",
    )
    parser.add_argument(
        "--quarter-turn-command",
        type=float,
        default=0.40,
        help="Angular command in rad/s for 90-degree turns.",
    )
    parser.add_argument(
        "--full-spin-command",
        type=float,
        default=0.35,
        help="Angular command in rad/s for full spin.",
    )
    parser.add_argument(
        "--quarter-turn-scale",
        type=float,
        default=2.0,
        help="Duration multiplier for 90-degree turns.",
    )
    parser.add_argument(
        "--full-spin-scale",
        type=float,
        default=2.0,
        help="Duration multiplier for 360-degree spin.",
    )
    parser.add_argument(
        "--command-refresh",
        type=float,
        default=0.10,
        help="Command resend interval in seconds.",
    )
    parser.add_argument(
        "--settle-pause",
        type=float,
        default=0.35,
        help="Pause between segments in seconds.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        port = args.port or detect_serial_port()
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 2

    scenario = ScenarioConfig(
        command_refresh_s=args.command_refresh,
        settle_pause_s=args.settle_pause,
        linear_speed_mps=args.linear_speed,
        quarter_turn_command_rad_s=args.quarter_turn_command,
        full_spin_command_rad_s=args.full_spin_command,
        quarter_turn_duration_scale=args.quarter_turn_scale,
        full_spin_duration_scale=args.full_spin_scale,
    )

    try:
        with SerialJsonLink(port=port) as link:
            run_scenario(link=link, scenario=scenario)
            send_stop(link)
            return 0
    except KeyboardInterrupt:
        print("[WARN] Interrupted by user. Sending stop.")
        try:
            with SerialJsonLink(port=port) as link:
                send_stop(link)
        except Exception:
            pass
        return 130
    except PermissionError:
        print(
            "[ERROR] Permission denied when opening the serial port. "
            "Try with sudo or add your user to the dialout group."
        )
        return 3
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 4


if __name__ == "__main__":
    raise SystemExit(main())