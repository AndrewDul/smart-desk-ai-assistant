from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_vosk_shadow_invocation_attempt import (
    main,
    validate_vosk_shadow_invocation_attempt_log,
)


def _attempt(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "attempt_stage": "vosk_shadow_invocation_attempt",
        "attempt_version": "vosk_shadow_invocation_attempt_v1",
        "enabled": True,
        "attempt_ready": True,
        "invocation_allowed": False,
        "invocation_blocked": True,
        "reason": "recognition_invocation_blocked_by_stage_policy",
        "metadata_key": "vosk_shadow_invocation_attempt",
        "hook": "capture_window_pre_transcription",
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "recognizer_name": "vosk_command_asr",
        "preflight_present": True,
        "preflight_ready": True,
        "preflight_recognition_blocked": True,
        "preflight_reason": "recognition_invocation_blocked_by_stage_policy",
        "audio_sample_count": 32000,
        "published_byte_count": 64000,
        "sample_rate": 16000,
        "pcm_encoding": "pcm_s16le",
        "pcm_retrieval_allowed": False,
        "pcm_retrieval_performed": False,
        "recognition_allowed": False,
        "recognition_invocation_allowed": False,
        "recognition_invocation_performed": False,
        "recognition_attempted": False,
        "result_present": False,
        "recognized": False,
        "command_matched": False,
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


def _write_log(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _record(attempt: dict[str, object] | None = None) -> dict[str, object]:
    metadata: dict[str, object] = {}
    if attempt is not None:
        metadata["vosk_shadow_invocation_attempt"] = attempt
    return {
        "hook": "capture_window_pre_transcription",
        "metadata": metadata,
    }


def test_validator_accepts_ready_but_blocked_invocation_attempt(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_record(_attempt())])

    result = validate_vosk_shadow_invocation_attempt_log(
        log_path=log_path,
        require_records=True,
        require_attempt_attached=True,
        require_enabled=True,
        require_ready=True,
    )

    assert result["accepted"] is True
    assert result["attempt_records"] == 1
    assert result["ready_attempt_records"] == 1
    assert result["unsafe_attempt_records"] == 0
    assert result["invocation_permission_records"] == 0


def test_validator_rejects_missing_attempt_when_required(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_record()])

    result = validate_vosk_shadow_invocation_attempt_log(
        log_path=log_path,
        require_records=True,
        require_attempt_attached=True,
        require_enabled=True,
        require_ready=True,
    )

    assert result["accepted"] is False
    assert "vosk_shadow_invocation_attempt_records_missing" in result["issues"]
    assert "enabled_vosk_shadow_invocation_attempt_records_missing" in result["issues"]
    assert "ready_vosk_shadow_invocation_attempt_records_missing" in result["issues"]


def test_validator_rejects_recognition_invocation_permission(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(
        log_path,
        [
            _record(
                _attempt(
                    recognition_invocation_allowed=True,
                    recognition_invocation_performed=True,
                    recognition_attempted=True,
                )
            )
        ],
    )

    result = validate_vosk_shadow_invocation_attempt_log(
        log_path=log_path,
        require_records=True,
        require_attempt_attached=True,
        require_enabled=True,
        require_ready=True,
    )

    assert result["accepted"] is False
    assert "line_1:recognition_invocation_allowed_must_be_false" in result["issues"]
    assert "line_1:recognition_invocation_not_allowed" in result["issues"]
    assert "recognition_invocation_records_not_allowed" in result["issues"]


def test_cli_accepts_ready_but_blocked_invocation_attempt(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_record(_attempt())])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-attempt-attached",
            "--require-enabled",
            "--require-ready",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["ready_attempt_records"] == 1
