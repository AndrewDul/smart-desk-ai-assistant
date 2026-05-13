from __future__ import annotations

import pytest

from modules.devices.mobile_base.safety import (
    DEFAULT_MOVEMENT_CONFIRM_ENV,
    DEFAULT_MOVEMENT_CONFIRM_VALUE,
    MobileBaseSafetyError,
    MobileBaseSafetyPolicy,
    is_zero_velocity,
)


def test_stop_velocity_is_allowed_when_movement_disabled() -> None:
    policy = MobileBaseSafetyPolicy(movement_enabled=False)

    assert policy.validate_velocity_request(linear_x_mps=0.0, angular_z_rad_s=0.0) == (0.0, 0.0)


def test_non_zero_movement_is_blocked_by_default() -> None:
    policy = MobileBaseSafetyPolicy(movement_enabled=False)

    with pytest.raises(MobileBaseSafetyError, match="disabled"):
        policy.validate_velocity_request(linear_x_mps=0.02, angular_z_rad_s=0.0)


def test_non_zero_movement_requires_environment_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    policy = MobileBaseSafetyPolicy(movement_enabled=True, require_movement_confirm_env=True)
    monkeypatch.delenv(DEFAULT_MOVEMENT_CONFIRM_ENV, raising=False)

    with pytest.raises(MobileBaseSafetyError, match="gate is closed"):
        policy.validate_velocity_request(linear_x_mps=0.02, angular_z_rad_s=0.0)

    monkeypatch.setenv(DEFAULT_MOVEMENT_CONFIRM_ENV, DEFAULT_MOVEMENT_CONFIRM_VALUE)

    assert policy.validate_velocity_request(linear_x_mps=0.02, angular_z_rad_s=0.0) == (0.02, 0.0)


def test_speed_is_clamped_when_movement_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DEFAULT_MOVEMENT_CONFIRM_ENV, DEFAULT_MOVEMENT_CONFIRM_VALUE)
    policy = MobileBaseSafetyPolicy(
        movement_enabled=True,
        max_linear_speed_mps=0.08,
        max_angular_speed_rad_s=0.25,
    )

    assert policy.validate_velocity_request(linear_x_mps=1.0, angular_z_rad_s=-1.0) == (0.08, -0.25)


def test_invalid_speed_is_rejected() -> None:
    policy = MobileBaseSafetyPolicy(movement_enabled=False)

    with pytest.raises(MobileBaseSafetyError, match="finite"):
        policy.validate_velocity_request(linear_x_mps=float("nan"), angular_z_rad_s=0.0)


def test_duration_is_clamped() -> None:
    policy = MobileBaseSafetyPolicy(max_command_duration_ms=350)

    assert policy.clamp_duration_ms(1000) == 350
    assert policy.clamp_duration_ms(20) == 20


def test_negative_duration_is_rejected() -> None:
    policy = MobileBaseSafetyPolicy()

    with pytest.raises(MobileBaseSafetyError, match="negative"):
        policy.clamp_duration_ms(-1)


def test_zero_velocity_helper() -> None:
    assert is_zero_velocity(linear_x_mps=0.0, angular_z_rad_s=0.0) is True
    assert is_zero_velocity(linear_x_mps=0.01, angular_z_rad_s=0.0) is False
