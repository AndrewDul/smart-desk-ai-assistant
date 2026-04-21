from __future__ import annotations

import argparse
import glob
import json
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
class DeskSafeScenario:
    command_refresh_s: float = 0.10
    settle_pause_s: float = 0.25
    forward_speed_mps: float = 0.20
    angled_speed_mps: float = 0.14
    turn_rate_rad_s: float = 0.80

    def build_segments(self) -> list[MotionSegment]:
        return [
            MotionSegment(
                name="forward_5cm",
                x_mps=self.forward_speed_mps,
                z_rad_s=0.0,
                duration_s=0.25,
            ),
            MotionSegment(
                name="backward_5cm",
                x_mps=-self.forward_speed_mps,
                z_rad_s=0.0,
                duration_s=0.25,
            ),
            MotionSegment(
                name="slight_right_turn",
                x_mps=0.0,
                z_rad_s=self.turn_rate_rad_s,
                duration_s=0.12,
            ),
            MotionSegment(
                name="forward_3cm",
                x_mps=self.angled_speed_mps,
                z_rad_s=0.0,
                duration_s=0.18,
            ),
            MotionSegment(
                name="backward_3cm",
                x_mps=-self.angled_speed_mps,
                z_rad_s=0.0,
                duration_s=0.18,
            ),
            MotionSegment(
                name="return_heading_left",
                x_mps=0.0,
                z_rad_s=-self.turn_rate_rad_s,
                duration_s=0.12,
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


def set_feedback_mode(link: SerialJsonLink) -> None:
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
    scenario: DeskSafeScenario,
) -> None:
    print(f"[INFO] Using port: {link.port}")
    print(
        "[INFO] Sequence: forward 5cm, backward 5cm, slight right turn, "
        "forward 3cm, backward 3cm, return heading."
    )

    set_feedback_mode(link)

    segments = scenario.build_segments()

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
        description="UGV02 desk-safe forward/backward hardware movement test."
    )
    parser.add_argument(
        "--port",
        type=str,
        default=None,
        help="Serial device path, e.g. /dev/ttyACM0.",
    )
    parser.add_argument(
        "--forward-speed",
        type=float,
        default=0.20,
        help="Forward and backward linear speed in m/s.",
    )
    parser.add_argument(
        "--angled-speed",
        type=float,
        default=0.14,
        help="Short angled linear speed in m/s.",
    )
    parser.add_argument(
        "--turn-rate",
        type=float,
        default=0.80,
        help="Angular speed in rad/s for slight turns.",
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

    scenario = DeskSafeScenario(
        forward_speed_mps=args.forward_speed,
        angled_speed_mps=args.angled_speed,
        turn_rate_rad_s=args.turn_rate,
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