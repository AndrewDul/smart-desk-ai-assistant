from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from modules.runtime.contracts import VisionObservation


SCRIPT_PATH = Path("scripts/run_vision_real_face_tracking_loop.py")


class _FakeCameraService:
    def __init__(self, config: dict[str, Any], observations: list[VisionObservation]) -> None:
        self.config = dict(config)
        self.observations = list(observations)
        self.index = 0
        self.started = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def latest_observation(self, *, force_refresh: bool = True) -> VisionObservation:
        del force_refresh
        if self.index >= len(self.observations):
            return self.observations[-1]
        observation = self.observations[self.index]
        self.index += 1
        return observation

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "backend": self.config.get("backend"),
            "last_error": None,
            "closed": self.closed,
        }

    def close(self) -> None:
        self.closed = True


class _FakePanTiltService:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = dict(config)
        self.move_calls: list[dict[str, float]] = []
        self.center_calls = 0
        self.closed = False

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "backend": self.config.get("backend", "waveshare_serial"),
            "enabled": self.config.get("enabled", False),
            "hardware_enabled": self.config.get("hardware_enabled", False),
            "motion_enabled": self.config.get("motion_enabled", False),
            "dry_run": self.config.get("dry_run", True),
            "movement_available": bool(
                self.config.get("enabled", False)
                and self.config.get("hardware_enabled", False)
                and self.config.get("motion_enabled", False)
                and not self.config.get("dry_run", True)
            ),
            "device": self.config.get("device", "/dev/serial0"),
            "baudrate": self.config.get("baudrate", 115200),
            "timeout_seconds": self.config.get("timeout_seconds", 0.2),
            "protocol": self.config.get("protocol", "waveshare_json_serial"),
            "startup_policy": "no_motion",
            "calibration_required": True,
            "allow_uncalibrated_motion": False,
            "calibration_ready": True,
            "serial_write_count": len(self.move_calls) * 6,
            "safe_limits": {
                "pan_min_degrees": -15.0,
                "pan_center_degrees": 0.0,
                "pan_max_degrees": 15.0,
                "tilt_min_degrees": -8.0,
                "tilt_center_degrees": 0.0,
                "tilt_max_degrees": 8.0,
            },
        }

    def move_delta(self, *, pan_delta_degrees: float, tilt_delta_degrees: float) -> dict[str, Any]:
        self.move_calls.append(
            {
                "pan_delta_degrees": float(pan_delta_degrees),
                "tilt_delta_degrees": float(tilt_delta_degrees),
            }
        )
        return {
            "ok": True,
            "movement_executed": True,
            "applied_pan_delta_degrees": float(pan_delta_degrees),
            "applied_tilt_delta_degrees": float(tilt_delta_degrees),
        }

    def center(self) -> dict[str, Any]:
        self.center_calls += 1
        return {"ok": True, "movement_executed": True, "centered": True}

    def close(self) -> None:
        self.closed = True


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_vision_real_face_tracking_loop",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_state(path: Path) -> None:
    path.write_text(
        """
{
  "port": "/dev/serial0",
  "baudrate": 115200,
  "x": 0.0,
  "y": 0.0,
  "marked_limits": {
    "pan_left_x": -15.0,
    "pan_right_x": 15.0,
    "tilt_min_y": -8.0,
    "tilt_max_y": 8.0
  }
}
""".strip(),
        encoding="utf-8",
    )


def _face_observation(*, center_x_norm: float, center_y_norm: float) -> VisionObservation:
    frame_width = 1280
    frame_height = 720
    box_width = 160
    box_height = 160
    center_x = int(center_x_norm * frame_width)
    center_y = int(center_y_norm * frame_height)
    left = center_x - box_width // 2
    top = center_y - box_height // 2
    return VisionObservation(
        detected=True,
        user_present=True,
        labels=["camera_online", "face_detected"],
        confidence=0.9,
        metadata={
            "frame_width": frame_width,
            "frame_height": frame_height,
            "perception": {
                "faces": [
                    {
                        "confidence": 0.92,
                        "bounding_box": {
                            "left": left,
                            "top": top,
                            "right": left + box_width,
                            "bottom": top + box_height,
                        },
                        "metadata": {"detector": "fake_loop_test"},
                    }
                ],
                "people": [],
            },
        },
    )


def _no_face_observation() -> VisionObservation:
    return VisionObservation(
        detected=True,
        user_present=False,
        labels=["camera_online"],
        metadata={
            "frame_width": 1280,
            "frame_height": 720,
            "perception": {"faces": [], "people": []},
        },
    )


