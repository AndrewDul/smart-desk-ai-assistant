from __future__ import annotations

import time

from typing import TYPE_CHECKING

from modules.core import assistant
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
from modules.core.session.visual_shell_state_feedback import (
    notify_visual_shell_idle,
    notify_visual_shell_voice_event,
)
from modules.presentation.visual_shell.contracts import VisualEventName
from modules.runtime.contracts import InputSource, TranscriptRequest, TranscriptResult, WakeDetectionResult
from modules.shared.logging.logger import append_log
from modules.runtime.voice_engine_v2.realtime_audio_bus_probe import (
    probe_realtime_audio_bus,
)
from .backend_helpers import (
    _assistant_output_blocks_input,
    _follow_up_window_seconds,
    _grace_window_seconds,
    _prepare_for_active_capture,
    _prepare_for_standby_capture,
    _resolve_wake_backend,
)
from .capture_adapters import capture_transcript, detect_wake_event
from .command_window_policy import CommandWindowPolicyService
from .resume_policy import ResumePolicyService
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


_COMMAND_WINDOW_POLICY_SERVICE = CommandWindowPolicyService()
_RESUME_POLICY_SERVICE = ResumePolicyService()


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


def _capture_handoff_reuse_enabled(assistant: CoreAssistant) -> bool:
    voice_input_cfg = assistant.settings.get("voice_input", {})
    configured = voice_input_cfg.get("wake_command_handoff_reuse_enabled")
    if configured is None:
        return True
    return bool(configured)


def _capture_handoff_reuse_max_age_seconds(assistant: CoreAssistant) -> float:
    voice_input_cfg = assistant.settings.get("voice_input", {})
    configured = voice_input_cfg.get("wake_command_handoff_reuse_max_age_seconds")
    if configured is not None:
        try:
            return max(0.1, float(configured))
        except (TypeError, ValueError):
            pass
    return 1.2


def _store_primed_capture_handoff(
    assistant: CoreAssistant,
    *,
    phase: str,
    strategy: str,
) -> dict[str, object]:
    snapshot = dict(getattr(assistant, "_last_capture_handoff", {}) or {})
    snapshot["source_phase"] = str(phase or "command").strip() or "command"
    snapshot["strategy"] = str(strategy or "wake_prime_prepare").strip() or "wake_prime_prepare"
    snapshot["reused"] = False
    snapshot["prepared_at_monotonic"] = time.perf_counter()
    assistant._last_capture_handoff = dict(snapshot)
    assistant._primed_capture_handoff = dict(snapshot)
    return dict(snapshot)


def _consume_primed_capture_handoff(
    assistant: CoreAssistant,
    *,
    phase: str,
) -> dict[str, object] | None:
    snapshot = dict(getattr(assistant, "_primed_capture_handoff", {}) or {})
    assistant._primed_capture_handoff = {}
    if not snapshot:
        return None
    if not _capture_handoff_reuse_enabled(assistant):
        return None
    if str(snapshot.get("source_phase", "") or "").strip() != str(phase or "").strip():
        return None
    prepared_at = float(snapshot.get("prepared_at_monotonic", 0.0) or 0.0)
    if prepared_at <= 0.0:
        return None
    age_seconds = max(0.0, time.perf_counter() - prepared_at)
    if age_seconds > _capture_handoff_reuse_max_age_seconds(assistant):
        return None
    if _assistant_output_blocks_input(assistant):
        return None
    if not bool(snapshot.get("wait_completed", True)):
        return None

    snapshot["strategy"] = "wake_prime_reuse"
    snapshot["reused"] = True
    snapshot["reuse_age_ms"] = age_seconds * 1000.0
    assistant._last_capture_handoff = dict(snapshot)
    return dict(snapshot)


def _input_source_label(value: object) -> str:
    raw = getattr(value, "value", value)
    cleaned = str(raw or "voice").strip().lower()
    return cleaned or "voice"


def _prepare_capture_handoff_for_phase(
    assistant: CoreAssistant,
    *,
    phase: str,
) -> dict[str, object]:
    if str(phase or "").strip() == PHASE_COMMAND:
        reused = _consume_primed_capture_handoff(assistant, phase=PHASE_COMMAND)
        if reused is not None:
            return reused

    _prepare_for_active_capture(assistant)
    snapshot = dict(getattr(assistant, "_last_capture_handoff", {}) or {})
    snapshot["source_phase"] = str(phase or "command").strip() or "command"
    snapshot["strategy"] = "active_prepare"
    snapshot["reused"] = False
    assistant._last_capture_handoff = dict(snapshot)
    return dict(snapshot)


