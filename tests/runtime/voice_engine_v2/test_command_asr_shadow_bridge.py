from __future__ import annotations

import pytest

from modules.devices.audio.command_asr.command_grammar import (
    build_default_command_grammar,
)
from modules.devices.audio.command_asr.vosk_command_recognizer import (
    VoskCommandRecognizer,
)
from modules.runtime.voice_engine_v2.command_asr_shadow_bridge import (
    COMMAND_ASR_SHADOW_BRIDGE_DISABLED_REASON,
    COMMAND_ASR_SHADOW_BRIDGE_OBSERVED_REASON,
    CommandAsrShadowBridgeSettings,
    enrich_record_with_command_asr_shadow,
)
from modules.runtime.voice_engine_v2.vosk_command_asr_adapter import (
    VOSK_COMMAND_ASR_DISABLED_REASON,
    VoskCommandAsrAdapter,
)


def _candidate(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "hook": "capture_window_pre_transcription",
        "candidate_present": True,
        "endpoint_detected": True,
        "reason": "endpoint_detected",
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "frames_processed": 47,
        "speech_score_max": 0.99,
        "capture_finished_to_vad_observed_ms": 228.0,
        "capture_window_publish_to_vad_observed_ms": 226.0,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }
    payload.update(overrides)
    return payload


def _capture_window(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "sample_rate": 16_000,
        "channels": 1,
        "audio_sample_count": 32_000,
        "audio_duration_seconds": 2.0,
        "published_frame_count": 32,
        "published_byte_count": 64_000,
        "capture_finished_to_publish_start_ms": 2.5,
    }
    payload.update(overrides)
    return payload


def _record(
    *,
    candidate: dict[str, object] | None = None,
    capture_window: dict[str, object] | None = None,
    action_executed: bool = False,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "capture_window_shadow_tap": (
            _capture_window() if capture_window is None else capture_window
        )
    }
    if candidate is not None:
        metadata["endpointing_candidate"] = candidate

    return {
        "turn_id": "turn-command-asr-shadow",
        "hook": "capture_window_pre_transcription",
        "action_executed": action_executed,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "metadata": metadata,
    }


def test_command_asr_shadow_bridge_is_disabled_by_default() -> None:
    enriched = enrich_record_with_command_asr_shadow(
        record=_record(candidate=_candidate()),
    )

    metadata = enriched["metadata"]
    bridge = metadata["command_asr_shadow_bridge"]

    assert "command_asr_candidate" not in metadata
    assert bridge["enabled"] is False
    assert bridge["observed"] is False
    assert bridge["reason"] == COMMAND_ASR_SHADOW_BRIDGE_DISABLED_REASON
    assert bridge["candidate_attached"] is False
    assert bridge["command_asr_candidate_present"] is False
    assert bridge["recognizer_enabled"] is False
    assert bridge["recognition_attempted"] is False
    assert bridge["recognized"] is False
    assert bridge["raw_pcm_included"] is False
    assert bridge["action_executed"] is False
    assert bridge["full_stt_prevented"] is False
    assert bridge["runtime_takeover"] is False


def test_command_asr_shadow_bridge_attaches_disabled_candidate_when_enabled() -> None:
    enriched = enrich_record_with_command_asr_shadow(
        record=_record(candidate=_candidate()),
        settings=CommandAsrShadowBridgeSettings(enabled=True),
    )

    metadata = enriched["metadata"]
    bridge = metadata["command_asr_shadow_bridge"]
    candidate = metadata["command_asr_candidate"]

    assert bridge["enabled"] is True
    assert bridge["observed"] is True
    assert bridge["reason"] == COMMAND_ASR_SHADOW_BRIDGE_OBSERVED_REASON
    assert bridge["candidate_attached"] is True
    assert bridge["command_asr_candidate_present"] is False
    assert bridge["command_asr_reason"] == "command_asr_disabled"
    assert bridge["asr_reason"] == "command_asr_disabled"
    assert bridge["recognizer_name"] == "disabled_command_asr"
    assert bridge["recognizer_enabled"] is False
    assert bridge["recognition_attempted"] is False
    assert bridge["recognized"] is False
    assert bridge["raw_pcm_included"] is False

    assert candidate["candidate_present"] is False
    assert candidate["reason"] == "command_asr_disabled"
    assert candidate["recognizer_name"] == "disabled_command_asr"
    assert candidate["recognizer_enabled"] is False
    assert candidate["recognition_attempted"] is False
    assert candidate["recognized"] is False
    assert candidate["raw_pcm_included"] is False


