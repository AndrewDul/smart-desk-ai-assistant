from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_vosk_shadow_recognition_preflight import (
    main,
    validate_vosk_shadow_recognition_preflight_log,
)


def _preflight(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "preflight_stage": "vosk_shadow_recognition_preflight",
        "preflight_version": "vosk_shadow_recognition_preflight_v1",
        "enabled": True,
        "preflight_ready": True,
        "recognition_allowed": False,
        "recognition_blocked": True,
        "reason": "recognition_invocation_blocked_by_stage_policy",
        "metadata_key": "vosk_shadow_recognition_preflight",
        "hook": "capture_window_pre_transcription",
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "recognizer_name": "vosk_command_asr",
        "live_shadow_present": True,
        "invocation_plan_present": True,
        "invocation_plan_ready": True,
        "pcm_reference_present": True,
        "pcm_reference_ready": True,
        "asr_result_present": True,
        "asr_result_not_attempted": True,
        "audio_sample_count": 32000,
        "published_byte_count": 64000,
        "sample_rate": 16000,
        "pcm_encoding": "pcm_s16le",
        "pcm_retrieval_allowed": False,
        "pcm_retrieval_performed": False,
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


def _record(
    preflight: dict[str, object] | None = None,
    *,
    hook: str | None = None,
) -> dict[str, object]:
    record_hook = hook or "capture_window_pre_transcription"
    metadata: dict[str, object] = {}
    if preflight is not None:
        metadata["vosk_shadow_recognition_preflight"] = preflight

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


def test_validator_accepts_ready_but_blocked_preflight(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_preflight())])

    result = validate_vosk_shadow_recognition_preflight_log(
        log_path=log_path,
        require_records=True,
        require_preflight_attached=True,
        require_enabled=True,
        require_ready=True,
    )

    assert result["accepted"] is True
    assert result["records"] == 1
    assert result["preflight_records"] == 1
    assert result["enabled_preflight_records"] == 1
    assert result["ready_preflight_records"] == 1
    assert result["blocked_preflight_records"] == 1
    assert result["ready_blocked_reason_records"] == 1
    assert result["recognition_permission_records"] == 0
    assert result["unsafe_preflight_records"] == 0
    assert result["issues"] == []


def test_validator_rejects_missing_preflight_when_required(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(None)])

    result = validate_vosk_shadow_recognition_preflight_log(
        log_path=log_path,
        require_records=True,
        require_preflight_attached=True,
    )

    assert result["accepted"] is False
    assert "vosk_shadow_recognition_preflight_records_missing" in result["issues"]


def test_validator_rejects_recognition_permission(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(
                _preflight(
                    recognition_allowed=True,
                    recognition_invocation_allowed=True,
                    recognition_invocation_performed=True,
                )
            )
        ],
    )

    result = validate_vosk_shadow_recognition_preflight_log(
        log_path=log_path,
        require_records=True,
        require_preflight_attached=True,
    )

    assert result["accepted"] is False
    assert result["recognition_permission_records"] == 1
    assert result["permission_field_counts"]["recognition_allowed"] == 1
    assert result["permission_field_counts"]["recognition_invocation_allowed"] == 1
    assert (
        result["permission_field_counts"]["recognition_invocation_performed"]
        == 1
    )
    assert "line_1:recognition_permission_not_allowed" in result["issues"]
    assert "recognition_permission_records_not_allowed" in result["issues"]


def test_validator_rejects_pcm_retrieval_permission(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(
                _preflight(
                    pcm_retrieval_allowed=True,
                    pcm_retrieval_performed=True,
                )
            )
        ],
    )

    result = validate_vosk_shadow_recognition_preflight_log(
        log_path=log_path,
        require_records=True,
        require_preflight_attached=True,
    )

    assert result["accepted"] is False
    assert result["recognition_permission_records"] == 1
    assert result["permission_field_counts"]["pcm_retrieval_allowed"] == 1
    assert result["permission_field_counts"]["pcm_retrieval_performed"] == 1
    assert "line_1:recognition_permission_not_allowed" in result["issues"]


def test_validator_rejects_runtime_takeover_attempt(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_preflight(runtime_takeover=True))])

    result = validate_vosk_shadow_recognition_preflight_log(
        log_path=log_path,
        require_records=True,
        require_preflight_attached=True,
    )

    assert result["accepted"] is False
    assert result["unsafe_field_counts"]["runtime_takeover"] == 1
    assert "line_1:runtime_takeover_must_be_false" in result["issues"]
    assert (
        "unsafe_vosk_shadow_recognition_preflight_records_present"
        in result["issues"]
    )


def test_validator_rejects_ready_preflight_without_dependency_flags(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_preflight(pcm_reference_ready=False))])

    result = validate_vosk_shadow_recognition_preflight_log(
        log_path=log_path,
        require_records=True,
        require_preflight_attached=True,
        require_ready=True,
    )

    assert result["accepted"] is False
    assert result["ready_preflight_records"] == 1
    assert "line_1:pcm_reference_ready_must_be_true" in result["issues"]
    assert "ready_preflight_dependency_flags_missing" in result["issues"]


def test_validator_rejects_non_capture_window_hook_by_default(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    preflight = _preflight(hook="post_capture")
    _write_jsonl(log_path, [_record(preflight, hook="post_capture")])

    result = validate_vosk_shadow_recognition_preflight_log(
        log_path=log_path,
        require_records=True,
        require_preflight_attached=True,
    )

    assert result["accepted"] is False
    assert result["non_capture_window_hook_records"] == 1
    assert "line_1:non_capture_window_hook" in result["issues"]


def test_validator_rejects_unexpected_source_by_default(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_preflight(source="second_microphone"))])

    result = validate_vosk_shadow_recognition_preflight_log(
        log_path=log_path,
        require_records=True,
        require_preflight_attached=True,
    )

    assert result["accepted"] is False
    assert "line_1:unexpected_audio_source" in result["issues"]


def test_validator_rejects_unexpected_version(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_preflight(preflight_version="unexpected"))])

    result = validate_vosk_shadow_recognition_preflight_log(
        log_path=log_path,
        require_records=True,
        require_preflight_attached=True,
    )

    assert result["accepted"] is False
    assert "unexpected_vosk_shadow_recognition_preflight_version" in result["issues"]


def test_cli_returns_zero_for_valid_preflight(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_preflight())])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-preflight-attached",
            "--require-enabled",
            "--require-ready",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["validator"] == "vosk_shadow_recognition_preflight"