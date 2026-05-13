from __future__ import annotations

from modules.devices.mobile_base import DryRunSerialTransport, MobileBaseController, MobileBaseSafetyPolicy
from modules.runtime.drive_mode import DriveModeAction, DriveModeService


def _build_service() -> tuple[DriveModeService, DryRunSerialTransport, MobileBaseController]:
    transport = DryRunSerialTransport()
    controller = MobileBaseController(
        transport=transport,
        safety_policy=MobileBaseSafetyPolicy(
            movement_enabled=True,
            require_movement_confirm_env=False,
            deadman_timeout_ms=50,
        ),
        stop_repeat=1,
        stop_interval_sec=0.0,
    )
    controller.open()
    return DriveModeService(controller=controller), transport, controller


def test_keydown_sends_motion_and_keyup_sends_stop() -> None:
    service, transport, controller = _build_service()
    try:
        result = service.handle_keyboard_event(event="down", key="w")
        assert result.ok is True
        assert result.action is DriveModeAction.FORWARD
        assert result.command == '{"T":13,"X":0.04,"Z":0.0}'

        release = service.handle_keyboard_event(event="up", key="w")
        assert release.ok is True
        assert release.stopped is True
        assert transport.written_lines[-1] == '{"T":13,"X":0.0,"Z":0.0}\n'
    finally:
        controller.close()


def test_space_sends_emergency_stop() -> None:
    service, transport, controller = _build_service()
    try:
        result = service.handle_keyboard_event(event="down", key="space")
        assert result.ok is True
        assert result.stopped is True
        assert transport.written_lines[-1] == '{"T":13,"X":0.0,"Z":0.0}\n'
    finally:
        controller.close()


def test_escape_sends_stop_and_requests_exit() -> None:
    service, _transport, controller = _build_service()
    try:
        result = service.handle_keyboard_event(event="down", key="Escape")
        assert result.ok is True
        assert result.stopped is True
        assert result.exit_requested is True
        assert service.exit_requested is True
    finally:
        controller.close()


def test_deadman_stop_after_motion_timeout() -> None:
    service, transport, controller = _build_service()
    try:
        service.handle_keyboard_event(event="down", key="d")
        assert transport.written_lines[-1] == '{"T":13,"X":0.0,"Z":-0.18}\n'

        sent = service.check_deadman(now_monotonic=controller._last_motion_monotonic + 0.060)
        assert sent.deadman_stop is True
        assert sent.stopped is True
        assert transport.written_lines[-1] == '{"T":13,"X":0.0,"Z":0.0}\n'
    finally:
        controller.close()


def test_unknown_key_does_not_move() -> None:
    service, transport, controller = _build_service()
    try:
        result = service.handle_keyboard_event(event="down", key="q")
        assert result.ok is False
        assert result.error == "unknown_key"
        assert transport.written_lines == []
    finally:
        controller.close()



def test_pressed_key_state_combines_forward_and_left() -> None:
    service, transport, controller = _build_service()
    try:
        result = service.handle_pressed_keys(keys=["w", "a"])
        assert result.ok is True
        assert result.action is DriveModeAction.FORWARD_LEFT
        assert result.command == '{"T":13,"X":0.04,"Z":0.18}'
        assert transport.written_lines[-1] == '{"T":13,"X":0.04,"Z":0.18}\n'
        release = service.handle_pressed_keys(keys=[])
        assert release.ok is True
        assert release.stopped is True
        assert transport.written_lines[-1] == '{"T":13,"X":0.0,"Z":0.0}\n'
    finally:
        controller.close()


def test_pressed_key_state_uses_wheel_profile_when_configured() -> None:
    transport = DryRunSerialTransport()
    controller = MobileBaseController(
        transport=transport,
        safety_policy=MobileBaseSafetyPolicy(
            movement_enabled=True,
            require_movement_confirm_env=False,
            max_linear_speed_mps=0.20,
            max_angular_speed_rad_s=0.45,
        ),
        stop_repeat=1,
        stop_interval_sec=0.0,
        command_profile="wheel",
        wheel_turn_speed_mps=0.12,
    )
    controller.open()
    try:
        service = DriveModeService(controller=controller, linear_speed_mps=0.15, angular_speed_rad_s=0.30)
        result = service.handle_pressed_keys(keys=["w", "a"])
        assert result.ok is True
        assert result.action is DriveModeAction.FORWARD_LEFT
        assert result.command == '{"T":1,"L":0.03,"R":0.2}'
    finally:
        controller.close()