def _capture_mode_for_active_phase(
    assistant: CoreAssistant,
    *,
    active_phase: str,
    capture_handoff: dict[str, object] | None = None,
) -> str:
    normalized_phase = str(active_phase or PHASE_COMMAND).strip() or PHASE_COMMAND

    if normalized_phase == "follow_up":
        pending_follow_up = getattr(assistant, "pending_follow_up", None)
        if isinstance(pending_follow_up, dict):
            pending_type = str(pending_follow_up.get("type", "") or "").strip().lower()
            if pending_type == "reminder_time":
                return "reminder_time"
            if pending_type == "reminder_message":
                return "reminder_message"
        return normalized_phase

    if normalized_phase != PHASE_COMMAND:
        return normalized_phase

    snapshot = dict(capture_handoff or getattr(assistant, "_last_capture_handoff", {}) or {})
    strategy = str(snapshot.get("strategy", "") or "").strip().lower()
    if strategy in {"wake_prime_prepare", "wake_prime_reuse"}:
        return "wake_command"

    return normalized_phase


def _remember_input_capture(
    assistant: CoreAssistant,
    *,
    text: str,
    phase: str,
    language: str,
    input_source: str,
    backend_label: str,
    mode: str,
    latency_ms: float,
    audio_duration_ms: float,
    confidence: float,
    metadata: dict[str, object] | None = None,
) -> None:
    assistant._last_input_capture = {
        "text": str(text or "").strip(),
        "phase": str(phase or "").strip(),
        "language": str(language or getattr(assistant, "last_language", "en")).strip().lower(),
        "input_source": str(input_source or "voice").strip().lower() or "voice",
        "backend_label": str(backend_label or "").strip(),
        "mode": str(mode or phase).strip(),
        "latency_ms": max(0.0, float(latency_ms or 0.0)),
        "audio_duration_ms": max(0.0, float(audio_duration_ms or 0.0)),
        "confidence": max(0.0, float(confidence or 0.0)),
        "metadata": dict(metadata or {}),
    }

    append_log(
        "Input capture remembered: "
        f"phase={phase}, "
        f"mode={mode}, "
        f"language={language}, "
        f"latency_ms={max(0.0, float(latency_ms or 0.0)):.1f}, "
        f"audio_duration_ms={max(0.0, float(audio_duration_ms or 0.0)):.1f}, "
        f"backend={backend_label}"
    )


def _remember_capture_from_transcript(
    assistant: CoreAssistant,
    transcript: TranscriptResult,
    *,
    phase: str,
) -> None:
    capture_metadata = dict(getattr(transcript, "metadata", {}) or {})
    _remember_input_capture(
        assistant,
        text=transcript.text,
        phase=phase,
        language=str(getattr(transcript, "language", "") or ""),
        input_source=_input_source_label(getattr(transcript, "source", "voice")),
        backend_label=str(capture_metadata.get("backend_label", "") or ""),
        mode=str(capture_metadata.get("mode", phase) or phase),
        latency_ms=float(getattr(transcript, "latency_ms", 0.0) or 0.0),
        audio_duration_ms=max(
            0.0,
            float(getattr(transcript, "duration_seconds", 0.0) or 0.0) * 1000.0,
        ),
        confidence=float(getattr(transcript, "confidence", 0.0) or 0.0),
        metadata=capture_metadata,
    )


def _note_turn_benchmark_wake_detected(
    assistant: CoreAssistant,
    *,
    source: str,
    wake_event: WakeDetectionResult | None = None,
) -> None:
    service = getattr(assistant, "turn_benchmark_service", None)
    if service is None:
        return

    method = getattr(service, "note_wake_detected", None)
    if not callable(method):
        return

    try:
        wake_metadata = dict(getattr(wake_event, "metadata", {}) or {})
        method(
            source=source,
            input_source=_input_source_label(getattr(wake_event, "source", "voice")),
            latency_ms=float(getattr(wake_event, "latency_ms", 0.0) or 0.0),
            backend_label=str(wake_metadata.get("backend_label", source) or source),
        )
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
    transcript: TranscriptResult | None = None,
) -> None:
    service = getattr(assistant, "turn_benchmark_service", None)
    if service is None:
        return

    method = getattr(service, "note_speech_finalized", None)
    if not callable(method):
        return

    try:
        transcript_metadata = dict(getattr(transcript, "metadata", {}) or {})
        method(
            text=text,
            phase=phase,
            language=str(getattr(transcript, "language", "") or ""),
            input_source=_input_source_label(getattr(transcript, "source", "voice")),
            latency_ms=float(getattr(transcript, "latency_ms", 0.0) or 0.0),
            audio_duration_ms=max(
                0.0,
                float(getattr(transcript, "duration_seconds", 0.0) or 0.0) * 1000.0,
            ),
            backend_label=str(transcript_metadata.get("backend_label", "") or ""),
            mode=str(transcript_metadata.get("mode", phase) or phase),
            confidence=float(getattr(transcript, "confidence", 0.0) or 0.0),
            finalized_at_monotonic=float(
                transcript_metadata.get("capture_finished_at_monotonic", 0.0) or 0.0
            ),
        )
    except Exception as error:
        append_log(f"Turn benchmark speech-finalized note failed: {error}")

