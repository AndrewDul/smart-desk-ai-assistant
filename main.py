from __future__ import annotations

import re
import shutil
import subprocess
import time
import traceback
import unicodedata
from typing import Any

from modules.core.assistant import CoreAssistant
from modules.core.session.voice_session import (
    VOICE_STATE_LISTENING,
    VOICE_STATE_ROUTING,
    VOICE_STATE_SHUTDOWN,
    VOICE_STATE_SPEAKING,
    VOICE_STATE_STANDBY,
    VOICE_STATE_TRANSCRIBING,
    VOICE_STATE_WAKE_DETECTED,
)
from modules.runtime.health import RuntimeHealthChecker
from modules.shared.logging.logger import append_log


WAKE_GATE_TIMEOUT_SECONDS = 2.2
FOLLOW_UP_WINDOW_SECONDS = 12.0
INITIAL_COMMAND_WINDOW_SECONDS = 6.5
POST_RESPONSE_GRACE_WINDOW_SECONDS = 8.0
INPUT_READY_MAX_WAIT_SECONDS = 2.0
DUPLICATE_TRANSCRIPT_COOLDOWN_SECONDS = 1.4
ACTIVE_IGNORE_LOG_COOLDOWN_SECONDS = 5.0

# Dedicated wake capture owns the microphone in standby.
# STT wake fallback is intentionally disabled in this architecture.
WAKE_STT_FALLBACK_ENABLED = False
WAKE_STT_FALLBACK_AFTER_MISSES = 999999
WAKE_STT_FALLBACK_TIMEOUT_SECONDS = 1.2
WAKE_STT_FALLBACK_COOLDOWN_SECONDS = 6.0

WAKE_REARM_SETTLE_SECONDS = 0.45
COMMAND_EMPTY_RETRY_LIMIT = 1
GRACE_EMPTY_RETRY_LIMIT = 2
FOLLOW_UP_EMPTY_RETRY_LIMIT = 3
COMMAND_IGNORE_RETRY_LIMIT = 1
GRACE_IGNORE_RETRY_LIMIT = 1
FOLLOW_UP_IGNORE_RETRY_LIMIT = 3
MIN_INLINE_COMMAND_ALPHA_CHARS = 3
MAX_ISOLATED_WAKE_TOKENS = 3

PHASE_COMMAND = "command"
PHASE_FOLLOW_UP = "follow_up"
PHASE_GRACE = "grace"


