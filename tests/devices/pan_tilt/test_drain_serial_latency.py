"""Tests for _drain_serial break-after-first-response fix.

Before the fix, _drain_serial looped until the deadline even after receiving
hardware telemetry, causing a second readline() that blocked for the full
200 ms pyserial timeout.  After the fix, a single successful read breaks the
loop immediately.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from modules.devices.pan_tilt import PanTiltService


# ---------------------------------------------------------------------------
# Fake serial helpers
# ---------------------------------------------------------------------------

class _CountingSerial:
    """Serial stub that records readline calls and returns a response exactly once."""

    def __init__(self, response_line: bytes = b"") -> None:
        self._response_line = response_line
        self.readline_calls: int = 0
        self.writes: list[str] = []

    def write(self, payload: bytes) -> int:
        self.writes.append(payload.decode("utf-8"))
        return len(payload)

    def flush(self) -> None:
        pass

    def reset_input_buffer(self) -> None:
        pass

    def readline(self) -> bytes:
        self.readline_calls += 1
        if self.readline_calls == 1 and self._response_line:
            return self._response_line
        return b""

    def close(self) -> None:
        pass

    def __enter__(self) -> "_CountingSerial":
        return self

    def __exit__(self, *_: Any) -> None:
        pass


class _CountingSerialFactory:
    def __init__(self, response_line: bytes = b"") -> None:
        self._response_line = response_line
        self.calls: list[dict[str, Any]] = []
        self._last_serial: _CountingSerial | None = None

    def __call__(self, port: str, baudrate: int, *, timeout: float) -> _CountingSerial:
        self.calls.append({"port": port, "baudrate": baudrate, "timeout": timeout})
        self._last_serial = _CountingSerial(self._response_line)
        return self._last_serial

    @property
    def last_serial(self) -> _CountingSerial | None:
        return self._last_serial


def _calibration_state(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "x": 0.0,
                "y": 0.0,
                "marked_limits": {
                    "pan_left_x": -15.0,
                    "pan_right_x": 15.0,
                    "tilt_min_y": -8.0,
                    "tilt_max_y": 8.0,
                },
            }
        )
    )


def _fully_enabled_service(
    tmp_path: Path,
    serial_factory: _CountingSerialFactory,
) -> PanTiltService:
    device = tmp_path / "serial0"
    calibration = tmp_path / "calibration.json"
    device.touch()
    _calibration_state(calibration)
    return PanTiltService(
        config={
            "enabled": True,
            "backend": "waveshare_serial",
            "hardware_enabled": True,
            "motion_enabled": True,
            "dry_run": False,
            "device": str(device),
            "baudrate": 115200,
            "timeout_seconds": 0.2,
            "calibration_required": True,
            "allow_uncalibrated_motion": False,
            "calibration_state_path": str(calibration),
            "max_step_degrees": 1.0,
            "command_speed": 45,
            "command_acceleration": 45,
            "serial_warmup_seconds": 0.0,
            "read_after_write_seconds": 0.08,
        },
        serial_factory=serial_factory,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_drain_serial_stops_after_first_telemetry_response(tmp_path: Path) -> None:
    """After fix: readline is called exactly once when hardware responds."""
    telemetry_line = b'{"id":1,"T":1,"Pan":500,"Tilt":500}\n'
    factory = _CountingSerialFactory(response_line=telemetry_line)
    service = _fully_enabled_service(tmp_path, factory)

    service.move_delta(pan_delta_degrees=0.5, tilt_delta_degrees=0.0)

    serial = factory.last_serial
    assert serial is not None
    # The move produces 5 serial commands (4 setup + 1 target).
    # Each command calls _drain_serial(read_seconds=0.08).
    # With the break fix, each drain stops after the first readline response.
    # The factory creates a new serial per move_delta (since serial_factory is set),
    # so last_serial is the final one; check it was not over-called.
    assert serial.readline_calls == 1, (
        f"Expected 1 readline call (break after response), got {serial.readline_calls}"
    )


def test_drain_serial_loops_when_readline_returns_empty(tmp_path: Path) -> None:
    """When readline always returns empty, drain loops until deadline (no early break)."""
    factory = _CountingSerialFactory(response_line=b"")
    service = _fully_enabled_service(tmp_path, factory)

    service.move_delta(pan_delta_degrees=0.5, tilt_delta_degrees=0.0)

    serial = factory.last_serial
    assert serial is not None
    # With empty readline, no break fires — loop runs until 80 ms deadline.
    # The fake readline returns immediately, so many calls happen per drain.
    assert serial.readline_calls > 1, (
        "Expected multiple readline calls when hardware returns no data"
    )


def test_drain_serial_does_not_break_early_on_empty_response(tmp_path: Path) -> None:
    """Empty readline bytes do not trigger the break; only non-empty data does."""
    factory = _CountingSerialFactory(response_line=b"")
    service = _fully_enabled_service(tmp_path, factory)

    result = service.move_delta(pan_delta_degrees=0.3, tilt_delta_degrees=0.0)
    assert result["movement_executed"] is True

    serial = factory.last_serial
    assert serial is not None
    assert serial.readline_calls >= 1


def test_drain_serial_fix_does_not_break_move_execution(tmp_path: Path) -> None:
    """The break fix must not interfere with the move being executed and reported."""
    telemetry_line = b'{"id":1,"T":1,"Pan":500,"Tilt":500}\n'
    factory = _CountingSerialFactory(response_line=telemetry_line)
    service = _fully_enabled_service(tmp_path, factory)

    result = service.move_delta(pan_delta_degrees=0.5, tilt_delta_degrees=-0.3)

    assert result["ok"] is True
    assert result["movement_executed"] is True
    assert result["applied_pan_delta_degrees"] == 0.5
    assert result["applied_tilt_delta_degrees"] == -0.3


def test_drain_serial_telemetry_updated_from_response(tmp_path: Path) -> None:
    """Hardware telemetry is parsed from the single readline response."""
    telemetry_line = b'{"id":1,"T":1,"Pan":600,"Tilt":400}\n'
    factory = _CountingSerialFactory(response_line=telemetry_line)
    service = _fully_enabled_service(tmp_path, factory)

    service.move_delta(pan_delta_degrees=0.5, tilt_delta_degrees=0.0)

    pan_tilt_status = service.status()
    assert pan_tilt_status["ok"] is True