def _wake_ack_skip_for_dedicated_gate_enabled(assistant: CoreAssistant) -> bool:
    voice_input_cfg = assistant.settings.get("voice_input", {})
    configured = voice_input_cfg.get("wake_ack_skip_for_dedicated_gate")
    if configured is None:
        return True
    return bool(configured)


def _should_skip_spoken_wake_ack(
    assistant: CoreAssistant,
    *,
    source_label: str,
    inline_command_present: bool,
) -> bool:
    if inline_command_present:
        return True

    normalized_source = str(source_label or "").strip().lower()
    if normalized_source in {"", "compatibility_voice_input", "voice_input"}:
        return False

    backend_statuses = getattr(assistant, "backend_statuses", {})
    wake_status = backend_statuses.get("wake_gate") if hasattr(backend_statuses, "get") else None
    selected_backend = str(getattr(wake_status, "selected_backend", "") or "").strip().lower()
    if selected_backend == "compatibility_voice_input":
        return False

    return _wake_ack_skip_for_dedicated_gate_enabled(assistant)


def _acknowledge_wake(
    assistant: CoreAssistant,
    *,
    source_label: str = "",
    inline_command_present: bool = False,
) -> None:
    assistant.voice_session.transition_to_wake_detected(detail="wake_phrase_detected")

    language = getattr(assistant, "last_language", "en")
    benchmark_service = getattr(assistant, "turn_benchmark_service", None)
    wake_ack = ""
    wake_ack_strategy = "listen_priority_skip"
    wake_ack_output_hold_seconds: float | None = None
    wake_ack_started_at = time.perf_counter()

    if _should_skip_spoken_wake_ack(
        assistant,
        source_label=source_label,
        inline_command_present=inline_command_present,
    ):
        wake_ack_latency_ms = max(0.0, (time.perf_counter() - wake_ack_started_at) * 1000.0)
        note_wake_acknowledged = getattr(benchmark_service, "note_wake_acknowledged", None)
        if callable(note_wake_acknowledged):
            try:
                note_wake_acknowledged(
                    text=wake_ack,
                    strategy=wake_ack_strategy,
                    latency_ms=wake_ack_latency_ms,
                    output_hold_seconds=wake_ack_output_hold_seconds,
                )
            except Exception as error:
                append_log(f"Turn benchmark wake-ack note failed: {error}")

        append_log(
            "Wake phrase detected. Spoken acknowledgement skipped to prioritize command capture: "
            f"source={source_label or 'unknown'} | strategy={wake_ack_strategy} | "
            f"ack_ms={wake_ack_latency_ms:.1f}"
        )
        print("Wake phrase detected. Waiting for command...")
        return

    wake_ack_service = getattr(assistant, "wake_ack_service", None)
    wake_ack = "I'm listening."
    wake_ack_strategy = "fallback"
    spoken = False

    if wake_ack_service is not None:
        try:
            result = wake_ack_service.speak(language=language, prefer_fast_phrase=True)
            wake_ack = result.text or wake_ack
            spoken = bool(result.spoken)
            wake_ack_strategy = str(getattr(result, "strategy", "fast") or "fast")
            wake_ack_output_hold_seconds = getattr(result, "output_hold_seconds", None)
        except Exception as error:
            append_log(f"Wake acknowledgement service failed: {error}")

    if not spoken:
        wake_builder = getattr(assistant.voice_session, "build_wake_acknowledgement", None)
        wake_ack = wake_builder() if callable(wake_builder) else wake_ack
        try:
            assistant.voice_out.speak(
                wake_ack,
                language=language,
                output_hold_seconds=wake_ack_output_hold_seconds,
            )
        except TypeError:
            assistant.voice_out.speak(
                wake_ack,
                language=language,
            )

    wake_ack_latency_ms = max(0.0, (time.perf_counter() - wake_ack_started_at) * 1000.0)
    note_wake_acknowledged = getattr(benchmark_service, "note_wake_acknowledged", None)
    if callable(note_wake_acknowledged):
        try:
            note_wake_acknowledged(
                text=wake_ack,
                strategy=wake_ack_strategy,
                latency_ms=wake_ack_latency_ms,
                output_hold_seconds=wake_ack_output_hold_seconds,
            )
        except Exception as error:
            append_log(f"Turn benchmark wake-ack note failed: {error}")

    append_log(
        "Wake phrase detected. Acknowledgement spoken: "
        f"{wake_ack} | strategy={wake_ack_strategy} | ack_ms={wake_ack_latency_ms:.1f}"
    )
    print("Wake phrase detected. Waiting for command...")


