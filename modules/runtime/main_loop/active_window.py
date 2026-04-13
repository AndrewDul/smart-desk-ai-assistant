from __future__ import annotations

import time
from typing import TYPE_CHECKING

from modules.core.session.voice_session import (
    VOICE_INPUT_OWNER_VOICE_INPUT,
    VOICE_INPUT_OWNER_WAKE_GATE,
    VOICE_PHASE_COMMAND,
    VOICE_PHASE_FOLLOW_UP,
    VOICE_PHASE_GRACE,
    VOICE_PHASE_TRANSCRIBE,
    VOICE_PHASE_WAKE_GATE,
    VOICE_STATE_STANDBY,
)
from modules.shared.logging.logger import append_log

from .backend_helpers import (
    _follow_up_window_seconds,
    _grace_window_seconds,
    _initial_command_window_seconds,
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
from .session_state import MainLoopRuntimeState
from .text_gate import (
    _is_blank_or_silence,
    _is_bracketed_non_speech,
    _looks_like_isolated_wake_transcript,
    _looks_like_wake_alias,
    _sanitize_inline_command,
)

if TYPE_CHECKING:
    from modules.core.assistant import CoreAssistant


_PHASE_TO_SESSION_PHASE = {
    PHASE_COMMAND: VOICE_PHASE_COMMAND,
    PHASE_FOLLOW_UP: VOICE_PHASE_FOLLOW_UP,
    PHASE_GRACE: VOICE_PHASE_GRACE,
}


def _reset_active_counters(state_flags: MainLoopRuntimeState) -> None:
    state_flags.reset_active_counters()


def _set_active_phase(state_flags: MainLoopRuntimeState, phase: str) -> None:
    state_flags.set_active_phase(phase)


def _active_phase(state_flags: MainLoopRuntimeState) -> str:
    return str(state_flags.active_phase or PHASE_COMMAND)


def _voice_phase_for_active_phase(phase: str) -> str:
    return _PHASE_TO_SESSION_PHASE.get(str(phase or PHASE_COMMAND), VOICE_PHASE_COMMAND)


def _banner_for_phase(phase: str) -> str:
    if phase == PHASE_FOLLOW_UP:
        return "\nStandby. Waiting for follow-up..."
    if phase == PHASE_GRACE:
        return "\nStandby. Still listening..."
    return "\nStandby. Waiting for command..."

def _note_turn_benchmark_wake_detected(
    assistant: CoreAssistant,
    *,
    source: str,
) -> None:
    service = getattr(assistant, "turn_benchmark_service", None)
    if service is None:
        return

    method = getattr(service, "note_wake_detected", None)
    if not callable(method):
        return

    try:
        method(source=source)
    except Exception as error:
        append_log(f"Turn benchmark wake note failed: {error}")


def _note_turn_benchmark_listening_started(
    assistant: CoreAssistant,
    *,
    phase: str,
) -> None:
    service = getattr(assistant, "turn_benchmark_service", None)
    if service is None:
        return

    method = getattr(service, "note_listening_started", None)
    if not callable(method):
        return

    try:
        method(phase=phase)
    except Exception as error:
        append_log(f"Turn benchmark listening note failed: {error}")


def _note_turn_benchmark_speech_finalized(
    assistant: CoreAssistant,
    *,
    text: str,
    phase: str,
) -> None:
    service = getattr(assistant, "turn_benchmark_service", None)
    if service is None:
        return

    method = getattr(service, "note_speech_finalized", None)
    if not callable(method):
        return

    try:
        method(text=text, phase=phase)
    except Exception as error:
        append_log(f"Turn benchmark speech-finalized note failed: {error}")

def _acknowledge_wake(assistant: CoreAssistant) -> None:
    assistant.voice_session.transition_to_wake_detected(detail="wake_phrase_detected")

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
    state_flags: MainLoopRuntimeState,
    *,
    reason: str,
) -> None:
    _prepare_for_standby_capture(assistant, state_flags)
    assistant.voice_session.transition_to_standby(
        detail=reason,
        phase=VOICE_PHASE_WAKE_GATE,
        input_owner=VOICE_INPUT_OWNER_WAKE_GATE,
        close_active_window=True,
    )
    state_flags.hide_standby_banner()
    state_flags.clear_prefetched_command()
    state_flags.arm_wake_rearm(WAKE_REARM_SETTLE_SECONDS)
    _set_active_phase(state_flags, PHASE_COMMAND)


