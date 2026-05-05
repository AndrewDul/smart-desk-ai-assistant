from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from modules.runtime.contracts import VisionObservation


SCRIPT_PATH = Path("scripts/run_vision_real_face_tracking_step.py")


class _FakeCameraService:
    def __init__(self, config: dict[str, Any], *, observation: VisionObservation | None = None) -> None:
        self.config = dict(config)
        self.observation = observation
        self.force_refresh_values: list[bool] = []
        self.started = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def latest_observation(self, *, force_refresh: bool = True) -> VisionObservation | None:
        self.force_refresh_values.append(bool(force_refresh))
        return self.observation

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
            "pan_angle": 0.0,
            "tilt_angle": 0.0,
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

    def close(self) -> None:
        self.closed = True


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "run_vision_real_face_tracking_step",
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


def _face_observation(*, center_x_norm: float = 0.7, center_y_norm: float = 0.5) -> VisionObservation:
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
                        "metadata": {"detector": "fake_real_face_test"},
                    }
                ],
                "people": [],
            },
        },
    )


def test_real_face_tracking_preview_uses_camera_observation_without_moving(tmp_path) -> None:
    module = _load_module()
    state_path = tmp_path / "pan_tilt_limit_calibration.json"
    status_path = tmp_path / "real_face_status.json"
    _write_state(state_path)

    pan_tilt = _FakePanTiltService

    def camera_factory(config: dict[str, Any]) -> _FakeCameraService:
        return _FakeCameraService(config, observation=_face_observation(center_x_norm=0.7))

    payload = module.run_real_face_tracking_step(
        settings_path=Path("config/settings.json"),
        state_path=state_path,
        status_path=status_path,
        width=1280,
        height=720,
        backend="picamera2",
        fallback_backend="opencv",
        hflip=False,
        vflip=False,
        attempts=3,
        interval_seconds=0.0,
        port=None,
        baudrate=None,
        max_step_degrees=1.0,
        pan_gain_degrees=4.0,
        tilt_gain_degrees=4.0,
        dead_zone_x=0.05,
        dead_zone_y=0.05,
        speed=55,
        acceleration=55,
        execute=False,
        understand=False,
        confirm_text="",
        camera_service_factory=camera_factory,
        pan_tilt_service_factory=pan_tilt,
    )

    assert payload["ok"] is True
    assert payload["execute"] is False
    assert payload["target_summary"]["has_target"] is True
    assert payload["plan"]["has_target"] is True
    assert payload["plan"]["pan_delta_degrees"] > 0.0
    assert payload["pan_tilt_adapter_result"]["backend_command_executed"] is False
    assert payload["pan_tilt_adapter_result"]["status"] == "dry_run_backend_command_blocked"


def test_real_face_tracking_execute_moves_fake_backend_with_explicit_gates(
    tmp_path,
    monkeypatch,
) -> None:
    module = _load_module()
    state_path = tmp_path / "pan_tilt_limit_calibration.json"
    status_path = tmp_path / "real_face_status.json"
    _write_state(state_path)
    monkeypatch.setenv(module.CONFIRM_ENV_NAME, module.CONFIRM_VALUE)

    pan_tilt_holder: dict[str, _FakePanTiltService] = {}

    def camera_factory(config: dict[str, Any]) -> _FakeCameraService:
        return _FakeCameraService(config, observation=_face_observation(center_x_norm=0.7))

    def pan_tilt_factory(config: dict[str, Any]) -> _FakePanTiltService:
        service = _FakePanTiltService(config)
        pan_tilt_holder["service"] = service
        return service

    payload = module.run_real_face_tracking_step(
        settings_path=Path("config/settings.json"),
        state_path=state_path,
        status_path=status_path,
        width=1280,
        height=720,
        backend="picamera2",
        fallback_backend="opencv",
        hflip=False,
        vflip=False,
        attempts=1,
        interval_seconds=0.0,
        port=None,
        baudrate=None,
        max_step_degrees=1.0,
        pan_gain_degrees=4.0,
        tilt_gain_degrees=4.0,
        dead_zone_x=0.05,
        dead_zone_y=0.05,
        speed=55,
        acceleration=55,
        execute=True,
        understand=True,
        confirm_text=module.CONFIRM_VALUE,
        camera_service_factory=camera_factory,
        pan_tilt_service_factory=pan_tilt_factory,
    )

    assert payload["ok"] is True
    assert payload["execute"] is True
    assert payload["pan_tilt_adapter_result"]["status"] == "backend_command_executed"
    assert payload["pan_tilt_adapter_result"]["backend_command_executed"] is True
    assert pan_tilt_holder["service"].move_calls
    assert pan_tilt_holder["service"].move_calls[0]["pan_delta_degrees"] > 0.0