def _return_to_wake_gate(
    assistant: CoreAssistant,
    state_flags: MainLoopRuntimeState,
    *,
    reason: str,
) -> None:
    assistant._primed_capture_handoff = {}
    _prepare_for_standby_capture(assistant, state_flags)
    assistant.voice_session.transition_to_standby(
        detail=reason,
        phase=VOICE_PHASE_WAKE_GATE,
        input_owner=VOICE_INPUT_OWNER_WAKE_GATE,
        close_active_window=True,
    )
    notify_visual_shell_idle(
        assistant,
        source="main_loop.return_to_wake_gate",
        detail=reason,
    )
    state_flags.hide_standby_banner()
    state_flags.clear_prefetched_command()
    state_flags.arm_wake_rearm(WAKE_REARM_SETTLE_SECONDS)
    _set_active_phase(state_flags, PHASE_COMMAND)
    _store_session_continuity_snapshot(
        assistant,
        action="standby",
        phase=VOICE_PHASE_WAKE_GATE,
        reason=reason,
        detail=reason,
        window_seconds=0.0,
    )


def _wake_rearm_remaining_seconds(state_flags: MainLoopRuntimeState) -> float:
    return state_flags.wake_rearm_remaining_seconds()


def _speech_request_source(assistant: CoreAssistant) -> InputSource:
    voice_in = getattr(assistant, "voice_in", None)
    class_name = getattr(getattr(voice_in, "__class__", None), "__name__", "").lower()
    if "textinput" in class_name:
        return InputSource.TEXT
    return InputSource.VOICE


def _capture_transcript_with_speech_service(
    assistant: CoreAssistant,
    *,
    timeout: float,
    debug: bool,
    mode: str,
) -> TranscriptResult | None:
    speech_recognition = getattr(assistant, "speech_recognition", None)
    transcribe = getattr(speech_recognition, "transcribe", None)
    if not callable(transcribe):
        return None

    try:
        request = TranscriptRequest(
            timeout_seconds=float(timeout),
            debug=bool(debug),
            source=_speech_request_source(assistant),
            mode=str(mode or "command").strip() or "command",
            metadata={
                "adapter": "active_window",
                "capture_mode": str(mode or "command").strip() or "command",
            },
        )
        result = transcribe(request)
    except Exception as error:
        append_log(f"SpeechRecognitionService capture failed: {error}")
        return None

    if not isinstance(result, TranscriptResult):
        return None

    if not str(result.text or "").strip():
        return None

    return result

def _observe_voice_engine_v2_vad_shadow(assistant: CoreAssistant) -> dict[str, object]:
    runtime = getattr(assistant, "runtime", None)
    runtime_metadata = getattr(runtime, "metadata", {}) if runtime is not None else {}

    observer = getattr(assistant, "voice_engine_v2_vad_shadow_observer", None)
    if observer is None and isinstance(runtime_metadata, dict):
        observer = runtime_metadata.get("voice_engine_v2_vad_shadow_observer")

    observe = getattr(observer, "observe", None)
    if not callable(observe):
        return {
            "enabled": False,
            "observed": False,
            "reason": "vad_shadow_observer_unavailable",
            "action_executed": False,
            "full_stt_prevented": False,
            "runtime_takeover": False,
        }

    try:
        snapshot = observe(assistant)
    except Exception as error:
        append_log(f"Voice Engine v2 VAD shadow failed safely: {error}")
        return {
            "enabled": True,
            "observed": False,
            "reason": f"vad_shadow_failed:{type(error).__name__}",
            "action_executed": False,
            "full_stt_prevented": False,
            "runtime_takeover": False,
            "error": str(error),
        }

    assistant._last_voice_engine_v2_vad_shadow = snapshot
    to_json_dict = getattr(snapshot, "to_json_dict", None)
    if callable(to_json_dict):
        return dict(to_json_dict())

    return {
        "enabled": True,
        "observed": False,
        "reason": "vad_shadow_snapshot_not_serializable",
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }


def _observe_voice_engine_v2_pre_stt_shadow(
    assistant: CoreAssistant,
    *,
    phase: str,
    capture_mode: str,
    capture_handoff: dict[str, object] | None = None,
) -> bool:
    """Observe the Stage 21A pre-STT hook before legacy full STT starts.

    This hook is observation-only. It must never execute actions, consume audio
    ownership or prevent the legacy FasterWhisper capture path.
    """

    adapter = getattr(assistant, "voice_engine_v2_pre_stt_shadow_adapter", None)
    if adapter is None:
        runtime = getattr(assistant, "runtime", None)
        runtime_metadata = getattr(runtime, "metadata", {}) if runtime is not None else {}
        if isinstance(runtime_metadata, dict):
            adapter = runtime_metadata.get("voice_engine_v2_pre_stt_shadow_adapter")

    observe_pre_stt = getattr(adapter, "observe_pre_stt", None)
    if not callable(observe_pre_stt):
        return False

    voice_session = getattr(assistant, "voice_session", None)
    input_owner = ""
    if voice_session is not None:
        get_input_owner = getattr(voice_session, "input_owner", None)
        if callable(get_input_owner):
            try:
                input_owner = str(get_input_owner() or "")
            except Exception:
                input_owner = ""

    if not input_owner:
        input_owner = VOICE_INPUT_OWNER_VOICE_INPUT

    turn_id = f"pre_stt_shadow-{time.monotonic():.6f}"
    benchmark_service = getattr(assistant, "turn_benchmark_service", None)
    current_turn_id = getattr(benchmark_service, "current_turn_id", None)
    if current_turn_id:
        turn_id = str(current_turn_id)

    audio_bus_probe = probe_realtime_audio_bus(assistant)
    vad_shadow_snapshot = _observe_voice_engine_v2_vad_shadow(assistant)

    try:
        result = observe_pre_stt(
            turn_id=turn_id,
            phase=str(phase or "command").strip() or "command",
            capture_mode=str(capture_mode or "command").strip() or "command",
            input_owner=input_owner,
            source="active_window",
            audio_bus_available=audio_bus_probe.audio_bus_present,
            audio_bus_probe=audio_bus_probe.to_json_dict(),
            metadata={
                "capture_handoff": dict(capture_handoff or {}),
                "voice_session_state": str(
                    getattr(voice_session, "state", "") if voice_session is not None else ""
                ),
                "vad_shadow": vad_shadow_snapshot,
            },
        )
    except Exception as error:
        append_log(f"Voice Engine v2 pre-STT shadow hook failed safely: {error}")
        return False

    assistant._last_voice_engine_v2_pre_stt_shadow = result
    return bool(getattr(result, "observed", False))

def _voice_engine_v2_current_turn_id(
    assistant: CoreAssistant,
    *,
    fallback_prefix: str,
) -> str:
    benchmark_service = getattr(assistant, "turn_benchmark_service", None)
    current_turn_id = getattr(benchmark_service, "current_turn_id", None)
    if current_turn_id:
        return str(current_turn_id)
    return f"{fallback_prefix}-{time.monotonic():.6f}"


def _voice_engine_v2_vad_timing_bridge_adapter(assistant: CoreAssistant):
    adapter = getattr(assistant, "voice_engine_v2_vad_timing_bridge_adapter", None)
    if adapter is not None:
        return adapter

    runtime = getattr(assistant, "runtime", None)
    runtime_metadata = getattr(runtime, "metadata", {}) if runtime is not None else {}
    if isinstance(runtime_metadata, dict):
        return runtime_metadata.get("voice_engine_v2_vad_timing_bridge_adapter")

    return None


def _arm_voice_engine_v2_vad_timing_bridge(
    assistant: CoreAssistant,
    *,
    phase: str,
    capture_mode: str,
    capture_handoff: dict[str, object] | None = None,
) -> bool:
    adapter = _voice_engine_v2_vad_timing_bridge_adapter(assistant)
    arm = getattr(adapter, "arm", None)
    if not callable(arm):
        return False

    try:
        return bool(
            arm(
                owner=assistant,
                turn_id=_voice_engine_v2_current_turn_id(
                    assistant,
                    fallback_prefix="vad_timing_bridge",
                ),
                phase=str(phase or "command").strip() or "command",
                capture_mode=str(capture_mode or "command").strip() or "command",
                capture_handoff=dict(capture_handoff or {}),
            )
        )
    except Exception as error:
        append_log(f"Voice Engine v2 VAD timing bridge arm failed safely: {error}")
        return False


def _voice_engine_v2_transcript_metadata(
    transcript: TranscriptResult | None,
) -> dict[str, object]:
    if transcript is None:
        return {}

    metadata = dict(getattr(transcript, "metadata", {}) or {})
    transcript_text = str(getattr(transcript, "text", "") or "").strip()
    transcript_language = str(getattr(transcript, "language", "") or "").strip()
    transcript_normalized_text = str(
        getattr(transcript, "normalized_text", "") or ""
    ).strip()

    metadata.setdefault("transcript_text", transcript_text)
    metadata.setdefault("transcript_language", transcript_language or "auto")
    metadata.setdefault("transcript_normalized_text", transcript_normalized_text)
    try:
        metadata.setdefault("transcript_confidence", float(transcript.confidence or 0.0))
    except (TypeError, ValueError):
        metadata.setdefault("transcript_confidence", 0.0)

    return metadata