def _default_kwargs(module, tmp_path: Path) -> dict[str, Any]:
    state_path = tmp_path / "pan_tilt_limit_calibration.json"
    status_path = tmp_path / "loop_status.json"
    _write_state(state_path)
    return {
        "settings_path": Path("config/settings.json"),
        "state_path": state_path,
        "status_path": status_path,
        "width": 1280,
        "height": 720,
        "backend": "picamera2",
        "fallback_backend": "opencv",
        "hflip": False,
        "vflip": False,
        "steps": 3,
        "interval_seconds": 0.05,
        "max_duration_seconds": 5.0,
        "port": None,
        "baudrate": None,
        "max_step_degrees": 1.0,
        "pan_gain_degrees": 4.0,
        "tilt_gain_degrees": 4.0,
        "dead_zone_x": 0.01,
        "dead_zone_y": 0.01,
        "speed": 55,
        "acceleration": 55,
        "execute": False,
        "understand": False,
        "confirm_text": "",
        "return_center": False,
    }


def test_loop_preview_tracks_targets_without_hardware_execution(tmp_path) -> None:
    module = _load_module()
    kwargs = _default_kwargs(module, tmp_path)

    observations = [
        _face_observation(center_x_norm=0.7, center_y_norm=0.5),
        _face_observation(center_x_norm=0.65, center_y_norm=0.52),
        _face_observation(center_x_norm=0.55, center_y_norm=0.51),
    ]

    def camera_factory(config: dict[str, Any]) -> _FakeCameraService:
        return _FakeCameraService(config, observations)

    payload = module.run_real_face_tracking_loop(
        **kwargs,
        camera_service_factory=camera_factory,
        pan_tilt_service_factory=_FakePanTiltService,
    )

    assert payload["ok"] is True
    assert payload["execute"] is False
    assert payload["target_count"] == 3
    assert payload["backend_command_count"] == 0
    assert payload["steps_completed"] == 3


def test_loop_execute_moves_fake_backend_multiple_times_and_can_return_center(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_module()
    kwargs = _default_kwargs(module, tmp_path)
    kwargs.update(
        {
            "execute": True,
            "understand": True,
            "confirm_text": module.CONFIRM_VALUE,
            "return_center": True,
        }
    )
    monkeypatch.setenv(module.CONFIRM_ENV_NAME, module.CONFIRM_VALUE)

    observations = [
        _face_observation(center_x_norm=0.72, center_y_norm=0.7),
        _face_observation(center_x_norm=0.66, center_y_norm=0.65),
        _face_observation(center_x_norm=0.6, center_y_norm=0.6),
    ]
    holder: dict[str, _FakePanTiltService] = {}

    def camera_factory(config: dict[str, Any]) -> _FakeCameraService:
        return _FakeCameraService(config, observations)

    def pan_tilt_factory(config: dict[str, Any]) -> _FakePanTiltService:
        service = _FakePanTiltService(config)
        holder["service"] = service
        return service

    payload = module.run_real_face_tracking_loop(
        **kwargs,
        camera_service_factory=camera_factory,
        pan_tilt_service_factory=pan_tilt_factory,
    )

    assert payload["ok"] is True
    assert payload["execute"] is True
    assert payload["target_count"] == 3
    assert payload["backend_command_count"] >= 1
    assert len(holder["service"].move_calls) >= 1
    assert holder["service"].center_calls == 1
    assert payload["return_center_result"]["ok"] is True


def test_loop_no_face_reports_no_target_without_hardware_execution(tmp_path) -> None:
    module = _load_module()
    kwargs = _default_kwargs(module, tmp_path)
    observations = [_no_face_observation(), _no_face_observation(), _no_face_observation()]

    def camera_factory(config: dict[str, Any]) -> _FakeCameraService:
        return _FakeCameraService(config, observations)

    payload = module.run_real_face_tracking_loop(
        **kwargs,
        camera_service_factory=camera_factory,
        pan_tilt_service_factory=_FakePanTiltService,
    )

    assert payload["ok"] is False
    assert payload["target_count"] == 0
    assert payload["no_target_count"] == 3
    assert payload["backend_command_count"] == 0


def test_loop_execute_requires_env_confirmation(tmp_path, monkeypatch) -> None:
    module = _load_module()
    kwargs = _default_kwargs(module, tmp_path)
    kwargs.update(
        {
            "execute": True,
            "understand": True,
            "confirm_text": module.CONFIRM_VALUE,
        }
    )
    monkeypatch.delenv(module.CONFIRM_ENV_NAME, raising=False)

    try:
        module.run_real_face_tracking_loop(
            **kwargs,
            camera_service_factory=lambda config: _FakeCameraService(
                config,
                [_face_observation(center_x_norm=0.7, center_y_norm=0.7)],
            ),
            pan_tilt_service_factory=_FakePanTiltService,
        )
    except SystemExit as error:
        assert module.CONFIRM_ENV_NAME in str(error)
    else:
        raise AssertionError("Expected SystemExit without confirmation env var.")
