from __future__ import annotations

from collections.abc import Mapping
from typing import Any


CONTRACT_NAME = "controlled_recognition_dry_run"
CONTRACT_VERSION = "controlled_recognition_dry_run_v1"

READINESS_HOOK = "capture_window_pre_transcription"
COMMAND_PHASE = "command"
WAKE_COMMAND_CAPTURE_MODE = "wake_command"

CONTROLLED_RECOGNITION_FLAGS: tuple[str, ...] = (
    "vosk_shadow_controlled_recognition_enabled",
    "vosk_shadow_controlled_recognition_dry_run_enabled",
    "vosk_shadow_controlled_recognition_result_enabled",
)

BLOCKED_BY_POLICY_REASON = "controlled_recognition_dry_run_blocked_by_policy"
DISABLED_REASON = "controlled_recognition_disabled"
UNSAFE_CONFIG_REASON = "controlled_recognition_flags_enabled_before_runtime_support"
MISSING_CANDIDATE_REASON = "controlled_recognition_command_candidate_missing"
MISSING_DEPENDENCY_REASON = "controlled_recognition_dependency_missing"


def build_controlled_recognition_dry_run_contract(
    *,
    voice_engine_settings: Mapping[str, Any] | None,
    hook: str,
    phase: str,
    capture_mode: str,
    turn_id: str = "",
    preflight_ready: bool = False,
    attempt_ready: bool = False,
    recognition_permission_blocked: bool = True,
    audio_sample_count: int | None = None,
    published_byte_count: int | None = None,
    sample_rate: int | None = None,
    pcm_encoding: str = "",
) -> dict[str, Any]:
    """Build a metadata-only dry-run contract for future controlled recognition.

    This function never calls Vosk, never retrieves raw PCM, never starts an
    input stream, and never executes commands. It only returns a serializable
    contract that later runtime telemetry can attach safely.
    """

    settings = dict(voice_engine_settings or {})
    controlled_flags = {
        key: bool(settings.get(key, False))
        for key in CONTROLLED_RECOGNITION_FLAGS
    }
    controlled_flags_enabled = [
        key for key, enabled in controlled_flags.items() if enabled
    ]

    command_candidate = (
        hook == READINESS_HOOK
        and phase == COMMAND_PHASE
        and capture_mode == WAKE_COMMAND_CAPTURE_MODE
    )
    dependency_ready = (
        bool(preflight_ready)
        and bool(attempt_ready)
        and bool(recognition_permission_blocked)
    )
    future_dry_run_candidate_ready = (
        command_candidate
        and dependency_ready
        and not controlled_flags_enabled
    )

    reason = _reason(
        controlled_flags_enabled=controlled_flags_enabled,
        command_candidate=command_candidate,
        dependency_ready=dependency_ready,
        future_dry_run_candidate_ready=future_dry_run_candidate_ready,
    )

    return {
        "contract_name": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "enabled": controlled_flags[
            "vosk_shadow_controlled_recognition_enabled"
        ],
        "dry_run_enabled": controlled_flags[
            "vosk_shadow_controlled_recognition_dry_run_enabled"
        ],
        "result_enabled": controlled_flags[
            "vosk_shadow_controlled_recognition_result_enabled"
        ],
        "controlled_flags": controlled_flags,
        "controlled_flags_enabled": controlled_flags_enabled,
        "future_dry_run_candidate_ready": future_dry_run_candidate_ready,
        "current_policy_allows_dry_run": False,
        "dry_run_allowed": False,
        "dry_run_blocked": True,
        "reason": reason,
        "turn_id": turn_id,
        "hook": hook,
        "phase": phase,
        "capture_mode": capture_mode,
        "command_candidate": command_candidate,
        "preflight_ready": bool(preflight_ready),
        "attempt_ready": bool(attempt_ready),
        "recognition_permission_blocked": bool(recognition_permission_blocked),
        "audio_sample_count": _safe_int(audio_sample_count),
        "published_byte_count": _safe_int(published_byte_count),
        "sample_rate": _safe_int(sample_rate),
        "pcm_encoding": str(pcm_encoding or ""),
        "pcm_retrieval_allowed": False,
        "pcm_retrieval_performed": False,
        "raw_pcm_included": False,
        "recognition_invocation_allowed": False,
        "recognition_invocation_performed": False,
        "recognition_attempted": False,
        "result_present": False,
        "recognized": False,
        "command_matched": False,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "independent_microphone_stream_started": False,
        "live_command_recognition_enabled": False,
    }


def _reason(
    *,
    controlled_flags_enabled: list[str],
    command_candidate: bool,
    dependency_ready: bool,
    future_dry_run_candidate_ready: bool,
) -> str:
    if controlled_flags_enabled:
        return UNSAFE_CONFIG_REASON

    if not command_candidate:
        return MISSING_CANDIDATE_REASON

    if not dependency_ready:
        return MISSING_DEPENDENCY_REASON

    if future_dry_run_candidate_ready:
        return BLOCKED_BY_POLICY_REASON

    return DISABLED_REASON


def _safe_int(value: int | None) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None
