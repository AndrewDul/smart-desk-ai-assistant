from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from modules.core.session.voice_session import (
    VOICE_STATE_LISTENING,
    VOICE_STATE_SPEAKING,
    VOICE_STATE_STANDBY,
    VOICE_STATE_TRANSCRIBING,
    VOICE_STATE_WAKE_DETECTED,
)
from modules.shared.logging.logger import append_log

from .backend_helpers import (
    _active_command_window_seconds,
    _ensure_wake_capture_released,
    _follow_up_window_seconds,
    _grace_window_seconds,
    _initial_command_window_seconds,
    _input_resume_poll_seconds,
    _prepare_for_active_capture,
    _prepare_for_standby_capture,
    _resolve_wake_backend,
    _session_requires_follow_up,
    _wait_for_input_ready,
)
from .constants import (
    COMMAND_EMPTY_RETRY_LIMIT,
    COMMAND_IGNORE_RETRY_LIMIT,
    FOLLOW_UP_EMPTY_RETRY_LIMIT,
    FOLLOW_UP_IGNORE_RETRY_LIMIT,
    GRACE_EMPTY_RETRY_LIMIT,
    GRACE_IGNORE_RETRY_LIMIT,
    PHASE_COMMAND,
    PHASE_FOLLOW_UP,
    PHASE_GRACE,
    WAKE_GATE_TIMEOUT_SECONDS,
    WAKE_REARM_SETTLE_SECONDS,
    WAKE_STT_FALLBACK_AFTER_MISSES,
    WAKE_STT_FALLBACK_COOLDOWN_SECONDS,
    WAKE_STT_FALLBACK_ENABLED,
    WAKE_STT_FALLBACK_TIMEOUT_SECONDS,
)
from .text_gate import (
    _is_blank_or_silence,
    _is_bracketed_non_speech,
    _looks_like_isolated_wake_transcript,
    _looks_like_wake_alias,
    _sanitize_inline_command,
    _should_ignore_active_transcript,
)

if TYPE_CHECKING:
    from modules.core.assistant import CoreAssistant


def _reset_active_counters(state_flags: dict[str, Any]) -> None:
    state_flags["active_empty_count"] = 0
    state_flags["active_ignored_count"] = 0


def _set_active_phase(state_flags: dict[str, Any], phase: str) -> None:
    state_flags["active_phase"] = phase
    _reset_active_counters(state_flags)


def _active_phase(state_flags: dict[str, Any]) -> str:
    return str(state_flags.get("active_phase", PHASE_COMMAND))


def _banner_for_phase(phase: str) -> str:
    if phase == PHASE_FOLLOW_UP:
        return "\nStandby. Waiting for follow-up..."
    if phase == PHASE_GRACE:
        return "\nStandby. Still listening..."
    return "\nStandby. Waiting for command..."


def _acknowledge_wake(assistant: CoreAssistant) -> None:
    assistant.voice_session.set_state(VOICE_STATE_WAKE_DETECTED, detail="wake_phrase_detected")

    wake_builder = getattr(assistant.voice_session, "build_wake_acknowledgement", None)
    wake_ack = wake_builder() if callable(wake_builder) else "I'm listening."

    assistant.voice_out.speak(
        wake_ack,
        language=getattr(assistant, "last_language", "en"),
    )

    append_log(f"Wake phrase detected. Acknowledgement spoken: {wake_ack}")
    print("Wake phrase detected. Waiting for command...")


def _return_to_wake_gate(
    assistant: CoreAssistant,
    state_flags: dict[str, Any],
    *,
    reason: str,
) -> None:
    _prepare_for_standby_capture(assistant, state_flags)
    assistant.voice_session.close_active_window()
    assistant.voice_session.set_state(VOICE_STATE_STANDBY, detail=reason)
    state_flags["standby_banner_shown"] = False
    state_flags["prefetched_command_text"] = None
    state_flags["wake_rearm_ready_monotonic"] = time.monotonic() + WAKE_REARM_SETTLE_SECONDS
    _set_active_phase(state_flags, PHASE_COMMAND)


def _wake_rearm_remaining_seconds(state_flags: dict[str, Any]) -> float:
    ready_at = float(state_flags.get("wake_rearm_ready_monotonic", 0.0) or 0.0)
    if ready_at <= 0.0:
        return 0.0
    return max(0.0, ready_at - time.monotonic())


def _listen_with_backend_fallback(
    assistant: CoreAssistant,
    *,
    timeout: float,
    debug: bool,
) -> str | None:
    voice_in = assistant.voice_in

    for method_name in ("listen", "listen_once", "listen_for_command"):
        method = getattr(voice_in, method_name, None)
        if callable(method):
            return method(timeout=timeout, debug=debug)

    raise AttributeError(
        "Voice input backend does not expose listen(), listen_once(), or listen_for_command()."
    )