def test_command_asr_shadow_bridge_can_attach_disabled_vosk_adapter() -> None:
    adapter = VoskCommandAsrAdapter()

    enriched = enrich_record_with_command_asr_shadow(
        record=_record(candidate=_candidate()),
        settings=CommandAsrShadowBridgeSettings(enabled=True),
        recognizer=adapter,
    )

    metadata = enriched["metadata"]
    bridge = metadata["command_asr_shadow_bridge"]
    candidate = metadata["command_asr_candidate"]

    assert bridge["enabled"] is True
    assert bridge["observed"] is True
    assert bridge["candidate_attached"] is True
    assert bridge["command_asr_candidate_present"] is False
    assert bridge["command_asr_reason"] == "command_asr_disabled"
    assert bridge["asr_reason"] == VOSK_COMMAND_ASR_DISABLED_REASON
    assert bridge["recognizer_name"] == "vosk_command_asr"
    assert bridge["recognizer_enabled"] is False
    assert bridge["recognition_attempted"] is False
    assert bridge["recognized"] is False

    assert candidate["recognizer_name"] == "vosk_command_asr"
    assert candidate["recognizer_enabled"] is False
    assert candidate["recognition_attempted"] is False
    assert candidate["recognized"] is False
    assert candidate["asr_reason"] == VOSK_COMMAND_ASR_DISABLED_REASON


def test_command_asr_shadow_bridge_can_attach_matched_injected_result() -> None:
    recognizer = VoskCommandRecognizer(
        grammar=build_default_command_grammar(),
        pcm_transcript_provider=lambda pcm: "show desktop",
    )
    adapter = VoskCommandAsrAdapter(
        recognizer=recognizer,
        segment_pcm_provider=lambda segment: b"\x00\x00" * 1600,
    )

    adapter = VoskCommandAsrAdapter(
        settings=adapter.settings.__class__(enabled=True),
        recognizer=recognizer,
        segment_pcm_provider=lambda segment: b"\x00\x00" * 1600,
    )

    enriched = enrich_record_with_command_asr_shadow(
        record=_record(candidate=_candidate()),
        settings=CommandAsrShadowBridgeSettings(enabled=True),
        recognizer=adapter,
    )

    metadata = enriched["metadata"]
    bridge = metadata["command_asr_shadow_bridge"]
    candidate = metadata["command_asr_candidate"]

    assert bridge["candidate_attached"] is True
    assert bridge["command_asr_candidate_present"] is True
    assert bridge["recognizer_name"] == "vosk_command_asr"
    assert bridge["recognizer_enabled"] is True
    assert bridge["recognition_attempted"] is True
    assert bridge["recognized"] is True
    assert bridge["raw_pcm_included"] is False

    assert candidate["candidate_present"] is True
    assert candidate["transcript"] == "show desktop"
    assert candidate["normalized_text"] == "show desktop"
    assert candidate["language"] == "en"
    assert candidate["action_executed"] is False
    assert candidate["full_stt_prevented"] is False
    assert candidate["runtime_takeover"] is False


def test_command_asr_shadow_bridge_rejects_unsafe_record() -> None:
    with pytest.raises(ValueError, match="must never receive action execution"):
        enrich_record_with_command_asr_shadow(
            record=_record(candidate=_candidate(), action_executed=True),
            settings=CommandAsrShadowBridgeSettings(enabled=True),
        )


def test_command_asr_shadow_bridge_rejects_duplicate_metadata_keys() -> None:
    with pytest.raises(ValueError, match="metadata keys must be different"):
        CommandAsrShadowBridgeSettings(
            bridge_metadata_key="command_asr",
            candidate_metadata_key="command_asr",
        )