def _observe_voice_engine_v2_vad_timing_bridge_after_capture(
    assistant: CoreAssistant,
    *,
    phase: str,
    capture_mode: str,
    transcript: TranscriptResult | None,
) -> bool:
    adapter = _voice_engine_v2_vad_timing_bridge_adapter(assistant)
    observe_after_capture = getattr(adapter, "observe_after_capture", None)
    if not callable(observe_after_capture):
        return False

    transcript_metadata = _voice_engine_v2_transcript_metadata(transcript)

    try:
        result = observe_after_capture(
            owner=assistant,
            turn_id=_voice_engine_v2_current_turn_id(
                assistant,
                fallback_prefix="vad_timing_bridge",
            ),
            phase=str(phase or "command").strip() or "command",
            capture_mode=str(capture_mode or "command").strip() or "command",
            transcript_present=transcript is not None,
            transcript_metadata=transcript_metadata,
        )
    except Exception as error:
        append_log(
            f"Voice Engine v2 VAD timing bridge observe failed safely: {error}"
        )
        return False

    assistant._last_voice_engine_v2_vad_timing_bridge = result
    return bool(getattr(result, "observed", False))




def _capture_transcript_for_assistant(
    assistant: CoreAssistant,
    *,
    timeout: float,
    debug: bool,
    mode: str,
) -> TranscriptResult | None:
    transcript = _capture_transcript_with_speech_service(
        assistant,
        timeout=timeout,
        debug=debug,
        mode=mode,
    )
    if transcript is not None:
        return transcript

    return capture_transcript(
        assistant.voice_in,
        timeout=timeout,
        debug=debug,
        mode=mode,
    )


def _listen_with_backend_fallback(
    assistant: CoreAssistant,
    *,
    timeout: float,
    debug: bool,
    mode: str = "command",
) -> str | None:
    transcript = capture_transcript(
        assistant.voice_in,
        timeout=timeout,
        debug=debug,
        mode=mode,
    )
    if transcript is None:
        return None
    return transcript.text

def _accept_standby_wake(
    assistant: CoreAssistant,
    state_flags: MainLoopRuntimeState,
    source_label: str,
    *,
    inline_command: str | None = None,
    wake_event: WakeDetectionResult | None = None,
) -> bool:
    safe_inline_command = _sanitize_inline_command(inline_command, assistant)
    if inline_command and safe_inline_command is None:
        append_log(
            "Discarded weak inline command after wake acceptance to avoid ghost routing: "
            f"{inline_command}"
        )

    _note_turn_benchmark_wake_detected(
    assistant,
    source=source_label,
    wake_event=wake_event,
)

    state_flags.reset_wake_detection()
    state_flags.hide_standby_banner()
    state_flags.store_prefetched_command(safe_inline_command)
    append_log(f"Wake phrase accepted by {source_label}.")
    _acknowledge_wake(
        assistant,
        source_label=source_label,
        inline_command_present=bool(safe_inline_command),
    )
    return True