def _wake_rearm_remaining_seconds(state_flags: MainLoopRuntimeState) -> float:
    return state_flags.wake_rearm_remaining_seconds()


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
    state_flags: MainLoopRuntimeState,
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

    _note_turn_benchmark_wake_detected(assistant, source=source_label)

    state_flags.reset_wake_detection()
    state_flags.hide_standby_banner()
    state_flags.store_prefetched_command(safe_inline_command)
    append_log(f"Wake phrase accepted by {source_label}.")
    _acknowledge_wake(assistant)
    return True


def _listen_for_wake_via_stt_fallback(
    assistant: CoreAssistant,
    state_flags: MainLoopRuntimeState,
) -> bool:
    state_flags.mark_stt_wake_fallback_attempt()
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


def _should_try_stt_wake_fallback(state_flags: MainLoopRuntimeState) -> bool:
    if not WAKE_STT_FALLBACK_ENABLED:
        return False

    if int(state_flags.wake_miss_count) < WAKE_STT_FALLBACK_AFTER_MISSES:
        return False

    return (
        time.monotonic() - float(state_flags.last_wake_stt_fallback_monotonic or 0.0)
    ) >= WAKE_STT_FALLBACK_COOLDOWN_SECONDS


def _listen_for_wake(assistant: CoreAssistant, state_flags: MainLoopRuntimeState) -> bool:
    _prepare_for_standby_capture(assistant, state_flags)

    if (
        assistant.voice_session.state != VOICE_STATE_STANDBY
        or assistant.voice_session.input_owner() != VOICE_INPUT_OWNER_WAKE_GATE
        or assistant.voice_session.interaction_phase() != VOICE_PHASE_WAKE_GATE
    ):
        assistant.voice_session.transition_to_standby(
            detail="waiting_for_wake",
            phase=VOICE_PHASE_WAKE_GATE,
            input_owner=VOICE_INPUT_OWNER_WAKE_GATE,
        )

    if not state_flags.standby_banner_shown:
        print("\nStandby. Waiting for wake phrase...")
        state_flags.show_standby_banner()

    rearm_remaining = _wake_rearm_remaining_seconds(state_flags)
    if rearm_remaining > 0.0:
        time.sleep(min(rearm_remaining, 0.05))
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

        state_flags.record_wake_miss()
        if _should_try_stt_wake_fallback(state_flags):
            return _listen_for_wake_via_stt_fallback(assistant, state_flags)
        return False

    if not state_flags.compatibility_wake_mode_logged:
        append_log(
            "No dedicated wake backend is available. "
            "Using compatibility wake flow through standard voice input listen()."
        )
        print("Compatibility wake mode active for current voice backend.")
        state_flags.compatibility_wake_mode_logged = True

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


def _listen_for_active_command(assistant: CoreAssistant, state_flags: MainLoopRuntimeState) -> str | None:
    prefetched = state_flags.consume_prefetched_command()
    if prefetched:
        _note_turn_benchmark_speech_finalized(
            assistant,
            text=prefetched,
            phase="inline_command_after_wake",
        )
        assistant.voice_session.transition_to_transcribing(
            detail="inline_command_after_wake",
            phase=VOICE_PHASE_TRANSCRIBE,
        )
        return prefetched

    _prepare_for_active_capture(assistant)
    active_phase = _active_phase(state_flags)

    _note_turn_benchmark_listening_started(
        assistant,
        phase=active_phase,
    )

    assistant.voice_session.transition_to_listening(
        detail=f"active_window:{active_phase}",
        phase=_voice_phase_for_active_phase(active_phase),
        input_owner=VOICE_INPUT_OWNER_VOICE_INPUT,
    )
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
        _note_turn_benchmark_speech_finalized(
            assistant,
            text=cleaned,
            phase=active_phase,
        )
        assistant.voice_session.transition_to_transcribing(
            detail="speech_captured",
            phase=VOICE_PHASE_TRANSCRIBE,
        )
    return cleaned or None


