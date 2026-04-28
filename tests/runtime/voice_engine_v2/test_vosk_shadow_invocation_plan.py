from __future__ import annotations

from modules.runtime.voice_engine_v2.vosk_shadow_invocation_plan import (
    INVOCATION_PLAN_READY_REASON,
    build_vosk_shadow_invocation_plan,
    validate_vosk_shadow_invocation_plan,
)


def _contract(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "enabled": True,
        "observed": False,
        "reason": "vosk_live_shadow_result_missing",
        "recognition_attempted": False,
        "recognized": False,
        "command_matched": False,
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "independent_microphone_stream_started": False,
        "live_command_recognition_enabled": False,
        "raw_pcm_included": False,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }
    payload.update(overrides)
    return payload


def _candidate(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_present": False,
        "segment_present": True,
        "segment_reason": "command_audio_segment_ready",
        "segment_audio_duration_ms": 1800.0,
        "segment_audio_sample_count": 32000,
        "segment_published_byte_count": 64000,
        "segment_sample_rate": 16000,
        "segment_pcm_encoding": "pcm_s16le",
        "recognizer_name": "disabled_command_asr",
        "recognizer_enabled": False,
        "recognition_attempted": False,
        "recognized": False,
        "raw_pcm_included": False,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }
    payload.update(overrides)
    return payload


def _metadata(
    *,
    contract: dict[str, object] | None = None,
    candidate: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "vosk_live_shadow": _contract() if contract is None else contract,
        "command_asr_shadow_bridge": {
            "enabled": True,
            "observed": True,
            "reason": "command_asr_shadow_bridge_observed",
            "candidate_attached": True,
            "command_asr_candidate_present": False,
            "recognizer_enabled": False,
            "recognition_attempted": False,
            "recognized": False,
            "raw_pcm_included": False,
            "action_executed": False,
            "full_stt_prevented": False,
            "runtime_takeover": False,
        },
        "command_asr_candidate": _candidate() if candidate is None else candidate,
    }


def test_invocation_plan_is_disabled_by_default() -> None:
    plan = build_vosk_shadow_invocation_plan(
        hook="capture_window_pre_transcription",
        metadata=_metadata(),
    )

    payload = plan.to_json_dict()

    assert payload["enabled"] is False
    assert payload["plan_ready"] is False
    assert payload["recognition_invocation_performed"] is False
    assert payload["recognition_attempted"] is False
    assert payload["recognized"] is False
    assert payload["command_matched"] is False
    assert validate_vosk_shadow_invocation_plan(plan)["accepted"] is True


def test_invocation_plan_accepts_ready_observe_only_boundary() -> None:
    from modules.runtime.voice_engine_v2.vosk_shadow_invocation_plan import (
        VoskShadowInvocationPlanSettings,
    )

    plan = build_vosk_shadow_invocation_plan(
        hook="capture_window_pre_transcription",
        metadata=_metadata(),
        settings=VoskShadowInvocationPlanSettings(enabled=True),
    )

    payload = plan.to_json_dict()

    assert payload["enabled"] is True
    assert payload["plan_ready"] is True
    assert payload["reason"] == INVOCATION_PLAN_READY_REASON
    assert payload["command_asr_bridge_present"] is True
    assert payload["command_asr_candidate_present"] is True
    assert payload["vosk_live_shadow_contract_present"] is True
    assert payload["segment_present"] is True
    assert payload["recognition_invocation_performed"] is False
    assert payload["recognition_attempted"] is False
    assert payload["recognized"] is False
    assert payload["command_matched"] is False
    assert payload["runtime_integration"] is False
    assert payload["command_execution_enabled"] is False
    assert payload["faster_whisper_bypass_enabled"] is False
    assert payload["microphone_stream_started"] is False
    assert payload["independent_microphone_stream_started"] is False
    assert payload["live_command_recognition_enabled"] is False
    assert payload["raw_pcm_included"] is False
    assert validate_vosk_shadow_invocation_plan(plan)["accepted"] is True


def test_invocation_plan_blocks_wrong_hook() -> None:
    from modules.runtime.voice_engine_v2.vosk_shadow_invocation_plan import (
        VoskShadowInvocationPlanSettings,
    )

    plan = build_vosk_shadow_invocation_plan(
        hook="post_capture",
        metadata=_metadata(),
        settings=VoskShadowInvocationPlanSettings(enabled=True),
    )

    assert plan.plan_ready is False
    assert plan.reason == "non_capture_window_hook"


def test_invocation_plan_blocks_missing_contract() -> None:
    from modules.runtime.voice_engine_v2.vosk_shadow_invocation_plan import (
        VoskShadowInvocationPlanSettings,
    )

    metadata = _metadata()
    metadata.pop("vosk_live_shadow")

    plan = build_vosk_shadow_invocation_plan(
        hook="capture_window_pre_transcription",
        metadata=metadata,
        settings=VoskShadowInvocationPlanSettings(enabled=True),
    )

    assert plan.plan_ready is False
    assert plan.reason == "vosk_live_shadow_contract_missing"


def test_invocation_plan_blocks_unsafe_contract() -> None:
    from modules.runtime.voice_engine_v2.vosk_shadow_invocation_plan import (
        VoskShadowInvocationPlanSettings,
    )

    plan = build_vosk_shadow_invocation_plan(
        hook="capture_window_pre_transcription",
        metadata=_metadata(contract=_contract(runtime_takeover=True)),
        settings=VoskShadowInvocationPlanSettings(enabled=True),
    )

    assert plan.plan_ready is False
    assert plan.reason == "unsafe_vosk_live_shadow_contract"


def test_invocation_plan_blocks_segment_not_ready() -> None:
    from modules.runtime.voice_engine_v2.vosk_shadow_invocation_plan import (
        VoskShadowInvocationPlanSettings,
    )

    plan = build_vosk_shadow_invocation_plan(
        hook="capture_window_pre_transcription",
        metadata=_metadata(
            candidate=_candidate(
                segment_present=False,
                segment_reason="speech_not_ended_yet",
            )
        ),
        settings=VoskShadowInvocationPlanSettings(enabled=True),
    )

    assert plan.plan_ready is False
    assert plan.reason == "command_audio_segment_not_ready:speech_not_ended_yet"