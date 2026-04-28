from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_vosk_shadow_asr_result import (
    main,
    validate_vosk_shadow_asr_result_log,
)


def _asr_result(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "result_stage": "vosk_shadow_asr_result",
        "result_version": "vosk_shadow_asr_result_v1",
        "enabled": True,
        "result_present": False,
        "reason": "vosk_shadow_asr_not_attempted",
        "metadata_key": "vosk_shadow_asr_result",
        "recognizer_name": "disabled_command_asr",
        "recognizer_enabled": False,
        "recognition_invocation_performed": False,
        "recognition_attempted": False,
        "recognized": False,
        "command_matched": False,
        "transcript": "",
        "normalized_text": "",
        "language": None,
        "confidence": None,
        "alternatives": [],
        "turn_id": "turn-vosk-shadow-asr-result",
        "hook": "capture_window_pre_transcription",
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "segment_present": True,
        "segment_reason": "command_audio_segment_ready",
        "segment_audio_duration_ms": 1800.0,
        "segment_audio_sample_count": 32000,
        "segment_published_byte_count": 64000,
        "segment_sample_rate": 16000,
        "segment_pcm_encoding": "pcm_s16le",
        "pcm_retrieval_performed": False,
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
    payload.update(overrides)
    return payload


def _record(
    asr_result: dict[str, object] | None = None,
    *,
    hook: str | None = None,
) -> dict[str, object]:
    record_hook = hook or "capture_window_pre_transcription"
    metadata: dict[str, object] = {}
    if asr_result is not None:
        metadata["vosk_shadow_asr_result"] = asr_result

    return {
        "hook": record_hook,
        "metadata": metadata,
    }


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def test_validator_accepts_safe_not_attempted_asr_result(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_asr_result())])

    result = validate_vosk_shadow_asr_result_log(
        log_path=log_path,
        require_records=True,
        require_result_attached=True,
        require_enabled=True,
        require_not_attempted=True,
    )

    assert result["accepted"] is True
    assert result["records"] == 1
    assert result["result_records"] == 1
    assert result["enabled_result_records"] == 1
    assert result["not_attempted_result_records"] == 1
    assert result["result_present_records"] == 0
    assert result["unsafe_result_records"] == 0
    assert result["recognition_attempt_records"] == 0
    assert result["issues"] == []


def test_validator_rejects_missing_asr_result_when_required(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(None)])

    result = validate_vosk_shadow_asr_result_log(
        log_path=log_path,
        require_records=True,
        require_result_attached=True,
    )

    assert result["accepted"] is False
    assert "vosk_shadow_asr_result_records_missing" in result["issues"]


def test_validator_rejects_recognition_attempt_by_default(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(
                _asr_result(
                    result_present=True,
                    reason="vosk_shadow_asr_recognized",
                    recognizer_name="vosk_command_asr",
                    recognizer_enabled=True,
                    recognition_invocation_performed=True,
                    recognition_attempted=True,
                    recognized=True,
                    command_matched=True,
                    transcript="show desktop",
                    normalized_text="show desktop",
                    language="en",
                    confidence=0.91,
                    pcm_retrieval_performed=True,
                )
            )
        ],
    )

    result = validate_vosk_shadow_asr_result_log(
        log_path=log_path,
        require_records=True,
        require_result_attached=True,
    )

    assert result["accepted"] is False
    assert result["result_present_records"] == 1
    assert result["recognition_attempt_records"] == 1
    assert result["recognition_field_counts"]["recognition_invocation_performed"] == 1
    assert "line_1:recognition_attempt_not_allowed" in result["issues"]
    assert "result_present_records_not_allowed" in result["issues"]
    assert "recognition_attempt_records_not_allowed" in result["issues"]


def test_validator_can_allow_future_recognition_attempt(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(
                _asr_result(
                    result_present=True,
                    reason="vosk_shadow_asr_recognized",
                    recognizer_name="vosk_command_asr",
                    recognizer_enabled=True,
                    recognition_invocation_performed=True,
                    recognition_attempted=True,
                    recognized=True,
                    command_matched=True,
                    transcript="show desktop",
                    normalized_text="show desktop",
                    language="en",
                    confidence=0.91,
                    pcm_retrieval_performed=True,
                )
            )
        ],
    )

    result = validate_vosk_shadow_asr_result_log(
        log_path=log_path,
        require_records=True,
        require_result_attached=True,
        allow_recognition_attempt=True,
    )

    assert result["accepted"] is True
    assert result["result_present_records"] == 1
    assert result["recognition_attempt_records"] == 1
    assert result["recognition_attempt_allowed"] is True


def test_validator_rejects_runtime_takeover_attempt(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_asr_result(runtime_takeover=True))])

    result = validate_vosk_shadow_asr_result_log(
        log_path=log_path,
        require_records=True,
        require_result_attached=True,
    )

    assert result["accepted"] is False
    assert result["unsafe_field_counts"]["runtime_takeover"] == 1
    assert "line_1:runtime_takeover_must_be_false" in result["issues"]
    assert "unsafe_vosk_shadow_asr_result_records_present" in result["issues"]


def test_validator_rejects_non_capture_window_hook_by_default(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    asr_result = _asr_result(hook="post_capture")
    _write_jsonl(log_path, [_record(asr_result, hook="post_capture")])

    result = validate_vosk_shadow_asr_result_log(
        log_path=log_path,
        require_records=True,
        require_result_attached=True,
    )

    assert result["accepted"] is False
    assert result["non_capture_window_hook_records"] == 1
    assert "line_1:non_capture_window_hook" in result["issues"]


def test_validator_rejects_unexpected_source_by_default(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_asr_result(source="second_microphone"))])

    result = validate_vosk_shadow_asr_result_log(
        log_path=log_path,
        require_records=True,
        require_result_attached=True,
    )

    assert result["accepted"] is False
    assert "line_1:unexpected_audio_source" in result["issues"]


def test_validator_rejects_unexpected_result_version(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_asr_result(result_version="unexpected"))])

    result = validate_vosk_shadow_asr_result_log(
        log_path=log_path,
        require_records=True,
        require_result_attached=True,
    )

    assert result["accepted"] is False
    assert "unexpected_vosk_shadow_asr_result_version" in result["issues"]


def test_cli_returns_zero_for_valid_asr_result(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_asr_result())])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-result-attached",
            "--require-enabled",
            "--require-not-attempted",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["validator"] == "vosk_shadow_asr_result"