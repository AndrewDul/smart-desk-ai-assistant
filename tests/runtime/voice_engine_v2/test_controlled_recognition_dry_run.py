from __future__ import annotations

from modules.runtime.voice_engine_v2.controlled_recognition_dry_run import (
    BLOCKED_BY_POLICY_REASON,
    MISSING_CANDIDATE_REASON,
    MISSING_DEPENDENCY_REASON,
    UNSAFE_CONFIG_REASON,
    build_controlled_recognition_dry_run_contract,
)


def _safe_settings() -> dict[str, object]:
    return {
        "vosk_shadow_controlled_recognition_enabled": False,
        "vosk_shadow_controlled_recognition_dry_run_enabled": False,
        "vosk_shadow_controlled_recognition_result_enabled": False,
    }


def _ready_contract(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "voice_engine_settings": _safe_settings(),
        "hook": "capture_window_pre_transcription",
        "phase": "command",
        "capture_mode": "wake_command",
        "turn_id": "turn-1",
        "preflight_ready": True,
        "attempt_ready": True,
        "recognition_permission_blocked": True,
        "audio_sample_count": 16000,
        "published_byte_count": 32000,
        "sample_rate": 16000,
        "pcm_encoding": "pcm_s16le",
    }
    payload.update(overrides)
    return build_controlled_recognition_dry_run_contract(**payload)


def test_dry_run_contract_reports_future_candidate_but_blocks_current_stage() -> None:
    contract = _ready_contract()

    assert contract["future_dry_run_candidate_ready"] is True
    assert contract["dry_run_allowed"] is False
    assert contract["dry_run_blocked"] is True
    assert contract["current_policy_allows_dry_run"] is False
    assert contract["reason"] == BLOCKED_BY_POLICY_REASON
    assert contract["controlled_flags_enabled"] == []


def test_dry_run_contract_never_allows_recognition_or_actions() -> None:
    contract = _ready_contract()

    for key in [
        "pcm_retrieval_allowed",
        "pcm_retrieval_performed",
        "raw_pcm_included",
        "recognition_invocation_allowed",
        "recognition_invocation_performed",
        "recognition_attempted",
        "result_present",
        "recognized",
        "command_matched",
        "action_executed",
        "full_stt_prevented",
        "runtime_takeover",
        "runtime_integration",
        "command_execution_enabled",
        "faster_whisper_bypass_enabled",
        "microphone_stream_started",
        "independent_microphone_stream_started",
        "live_command_recognition_enabled",
    ]:
        assert contract[key] is False


def test_dry_run_contract_rejects_follow_up_as_command_candidate() -> None:
    contract = _ready_contract(phase="follow_up", capture_mode="follow_up")

    assert contract["future_dry_run_candidate_ready"] is False
    assert contract["command_candidate"] is False
    assert contract["reason"] == MISSING_CANDIDATE_REASON
    assert contract["dry_run_allowed"] is False


def test_dry_run_contract_rejects_missing_dependencies() -> None:
    contract = _ready_contract(preflight_ready=False)

    assert contract["future_dry_run_candidate_ready"] is False
    assert contract["preflight_ready"] is False
    assert contract["reason"] == MISSING_DEPENDENCY_REASON
    assert contract["dry_run_allowed"] is False


def test_dry_run_contract_rejects_enabled_controlled_flags() -> None:
    settings = _safe_settings()
    settings["vosk_shadow_controlled_recognition_enabled"] = True

    contract = _ready_contract(voice_engine_settings=settings)

    assert contract["future_dry_run_candidate_ready"] is False
    assert contract["enabled"] is True
    assert contract["controlled_flags_enabled"] == [
        "vosk_shadow_controlled_recognition_enabled"
    ]
    assert contract["reason"] == UNSAFE_CONFIG_REASON
    assert contract["dry_run_allowed"] is False


def test_dry_run_contract_preserves_metadata_counts_without_raw_pcm() -> None:
    contract = _ready_contract(
        audio_sample_count=13632,
        published_byte_count=27264,
        sample_rate=16000,
        pcm_encoding="pcm_s16le",
    )

    assert contract["audio_sample_count"] == 13632
    assert contract["published_byte_count"] == 27264
    assert contract["sample_rate"] == 16000
    assert contract["pcm_encoding"] == "pcm_s16le"
    assert contract["raw_pcm_included"] is False
