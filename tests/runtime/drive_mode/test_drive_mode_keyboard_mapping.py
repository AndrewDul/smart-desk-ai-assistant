from __future__ import annotations

from modules.runtime.drive_mode.keyboard_mapping import DriveModeAction, map_keyboard_event, normalize_key


def test_maps_wasd_keys_to_motion_actions() -> None:
    assert map_keyboard_event("w") is DriveModeAction.FORWARD
    assert map_keyboard_event("S") is DriveModeAction.BACKWARD
    assert map_keyboard_event("a") is DriveModeAction.ROTATE_LEFT
    assert map_keyboard_event("D") is DriveModeAction.ROTATE_RIGHT


def test_maps_arrow_keys_to_motion_actions() -> None:
    assert map_keyboard_event("ArrowUp") is DriveModeAction.FORWARD
    assert map_keyboard_event("ArrowDown") is DriveModeAction.BACKWARD
    assert map_keyboard_event("ArrowLeft") is DriveModeAction.ROTATE_LEFT
    assert map_keyboard_event("ArrowRight") is DriveModeAction.ROTATE_RIGHT


def test_maps_stop_and_exit_keys() -> None:
    assert map_keyboard_event(" ") is DriveModeAction.EMERGENCY_STOP
    assert map_keyboard_event("Space") is DriveModeAction.EMERGENCY_STOP
    assert map_keyboard_event("Escape") is DriveModeAction.EXIT
    assert map_keyboard_event("Esc") is DriveModeAction.EXIT


def test_unknown_key_is_safe_unknown_action() -> None:
    assert map_keyboard_event("q") is DriveModeAction.UNKNOWN


def test_normalize_key_removes_browser_spacing() -> None:
    assert normalize_key("Arrow Up") == "arrowup"
