from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_command_asr_disabled import (
    main,
    validate_disabled_command_asr_log,
)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
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
    candidate: dict[str, object] | None,
    *,
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
        "timestamp_utc": "2026-04-28T00:00:00+00:00",
        "enabled": True,
        "observed": True,
        "reason": "vad_timing_bridge_pre_transcription_observed_audio",
        "hook": "capture_window_pre_transcription",
        "turn_id": "turn-command-asr-validator",
        "phase": "command",
        "capture_mode": "wake_command",
        "legacy_runtime_primary": True,
        "action_executed": action_executed,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "transcript_present": False,
        "vad_shadow": {},
        "metadata": metadata,
    }


def test_validate_disabled_command_asr_log_accepts_disabled_contract(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(log_path, [_record(_candidate())])

    result = validate_disabled_command_asr_log(
        log_path=log_path,
        require_records=True,
        require_segment_backed_disabled_records=True,
    )

    assert result["accepted"] is True
    assert result["command_asr_contract_records"] == 1
    assert result["segment_backed_disabled_records"] == 1
    assert result["not_ready_records"] == 0
    assert result["reason_counts"] == {"command_asr_disabled": 1}
    assert result["asr_reason_counts"] == {"command_asr_disabled": 1}
    assert result["recognizer_name_counts"] == {"disabled_command_asr": 1}
    assert result["source_counts"] == {
        "faster_whisper_capture_window_shadow_tap": 1
    }
    assert result["publish_stage_counts"] == {"before_transcription": 1}
    assert result["recognizer_enabled_records"] == 0
    assert result["recognition_attempted_records"] == 0
    assert result["recognized_records"] == 0
    assert result["candidate_present_records"] == 0
    assert result["raw_pcm_records"] == 0
    assert result["unsafe_action_records"] == 0
    assert result["unsafe_full_stt_records"] == 0
    assert result["unsafe_takeover_records"] == 0
    assert result["issues"] == []


def test_validate_disabled_command_asr_log_accepts_not_ready_when_not_strict(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(
                _candidate(
                    endpoint_detected=False,
                    reason="speech_not_ended_yet",
                )
            )
        ],
    )

    result = validate_disabled_command_asr_log(
        log_path=log_path,
        require_records=True,
        require_segment_backed_disabled_records=False,
    )

    assert result["accepted"] is True
    assert result["command_asr_contract_records"] == 1
    assert result["segment_backed_disabled_records"] == 0
    assert result["not_ready_records"] == 1
    assert result["recognition_attempted_records"] == 0
    assert result["recognized_records"] == 0


def test_validate_disabled_command_asr_log_fails_when_segment_backed_required(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(
                _candidate(
                    endpoint_detected=False,
                    reason="speech_not_ended_yet",
                )
            )
        ],
    )

    result = validate_disabled_command_asr_log(
        log_path=log_path,
        require_records=True,
        require_segment_backed_disabled_records=True,
    )

    assert result["accepted"] is False
    assert "command_asr_segment_backed_disabled_records_missing" in result["issues"]


def test_validate_disabled_command_asr_log_fails_on_unsafe_record(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(log_path, [_record(_candidate(), action_executed=True)])

    result = validate_disabled_command_asr_log(log_path=log_path)

    assert result["accepted"] is False
    assert any(
        "unsafe_command_asr" in issue and "must never execute actions" in issue
        for issue in result["issues"]
    )


def test_cli_returns_zero_for_disabled_contract(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(log_path, [_record(_candidate())])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-segment-backed-disabled-records",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["segment_backed_disabled_records"] == 1


def test_cli_returns_one_when_records_missing(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(log_path, [_record(None)])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "command_asr_contract_records_missing" in payload["issues"]