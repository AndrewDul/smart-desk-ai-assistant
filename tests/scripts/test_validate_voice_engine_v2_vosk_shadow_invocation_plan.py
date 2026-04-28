from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_vosk_shadow_invocation_plan import (
    main,
    validate_vosk_shadow_invocation_plan_log,
)


def _plan(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "plan_stage": "vosk_shadow_invocation_plan",
        "plan_version": "vosk_shadow_invocation_plan_v1",
        "enabled": True,
        "plan_ready": True,
        "reason": "observe_only_invocation_boundary_ready",
        "metadata_key": "vosk_shadow_invocation_plan",
        "hook": "capture_window_pre_transcription",
        "input_source": "existing_command_audio_segment_metadata_only",
        "recognizer_name": "vosk_command_asr",
        "command_asr_bridge_present": True,
        "command_asr_candidate_present": True,
        "vosk_live_shadow_contract_present": True,
        "segment_present": True,
        "segment_reason": "command_audio_segment_ready",
        "segment_audio_duration_ms": 1800.0,
        "segment_audio_sample_count": 32000,
        "segment_published_byte_count": 64000,
        "segment_sample_rate": 16000,
        "segment_pcm_encoding": "pcm_s16le",
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


def _record(plan: dict[str, object] | None = None, *, hook: str | None = None) -> dict[str, object]:
    record_hook = hook or "capture_window_pre_transcription"
    metadata: dict[str, object] = {}
    if plan is not None:
        metadata["vosk_shadow_invocation_plan"] = plan

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


def test_validator_accepts_ready_observe_only_invocation_plan(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_plan())])

    result = validate_vosk_shadow_invocation_plan_log(
        log_path=log_path,
        require_records=True,
        require_plan_attached=True,
        require_enabled=True,
        require_ready=True,
    )

    assert result["accepted"] is True
    assert result["records"] == 1
    assert result["plan_records"] == 1
    assert result["enabled_plan_records"] == 1
    assert result["ready_plan_records"] == 1
    assert result["unsafe_plan_records"] == 0
    assert result["issues"] == []


def test_validator_rejects_missing_plan_when_required(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(None)])

    result = validate_vosk_shadow_invocation_plan_log(
        log_path=log_path,
        require_records=True,
        require_plan_attached=True,
    )

    assert result["accepted"] is False
    assert "vosk_shadow_invocation_plan_records_missing" in result["issues"]


def test_validator_rejects_recognition_invocation_attempt(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(
                _plan(
                    recognition_invocation_performed=True,
                    recognition_attempted=True,
                )
            )
        ],
    )

    result = validate_vosk_shadow_invocation_plan_log(
        log_path=log_path,
        require_records=True,
        require_plan_attached=True,
    )

    assert result["accepted"] is False
    assert result["unsafe_plan_records"] == 1
    assert "unsafe_vosk_shadow_invocation_plan_records_present" in result["issues"]
    assert "line_1:recognition_invocation_performed_must_be_false" in result["issues"]
    assert "line_1:recognition_attempted_must_be_false" in result["issues"]


def test_validator_rejects_runtime_takeover_attempt(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_plan(runtime_takeover=True))])

    result = validate_vosk_shadow_invocation_plan_log(
        log_path=log_path,
        require_records=True,
        require_plan_attached=True,
    )

    assert result["accepted"] is False
    assert result["unsafe_field_counts"]["runtime_takeover"] == 1
    assert "line_1:runtime_takeover_must_be_false" in result["issues"]


def test_validator_rejects_non_capture_window_hook_by_default(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    plan = _plan(hook="post_capture")
    _write_jsonl(log_path, [_record(plan, hook="post_capture")])

    result = validate_vosk_shadow_invocation_plan_log(
        log_path=log_path,
        require_records=True,
        require_plan_attached=True,
    )

    assert result["accepted"] is False
    assert result["non_capture_window_hook_records"] == 1
    assert "line_1:non_capture_window_hook" in result["issues"]


def test_validator_can_allow_non_ready_plan_when_not_required(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(
                _plan(
                    plan_ready=False,
                    reason="command_audio_segment_not_ready:speech_not_ended_yet",
                    segment_present=False,
                )
            )
        ],
    )

    result = validate_vosk_shadow_invocation_plan_log(
        log_path=log_path,
        require_records=True,
        require_plan_attached=True,
        require_enabled=True,
        require_ready=False,
    )

    assert result["accepted"] is True
    assert result["ready_plan_records"] == 0


def test_validator_rejects_non_ready_plan_when_required(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(
                _plan(
                    plan_ready=False,
                    reason="command_audio_segment_not_ready:speech_not_ended_yet",
                    segment_present=False,
                )
            )
        ],
    )

    result = validate_vosk_shadow_invocation_plan_log(
        log_path=log_path,
        require_records=True,
        require_plan_attached=True,
        require_enabled=True,
        require_ready=True,
    )

    assert result["accepted"] is False
    assert "ready_vosk_shadow_invocation_plan_records_missing" in result["issues"]


def test_cli_returns_zero_for_valid_invocation_plan(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record(_plan())])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-plan-attached",
            "--require-enabled",
            "--require-ready",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["validator"] == "vosk_shadow_invocation_plan"