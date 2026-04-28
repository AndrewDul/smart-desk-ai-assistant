from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_command_audio_segments import (
    main,
    validate_command_audio_segments_log,
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
    hook: str = "capture_window_pre_transcription",
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
        "hook": hook,
        "turn_id": "turn-test",
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


def test_validate_command_audio_segments_log_accepts_ready_segment(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(log_path, [_record(_candidate())])

    result = validate_command_audio_segments_log(
        log_path=log_path,
        require_segments=True,
        require_ready_segment=True,
    )

    assert result["accepted"] is True
    assert result["segment_records"] == 1
    assert result["segment_present_records"] == 1
    assert result["rejected_segment_records"] == 0
    assert result["segment_reason_counts"] == {
        "segment_ready_for_command_recognizer": 1
    }
    assert result["source_counts"] == {
        "faster_whisper_capture_window_shadow_tap": 1
    }
    assert result["publish_stage_counts"] == {
        "before_transcription": 1
    }
    assert result["readiness_reason_counts"] == {
        "ready_for_command_recognition": 1
    }
    assert result["max_speech_score"] == 0.99
    assert result["max_audio_duration_ms"] == 2000.0
    assert result["max_audio_sample_count"] == 32_000
    assert result["max_published_byte_count"] == 64_000
    assert result["max_capture_finished_to_vad_observed_ms"] == 228.0
    assert result["max_capture_window_publish_to_vad_observed_ms"] == 226.0
    assert result["unsafe_action_records"] == 0
    assert result["unsafe_full_stt_records"] == 0
    assert result["unsafe_takeover_records"] == 0
    assert result["issues"] == []


def test_validate_command_audio_segments_log_allows_rejected_segment_when_not_strict(
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

    result = validate_command_audio_segments_log(
        log_path=log_path,
        require_segments=True,
        require_ready_segment=False,
        require_no_rejected_segments=False,
    )

    assert result["accepted"] is True
    assert result["segment_records"] == 1
    assert result["segment_present_records"] == 0
    assert result["rejected_segment_records"] == 1
    assert result["segment_reason_counts"] == {
        "not_ready:not_ready:endpoint_detected": 1
    }


def test_validate_command_audio_segments_log_fails_when_ready_segment_required(
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

    result = validate_command_audio_segments_log(
        log_path=log_path,
        require_segments=True,
        require_ready_segment=True,
    )

    assert result["accepted"] is False
    assert result["segment_records"] == 1
    assert result["segment_present_records"] == 0
    assert result["rejected_segment_records"] == 1
    assert "command_audio_ready_segment_records_missing" in result["issues"]


def test_validate_command_audio_segments_log_fails_in_strict_mode(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(_candidate()),
            _record(
                _candidate(
                    endpoint_detected=False,
                    reason="speech_not_ended_yet",
                )
            ),
        ],
    )

    result = validate_command_audio_segments_log(
        log_path=log_path,
        require_segments=True,
        require_ready_segment=True,
        require_no_rejected_segments=True,
    )

    assert result["accepted"] is False
    assert result["segment_present_records"] == 1
    assert result["rejected_segment_records"] == 1
    assert "command_audio_rejected_segment_records_present" in result["issues"]


def test_validate_command_audio_segments_log_fails_on_unsafe_record(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(
                _candidate(),
                action_executed=True,
            )
        ],
    )

    result = validate_command_audio_segments_log(log_path=log_path)

    assert result["accepted"] is False
    assert any(
        "unsafe_segment" in issue and "must never execute actions" in issue
        for issue in result["issues"]
    )


def test_cli_returns_zero_for_ready_segment(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(log_path, [_record(_candidate())])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-segments",
            "--require-ready-segment",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["segment_present_records"] == 1


def test_cli_returns_one_when_segment_missing(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(log_path, [_record(None)])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-segments",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "command_audio_segment_records_missing" in payload["issues"]