from __future__ import annotations

from enum import Enum


class DriveModeAction(str, Enum):
    FORWARD = "forward"
    BACKWARD = "backward"
    ROTATE_LEFT = "rotate_left"
    ROTATE_RIGHT = "rotate_right"
    FORWARD_LEFT = "forward_left"
    FORWARD_RIGHT = "forward_right"
    BACKWARD_LEFT = "backward_left"
    BACKWARD_RIGHT = "backward_right"
    EMERGENCY_STOP = "emergency_stop"
    EXIT = "exit"
    UNKNOWN = "unknown"
    STOP = "stop"


MOTION_ACTIONS = frozenset(
    {
        DriveModeAction.FORWARD,
        DriveModeAction.BACKWARD,
        DriveModeAction.ROTATE_LEFT,
        DriveModeAction.ROTATE_RIGHT,
        DriveModeAction.FORWARD_LEFT,
        DriveModeAction.FORWARD_RIGHT,
        DriveModeAction.BACKWARD_LEFT,
        DriveModeAction.BACKWARD_RIGHT,
    }
)


def normalize_key(key: str) -> str:
    if key == " ":
        return "space"
    value = str(key or "").strip().lower().replace(" ", "")
    return {"esc": "escape", "spacebar": "space"}.get(value, value)


def _motion_key(key: str) -> str:
    return {
        "arrowup": "w",
        "arrowdown": "s",
        "arrowleft": "a",
        "arrowright": "d",
    }.get(normalize_key(key), normalize_key(key))


def map_keyboard_event(key: str) -> DriveModeAction:
    return {
        "w": DriveModeAction.FORWARD,
        "s": DriveModeAction.BACKWARD,
        "a": DriveModeAction.ROTATE_LEFT,
        "d": DriveModeAction.ROTATE_RIGHT,
        "space": DriveModeAction.EMERGENCY_STOP,
        "escape": DriveModeAction.EXIT,
    }.get(_motion_key(key), DriveModeAction.UNKNOWN)


def action_from_key_event(key: str) -> str:
    return map_keyboard_event(key).value


def action_from_active_keys(keys) -> str:
    active = {_motion_key(key) for key in keys if _motion_key(key)}
    if "escape" in active:
        return DriveModeAction.EXIT.value
    if "space" in active:
        return DriveModeAction.EMERGENCY_STOP.value

    forward = "w" in active
    backward = "s" in active
    left = "a" in active
    right = "d" in active

    if forward and not backward:
        if left and not right:
            return DriveModeAction.FORWARD_LEFT.value
        if right and not left:
            return DriveModeAction.FORWARD_RIGHT.value
        return DriveModeAction.FORWARD.value

    if backward and not forward:
        if left and not right:
            return DriveModeAction.BACKWARD_LEFT.value
        if right and not left:
            return DriveModeAction.BACKWARD_RIGHT.value
        return DriveModeAction.BACKWARD.value

    if left and not right:
        return DriveModeAction.ROTATE_LEFT.value
    if right and not left:
        return DriveModeAction.ROTATE_RIGHT.value
    return DriveModeAction.STOP.value