def test_real_face_tracking_no_face_does_not_execute_backend(tmp_path) -> None:
    module = _load_module()
    state_path = tmp_path / "pan_tilt_limit_calibration.json"
    status_path = tmp_path / "real_face_status.json"
    _write_state(state_path)

    pan_tilt_holder: dict[str, _FakePanTiltService] = {}

    def camera_factory(config: dict[str, Any]) -> _FakeCameraService:
        return _FakeCameraService(
            config,
            observation=VisionObservation(
                detected=True,
                user_present=False,
                labels=["camera_online"],
                metadata={
                    "frame_width": 1280,
                    "frame_height": 720,
                    "perception": {"faces": [], "people": []},
                },
            ),
        )

    def pan_tilt_factory(config: dict[str, Any]) -> _FakePanTiltService:
        service = _FakePanTiltService(config)
        pan_tilt_holder["service"] = service
        return service

    payload = module.run_real_face_tracking_step(
        settings_path=Path("config/settings.json"),
        state_path=state_path,
        status_path=status_path,
        width=1280,
        height=720,
        backend="picamera2",
        fallback_backend="opencv",
        hflip=False,
        vflip=False,
        attempts=2,
        interval_seconds=0.0,
        port=None,
        baudrate=None,
        max_step_degrees=1.0,
        pan_gain_degrees=4.0,
        tilt_gain_degrees=4.0,
        dead_zone_x=0.05,
        dead_zone_y=0.05,
        speed=55,
        acceleration=55,
        execute=False,
        understand=False,
        confirm_text="",
        camera_service_factory=camera_factory,
        pan_tilt_service_factory=pan_tilt_factory,
    )

    assert payload["ok"] is False
    assert payload["target_summary"]["has_target"] is False
    assert payload["plan"]["reason"] == "no_target"
    assert pan_tilt_holder["service"].move_calls == []


def test_real_face_tracking_execute_requires_env_confirmation(tmp_path, monkeypatch) -> None:
    module = _load_module()
    state_path = tmp_path / "pan_tilt_limit_calibration.json"
    _write_state(state_path)
    monkeypatch.delenv(module.CONFIRM_ENV_NAME, raising=False)

    try:
        module.run_real_face_tracking_step(
            settings_path=Path("config/settings.json"),
            state_path=state_path,
            status_path=tmp_path / "real_face_status.json",
            width=1280,
            height=720,
            backend="picamera2",
            fallback_backend="opencv",
            hflip=False,
            vflip=False,
            attempts=1,
            interval_seconds=0.0,
            port=None,
            baudrate=None,
            max_step_degrees=1.0,
            pan_gain_degrees=4.0,
            tilt_gain_degrees=4.0,
            dead_zone_x=0.05,
            dead_zone_y=0.05,
            speed=55,
            acceleration=55,
            execute=True,
            understand=True,
            confirm_text=module.CONFIRM_VALUE,
            camera_service_factory=lambda config: _FakeCameraService(
                config,
                observation=_face_observation(),
            ),
            pan_tilt_service_factory=_FakePanTiltService,
        )
    except SystemExit as error:
        assert module.CONFIRM_ENV_NAME in str(error)
    else:
        raise AssertionError("Expected SystemExit without confirmation env var.")
