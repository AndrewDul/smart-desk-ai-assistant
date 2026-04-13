from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from modules.core.session.voice_session import (
    VOICE_INPUT_OWNER_ASSISTANT_OUTPUT,
    VOICE_INPUT_OWNER_NONE,
    VOICE_INPUT_OWNER_VOICE_INPUT,
    VOICE_INPUT_OWNER_WAKE_GATE,
    VOICE_STATE_SHUTDOWN,
    VOICE_STATE_SPEAKING,
    VOICE_STATE_THINKING,
)
from modules.shared.logging.logger import append_log

from .constants import (
    FOLLOW_UP_WINDOW_SECONDS,
    INITIAL_COMMAND_WINDOW_SECONDS,
    INPUT_READY_MAX_WAIT_SECONDS,
    POST_RESPONSE_GRACE_WINDOW_SECONDS,
)

if TYPE_CHECKING:
    from modules.core.assistant import CoreAssistant


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


def _backend_status_for(assistant: CoreAssistant, component: str) -> Any | None:
    return getattr(assistant, "backend_statuses", {}).get(component)


def _wake_backend_shares_voice_input(assistant: CoreAssistant, wake_backend: Any | None = None) -> bool:
    voice_in = getattr(assistant, "voice_in", None)
    if voice_in is None:
        return False

    backend = wake_backend
    if backend is None:
        backend, _ = _resolve_wake_backend(assistant)

    if backend is None:
        return False
    if backend is voice_in:
        return True

    wrapped_voice_input = getattr(backend, "voice_input", None)
    if wrapped_voice_input is voice_in:
        return True

    wake_status = _backend_status_for(assistant, "wake_gate")
    selected_backend = str(getattr(wake_status, "selected_backend", "") or "").strip().lower()
    return selected_backend == "compatibility_voice_input"


def _wake_backend_is_usable(assistant: CoreAssistant, wake_backend: Any | None) -> bool:
    if wake_backend is None:
        return False

    wake_status = _backend_status_for(assistant, "wake_gate")
    if wake_status is not None and not bool(getattr(wake_status, "ok", False)):
        return False

    class_name = wake_backend.__class__.__name__.lower()
    if class_name == "nullwakegate":
        return False

    listen_method = getattr(wake_backend, "listen_for_wake_phrase", None)
    return callable(listen_method)


def _resolve_wake_backend(assistant: CoreAssistant) -> tuple[Any | None, str]:
    wake_gate = getattr(assistant, "wake_gate", None)
    if wake_gate is None:
        runtime = getattr(assistant, "runtime", None)
        wake_gate = getattr(runtime, "wake_gate", None)

    if _wake_backend_is_usable(assistant, wake_gate):
        return wake_gate, "runtime.wake_gate"

    voice_in = getattr(assistant, "voice_in", None)
    if voice_in is not None and callable(getattr(voice_in, "listen_for_wake_phrase", None)):
        return voice_in, "voice_input.listen_for_wake_phrase"

    if voice_in is not None and any(
        callable(getattr(voice_in, method_name, None))
        for method_name in ("listen", "listen_once", "listen_for_command")
    ):
        return voice_in, "voice_input.listen"

    return None, "voice_input.listen"


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


def _assistant_output_blocks_input(assistant: CoreAssistant) -> bool:
    coordinator = getattr(getattr(assistant, "voice_out", None), "audio_coordinator", None)
    if coordinator is None:
        return False

    input_blocked = getattr(coordinator, "input_blocked", None)
    if not callable(input_blocked):
        return False

    try:
        blocked = bool(input_blocked())
    except Exception:
        return False

    set_input_owner = getattr(assistant.voice_session, "set_input_owner", None)
    if callable(set_input_owner):
        try:
            set_input_owner(
                VOICE_INPUT_OWNER_ASSISTANT_OUTPUT if blocked else VOICE_INPUT_OWNER_NONE
            )
        except Exception:
            pass

    if blocked and assistant.voice_session.state not in {
        VOICE_STATE_SPEAKING,
        VOICE_STATE_THINKING,
        VOICE_STATE_SHUTDOWN,
    }:
        assistant.voice_session.set_state(VOICE_STATE_SPEAKING, detail="assistant_output_shield")
    return blocked


