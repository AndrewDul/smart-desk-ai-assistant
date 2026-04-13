from __future__ import annotations

import time
from typing import TYPE_CHECKING

from modules.core.session.voice_session import VOICE_PHASE_COMMAND
from modules.shared.logging.logger import append_log

from .active_window import (
    _active_phase,
    _banner_for_phase,
    _handle_ignored_active_transcript,
    _handle_no_speech_capture,
    _listen_for_active_command,
    _listen_for_wake,
    _prime_command_window_after_wake,
    _rearm_after_command,
)
from .backend_helpers import (
    _assistant_output_blocks_input,
    _ensure_wake_capture_released,
    _input_resume_poll_seconds,
)
from .barge_in import try_handle_barge_in_during_output
from .session_state import MainLoopRuntimeState
from .text_gate import (
    _looks_like_wake_alias,
    _normalize_gate_text,
    _sanitize_inline_command,
    _should_ignore_active_transcript,
)

if TYPE_CHECKING:
    from modules.core.assistant import CoreAssistant


def build_main_loop_state_flags() -> MainLoopRuntimeState:
    return MainLoopRuntimeState(active_phase=VOICE_PHASE_COMMAND)


def run_assistant_loop(
    assistant: CoreAssistant,
    *,
    state_flags: MainLoopRuntimeState,
    gate_log_times: dict[str, float],
) -> None:
    while True:
        if _assistant_output_blocks_input(assistant):
            if try_handle_barge_in_during_output(assistant, state_flags):
                continue

            time.sleep(_input_resume_poll_seconds(assistant))
            continue

        if not assistant.voice_session.active_window_open():
            if not _listen_for_wake(assistant, state_flags):
                continue

            _prime_command_window_after_wake(assistant, state_flags)
        else:
            if not state_flags.standby_banner_shown:
                print(_banner_for_phase(_active_phase(state_flags)))
                state_flags.show_standby_banner()

        heard_text = _listen_for_active_command(assistant, state_flags)
        if heard_text is None:
            if _handle_no_speech_capture(assistant, state_flags):
                continue
            continue

        state_flags.hide_standby_banner()

        if assistant.voice_session.heard_wake_phrase(heard_text) or _looks_like_wake_alias(heard_text):
            append_log(f"Wake phrase heard during active window: {heard_text}")
            stripped_wake = assistant.voice_session.strip_wake_phrase(heard_text)
            safe_inline_after_rewake = _sanitize_inline_command(stripped_wake, assistant)
            if safe_inline_after_rewake:
                heard_text = safe_inline_after_rewake
                append_log(f"Continuing with inline command after wake phrase: {heard_text}")
            else:
                _prime_command_window_after_wake(assistant, state_flags)
                assistant.voice_session.transition_to_listening(
                    detail="awaiting_command_after_rewake",
                    phase=VOICE_PHASE_COMMAND,
                )
                print("Wake phrase heard again. Waiting for command...")
                continue

        if _should_ignore_active_transcript(
            assistant,
            heard_text,
            gate_log_times,
            last_transcript_normalized=state_flags.last_transcript_normalized,
            last_transcript_time=state_flags.last_transcript_time,
        ):
            if _handle_ignored_active_transcript(assistant, state_flags):
                continue
            continue

        normalized_command = _normalize_gate_text(heard_text)
        if not normalized_command:
            if _handle_ignored_active_transcript(assistant, state_flags):
                continue
            continue

        print(f"Heard: {heard_text}")
        append_log(f"Accepted transcript in active session: {heard_text}")

        state_flags.remember_accepted_transcript(normalized_command)
        state_flags.reset_active_counters()

        assistant.voice_session.transition_to_routing(detail="dispatching_command")
        should_continue = assistant.handle_command(heard_text)

        if not should_continue:
            assistant.voice_session.transition_to_shutdown(detail="main_loop_exit")
            break

        _rearm_after_command(assistant, state_flags)
        _ensure_wake_capture_released(assistant)