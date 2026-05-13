from __future__ import annotations

import pytest

from modules.devices.mobile_base import DryRunSerialTransport, MobileBaseController, MobileBaseSafetyError, MobileBaseSafetyPolicy


def _payloads(transport: DryRunSerialTransport) -> list[str]:
    return [line.strip() for line in transport.written_lines]


def test_controller_stop_sends_repeated_zero_velocity_commands() -> None:
    transport = DryRunSerialTransport()
    controller = MobileBaseController(transport=transport, stop_repeat=2, stop_interval_sec=0.0)

    controller.open()
    written = controller.stop(reason="test")

    assert written == ['{"T":13,"X":0.0,"Z":0.0}', '{"T":13,"X":0.0,"Z":0.0}']
    assert _payloads(transport) == written


def test_controller_context_sends_stop_before_close() -> None:
    transport = DryRunSerialTransport()

    with MobileBaseController(transport=transport, stop_repeat=1, stop_interval_sec=0.0):
        assert transport.opened is True

    assert transport.closed is True
    assert _payloads(transport) == ['{"T":13,"X":0.0,"Z":0.0}']


def test_controller_blocks_movement_by_default() -> None:
    transport = DryRunSerialTransport()
    controller = MobileBaseController(transport=transport, stop_interval_sec=0.0)
    controller.open()

    with pytest.raises(MobileBaseSafetyError, match="disabled"):
        controller.drive_forward()

    assert _payloads(transport) == []


def test_controller_allows_small_movement_when_policy_and_env_gate_are_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONFIRM_NEXA_MOBILE_BASE_MOVE", "RUN")
    transport = DryRunSerialTransport()
    policy = MobileBaseSafetyPolicy(movement_enabled=True, max_linear_speed_mps=0.08)
    controller = MobileBaseController(
        transport=transport,
        safety_policy=policy,
        stop_repeat=1,
        stop_interval_sec=0.0,
    )
    controller.open()

    line = controller.drive_forward(speed_mps=1.0)

    assert line == '{"T":13,"X":0.08,"Z":0.0}'
    assert _payloads(transport) == ['{"T":13,"X":0.08,"Z":0.0}']


def test_controller_deadman_sends_stop_after_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIRM_NEXA_MOBILE_BASE_MOVE", "RUN")
    transport = DryRunSerialTransport()
    policy = MobileBaseSafetyPolicy(movement_enabled=True, deadman_timeout_ms=250)
    controller = MobileBaseController(
        transport=transport,
        safety_policy=policy,
        stop_repeat=1,
        stop_interval_sec=0.0,
    )
    controller.open()
    controller.drive_forward(speed_mps=0.02)

    assert controller.check_deadman(now_monotonic=controller._last_motion_monotonic + 0.1) is False
    assert controller.check_deadman(now_monotonic=controller._last_motion_monotonic + 0.3) is True

    assert _payloads(transport) == [
        '{"T":13,"X":0.02,"Z":0.0}',
        '{"T":13,"X":0.0,"Z":0.0}',
    ]


def test_controller_rotate_uses_angular_velocity_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIRM_NEXA_MOBILE_BASE_MOVE", "RUN")
    transport = DryRunSerialTransport()
    policy = MobileBaseSafetyPolicy(movement_enabled=True, max_angular_speed_rad_s=0.25)
    controller = MobileBaseController(transport=transport, safety_policy=policy, stop_interval_sec=0.0)
    controller.open()

    left = controller.rotate_left(speed_rad_s=0.5)
    right = controller.rotate_right(speed_rad_s=0.5)

    assert left == '{"T":13,"X":0.0,"Z":0.25}'
    assert right == '{"T":13,"X":0.0,"Z":-0.25}'


def test_controller_wheel_profile_sends_direct_left_right_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIRM_NEXA_MOBILE_BASE_MOVE", "RUN")
    transport = DryRunSerialTransport()
    policy = MobileBaseSafetyPolicy(movement_enabled=True, max_linear_speed_mps=0.20, max_angular_speed_rad_s=0.45)
    controller = MobileBaseController(
        transport=transport,
        safety_policy=policy,
        stop_repeat=1,
        stop_interval_sec=0.0,
        command_profile="wheel",
        wheel_turn_speed_mps=0.12,
    )
    controller.open()

    forward = controller.drive_forward(speed_mps=0.15)
    left = controller.rotate_left(speed_rad_s=0.30)
    stop = controller.stop(reason="test")

    assert forward == '{"T":1,"L":0.15,"R":0.15}'
    assert left == '{"T":1,"L":-0.12,"R":0.12}'
    assert stop == ['{"T":1,"L":0.0,"R":0.0}']