def _input_resume_poll_seconds(assistant: CoreAssistant) -> float:
    cfg = assistant.settings.get("audio_coordination", {})
    configured = cfg.get("listen_resume_poll_seconds")
    if configured is not None:
        try:
            return max(0.01, float(configured))
        except (TypeError, ValueError):
            pass

    coordinator = getattr(getattr(assistant, "voice_out", None), "audio_coordinator", None)
    for attr in ("listen_resume_poll_seconds", "input_poll_interval_seconds"):
        value = getattr(coordinator, attr, None)
        if value is not None:
            try:
                return max(0.01, float(value))
            except (TypeError, ValueError):
                continue
    return 0.05


def _input_settle_seconds(assistant: CoreAssistant) -> float:
    settle_candidates: list[float] = []
    for component_name in ("voice_in", "wake_gate"):
        component = getattr(assistant, component_name, None)
        if component is None:
            continue
        for attr in ("input_unblock_settle_seconds", "block_release_settle_seconds"):
            value = getattr(component, attr, None)
            if value is None:
                continue
            try:
                settle_candidates.append(max(0.0, float(value)))
            except (TypeError, ValueError):
                continue
    return max(settle_candidates) if settle_candidates else 0.0


def _wait_for_input_ready(
    assistant: CoreAssistant,
    *,
    max_wait_seconds: float = INPUT_READY_MAX_WAIT_SECONDS,
) -> None:
    deadline = time.monotonic() + max(0.1, float(max_wait_seconds))
    blocked_observed = False

    while time.monotonic() < deadline:
        if not _assistant_output_blocks_input(assistant):
            break
        blocked_observed = True
        time.sleep(_input_resume_poll_seconds(assistant))

    if blocked_observed:
        settle_seconds = _input_settle_seconds(assistant)
        if settle_seconds > 0.0:
            time.sleep(settle_seconds)


def _safe_close_runtime_component(component: Any | None, label: str) -> bool:
    if component is None:
        return False

    close_method = getattr(component, "close", None)
    if not callable(close_method):
        return False

    stream_before = getattr(component, "_stream", None)

    try:
        close_method()
        if stream_before is not None:
            append_log(f"Closed runtime input component for capture handoff: {label}")
        return True
    except Exception as error:
        append_log(f"Failed to close runtime input component {label}: {error}")
        return False


def _ensure_wake_capture_released(assistant: CoreAssistant) -> None:
    wake_backend, backend_label = _resolve_wake_backend(assistant)
    voice_in = getattr(assistant, "voice_in", None)
    if wake_backend is None:
        return
    if wake_backend is voice_in:
        return
    if _wake_backend_shares_voice_input(assistant, wake_backend):
        return

    _safe_close_runtime_component(wake_backend, backend_label)


def _ensure_voice_capture_released(assistant: CoreAssistant) -> None:
    voice_in = getattr(assistant, "voice_in", None)
    if voice_in is None:
        return

    wake_backend, _ = _resolve_wake_backend(assistant)
    if _wake_backend_shares_voice_input(assistant, wake_backend):
        return

    _safe_close_runtime_component(voice_in, "voice_input")


def _prepare_for_active_capture(assistant: CoreAssistant) -> None:
    _ensure_wake_capture_released(assistant)
    _wait_for_input_ready(assistant)

    set_input_owner = getattr(assistant.voice_session, "set_input_owner", None)
    if callable(set_input_owner):
        try:
            set_input_owner(VOICE_INPUT_OWNER_VOICE_INPUT)
        except Exception:
            pass


def _prepare_for_standby_capture(assistant: CoreAssistant, state_flags: Any) -> None:
    del state_flags
    _ensure_voice_capture_released(assistant)

    set_input_owner = getattr(assistant.voice_session, "set_input_owner", None)
    if callable(set_input_owner):
        try:
            set_input_owner(VOICE_INPUT_OWNER_WAKE_GATE)
        except Exception:
            pass