from __future__ import annotations

from modules.runtime.voice_engine_v2.vosk_shadow_candidate_comparison import (
    COMPARISON_AGREES_REASON,
    COMPARISON_INTENT_MISMATCH_REASON,
    VoskShadowCandidateComparisonSettings,
    build_vosk_shadow_candidate_comparison,
    validate_vosk_shadow_candidate_comparison,
)


def _metadata(
    *,
    vosk_transcript: str = "show desktop",
    vosk_language: str = "en",
    legacy_transcript: str = "show desktop",
    legacy_language: str = "en",
) -> dict[str, object]:
    return {
        "capture_window_vosk_shadow_asr_result": {
            "enabled": True,
            "result_present": True,
            "recognition_attempted": True,
            "recognized": True,
            "command_matched": True,
            "transcript": vosk_transcript,
            "normalized_text": vosk_transcript,
            "language": vosk_language,
            "confidence": 1.0,
            "raw_pcm_included": False,
            "action_executed": False,
            "full_stt_prevented": False,
            "runtime_takeover": False,
        },
        "transcript_metadata": {
            "transcript_text": legacy_transcript,
            "transcript_language": legacy_language,
            "transcript_confidence": 0.91,
            "backend_label": "faster_whisper",
        },
    }


def test_candidate_comparison_accepts_matching_vosk_and_legacy_command() -> None:
    comparison = build_vosk_shadow_candidate_comparison(
        hook="post_capture",
        turn_id="turn-compare",
        metadata=_metadata(),
        settings=VoskShadowCandidateComparisonSettings(enabled=True),
    )
    payload = comparison.to_json_dict()

    assert payload["enabled"] is True
    assert payload["comparison_present"] is True
    assert payload["reason"] == COMPARISON_AGREES_REASON
    assert payload["vosk_intent_key"] == "visual_shell.show_desktop"
    assert payload["legacy_intent_key"] == "visual_shell.show_desktop"
    assert payload["language_match"] is True
    assert payload["intent_match"] is True
    assert payload["candidate_agrees_with_legacy"] is True
    assert payload["safe_to_promote_later"] is True
    assert payload["action_executed"] is False
    assert payload["full_stt_prevented"] is False
    assert payload["runtime_takeover"] is False

    assert validate_vosk_shadow_candidate_comparison(payload)["accepted"] is True


def test_candidate_comparison_rejects_intent_mismatch_without_runtime_effects() -> None:
    comparison = build_vosk_shadow_candidate_comparison(
        hook="post_capture",
        turn_id="turn-compare",
        metadata=_metadata(
            vosk_transcript="show desktop",
            legacy_transcript="hide desktop",
        ),
        settings=VoskShadowCandidateComparisonSettings(enabled=True),
    )
    payload = comparison.to_json_dict()

    assert payload["comparison_present"] is True
    assert payload["reason"] == COMPARISON_INTENT_MISMATCH_REASON
    assert payload["intent_match"] is False
    assert payload["candidate_agrees_with_legacy"] is False
    assert payload["safe_to_promote_later"] is False
    assert payload["action_executed"] is False
    assert payload["full_stt_prevented"] is False
    assert payload["runtime_takeover"] is False

    assert validate_vosk_shadow_candidate_comparison(payload)["accepted"] is True