def _accept_standby_wake(
    assistant: CoreAssistant,
    state_flags: dict[str, Any],
    source_label: str,
    *,
    inline_command: str | None = None,
) -> bool:
    safe_inline_command = _sanitize_inline_command(inline_command, assistant)
    if inline_command and safe_inline_command is None:
        append_log(
            "Discarded weak inline command after wake acceptance to avoid ghost routing: "
            f"{inline_command}"
        )

    state_flags["wake_miss_count"] = 0
    state_flags["compatibility_wake_mode_logged"] = False
    state_flags["standby_banner_shown"] = False
    state_flags["wake_rearm_ready_monotonic"] = 0.0
    state_flags["prefetched_command_text"] = safe_inline_command
    append_log(f"Wake phrase accepted by {source_label}.")
    _acknowledge_wake(assistant)
    return True


def _listen_for_wake_via_stt_fallback(
    assistant: CoreAssistant,
    state_flags: dict[str, Any],
) -> bool:
    state_flags["last_wake_stt_fallback_monotonic"] = time.monotonic()
    heard_text = _listen_with_backend_fallback(
        assistant,
        timeout=WAKE_STT_FALLBACK_TIMEOUT_SECONDS,
        debug=False,
    )
    if heard_text is None:
        return False

    cleaned = heard_text.strip()
    if not cleaned:
        return False

    if _is_blank_or_silence(cleaned) or _is_bracketed_non_speech(cleaned):
        return False

    if _looks_like_isolated_wake_transcript(cleaned):
        return _accept_standby_wake(
            assistant,
            state_flags,
            "stt_fallback",
            inline_command=None,
        )

    if assistant.voice_session.heard_wake_phrase(cleaned) or _looks_like_wake_alias(cleaned):
        append_log(
            "Rejected mixed STT wake fallback transcript to avoid false wake->command injection: "
            f"{cleaned}"
        )
        return False

    append_log(f"Ignored STT wake fallback transcript: {cleaned}")
    return False


def _should_try_stt_wake_fallback(state_flags: dict[str, Any]) -> bool:
    if not WAKE_STT_FALLBACK_ENABLED:
        return False

    consecutive_misses = int(state_flags.get("wake_miss_count", 0))
    if consecutive_misses < WAKE_STT_FALLBACK_AFTER_MISSES:
        return False

    last_attempt = float(state_flags.get("last_wake_stt_fallback_monotonic", 0.0) or 0.0)
    return (time.monotonic() - last_attempt) >= WAKE_STT_FALLBACK_COOLDOWN_SECONDS


def _listen_for_wake(assistant: CoreAssistant, state_flags: dict[str, Any]) -> bool:
    _prepare_for_standby_capture(assistant, state_flags)

    if assistant.voice_session.state != VOICE_STATE_STANDBY:
        assistant.voice_session.set_state(VOICE_STATE_STANDBY, detail="waiting_for_wake")

    if not state_flags.get("standby_banner_shown", False):
        print("\nStandby. Waiting for wake phrase...")
        state_flags["standby_banner_shown"] = True

    rearm_remaining = _wake_rearm_remaining_seconds(state_flags)
    if rearm_remaining > 0.0:
        time.sleep(min(rearm_remaining, _input_resume_poll_seconds(assistant)))
        return False

    wake_backend, backend_label = _resolve_wake_backend(assistant)
    wake_method = getattr(wake_backend, "listen_for_wake_phrase", None) if wake_backend is not None else None

    if callable(wake_method):
        heard_wake = wake_method(
            timeout=WAKE_GATE_TIMEOUT_SECONDS,
            debug=False,
            ignore_audio_block=False,
        )
        if heard_wake is not None:
            return _accept_standby_wake(assistant, state_flags, backend_label)

        state_flags["wake_miss_count"] = int(state_flags.get("wake_miss_count", 0)) + 1
        if _should_try_stt_wake_fallback(state_flags):
            return _listen_for_wake_via_stt_fallback(assistant, state_flags)
        return False

    if not state_flags.get("compatibility_wake_mode_logged", False):
        append_log(
            "No dedicated wake backend is available. "
            "Using compatibility wake flow through standard voice input listen()."
        )
        print("Compatibility wake mode active for current voice backend.")
        state_flags["compatibility_wake_mode_logged"] = True

    heard_text = _listen_with_backend_fallback(
        assistant,
        timeout=WAKE_GATE_TIMEOUT_SECONDS,
        debug=False,
    )
    if heard_text is None:
        return False

    heard_text = heard_text.strip()
    if not heard_text:
        return False

    if assistant.voice_session.heard_wake_phrase(heard_text) or _looks_like_wake_alias(heard_text):
        inline_command = assistant.voice_session.strip_wake_phrase(heard_text)
        return _accept_standby_wake(
            assistant,
            state_flags,
            "compatibility_voice_input",
            inline_command=inline_command or None,
        )

    append_log(f"Ignored transcript while waiting for wake phrase: {heard_text}")
    return False


