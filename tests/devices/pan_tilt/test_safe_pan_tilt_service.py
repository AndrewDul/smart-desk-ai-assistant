from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from modules.devices.pan_tilt import PanTiltService


class _FakeSerialPort:
    def __init__(self, writes: list[str]) -> None:
        self._writes = writes
        self.reset_called = False
        self.flush_count = 0

    def __enter__(self) -> "_FakeSerialPort":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def reset_input_buffer(self) -> None:
        self.reset_called = True

    def write(self, payload: bytes) -> int:
        text = payload.decode("utf-8")
        self._writes.append(text)
        return len(payload)

    def flush(self) -> None:
        self.flush_count += 1

    def readline(self) -> bytes:
        return b""


class _FakeSerialFactory:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.writes: list[str] = []

    def __call__(self, port: str, baudrate: int, *, timeout: float) -> _FakeSerialPort:
        self.calls.append(
            {
                "port": port,
                "baudrate": baudrate,
                "timeout": timeout,
            }
        )
        return _FakeSerialPort(self.writes)


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


def test_disabled_backend_never_sends_motion() -> None:
    service = PanTiltService(
        config={
            "enabled": False,
            "backend": "waveshare_serial",
            "device": "/dev/ttyACM0",
        }
    )

    status = service.status()
    assert status["ok"] is True
    assert status["backend"] == "disabled"
    assert status["movement_available"] is False

    result = service.move_direction("left")
    assert result["ok"] is False
    assert "disabled" in result["error"].lower()

    delta = service.move_delta(pan_delta_degrees=0.5, tilt_delta_degrees=0.0)
    assert delta["ok"] is False
    assert delta["movement_executed"] is False


def test_legacy_pca9685_backend_is_blocked() -> None:
    service = PanTiltService(
        config={
            "enabled": True,
            "backend": "pca9685",
            "hardware_enabled": True,
            "motion_enabled": True,
        }
    )

    status = service.status()
    assert status["backend"] == "disabled"
    assert status["movement_available"] is False

    result = service.center()
    assert result["ok"] is False


def test_waveshare_serial_backend_is_status_only_by_default(tmp_path: Path) -> None:
    device = tmp_path / "serial0"
    device.touch()
    service = PanTiltService(
        config={
            "enabled": True,
            "backend": "waveshare_serial",
            "hardware_enabled": False,
            "motion_enabled": False,
            "dry_run": True,
            "device": str(device),
        }
    )

    status = service.status()
    assert status["ok"] is True
    assert status["backend"] == "waveshare_serial"
    assert status["serial_opened"] is False
    assert status["serial_write_enabled"] is False
    assert status["movement_available"] is False

    result = service.move_direction("left")
    assert result["ok"] is False
    assert "blocked" in result["error"].lower()

    delta = service.move_delta(pan_delta_degrees=0.5, tilt_delta_degrees=0.0)
    assert delta["ok"] is False
    assert delta["movement_executed"] is False
    assert "pan_tilt.hardware_enabled" in delta["missing_safety_gates"]
    assert "pan_tilt.motion_enabled" in delta["missing_safety_gates"]
    assert "pan_tilt.dry_run=false" in delta["missing_safety_gates"]


def test_waveshare_serial_backend_requires_calibration_when_configured(tmp_path: Path) -> None:
    device = tmp_path / "serial0"
    device.touch()
    fake_serial = _FakeSerialFactory()
    service = PanTiltService(
        config={
            "enabled": True,
            "backend": "waveshare_serial",
            "hardware_enabled": True,
            "motion_enabled": True,
            "dry_run": False,
            "device": str(device),
            "calibration_required": True,
            "allow_uncalibrated_motion": False,
            "calibration_state_path": str(tmp_path / "missing_calibration.json"),
        },
        serial_factory=fake_serial,
    )

    result = service.move_delta(pan_delta_degrees=0.25, tilt_delta_degrees=0.0)

    assert result["ok"] is False
    assert result["movement_executed"] is False
    assert result["calibration_ready"] is False
    assert "pan_tilt.calibration_ready" in result["missing_safety_gates"]
    assert fake_serial.calls == []


def test_waveshare_serial_move_delta_executes_only_when_all_backend_gates_are_enabled(
    tmp_path: Path,
) -> None:
    device = tmp_path / "serial0"
    calibration = tmp_path / "pan_tilt_limit_calibration.json"
    device.touch()
    _calibration_state(calibration)
    fake_serial = _FakeSerialFactory()
    service = PanTiltService(
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
            "max_step_degrees": 0.5,
            "command_speed": 45,
            "command_acceleration": 45,
            "serial_warmup_seconds": 0.0,
        },
        serial_factory=fake_serial,
    )

    result = service.move_delta(pan_delta_degrees=1.5, tilt_delta_degrees=-0.25)

    assert result["ok"] is True
    assert result["movement_executed"] is True
    assert result["serial_write_enabled"] is True
    assert result["applied_pan_delta_degrees"] == 0.5
    assert result["applied_tilt_delta_degrees"] == -0.25
    assert fake_serial.calls == [
        {
            "port": str(device),
            "baudrate": 115200,
            "timeout": 0.2,
        }
    ]
    sent_commands = [json.loads(line) for line in fake_serial.writes]
    assert sent_commands[:3] == [
        {"T": 137, "s": 0, "y": 0},
        {"T": 4, "cmd": 2},
        {"T": 210, "cmd": 1},
    ]
    assert sent_commands[3] == {
        "T": 133,
        "X": 0.5,
        "Y": -0.25,
        "SPD": 45,
        "ACC": 45,
    }


def test_mock_backend_respects_safe_limits() -> None:
    service = PanTiltService(
        config={
            "enabled": True,
            "backend": "mock",
            "motion_enabled": True,
            "max_step_degrees": 2.0,
            "safe_limits": {
                "pan_min_degrees": -2.0,
                "pan_center_degrees": 0.0,
                "pan_max_degrees": 2.0,
                "tilt_min_degrees": -1.0,
                "tilt_center_degrees": 0.0,
                "tilt_max_degrees": 1.0,
            },
        }
    )

    left = service.move_direction("left")
    assert left["ok"] is True
    assert left["pan_angle"] == -2.0

    second_left = service.move_direction("left")
    assert second_left["ok"] is True
    assert second_left["pan_angle"] == -2.0

    up = service.move_direction("up")
    assert up["ok"] is True
    assert up["tilt_angle"] == 1.0

    delta = service.move_delta(pan_delta_degrees=10.0, tilt_delta_degrees=-10.0)
    assert delta["ok"] is True
    assert delta["applied_pan_delta_degrees"] == 2.0
    assert delta["applied_tilt_delta_degrees"] == -2.0
    assert delta["pan_angle"] == 0.0
    assert delta["tilt_angle"] == -1.0