def _normalize_gate_text(text: str) -> str:
    lowered = str(text or "").lower().strip()
    lowered = unicodedata.normalize("NFKD", lowered)
    lowered = lowered.replace("ł", "l")
    lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
    lowered = re.sub(r"[^a-z0-9\s\[\]().,_/-]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _normalized_tokens(text: str) -> list[str]:
    return [token for token in _normalize_gate_text(text).split() if token]


def _alpha_char_count(text: str) -> int:
    return len(re.sub(r"[^a-z]", "", _normalize_gate_text(text)))


def _looks_like_wake_alias(text: str) -> bool:
    normalized = _normalize_gate_text(text)
    if not normalized:
        return False

    compact_tokens = [re.sub(r"[^a-z0-9]", "", token) for token in normalized.split()[:3]]
    wake_aliases = {
        "nexa",
        "nexta",
        "neksa",
        "nexaah",
        "nex",
    }
    return any(token in wake_aliases or token.startswith("nex") for token in compact_tokens if token)


def _all_tokens_look_like_wake_aliases(tokens: list[str]) -> bool:
    return bool(tokens) and all(_looks_like_wake_alias(token) for token in tokens)


def _looks_like_isolated_wake_transcript(text: str) -> bool:
    tokens = _normalized_tokens(text)
    if not tokens or len(tokens) > MAX_ISOLATED_WAKE_TOKENS:
        return False
    return _all_tokens_look_like_wake_aliases(tokens)


def _is_blank_or_silence(text: str) -> bool:
    normalized = _normalize_gate_text(text)
    return normalized in {
        "",
        "blank audio",
        "[blank_audio]",
        "blank_audio",
        "silence",
        "[ silence ]",
        "no speech",
        "no speech recognized",
        "[noise]",
        "noise",
        "<empty>",
        "...",
        ".",
        "-",
    }


def _is_bracketed_non_speech(text: str) -> bool:
    normalized = _normalize_gate_text(text)
    if not normalized:
        return True

    bracketed_patterns = [
        r"^\[[a-z0-9 _-]+\]$",
        r"^\([a-z0-9 _-]+\)$",
    ]
    if not any(re.fullmatch(pattern, normalized) for pattern in bracketed_patterns):
        return False

    inner = re.sub(r"^[\[(]|[\])]\Z", "", normalized).strip()
    non_speech_terms = {
        "music",
        "upbeat music",
        "applause",
        "laughter",
        "background noise",
        "ambient sound",
        "static",
        "noise",
        "silence",
        "coughing",
        "breathing",
        "sigh",
        "keyboard",
        "typing",
        "knocking",
        "chair",
        "chair movement",
        "moving chair",
        "desk hit",
        "clap",
        "clapping",
        "stukanie",
        "stukniecie",
        "stukniecia",
        "klawiatura",
        "pisanie",
        "pisanie na klawiaturze",
        "krzeslo",
        "ruch krzesla",
        "przesuwanie krzesla",
        "klasniecie",
        "klasniecia",
        "klaskanie",
    }
    return inner in non_speech_terms


def _looks_like_non_speech_description(normalized: str) -> bool:
    if not normalized:
        return True

    exact_non_speech = {
        "keyboard",
        "typing",
        "knocking",
        "chair",
        "chair movement",
        "moving chair",
        "desk hit",
        "clap",
        "clapping",
        "applause",
        "music",
        "laughter",
        "noise",
        "static",
        "stukanie",
        "stukniecie",
        "stukniecia",
        "klawiatura",
        "pisanie",
        "pisanie na klawiaturze",
        "krzeslo",
        "ruch krzesla",
        "przesuwanie krzesla",
        "klasniecie",
        "klasniecia",
        "klaskanie",
    }
    if normalized in exact_non_speech:
        return True

    non_speech_keywords = {
        "keyboard",
        "typing",
        "knocking",
        "chair",
        "clap",
        "clapping",
        "applause",
        "music",
        "noise",
        "static",
        "stukanie",
        "klawiatura",
        "krzeslo",
        "klasniecie",
        "klaskanie",
    }

    tokens = set(normalized.split())
    if tokens and tokens.issubset(non_speech_keywords):
        return True
    if len(tokens) <= 4 and (tokens & non_speech_keywords):
        return True
    return False


def _is_low_value_noise(text: str, assistant: CoreAssistant) -> bool:
    if assistant.pending_follow_up or assistant.pending_confirmation:
        return False

    normalized = _normalize_gate_text(text)
    if not normalized:
        return True

    filler_words = {
        "uh",
        "um",
        "hmm",
        "hm",
        "mmm",
        "ah",
        "eh",
        "yyy",
        "eee",
        "ok",
        "okay",
        "huh",
    }
    silence_hallucinations = {
        "thank you",
        "thanks for watching",
        "you",
        "bye",
        "foreign",
        "speaking in foreign language",
        "keyboard",
        "typing",
        "knocking",
        "chair",
        "chair movement",
        "moving chair",
        "clap",
        "clapping",
        "applause",
        "music",
        "noise",
        "static",
        "stukanie",
        "stukniecie",
        "stukniecia",
        "klawiatura",
        "pisanie",
        "pisanie na klawiaturze",
        "krzeslo",
        "ruch krzesla",
        "przesuwanie krzesla",
        "klasniecie",
        "klasniecia",
        "klaskanie",
    }

    if normalized in filler_words or normalized in silence_hallucinations:
        return True

    if _looks_like_non_speech_description(normalized):
        return True
    if not re.search(r"[a-z]", normalized):
        return True

    alpha_only = re.sub(r"[^a-z]", "", normalized)
    return len(alpha_only) <= 1


def _has_meaningful_inline_command(text: str, assistant: CoreAssistant) -> bool:
    normalized = _normalize_gate_text(text)
    if not normalized:
        return False
    if _is_blank_or_silence(text):
        return False
    if _is_bracketed_non_speech(text):
        return False
    if _is_low_value_noise(text, assistant):
        return False

    tokens = _normalized_tokens(text)
    if _all_tokens_look_like_wake_aliases(tokens):
        return False

    return _alpha_char_count(text) >= MIN_INLINE_COMMAND_ALPHA_CHARS


def _sanitize_inline_command(text: str | None, assistant: CoreAssistant) -> str | None:
    cleaned = " ".join(str(text or "").split()).strip()
    if not cleaned:
        return None
    if not _has_meaningful_inline_command(cleaned, assistant):
        return None
    return cleaned


def _should_ignore_duplicate_transcript(
    text: str,
    assistant: CoreAssistant,
    *,
    last_transcript_normalized: str | None,
    last_transcript_time: float | None,
    cooldown_seconds: float = DUPLICATE_TRANSCRIPT_COOLDOWN_SECONDS,
) -> bool:
    if assistant.pending_follow_up or assistant.pending_confirmation:
        return False

    normalized = _normalize_gate_text(text)
    if not normalized or last_transcript_normalized is None or last_transcript_time is None:
        return False

    return (
        normalized == last_transcript_normalized
        and (time.monotonic() - last_transcript_time) <= cooldown_seconds
    )


def _should_log_gate_event(
    gate_event: str,
    gate_log_times: dict[str, float],
    cooldown_seconds: float = ACTIVE_IGNORE_LOG_COOLDOWN_SECONDS,
) -> bool:
    now = time.monotonic()
    last_time = gate_log_times.get(gate_event)
    if last_time is None or (now - last_time) >= cooldown_seconds:
        gate_log_times[gate_event] = now
        return True
    return False


def _log_ignored_active_transcript(
    event_key: str,
    heard_text: str,
    gate_log_times: dict[str, float],
    message: str,
) -> None:
    if _should_log_gate_event(event_key, gate_log_times):
        append_log(f"Ignored active transcript [{event_key}]: {heard_text}")
    print(message)


def _should_ignore_active_transcript(
    assistant: CoreAssistant,
    heard_text: str,
    gate_log_times: dict[str, float],
    *,
    last_transcript_normalized: str | None,
    last_transcript_time: float | None,
) -> bool:
    if _is_blank_or_silence(heard_text):
        _log_ignored_active_transcript(
            "blank_or_silence",
            heard_text,
            gate_log_times,
            "Ignored blank audio marker.",
        )
        return True

    normalized_heard = _normalize_gate_text(heard_text)
    if not normalized_heard:
        _log_ignored_active_transcript(
            "empty_normalized",
            heard_text,
            gate_log_times,
            "Ignored empty normalized transcript.",
        )
        return True

    if _is_bracketed_non_speech(heard_text):
        _log_ignored_active_transcript(
            "bracketed_non_speech",
            heard_text,
            gate_log_times,
            f"Ignored non-speech transcript: {heard_text}",
        )
        return True

    if _is_low_value_noise(heard_text, assistant):
        _log_ignored_active_transcript(
            "low_value_noise",
            heard_text,
            gate_log_times,
            f"Ignored low-value noise: {heard_text}",
        )
        return True

    if _should_ignore_duplicate_transcript(
        heard_text,
        assistant,
        last_transcript_normalized=last_transcript_normalized,
        last_transcript_time=last_transcript_time,
    ):
        _log_ignored_active_transcript(
            "duplicate_transcript",
            heard_text,
            gate_log_times,
            f"Ignored duplicate transcript: {heard_text}",
        )
        return True

    return False


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


def _collect_runtime_warnings(assistant: CoreAssistant) -> list[str]:
    warnings: list[str] = []
    for component, status in assistant.backend_statuses.items():
        label = _component_label(component)

        if component == "wake_gate":
            selected_backend = str(getattr(status, "selected_backend", "") or "").strip().lower()
            voice_input_status = _backend_status_for(assistant, "voice_input")
            compatibility_ready = (
                selected_backend == "compatibility_voice_input"
                and bool(getattr(status, "ok", False))
                and bool(getattr(voice_input_status, "ok", False))
            )
            if compatibility_ready:
                continue

        if status.ok and not status.fallback_used:
            continue
        if status.fallback_used and status.ok:
            warnings.append(f"{label}: fallback active")
            continue
        if status.fallback_used:
            warnings.append(f"{label}: degraded fallback")
            continue
        warnings.append(f"{label}: limited")
    return warnings


def _log_startup_summary(report: Any, assistant: CoreAssistant, runtime_warnings: list[str]) -> None:
    append_log("Startup summary begins.")

    if report.startup_allowed:
        append_log("Startup health report: no blocking critical issues.")
    else:
        append_log("Startup health report: critical issues detected, runtime may be degraded.")

    for item in report.items:
        level = "OK" if item.ok else item.severity.value.upper()
        append_log(f"Startup health item [{level}] {item.name}: {item.details}")

    for component, status in assistant.backend_statuses.items():
        level = "OK" if status.ok and not status.fallback_used else "WARN"
        append_log(
            f"Runtime backend item [{level}] {component}: "
            f"backend={status.selected_backend}, fallback={status.fallback_used}, detail={status.detail}"
        )

    if runtime_warnings:
        append_log(f"Runtime warning summary: {' | '.join(runtime_warnings)}")
    else:
        append_log("Runtime warning summary: none")

    append_log("Startup summary ends.")


def _run_startup_sequence(assistant: CoreAssistant) -> None:
    append_log("Startup sequence initiated.")
    checker = RuntimeHealthChecker(assistant.settings)
    report = checker.run()
    runtime_warnings = _collect_runtime_warnings(assistant)

    assistant._boot_report_ok = report.startup_allowed and not runtime_warnings
    _log_startup_summary(report, assistant, runtime_warnings)
    assistant.boot()


def _perform_system_shutdown(assistant: CoreAssistant) -> None:
    system_cfg = assistant.settings.get("system", {})
    allow_shutdown = bool(system_cfg.get("allow_shutdown_commands", False))
    if not allow_shutdown:
        append_log("Shutdown requested, but system shutdown commands are disabled in config.")
        print("System shutdown requested, but shutdown commands are disabled in config.")
        return

    shutdown_command = system_cfg.get("shutdown_command")
    if isinstance(shutdown_command, list) and shutdown_command:
        cmd = [str(part) for part in shutdown_command]
    elif shutil.which("systemctl"):
        cmd = ["systemctl", "poweroff"]
    elif shutil.which("shutdown"):
        cmd = ["shutdown", "-h", "now"]
    else:
        append_log("Shutdown requested, but no supported shutdown command was found.")
        print("Shutdown requested, but no supported shutdown command was found.")
        return

    append_log(f"Executing system shutdown command: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=False)
    except Exception as error:
        append_log(f"System shutdown command failed: {error}")
        print(f"System shutdown command failed: {error}")


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

    if blocked:
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


def _wait_for_input_ready(assistant: CoreAssistant, *, max_wait_seconds: float = INPUT_READY_MAX_WAIT_SECONDS) -> None:
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


def _prepare_for_standby_capture(assistant: CoreAssistant, state_flags: dict[str, Any]) -> None:
    _ensure_voice_capture_released(assistant)


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


def _log_runtime_mode(assistant: CoreAssistant) -> None:
    wake_backend, backend_label = _resolve_wake_backend(assistant)
    wake_name = wake_backend.__class__.__name__ if wake_backend is not None else "none"
    shared_note = (
        " Compatibility wake shares the main voice input backend and keeps a single input owner across standby and command capture."
        if _wake_backend_shares_voice_input(assistant, wake_backend)
        else " Dedicated wake capture owns the microphone only in standby."
    )
    fallback_note = " Standby STT wake fallback is disabled."
    append_log(
        "Half-duplex voice mode active. "
        f"Wake path={backend_label} ({wake_name}). "
        "Wake barge-in during assistant speech is disabled to prevent self-interruptions."
        f"{shared_note}{fallback_note}"
    )
    print("Voice mode: half-duplex (assistant will not listen while speaking).")


def main() -> None:
    assistant = CoreAssistant()
    _run_startup_sequence(assistant)
    _log_runtime_mode(assistant)

    gate_log_times: dict[str, float] = {}
    last_transcript_normalized: str | None = None
    last_transcript_time: float | None = None
    state_flags: dict[str, Any] = {
        "standby_banner_shown": False,
        "compatibility_wake_mode_logged": False,
        "wake_miss_count": 0,
        "last_wake_stt_fallback_monotonic": 0.0,
        "wake_rearm_ready_monotonic": 0.0,
        "prefetched_command_text": None,
        "active_phase": PHASE_COMMAND,
        "active_empty_count": 0,
        "active_ignored_count": 0,
    }

    fatal_error: Exception | None = None

    try:
        while True:
            if _assistant_output_blocks_input(assistant):
                time.sleep(_input_resume_poll_seconds(assistant))
                continue

            if not assistant.voice_session.active_window_open():
                if not _listen_for_wake(assistant, state_flags):
                    continue

                _wait_for_input_ready(assistant)
                assistant.voice_session.open_active_window(seconds=_initial_command_window_seconds(assistant))
                assistant.voice_session.set_state(VOICE_STATE_LISTENING, detail="awaiting_command_after_wake")
                _set_active_phase(state_flags, PHASE_COMMAND)
                state_flags["standby_banner_shown"] = False
            else:
                if not state_flags.get("standby_banner_shown", False):
                    print(_banner_for_phase(_active_phase(state_flags)))
                    state_flags["standby_banner_shown"] = True

            heard_text = _listen_for_active_command(assistant, state_flags)
            if heard_text is None:
                if _handle_no_speech_capture(assistant, state_flags):
                    continue
                continue

            state_flags["standby_banner_shown"] = False

            if assistant.voice_session.heard_wake_phrase(heard_text) or _looks_like_wake_alias(heard_text):
                append_log(f"Wake phrase heard during active window: {heard_text}")
                stripped_wake = assistant.voice_session.strip_wake_phrase(heard_text)
                safe_inline_after_rewake = _sanitize_inline_command(stripped_wake, assistant)
                if safe_inline_after_rewake:
                    heard_text = safe_inline_after_rewake
                    append_log(f"Continuing with inline command after wake phrase: {heard_text}")
                else:
                    assistant.voice_session.open_active_window(seconds=_initial_command_window_seconds(assistant))
                    assistant.voice_session.set_state(VOICE_STATE_LISTENING, detail="awaiting_command_after_rewake")
                    _set_active_phase(state_flags, PHASE_COMMAND)
                    print("Wake phrase heard again. Waiting for command...")
                    continue

            if _should_ignore_active_transcript(
                assistant,
                heard_text,
                gate_log_times,
                last_transcript_normalized=last_transcript_normalized,
                last_transcript_time=last_transcript_time,
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

            last_transcript_normalized = normalized_command
            last_transcript_time = time.monotonic()
            _reset_active_counters(state_flags)

            assistant.voice_session.set_state(VOICE_STATE_ROUTING, detail="dispatching_command")
            should_continue = assistant.handle_command(heard_text)

            if not should_continue:
                assistant.voice_session.set_state(VOICE_STATE_SHUTDOWN, detail="main_loop_exit")
                break

            _wait_for_input_ready(assistant)
            _rearm_after_command(assistant, state_flags)
            _ensure_wake_capture_released(assistant)

    except KeyboardInterrupt:
        print("\nStopping assistant with keyboard interrupt.")
        append_log("Assistant stopped with keyboard interrupt.")
    except Exception as error:
        fatal_error = error
        append_log(f"Fatal runtime error in main loop: {error}")
        append_log(traceback.format_exc())
        print("\nFatal runtime error in main loop:")
        traceback.print_exc()
    finally:
        shutdown_requested = assistant.shutdown_requested

        try:
            assistant.shutdown()
        except Exception as shutdown_error:
            append_log(f"Error during assistant shutdown: {shutdown_error}")
            append_log(traceback.format_exc())
            print("\nError during assistant shutdown:")
            traceback.print_exc()

        if shutdown_requested:
            _perform_system_shutdown(assistant)

        if fatal_error is not None:
            print("Assistant exited after handling a runtime error.")


if __name__ == "__main__":
    main()