from __future__ import annotations

from modules.runtime.voice_engine_v2.vosk_shadow_pcm_reference import (
    PCM_REFERENCE_READY_REASON,
    VoskShadowPcmReferenceSettings,
    build_vosk_shadow_pcm_reference,
    validate_vosk_shadow_pcm_reference,
)


def _plan(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "plan_ready": True,
        "recognition_invocation_performed": False,
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
        "segment_present": True,
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "pcm_encoding": "pcm_s16le",
        "sample_rate": 16000,
        "channels": 1,
        "sample_width_bytes": 2,
        "audio_sample_count": 32000,
        "audio_duration_ms": 2000.0,
        "published_frame_count": 32,
        "published_byte_count": 64000,
        "raw_pcm_included": False,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }
    payload.update(overrides)
    return payload


def _metadata(
    *,
    plan: dict[str, object] | None = None,
    candidate: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "vosk_shadow_invocation_plan": _plan() if plan is None else plan,
        "command_asr_candidate": _candidate() if candidate is None else candidate,
    }


def test_pcm_reference_is_disabled_by_default() -> None:
    reference = build_vosk_shadow_pcm_reference(
        hook="capture_window_pre_transcription",
        metadata=_metadata(),
    )

    payload = reference.to_json_dict()

    assert payload["enabled"] is False
    assert payload["reference_ready"] is False
    assert payload["raw_pcm_included"] is False
    assert payload["pcm_retrieval_performed"] is False
    assert payload["recognition_invocation_performed"] is False
    assert validate_vosk_shadow_pcm_reference(reference)["accepted"] is True


def test_pcm_reference_accepts_ready_existing_capture_window() -> None:
    reference = build_vosk_shadow_pcm_reference(
        hook="capture_window_pre_transcription",
        metadata=_metadata(),
        settings=VoskShadowPcmReferenceSettings(enabled=True),
    )

    payload = reference.to_json_dict()

    assert payload["enabled"] is True
    assert payload["reference_ready"] is True
    assert payload["reason"] == PCM_REFERENCE_READY_REASON
    assert payload["source"] == "faster_whisper_capture_window_shadow_tap"
    assert payload["publish_stage"] == "before_transcription"
    assert payload["pcm_encoding"] == "pcm_s16le"
    assert payload["sample_rate"] == 16000
    assert payload["channels"] == 1
    assert payload["sample_width_bytes"] == 2
    assert payload["audio_sample_count"] == 32000
    assert payload["published_byte_count"] == 64000
    assert payload["raw_pcm_included"] is False
    assert payload["pcm_retrieval_performed"] is False
    assert payload["recognition_invocation_performed"] is False
    assert payload["recognition_attempted"] is False
    assert payload["recognized"] is False
    assert payload["command_matched"] is False
    assert payload["runtime_takeover"] is False
    assert validate_vosk_shadow_pcm_reference(reference)["accepted"] is True


def test_pcm_reference_blocks_missing_invocation_plan() -> None:
    metadata = _metadata()
    metadata.pop("vosk_shadow_invocation_plan")

    reference = build_vosk_shadow_pcm_reference(
        hook="capture_window_pre_transcription",
        metadata=metadata,
        settings=VoskShadowPcmReferenceSettings(enabled=True),
    )

    assert reference.reference_ready is False
    assert reference.reason == "vosk_shadow_invocation_plan_missing"


def test_pcm_reference_blocks_not_ready_invocation_plan() -> None:
    reference = build_vosk_shadow_pcm_reference(
        hook="capture_window_pre_transcription",
        metadata=_metadata(plan=_plan(plan_ready=False)),
        settings=VoskShadowPcmReferenceSettings(enabled=True),
    )

    assert reference.reference_ready is False
    assert reference.reason == "vosk_shadow_invocation_plan_not_ready"


def test_pcm_reference_blocks_raw_pcm_candidate() -> None:
    reference = build_vosk_shadow_pcm_reference(
        hook="capture_window_pre_transcription",
        metadata=_metadata(candidate=_candidate(raw_pcm_included=True)),
        settings=VoskShadowPcmReferenceSettings(enabled=True),
    )

    assert reference.reference_ready is False
    assert reference.reason == "unsafe_command_asr_candidate"


def test_pcm_reference_blocks_wrong_source() -> None:
    reference = build_vosk_shadow_pcm_reference(
        hook="capture_window_pre_transcription",
        metadata=_metadata(candidate=_candidate(source="other_source")),
        settings=VoskShadowPcmReferenceSettings(enabled=True),
    )

    assert reference.reference_ready is False
    assert reference.reason == "unexpected_audio_source"


def test_pcm_reference_blocks_wrong_publish_stage() -> None:
    reference = build_vosk_shadow_pcm_reference(
        hook="capture_window_pre_transcription",
        metadata=_metadata(candidate=_candidate(publish_stage="after_transcription")),
        settings=VoskShadowPcmReferenceSettings(enabled=True),
    )

    assert reference.reference_ready is False
    assert reference.reason == "unexpected_publish_stage"


def test_pcm_reference_blocks_missing_audio_counts() -> None:
    reference = build_vosk_shadow_pcm_reference(
        hook="capture_window_pre_transcription",
        metadata=_metadata(candidate=_candidate(audio_sample_count=0)),
        settings=VoskShadowPcmReferenceSettings(enabled=True),
    )

    assert reference.reference_ready is False
    assert reference.reason == "audio_counts_missing"



def test_pcm_reference_accepts_segment_prefixed_candidate_fields() -> None:
    reference = build_vosk_shadow_pcm_reference(
        hook="capture_window_pre_transcription",
        metadata=_metadata(
            candidate={
                "segment_present": True,
                "segment_audio_duration_ms": 2000.0,
                "segment_audio_sample_count": 32000,
                "segment_published_byte_count": 64000,
                "segment_sample_rate": 16000,
                "segment_pcm_encoding": "pcm_s16le",
                "raw_pcm_included": False,
                "action_executed": False,
                "full_stt_prevented": False,
                "runtime_takeover": False,
            }
        ),
        settings=VoskShadowPcmReferenceSettings(enabled=True),
    )

    payload = reference.to_json_dict()

    assert payload["reference_ready"] is True
    assert payload["source"] == "faster_whisper_capture_window_shadow_tap"
    assert payload["publish_stage"] == "before_transcription"
    assert payload["audio_sample_count"] == 32000
    assert payload["published_byte_count"] == 64000
    assert payload["sample_rate"] == 16000
    assert payload["channels"] == 1
    assert payload["sample_width_bytes"] == 2
    assert payload["pcm_encoding"] == "pcm_s16le"
    assert payload["raw_pcm_included"] is False
    assert payload["pcm_retrieval_performed"] is False
    assert payload["recognition_invocation_performed"] is False