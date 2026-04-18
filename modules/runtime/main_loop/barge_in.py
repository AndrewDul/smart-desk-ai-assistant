from __future__ import annotations

import time
from typing import TYPE_CHECKING

from modules.core.session.voice_session import (
    VOICE_INPUT_OWNER_VOICE_INPUT,
    VOICE_PHASE_COMMAND,
)
from modules.shared.logging.logger import append_log

from .active_window import _prime_command_window_after_wake
from .backend_helpers import (
    _assistant_output_blocks_input,
    _resolve_wake_backend,
    _wait_for_input_ready,
    _wake_backend_shares_voice_input,
)
from .constants import (
    BARGE_IN_MIN_OUTPUT_AGE_SECONDS,
    BARGE_IN_REFRACTORY_SECONDS,
    BARGE_IN_RESUME_TIMEOUT_SECONDS,
    BARGE_IN_WAKE_TIMEOUT_SECONDS,
)

if TYPE_CHECKING:
    from modules.core.assistant import CoreAssistant
    from .session_state import MainLoopRuntimeState


def _store_barge_in_interrupt_snapshot(
    assistant: CoreAssistant,
    *,
    backend_label: str,
    heard_wake: str | None,
    output_age_seconds: float,
    reopened_command_window: bool,
) -> None:
    current_snapshot = dict(getattr(assistant, "_last_interrupt_snapshot", {}) or {})
    interrupt_controller = getattr(assistant, "interrupt_controller", None)
    generation = 0
    requested_generation = getattr(interrupt_controller, "requested_generation", None)
    if callable(requested_generation):
        try:
            generation = int(requested_generation() or 0)
        except Exception:
            generation = 0

    metadata = dict(current_snapshot.get("metadata", {}) or {})
    metadata.update(
        {
            "interrupt_kind": "barge_in",
            "backend": backend_label,
            "heard": str(heard_wake or "").strip(),
            "output_age_seconds": max(0.0, float(output_age_seconds or 0.0)),
            "reopened_command_window": bool(reopened_command_window),
        }
    )

    snapshot = {
        "requested": True,
        "generation": generation or int(current_snapshot.get("generation", 0) or 0),
        "reason": "wake_barge_in",
        "source": "wake_gate",
        "kind": "barge_in",
        "requested_at_monotonic": float(
            current_snapshot.get("requested_at_monotonic", 0.0) or 0.0
        ),
        "metadata": metadata,
    }
    assistant._last_interrupt_snapshot = snapshot

    benchmark_service = getattr(assistant, "turn_benchmark_service", None)
    annotate = getattr(benchmark_service, "annotate_last_completed_turn", None)
    if callable(annotate):
        try:
            annotate(interrupt_snapshot=dict(snapshot))
        except Exception:
            pass


def wake_barge_in_status(assistant: CoreAssistant) -> tuple[bool, str]:
    voice_input_cfg = assistant.settings.get("voice_input", {})
    if not bool(voice_input_cfg.get("wake_barge_in_enabled", True)):
        return False, "disabled by config"

    wake_backend, backend_label = _resolve_wake_backend(assistant)
    if wake_backend is None:
        return False, "no wake backend"

    if _wake_backend_shares_voice_input(assistant, wake_backend):
        return False, "shared voice input backend"

    listen_method = getattr(wake_backend, "listen_for_wake_phrase", None)
    if not callable(listen_method):
        return False, "wake backend has no listen_for_wake_phrase"

    return True, backend_label