def _listen_for_wake_via_stt_fallback(
    assistant: CoreAssistant,
    state_flags: MainLoopRuntimeState,
) -> bool:
    state_flags.mark_stt_wake_fallback_attempt()
    transcript = _capture_transcript_for_assistant(
        assistant,
        timeout=WAKE_STT_FALLBACK_TIMEOUT_SECONDS,
        debug=False,
        mode="wake_fallback",
    )
    if transcript is None:
        return False

    cleaned = transcript.text.strip()
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
    wake_event = detect_wake_event(
        wake_backend,
        timeout_seconds=WAKE_GATE_TIMEOUT_SECONDS,
        debug=False,
        ignore_audio_block=False,
    )

    if wake_event is not None and wake_event.accepted:
        return _accept_standby_wake(
            assistant,
            state_flags,
            backend_label,
            wake_event=wake_event,
        )

    if wake_backend is not None and callable(getattr(wake_backend, "listen_for_wake_phrase", None)):
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
        _remember_input_capture(
            assistant,
            text=prefetched,
            phase="inline_command_after_wake",
            language=getattr(assistant, "last_language", "en"),
            input_source="voice",
            backend_label="wake_inline_command",
            mode="inline_command_after_wake",
            latency_ms=0.0,
            audio_duration_ms=0.0,
            confidence=1.0,
            metadata={"origin": "wake_inline_command"},
        )
        _note_turn_benchmark_speech_finalized(
            assistant,
            text=prefetched,
            phase="inline_command_after_wake",
        )
        assistant.voice_session.transition_to_transcribing(
            detail="inline_command_after_wake",
            phase=VOICE_PHASE_TRANSCRIBE,
        )
        notify_visual_shell_voice_event(
            assistant,
            VisualEventName.LISTENING_FINISHED,
            source="main_loop.inline_command_after_wake",
            detail="inline_command_after_wake",
            payload={
                "phase": "inline_command_after_wake",
                "text_present": True,
            },
        )
        return prefetched

    active_phase = _active_phase(state_flags)
    capture_handoff = _prepare_capture_handoff_for_phase(assistant, phase=active_phase)
    capture_mode = _capture_mode_for_active_phase(
        assistant,
        active_phase=active_phase,
        capture_handoff=capture_handoff,
    )

    _note_turn_benchmark_listening_started(
        assistant,
        phase=active_phase,
    )

    assistant.voice_session.transition_to_listening(
        detail=f"active_window:{active_phase}",
        phase=_voice_phase_for_active_phase(active_phase),
        input_owner=VOICE_INPUT_OWNER_VOICE_INPUT,
    )
    notify_visual_shell_voice_event(
        assistant,
        VisualEventName.LISTENING_STARTED,
        source="main_loop.active_capture",
        detail=f"active_window:{active_phase}",
        payload={
            "phase": active_phase,
            "capture_mode": capture_mode,
        },
    )
    print("\nListening for your request...")

    _observe_voice_engine_v2_pre_stt_shadow(
        assistant,
        phase=active_phase,
        capture_mode=capture_mode,
        capture_handoff=capture_handoff,
    )

    _arm_voice_engine_v2_vad_timing_bridge(
        assistant,
        phase=active_phase,
        capture_mode=capture_mode,
        capture_handoff=capture_handoff,
    )

    transcript = _capture_transcript_for_assistant(
        assistant,
        timeout=_active_command_timeout(assistant),
        debug=bool(getattr(assistant, "voice_debug", False)),
        mode=capture_mode,
    )

    _observe_voice_engine_v2_vad_timing_bridge_after_capture(
        assistant,
        phase=active_phase,
        capture_mode=capture_mode,
        transcript=transcript,
    )

    if transcript is None:
        return None

    _remember_capture_from_transcript(
        assistant,
        transcript,
        phase=active_phase,
    )

    heard_text = transcript.text
    cleaned = heard_text.strip()
    if cleaned:
        _note_turn_benchmark_speech_finalized(
            assistant,
            text=cleaned,
            phase=active_phase,
            transcript=transcript,
        )
        assistant.voice_session.transition_to_transcribing(
            detail="speech_captured",
            phase=VOICE_PHASE_TRANSCRIBE,
        )
        notify_visual_shell_voice_event(
            assistant,
            VisualEventName.LISTENING_FINISHED,
            source="main_loop.active_capture",
            detail="speech_captured",
            payload={
                "phase": active_phase,
                "capture_mode": capture_mode,
                "text_present": True,
            },
        )
    return cleaned or None


def _store_session_continuity_snapshot(
    assistant: CoreAssistant,
    *,
    action: str,
    phase: str,
    reason: str,
    detail: str,
    window_seconds: float,
) -> None:
    resume_snapshot = dict(getattr(assistant, "_last_resume_policy_snapshot", {}) or {})
    command_snapshot = dict(getattr(assistant, "_last_command_window_policy_snapshot", {}) or {})

    assistant._last_session_continuity_snapshot = {
        "action": str(action or "").strip(),
        "phase": str(phase or "").strip(),
        "reason": str(reason or "").strip(),
        "detail": str(detail or "").strip(),
        "window_seconds": max(0.0, float(window_seconds or 0.0)),
        "pending_kind": str(resume_snapshot.get("pending_kind", "") or "").strip(),
        "pending_type": str(resume_snapshot.get("pending_type", "") or "").strip(),
        "pending_language": str(resume_snapshot.get("pending_language", "") or "").strip().lower(),
        "resume_policy": resume_snapshot,
        "command_window_policy": command_snapshot,
    }

    benchmark_service = getattr(assistant, "turn_benchmark_service", None)
    annotate = getattr(benchmark_service, "annotate_last_completed_turn", None)
    if callable(annotate):
        try:
            annotate(continuity_snapshot=dict(assistant._last_session_continuity_snapshot))
        except TypeError:
            pass
        except Exception:
            pass


def _start_follow_up_window(assistant: CoreAssistant, state_flags: MainLoopRuntimeState) -> None:
    window_seconds = _follow_up_window_seconds(assistant)
    assistant.voice_session.open_active_window(
        seconds=window_seconds,
        phase=VOICE_PHASE_FOLLOW_UP,
        input_owner=VOICE_INPUT_OWNER_VOICE_INPUT,
        detail="awaiting_follow_up",
    )
    notify_visual_shell_voice_event(
        assistant,
        VisualEventName.LISTENING_STARTED,
        source="main_loop.follow_up_window",
        detail="awaiting_follow_up",
        payload={
            "phase": PHASE_FOLLOW_UP,
            "window_seconds": window_seconds,
        },
    )
    _set_active_phase(state_flags, PHASE_FOLLOW_UP)
    state_flags.hide_standby_banner()
    _store_session_continuity_snapshot(
        assistant,
        action="follow_up",
        phase=PHASE_FOLLOW_UP,
        reason=str(getattr(assistant, "_last_resume_policy_snapshot", {}).get("reason", "") or "pending_follow_up"),
        detail="awaiting_follow_up",
        window_seconds=window_seconds,
    )


