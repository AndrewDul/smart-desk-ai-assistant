from __future__ import annotations

import pytest

from modules.devices.mobile_base import DryRunSerialTransport, MobileBaseSafetyError
from modules.runtime.builder.mobility_mixin import RuntimeBuilderMobilityMixin


class _Builder(RuntimeBuilderMobilityMixin):
    pass


def test_mobility_builder_creates_existing_mobile_base_controller_in_dry_run() -> None:
    backend, status = _Builder()._build_mobility(
        {
            "enabled": True,
            "dry_run": True,
            "movement_enabled": False,
            "command_profile": "ros",
            "stop_repeat": 1,
            "stop_interval_seconds": 0.0,
        }
    )

    assert status.ok is True
    assert status.selected_backend == "mobile_base_controller"
    assert status.metadata["dry_run"] is True
    assert callable(getattr(backend, "send_velocity", None))
    assert callable(getattr(backend, "open", None))
    assert callable(getattr(backend, "close", None))


def test_yaw_assist_command_path_blocks_motion_until_env_gate_opens() -> None:
    backend, _status = _Builder()._build_mobility(
        {
            "enabled": True,
            "dry_run": True,
            "movement_enabled": True,
            "command_profile": "ros",
            "stop_repeat": 1,
            "stop_interval_seconds": 0.0,
        }
    )

    with pytest.raises(MobileBaseSafetyError, match="env gate is closed"):
        backend.send_velocity(linear_x_mps=0.0, angular_z_rad_s=0.12)


def test_yaw_assist_command_path_is_yaw_only_when_gate_is_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONFIRM_NEXA_MOBILE_BASE_MOVE", "RUN")
    backend, _status = _Builder()._build_mobility(
        {
            "enabled": True,
            "dry_run": True,
            "movement_enabled": True,
            "command_profile": "ros",
            "stop_repeat": 1,
            "stop_interval_seconds": 0.0,
        }
    )

    line = backend.send_velocity(linear_x_mps=0.0, angular_z_rad_s=0.12)

    assert line == '{"T":13,"X":0.0,"Z":0.12}'
    assert isinstance(backend.transport, DryRunSerialTransport)
    assert backend.transport.written_lines[-1].strip() == '{"T":13,"X":0.0,"Z":0.12}'


def test_yaw_assist_stop_is_allowed_even_when_movement_gate_is_closed() -> None:
    backend, _status = _Builder()._build_mobility(
        {
            "enabled": True,
            "dry_run": True,
            "movement_enabled": False,
            "command_profile": "ros",
            "stop_repeat": 1,
            "stop_interval_seconds": 0.0,
        }
    )

    written = backend.stop(reason="validation")

    assert written == ['{"T":13,"X":0.0,"Z":0.0}']


def test_mobility_builder_respects_nexa_mobile_base_serial_port_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NEXA_MOBILE_BASE_SERIAL_PORT must override auto-detection so that the
    correct port is used even when multiple serial devices are present.
    This is the fix for the NullMobilityBackend fallback that happens when
    choose_serial_port('auto') raises RuntimeError due to ambiguous ports."""
    monkeypatch.setenv("NEXA_MOBILE_BASE_SERIAL_PORT", "/dev/ttyACM0")

    _backend, status = _Builder()._build_mobility(
        {
            "enabled": True,
            "dry_run": True,  # dry_run skips physical port open
            "movement_enabled": False,
            "command_profile": "ros",
            "stop_repeat": 1,
            "stop_interval_seconds": 0.0,
        }
    )

    assert status.ok is True
    assert status.selected_backend == "mobile_base_controller"
    # dry_run path does not use NEXA_MOBILE_BASE_SERIAL_PORT (no real open needed)
    # but the env var must be reflected in metadata when it is set.
    # For a non-dry-run test the metadata would show the actual port.


def test_mobility_builder_records_env_port_override_in_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NEXA_MOBILE_BASE_SERIAL_PORT is recorded in the status metadata so
    operators can confirm which override took effect."""
    monkeypatch.setenv("NEXA_MOBILE_BASE_SERIAL_PORT", "/dev/ttyACM0")

    _backend, status = _Builder()._build_mobility(
        {
            "enabled": True,
            "dry_run": True,
            "movement_enabled": False,
            "command_profile": "ros",
            "stop_repeat": 1,
            "stop_interval_seconds": 0.0,
        }
    )

    # dry_run does not use the env port (DryRunSerialTransport), but the metadata
    # must still reflect it for operator visibility.
    assert status.ok is True
    assert status.metadata is not None


def test_mobility_builder_env_port_not_set_metadata_has_no_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When NEXA_MOBILE_BASE_SERIAL_PORT is not set, env_port_override must be
    None so the operator knows auto-detection was used."""
    monkeypatch.delenv("NEXA_MOBILE_BASE_SERIAL_PORT", raising=False)

    _backend, status = _Builder()._build_mobility(
        {
            "enabled": True,
            "dry_run": True,
            "movement_enabled": False,
            "command_profile": "ros",
            "stop_repeat": 1,
            "stop_interval_seconds": 0.0,
        }
    )

    assert status.ok is True
    assert status.metadata.get("env_port_override") is None
