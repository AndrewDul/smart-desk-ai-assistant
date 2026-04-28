from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_vosk_shadow_pcm_reference import (
    main,
    validate_vosk_shadow_pcm_reference_log,
)


def _reference(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "reference_stage": "vosk_shadow_pcm_reference",
        "reference_version": "vosk_shadow_pcm_reference_v1",
        "enabled": True,
        "reference_ready": True,
        "reason": "existing_capture_window_pcm_reference_ready",
        "metadata_key": "vosk_shadow_pcm_reference",
        "hook": "capture_window_pre_transcription",
        "retrieval_strategy": "existing_capture_window_audio_bus_snapshot",
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
        "segment_present": True,
        "invocation_plan_present": True,
        "invocation_plan_ready": True,
        "command_asr_candidate_present": True,
        "raw_pcm_included": False,
        "pcm_retrieval_performed": False,
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
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }
    payload.update(overrides)
    return payload


def _record(
    reference: dict[str, object] | None = None,
    *,
    hook: str | None = None,
) -> dict[str, object]:
    record_hook = hook or "capture_window_pre_transcription"
    metadata: dict[str, object] = {}
    if reference is not None:
        metadata["vosk_shadow_pcm_reference"] = reference

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


def test_validator_accepts_ready_pcm_reference(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_reference())])

    result = validate_vosk_shadow_pcm_reference_log(
        log_path=log_path,
        require_records=True,
        require_reference_attached=True,
        require_enabled=True,
        require_ready=True,
    )

    assert result["accepted"] is True
    assert result["records"] == 1
    assert result["reference_records"] == 1
    assert result["enabled_reference_records"] == 1
    assert result["ready_reference_records"] == 1
    assert result["expected_version_records"] == 1
    assert result["expected_source_records"] == 1
    assert result["expected_publish_stage_records"] == 1
    assert result["raw_pcm_records"] == 0
    assert result["pcm_retrieval_records"] == 0
    assert result["unsafe_reference_records"] == 0
    assert result["issues"] == []


def test_validator_rejects_missing_reference_when_required(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(None)])

    result = validate_vosk_shadow_pcm_reference_log(
        log_path=log_path,
        require_records=True,
        require_reference_attached=True,
    )

    assert result["accepted"] is False
    assert "vosk_shadow_pcm_reference_records_missing" in result["issues"]


def test_validator_rejects_raw_pcm_in_reference_telemetry(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_reference(raw_pcm_included=True))])

    result = validate_vosk_shadow_pcm_reference_log(
        log_path=log_path,
        require_records=True,
        require_reference_attached=True,
    )

    assert result["accepted"] is False
    assert result["raw_pcm_records"] == 1
    assert "raw_pcm_included_in_reference_telemetry" in result["issues"]
    assert "line_1:raw_pcm_included_must_be_false" in result["issues"]


def test_validator_rejects_pcm_retrieval(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_reference(pcm_retrieval_performed=True))])

    result = validate_vosk_shadow_pcm_reference_log(
        log_path=log_path,
        require_records=True,
        require_reference_attached=True,
    )

    assert result["accepted"] is False
    assert result["pcm_retrieval_records"] == 1
    assert "pcm_retrieval_performed_in_reference_stage" in result["issues"]
    assert "line_1:pcm_retrieval_performed_must_be_false" in result["issues"]


def test_validator_rejects_recognition_invocation_attempt(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(
                _reference(
                    recognition_invocation_performed=True,
                    recognition_attempted=True,
                )
            )
        ],
    )

    result = validate_vosk_shadow_pcm_reference_log(
        log_path=log_path,
        require_records=True,
        require_reference_attached=True,
    )

    assert result["accepted"] is False
    assert result["unsafe_reference_records"] == 1
    assert "unsafe_vosk_shadow_pcm_reference_records_present" in result["issues"]
    assert "line_1:recognition_invocation_performed_must_be_false" in result["issues"]
    assert "line_1:recognition_attempted_must_be_false" in result["issues"]


def test_validator_rejects_runtime_takeover_attempt(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_reference(runtime_takeover=True))])

    result = validate_vosk_shadow_pcm_reference_log(
        log_path=log_path,
        require_records=True,
        require_reference_attached=True,
    )

    assert result["accepted"] is False
    assert result["unsafe_field_counts"]["runtime_takeover"] == 1
    assert "line_1:runtime_takeover_must_be_false" in result["issues"]


def test_validator_rejects_non_capture_window_hook_by_default(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    reference = _reference(hook="post_capture")
    _write_jsonl(log_path, [_record(reference, hook="post_capture")])

    result = validate_vosk_shadow_pcm_reference_log(
        log_path=log_path,
        require_records=True,
        require_reference_attached=True,
    )

    assert result["accepted"] is False
    assert result["non_capture_window_hook_records"] == 1
    assert "line_1:non_capture_window_hook" in result["issues"]


def test_validator_rejects_unexpected_source_by_default(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_reference(source="other_source"))])

    result = validate_vosk_shadow_pcm_reference_log(
        log_path=log_path,
        require_records=True,
        require_reference_attached=True,
    )

    assert result["accepted"] is False
    assert "line_1:unexpected_audio_source" in result["issues"]


def test_validator_can_allow_non_ready_reference_when_not_required(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(
                _reference(
                    reference_ready=False,
                    reason="command_audio_segment_not_ready",
                    segment_present=False,
                )
            )
        ],
    )

    result = validate_vosk_shadow_pcm_reference_log(
        log_path=log_path,
        require_records=True,
        require_reference_attached=True,
        require_enabled=True,
        require_ready=False,
    )

    assert result["accepted"] is True
    assert result["ready_reference_records"] == 0


def test_validator_rejects_non_ready_reference_when_required(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(
                _reference(
                    reference_ready=False,
                    reason="command_audio_segment_not_ready",
                    segment_present=False,
                )
            )
        ],
    )

    result = validate_vosk_shadow_pcm_reference_log(
        log_path=log_path,
        require_records=True,
        require_reference_attached=True,
        require_enabled=True,
        require_ready=True,
    )

    assert result["accepted"] is False
    assert "ready_vosk_shadow_pcm_reference_records_missing" in result["issues"]


def test_cli_returns_zero_for_valid_pcm_reference(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_reference())])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-reference-attached",
            "--require-enabled",
            "--require-ready",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["validator"] == "vosk_shadow_pcm_reference"