def _start_follow_up_window(assistant: CoreAssistant, state_flags: MainLoopRuntimeState) -> None:
    assistant.voice_session.open_active_window(
        seconds=_follow_up_window_seconds(assistant),
        phase=VOICE_PHASE_FOLLOW_UP,
        input_owner=VOICE_INPUT_OWNER_VOICE_INPUT,
        detail="awaiting_follow_up",
    )
    _set_active_phase(state_flags, PHASE_FOLLOW_UP)
    state_flags.hide_standby_banner()


def _start_grace_window(assistant: CoreAssistant, state_flags: MainLoopRuntimeState) -> None:
    assistant.voice_session.open_active_window(
        seconds=_grace_window_seconds(assistant),
        phase=VOICE_PHASE_GRACE,
        input_owner=VOICE_INPUT_OWNER_VOICE_INPUT,
        detail="grace_after_response",
    )
    _set_active_phase(state_flags, PHASE_GRACE)
    state_flags.hide_standby_banner()


def _rearm_after_command(assistant: CoreAssistant, state_flags: MainLoopRuntimeState) -> None:
    if _session_requires_follow_up(assistant):
        _start_follow_up_window(assistant, state_flags)
        return
    _start_grace_window(assistant, state_flags)


def _handle_no_speech_capture(assistant: CoreAssistant, state_flags: MainLoopRuntimeState) -> bool:
    phase = _active_phase(state_flags)
    attempt_number = state_flags.record_empty_capture()
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

    if remaining > 0.35 and attempt_number <= retry_limit:
        assistant.voice_session.transition_to_listening(
            detail=detail,
            phase=_voice_phase_for_active_phase(phase),
            input_owner=VOICE_INPUT_OWNER_VOICE_INPUT,
        )
        return True

    _return_to_wake_gate(assistant, state_flags, reason=f"{phase}_window_expired")
    return False


def _handle_ignored_active_transcript(assistant: CoreAssistant, state_flags: MainLoopRuntimeState) -> bool:
    phase = _active_phase(state_flags)
    attempt_number = state_flags.record_ignored_capture()
    remaining = assistant.voice_session.active_window_remaining_seconds()

    if phase == PHASE_FOLLOW_UP:
        retry_limit = FOLLOW_UP_IGNORE_RETRY_LIMIT
    elif phase == PHASE_GRACE:
        retry_limit = GRACE_IGNORE_RETRY_LIMIT
    else:
        retry_limit = COMMAND_IGNORE_RETRY_LIMIT

    if remaining > 0.35 and attempt_number <= retry_limit:
        assistant.voice_session.transition_to_listening(
            detail=f"{phase}_ignored_transcript",
            phase=_voice_phase_for_active_phase(phase),
            input_owner=VOICE_INPUT_OWNER_VOICE_INPUT,
        )
        return True

    _return_to_wake_gate(assistant, state_flags, reason=f"{phase}_ignored_transcript")
    return False


def _prime_command_window_after_wake(assistant: CoreAssistant, state_flags: MainLoopRuntimeState) -> None:
    _wait_for_input_ready(assistant)
    assistant.voice_session.open_active_window(
        seconds=_initial_command_window_seconds(assistant),
        phase=VOICE_PHASE_COMMAND,
        input_owner=VOICE_INPUT_OWNER_VOICE_INPUT,
        detail="awaiting_command_after_wake",
    )
    _set_active_phase(state_flags, PHASE_COMMAND)
    state_flags.hide_standby_banner()