def _start_grace_window(assistant: CoreAssistant, state_flags: MainLoopRuntimeState) -> None:
    window_seconds = _grace_window_seconds(assistant)
    assistant.voice_session.open_active_window(
        seconds=window_seconds,
        phase=VOICE_PHASE_GRACE,
        input_owner=VOICE_INPUT_OWNER_VOICE_INPUT,
        detail="grace_after_response",
    )
    notify_visual_shell_voice_event(
        assistant,
        VisualEventName.LISTENING_STARTED,
        source="main_loop.grace_window",
        detail="grace_after_response",
        payload={
            "phase": PHASE_GRACE,
            "window_seconds": window_seconds,
        },
    )
    _set_active_phase(state_flags, PHASE_GRACE)
    state_flags.hide_standby_banner()
    _store_session_continuity_snapshot(
        assistant,
        action="grace",
        phase=PHASE_GRACE,
        reason=str(getattr(assistant, "_last_resume_policy_snapshot", {}).get("reason", "") or "response_delivered"),
        detail="grace_after_response",
        window_seconds=window_seconds,
    )


def _rearm_after_command(assistant: CoreAssistant, state_flags: MainLoopRuntimeState) -> None:
    decision = _RESUME_POLICY_SERVICE.decide(assistant)

    if decision.action == "follow_up":
        _start_follow_up_window(assistant, state_flags)
        return

    if decision.action == "grace":
        _start_grace_window(assistant, state_flags)
        return

    _return_to_wake_gate(assistant, state_flags, reason=decision.reason or "resume_policy_standby")


def _handle_no_speech_capture(assistant: CoreAssistant, state_flags: MainLoopRuntimeState) -> bool:
    phase = _active_phase(state_flags)
    attempt_number = state_flags.record_empty_capture()
    remaining = assistant.voice_session.active_window_remaining_seconds()
    decision = _COMMAND_WINDOW_POLICY_SERVICE.decide_after_empty_capture(
        assistant,
        phase=phase,
        attempt_number=attempt_number,
        remaining_seconds=remaining,
    )

    if decision.action == "retry":
        assistant.voice_session.transition_to_listening(
            detail=decision.detail,
            phase=_voice_phase_for_active_phase(phase),
            input_owner=VOICE_INPUT_OWNER_VOICE_INPUT,
        )
        return True

    _return_to_wake_gate(assistant, state_flags, reason=decision.reason or f"{phase}_window_expired")
    return False


def _handle_ignored_active_transcript(assistant: CoreAssistant, state_flags: MainLoopRuntimeState) -> bool:
    phase = _active_phase(state_flags)
    attempt_number = state_flags.record_ignored_capture()
    remaining = assistant.voice_session.active_window_remaining_seconds()
    decision = _COMMAND_WINDOW_POLICY_SERVICE.decide_after_ignored_transcript(
        assistant,
        phase=phase,
        attempt_number=attempt_number,
        remaining_seconds=remaining,
    )

    if decision.action == "retry":
        assistant.voice_session.transition_to_listening(
            detail=decision.detail,
            phase=_voice_phase_for_active_phase(phase),
            input_owner=VOICE_INPUT_OWNER_VOICE_INPUT,
        )
        return True

    _return_to_wake_gate(assistant, state_flags, reason=decision.reason or f"{phase}_ignored_transcript")
    return False

def _prime_command_window_after_wake(assistant: CoreAssistant, state_flags: MainLoopRuntimeState) -> None:
    _prepare_for_active_capture(assistant)
    _store_primed_capture_handoff(assistant, phase=PHASE_COMMAND, strategy="wake_prime_prepare")
    decision = _COMMAND_WINDOW_POLICY_SERVICE.initial_window_decision(assistant)

    window_seconds = float(getattr(decision, "window_seconds", 0.0) or 0.0)
    detail = str(getattr(decision, "detail", "") or "awaiting_command_after_wake")
    reason = str(getattr(decision, "reason", "") or "wake_accepted")

    assistant.voice_session.open_active_window(
        seconds=window_seconds,
        phase=VOICE_PHASE_COMMAND,
        input_owner=VOICE_INPUT_OWNER_VOICE_INPUT,
        detail=detail,
    )
    notify_visual_shell_voice_event(
        assistant,
        VisualEventName.LISTENING_STARTED,
        source="main_loop.command_window_after_wake",
        detail=detail,
        payload={
            "phase": PHASE_COMMAND,
            "window_seconds": window_seconds,
            "reason": reason,
        },
    )
    _set_active_phase(state_flags, PHASE_COMMAND)
    state_flags.hide_standby_banner()

    _store_session_continuity_snapshot(
        assistant,
        action="command_window_open",
        phase=PHASE_COMMAND,
        reason=reason,
        detail=detail,
        window_seconds=window_seconds,
    )