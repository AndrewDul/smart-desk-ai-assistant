from __future__ import annotations

from modules.devices.pan_tilt import PanTiltService


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


def test_waveshare_serial_backend_is_status_only() -> None:
    service = PanTiltService(
        config={
            "enabled": True,
            "backend": "waveshare_serial",
            "hardware_enabled": False,
            "motion_enabled": False,
            "dry_run": True,
            "device": "/tmp/nexa_missing_pan_tilt_device",
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
