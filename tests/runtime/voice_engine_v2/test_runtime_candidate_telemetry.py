from __future__ import annotations

import json
from pathlib import Path

from modules.devices.audio.command_asr import CommandLanguage
from modules.runtime.voice_engine_v2 import build_voice_engine_v2_runtime


def _bundle(
    *,
    log_path: Path,
    runtime_candidates_enabled: bool = True,
):
    return build_voice_engine_v2_runtime(
        {
            "voice_engine": {
                "enabled": False,
                "version": "v2",
                "mode": "legacy",
                "command_first_enabled": False,
                "fallback_to_legacy_enabled": True,
                "runtime_candidates_enabled": runtime_candidates_enabled,
                "runtime_candidate_intent_allowlist": [
                    "assistant.identity",
                    "system.current_time",
                ],
                "runtime_candidate_log_path": str(log_path),
            }
        }
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _safe_vosk_shadow_result(
    *,
    transcript: str,
    normalized_text: str,
    language: str,
) -> dict[str, object]:
    return {
        "result_stage": "vosk_shadow_asr_result",
        "result_version": "vosk_shadow_asr_result_v1",
        "reason": "vosk_shadow_asr_recognized",
        "recognizer_name": "vosk_command_asr",
        "recognizer_enabled": True,
        "recognition_invocation_performed": True,
        "recognition_attempted": True,
        "recognized": True,
        "command_matched": True,
        "transcript": transcript,
        "normalized_text": normalized_text,
        "language": language,
        "confidence": 1.0,
        "raw_pcm_included": False,
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


def test_runtime_candidate_telemetry_records_accepted_time_candidate(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "runtime_candidates.jsonl"
    bundle = _bundle(log_path=log_path)

    result = bundle.runtime_candidate_adapter.process_transcript(
        turn_id="turn-time",
        transcript="what time is it",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
        metadata={"source": "unit_test"},
    )

    assert result.accepted is True
    assert result.telemetry_written is True
    assert log_path.exists()

    records = _read_jsonl(log_path)

    assert len(records) == 1
    assert records[0]["accepted"] is True
    assert records[0]["reason"] == "accepted"
    assert records[0]["transcript"] == "what time is it"
    assert records[0]["legacy_runtime_primary"] is True
    assert records[0]["voice_engine_intent"] == "system.current_time"
    assert records[0]["voice_engine_action"] == "report_current_time"
    assert records[0]["primary_intent"] == "ask_time"
    assert records[0]["route_kind"] == "action"
    assert records[0]["llm_prevented"] is True
    assert records[0]["metadata"]["source"] == "unit_test"


def test_runtime_candidate_telemetry_records_rejected_candidate(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "runtime_candidates.jsonl"
    bundle = _bundle(log_path=log_path)

    result = bundle.runtime_candidate_adapter.process_transcript(
        turn_id="turn-show-shell-ambiguous",
        transcript="So shall.",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is False
    assert result.telemetry_written is True

    records = _read_jsonl(log_path)

    assert len(records) == 1
    assert records[0]["accepted"] is False
    assert records[0]["reason"] == "fallback_required:no_match"
    assert records[0]["transcript"] == "So shall."
    assert records[0]["voice_engine_route"] == "fallback"
    assert records[0]["fallback_reason"] == "no_match"
    assert records[0]["primary_intent"] == ""
    assert records[0]["llm_prevented"] is False


def test_runtime_candidate_telemetry_is_not_written_when_candidates_disabled(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "runtime_candidates.jsonl"
    bundle = _bundle(
        log_path=log_path,
        runtime_candidates_enabled=False,
    )

    result = bundle.runtime_candidate_adapter.process_transcript(
        turn_id="turn-disabled",
        transcript="what time is it",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is False
    assert result.reason == "runtime_candidates_disabled"
    assert result.telemetry_written is False
    assert not log_path.exists()


def test_runtime_candidate_telemetry_appends_multiple_records(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "runtime_candidates.jsonl"
    bundle = _bundle(log_path=log_path)

    bundle.runtime_candidate_adapter.process_transcript(
        turn_id="turn-identity",
        transcript="what is your name",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )
    bundle.runtime_candidate_adapter.process_transcript(
        turn_id="turn-time",
        transcript="what time is it",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=2.0,
        speech_end_monotonic=2.0,
    )

    records = _read_jsonl(log_path)

    assert len(records) == 2
    assert records[0]["voice_engine_intent"] == "assistant.identity"
    assert records[0]["primary_intent"] == "introduce_self"
    assert records[1]["voice_engine_intent"] == "system.current_time"
    assert records[1]["primary_intent"] == "ask_time"


def test_runtime_candidate_telemetry_records_vosk_shadow_source_metadata(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "runtime_candidates.jsonl"
    bundle = _bundle(log_path=log_path)

    result = bundle.runtime_candidate_adapter.process_vosk_shadow_result(
        turn_id="turn-vosk-time",
        result_metadata=_safe_vosk_shadow_result(
            transcript="która jest godzina",
            normalized_text="ktora jest godzina",
            language="pl",
        ),
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
        metadata={"source": "unit_test"},
    )

    assert result.accepted is True
    assert result.telemetry_written is True

    records = _read_jsonl(log_path)

    assert len(records) == 1
    assert records[0]["accepted"] is True
    assert records[0]["voice_engine_intent"] == "system.current_time"
    assert records[0]["primary_intent"] == "ask_time"
    assert records[0]["language"] == "pl"
    assert records[0]["metadata"]["candidate_source"] == "vosk_shadow_asr_result"
    assert records[0]["metadata"]["vosk_shadow_result"]["raw_pcm_included"] is False