def _active_command_timeout(assistant: CoreAssistant) -> float:
    remaining = assistant.voice_session.active_window_remaining_seconds()
    if remaining > 0:
        return max(0.35, min(float(getattr(assistant, "voice_listen_timeout", 8.0)), remaining))
    return max(0.35, float(getattr(assistant, "voice_listen_timeout", 8.0)))


def _listen_for_active_command(assistant: CoreAssistant, state_flags: dict[str, Any]) -> str | None:
    prefetched = state_flags.get("prefetched_command_text")
    if isinstance(prefetched, str) and prefetched.strip():
        state_flags["prefetched_command_text"] = None
        assistant.voice_session.set_state(VOICE_STATE_TRANSCRIBING, detail="inline_command_after_wake")
        return prefetched.strip()

    _prepare_for_active_capture(assistant)
    assistant.voice_session.set_state(VOICE_STATE_LISTENING, detail=f"active_window:{_active_phase(state_flags)}")
    print("\nListening for your request...")

    heard_text = _listen_with_backend_fallback(
        assistant,
        timeout=_active_command_timeout(assistant),
        debug=bool(getattr(assistant, "voice_debug", False)),
    )
    if heard_text is None:
        return None

    cleaned = heard_text.strip()
    if cleaned:
        assistant.voice_session.set_state(VOICE_STATE_TRANSCRIBING, detail="speech_captured")
    return cleaned or None


def _start_follow_up_window(assistant: CoreAssistant, state_flags: dict[str, Any]) -> None:
    assistant.voice_session.open_active_window(seconds=_follow_up_window_seconds(assistant))
    assistant.voice_session.set_state(VOICE_STATE_LISTENING, detail="awaiting_follow_up")
    _set_active_phase(state_flags, PHASE_FOLLOW_UP)
    state_flags["standby_banner_shown"] = False


def _start_grace_window(assistant: CoreAssistant, state_flags: dict[str, Any]) -> None:
    assistant.voice_session.open_active_window(seconds=_grace_window_seconds(assistant))
    assistant.voice_session.set_state(VOICE_STATE_LISTENING, detail="grace_after_response")
    _set_active_phase(state_flags, PHASE_GRACE)
    state_flags["standby_banner_shown"] = False


def _rearm_after_command(assistant: CoreAssistant, state_flags: dict[str, Any]) -> None:
    if _session_requires_follow_up(assistant):
        _start_follow_up_window(assistant, state_flags)
        return
    _start_grace_window(assistant, state_flags)


def _handle_no_speech_capture(assistant: CoreAssistant, state_flags: dict[str, Any]) -> bool:
    phase = _active_phase(state_flags)
    state_flags["active_empty_count"] = int(state_flags.get("active_empty_count", 0)) + 1
    remaining = assistant.voice_session.active_window_remaining_seconds()

    if phase == PHASE_FOLLOW_UP:
        retry_limit = FOLLOW_UP_EMPTY_RETRY_LIMIT
        detail = "awaiting_followup_after_silence"
    elif phase == PHASE_GRACE:
        retry_limit = GRACE_EMPTY_RETRY_LIMIT
        detail = "grace_after_silence"
    else:
        retry_limit = COMMAND_EMPTY_RETRY_LIMIT
        detail = "awaiting_command_after_silence"

    if remaining > 0.35 and state_flags["active_empty_count"] <= retry_limit:
        assistant.voice_session.set_state(VOICE_STATE_LISTENING, detail=detail)
        return True

    _return_to_wake_gate(assistant, state_flags, reason=f"{phase}_window_expired")
    return False


def _handle_ignored_active_transcript(assistant: CoreAssistant, state_flags: dict[str, Any]) -> bool:
    phase = _active_phase(state_flags)
    state_flags["active_ignored_count"] = int(state_flags.get("active_ignored_count", 0)) + 1
    remaining = assistant.voice_session.active_window_remaining_seconds()

    if phase == PHASE_FOLLOW_UP:
        retry_limit = FOLLOW_UP_IGNORE_RETRY_LIMIT
    elif phase == PHASE_GRACE:
        retry_limit = GRACE_IGNORE_RETRY_LIMIT
    else:
        retry_limit = COMMAND_IGNORE_RETRY_LIMIT

    if remaining > 0.35 and state_flags["active_ignored_count"] <= retry_limit:
        assistant.voice_session.set_state(VOICE_STATE_LISTENING, detail=f"{phase}_ignored_transcript")
        return True

    _return_to_wake_gate(assistant, state_flags, reason=f"{phase}_ignored_transcript")
    return False


def _prime_command_window_after_wake(assistant: CoreAssistant, state_flags: dict[str, Any]) -> None:
    _wait_for_input_ready(assistant)
    assistant.voice_session.open_active_window(seconds=_initial_command_window_seconds(assistant))
    assistant.voice_session.set_state(VOICE_STATE_LISTENING, detail="awaiting_command_after_wake")
    _set_active_phase(state_flags, PHASE_COMMAND)
    state_flags["standby_banner_shown"] = False