def try_handle_barge_in_during_output(
    assistant: CoreAssistant,
    state_flags: MainLoopRuntimeState,
) -> bool:
    enabled, status_text = wake_barge_in_status(assistant)
    if not enabled:
        return False

    if state_flags.wake_rearm_remaining_seconds() > 0.0:
        return False

    coordinator = getattr(assistant, "audio_coordinator", None)
    if coordinator is None:
        coordinator = getattr(getattr(assistant, "voice_out", None), "audio_coordinator", None)
    if coordinator is None:
        return False

    has_active_output = getattr(coordinator, "has_active_output", None)
    if not callable(has_active_output) or not bool(has_active_output()):
        return False

    output_age_seconds = 999.0
    snapshot_method = getattr(coordinator, "snapshot", None)
    if callable(snapshot_method):
        try:
            snapshot = snapshot_method()
            started_at = float(getattr(snapshot, "last_output_started_monotonic", 0.0) or 0.0)
            if started_at > 0.0:
                output_age_seconds = max(0.0, time.monotonic() - started_at)
        except Exception:
            output_age_seconds = 999.0

    voice_input_cfg = assistant.settings.get("voice_input", {})
    min_output_age_seconds = max(
        0.0,
        float(
            voice_input_cfg.get(
                "wake_barge_in_min_output_age_seconds",
                BARGE_IN_MIN_OUTPUT_AGE_SECONDS,
            )
        ),
    )
    if output_age_seconds < min_output_age_seconds:
        return False

    timeout_seconds = max(
        0.05,
        float(
            voice_input_cfg.get(
                "wake_barge_in_timeout_seconds",
                BARGE_IN_WAKE_TIMEOUT_SECONDS,
            )
        ),
    )
    resume_timeout_seconds = max(
        0.2,
        float(
            voice_input_cfg.get(
                "wake_barge_in_resume_timeout_seconds",
                BARGE_IN_RESUME_TIMEOUT_SECONDS,
            )
        ),
    )
    refractory_seconds = max(
        0.1,
        float(
            voice_input_cfg.get(
                "wake_barge_in_refractory_seconds",
                BARGE_IN_REFRACTORY_SECONDS,
            )
        ),
    )

    wake_backend, backend_label = _resolve_wake_backend(assistant)
    if wake_backend is None:
        return False

    listen_method = getattr(wake_backend, "listen_for_wake_phrase", None)
    if not callable(listen_method):
        return False

    try:
        heard_wake = listen_method(
            timeout=timeout_seconds,
            debug=False,
            ignore_audio_block=True,
        )
    except TypeError:
        append_log(
            "Wake barge-in requires a wake backend that supports ignore_audio_block=True. "
            f"Current backend: {status_text}"
        )
        return False
    except Exception as error:
        append_log(f"Wake barge-in check failed: {error}")
        return False

    if heard_wake is None:
        return False

    append_log(
        "Wake barge-in accepted: "
        f"backend={backend_label}, heard={heard_wake}, output_age={output_age_seconds:.2f}s"
    )

    benchmark_service = getattr(assistant, "turn_benchmark_service", None)
    if benchmark_service is not None:
        note_wake_detected = getattr(benchmark_service, "note_wake_detected", None)
        if callable(note_wake_detected):
            try:
                note_wake_detected(source=f"barge_in:{backend_label}")
            except Exception as error:
                append_log(f"Wake barge-in benchmark note failed: {error}")

    request_interrupt = getattr(assistant, "request_interrupt", None)
    if callable(request_interrupt):
        try:
            request_interrupt(
                reason="wake_barge_in",
                source="wake_gate",
                metadata={
                    "interrupt_kind": "barge_in",
                    "heard": heard_wake,
                    "backend": backend_label,
                    "output_age_seconds": output_age_seconds,
                },
            )
        except Exception as error:
            append_log(f"Wake barge-in interrupt request failed: {error}")

    mark_interrupt_requested = getattr(assistant.voice_session, "mark_interrupt_requested", None)
    if callable(mark_interrupt_requested):
        try:
            mark_interrupt_requested(detail="wake_barge_in")
        except Exception:
            pass

    stop_playback = getattr(getattr(assistant, "voice_out", None), "stop_playback", None)
    if callable(stop_playback):
        try:
            stop_playback()
        except Exception as error:
            append_log(f"Wake barge-in stop_playback failed: {error}")

    state_flags.arm_wake_rearm(refractory_seconds)
    state_flags.hide_standby_banner()
    state_flags.clear_prefetched_command()

    _wait_for_input_ready(
        assistant,
        max_wait_seconds=resume_timeout_seconds,
    )

    if _assistant_output_blocks_input(assistant):
        append_log("Wake barge-in accepted, but audio output is still blocking input.")
        return False

    _prime_command_window_after_wake(assistant, state_flags)
    assistant.voice_session.transition_to_listening(
        detail="awaiting_command_after_barge_in",
        phase=VOICE_PHASE_COMMAND,
        input_owner=VOICE_INPUT_OWNER_VOICE_INPUT,
    )
    _store_barge_in_interrupt_snapshot(
        assistant,
        backend_label=backend_label,
        heard_wake=heard_wake,
        output_age_seconds=output_age_seconds,
        reopened_command_window=True,
    )

    print("\nBarge-in accepted. Listening for command...")
    return True


__all__ = [
    "try_handle_barge_in_during_output",
    "wake_barge_in_status",
]