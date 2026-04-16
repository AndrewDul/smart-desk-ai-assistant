from __future__ import annotations

from typing import TYPE_CHECKING

from .capture_ownership import CaptureOwnershipService
from .constants import (
    FOLLOW_UP_WINDOW_SECONDS,
    INITIAL_COMMAND_WINDOW_SECONDS,
    INPUT_READY_MAX_WAIT_SECONDS,
    POST_RESPONSE_GRACE_WINDOW_SECONDS,
)

if TYPE_CHECKING:
    from modules.core.assistant import CoreAssistant


_CAPTURE_OWNERSHIP_SERVICE = CaptureOwnershipService()


def _component_label(component: str) -> str:
    labels = {
        "voice_input": "voice input",
        "wake_gate": "wake gate",
        "voice_output": "voice output",
        "display": "display",
        "vision": "vision",
        "mobility": "mobility",
    }
    return labels.get(component, component.replace("_", " "))


def _active_command_window_seconds(assistant: CoreAssistant) -> float:
    return max(1.0, float(getattr(assistant.voice_session, "active_listen_window_seconds", 8.0)))


def _initial_command_window_seconds(assistant: CoreAssistant) -> float:
    voice_input_cfg = assistant.settings.get("voice_input", {})
    configured = voice_input_cfg.get("initial_command_window_seconds")
    if configured is not None:
        try:
            return max(2.0, float(configured))
        except (TypeError, ValueError):
            pass
    return max(6.0, min(_active_command_window_seconds(assistant), INITIAL_COMMAND_WINDOW_SECONDS))


def _follow_up_window_seconds(assistant: CoreAssistant) -> float:
    voice_input_cfg = assistant.settings.get("voice_input", {})
    configured = voice_input_cfg.get("follow_up_window_seconds")
    if configured is not None:
        try:
            return max(2.0, float(configured))
        except (TypeError, ValueError):
            pass
    return FOLLOW_UP_WINDOW_SECONDS


def _grace_window_seconds(assistant: CoreAssistant) -> float:
    voice_input_cfg = assistant.settings.get("voice_input", {})
    configured = voice_input_cfg.get("post_response_listen_window_seconds")
    if configured is not None:
        try:
            return max(2.0, float(configured))
        except (TypeError, ValueError):
            pass
    return POST_RESPONSE_GRACE_WINDOW_SECONDS


def _session_requires_follow_up(assistant: CoreAssistant) -> bool:
    return bool(assistant.pending_confirmation or assistant.pending_follow_up)


def _backend_status_for(assistant: CoreAssistant, component: str):
    return getattr(assistant, "backend_statuses", {}).get(component)


def _wake_backend_shares_voice_input(assistant: CoreAssistant, wake_backend=None) -> bool:
    return _CAPTURE_OWNERSHIP_SERVICE._wake_backend_shares_voice_input(assistant, wake_backend)


def _wake_backend_is_usable(assistant: CoreAssistant, wake_backend) -> bool:
    return _CAPTURE_OWNERSHIP_SERVICE._wake_backend_is_usable(assistant, wake_backend)


def _resolve_wake_backend(assistant: CoreAssistant):
    return _CAPTURE_OWNERSHIP_SERVICE._resolve_wake_backend(assistant)


def _assistant_output_blocks_input(assistant: CoreAssistant) -> bool:
    return _CAPTURE_OWNERSHIP_SERVICE.assistant_output_blocks_input(assistant)


def _input_resume_poll_seconds(assistant: CoreAssistant) -> float:
    return _CAPTURE_OWNERSHIP_SERVICE.input_resume_poll_seconds(assistant)


def _wait_for_input_ready(
    assistant: CoreAssistant,
    *,
    max_wait_seconds: float = INPUT_READY_MAX_WAIT_SECONDS,
) -> None:
    _CAPTURE_OWNERSHIP_SERVICE.wait_for_input_ready(
        assistant,
        max_wait_seconds=max_wait_seconds,
    )


def _safe_close_runtime_component(component, label: str) -> bool:
    return _CAPTURE_OWNERSHIP_SERVICE._safe_close_runtime_component(component, label)


def _ensure_wake_capture_released(assistant: CoreAssistant) -> None:
    _CAPTURE_OWNERSHIP_SERVICE.ensure_wake_capture_released(assistant)


def _ensure_voice_capture_released(assistant: CoreAssistant) -> None:
    _CAPTURE_OWNERSHIP_SERVICE.ensure_voice_capture_released(assistant)


def _prepare_for_active_capture(assistant: CoreAssistant) -> None:
    _CAPTURE_OWNERSHIP_SERVICE.prepare_for_active_capture(assistant)


def _prepare_for_standby_capture(assistant: CoreAssistant, state_flags) -> None:
    del state_flags
    _CAPTURE_OWNERSHIP_SERVICE.prepare_for_standby_capture(assistant)