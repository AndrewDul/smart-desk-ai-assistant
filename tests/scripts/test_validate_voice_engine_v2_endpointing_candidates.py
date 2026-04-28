from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_endpointing_candidates import (
    main,
    validate_endpointing_candidate_log,
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
        "frames_processed": 7,
        "speech_started": True,
        "speech_ended": True,
        "speech_started_count": 1,
        "speech_ended_count": 1,
        "speech_frame_count": 3,
        "silence_frame_count": 4,
        "speech_score_max": 0.99,
        "speech_score_avg": 0.51,
        "speech_score_over_threshold_count": 3,
        "latest_event_type": "speech_ended",
        "pcm_profile_signal_level": "high",
        "pcm_profile_rms": 0.08,
        "pcm_profile_peak_abs": 0.72,
        "frame_source_counts": {
            "faster_whisper_capture_window_shadow_tap": 7,
        },
        "capture_finished_to_publish_start_ms": 2.5,
        "capture_window_publish_to_vad_observed_ms": 226.0,
        "capture_finished_to_vad_observed_ms": 228.0,
        "latest_speech_end_to_observe_ms": 180.0,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }
    payload.update(overrides)
    return payload


def _record(
    candidate: dict[str, object] | None = None,
    *,
    hook: str = "capture_window_pre_transcription",
    action_executed: bool = False,
    full_stt_prevented: bool = False,
    runtime_takeover: bool = False,
) -> dict[str, object]:
    metadata: dict[str, object] = {}
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
        "full_stt_prevented": full_stt_prevented,
        "runtime_takeover": runtime_takeover,
        "transcript_present": False,
        "vad_shadow": {},
        "metadata": metadata,
    }


def test_validate_endpointing_candidate_log_accepts_safe_candidates(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(log_path, [_record(_candidate())])

    result = validate_endpointing_candidate_log(
        log_path=log_path,
        require_candidates=True,
        require_candidate_present=True,
        require_endpoint_detected=True,
        require_pre_transcription_hook=True,
        require_capture_window_source=True,
        require_before_transcription_stage=True,
        require_latency_metrics=True,
    )

    assert result["accepted"] is True
    assert result["candidate_records"] == 1
    assert result["candidate_present_records"] == 1
    assert result["endpoint_detected_records"] == 1
    assert result["pre_transcription_candidate_records"] == 1
    assert result["candidate_reason_counts"] == {"endpoint_detected": 1}
    assert result["candidate_source_counts"] == {
        "faster_whisper_capture_window_shadow_tap": 1
    }
    assert result["candidate_publish_stage_counts"] == {
        "before_transcription": 1
    }
    assert result["candidate_signal_level_counts"] == {"high": 1}
    assert result["max_speech_score"] == 0.99
    assert result["max_frames_processed"] == 7
    assert result["latency_metric_records"] == 1
    assert result["max_capture_finished_to_vad_observed_ms"] == 228.0
    assert result["max_capture_window_publish_to_vad_observed_ms"] == 226.0
    assert result["unsafe_action_records"] == 0
    assert result["unsafe_full_stt_records"] == 0
    assert result["unsafe_takeover_records"] == 0
    assert result["unsafe_candidate_action_records"] == 0
    assert result["unsafe_candidate_full_stt_records"] == 0
    assert result["unsafe_candidate_takeover_records"] == 0
    assert result["issues"] == []


def test_validate_endpointing_candidate_log_fails_when_required_candidate_missing(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(log_path, [_record(None)])

    result = validate_endpointing_candidate_log(
        log_path=log_path,
        require_candidates=True,
        require_candidate_present=True,
        require_endpoint_detected=True,
        require_pre_transcription_hook=True,
    )

    assert result["accepted"] is False
    assert "endpointing_candidate_records_missing" in result["issues"]
    assert "endpointing_candidate_present_records_missing" in result["issues"]
    assert "endpointing_endpoint_detected_records_missing" in result["issues"]
    assert "endpointing_pre_transcription_candidate_records_missing" in result["issues"]


def test_validate_endpointing_candidate_log_fails_on_unsafe_candidate(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(
                _candidate(
                    action_executed=True,
                    full_stt_prevented=True,
                    runtime_takeover=True,
                )
            )
        ],
    )

    result = validate_endpointing_candidate_log(log_path=log_path)

    assert result["accepted"] is False
    assert result["unsafe_candidate_action_records"] == 1
    assert result["unsafe_candidate_full_stt_records"] == 1
    assert result["unsafe_candidate_takeover_records"] == 1
    assert "line_1:candidate_action_executed" in result["issues"]
    assert "line_1:candidate_full_stt_prevented" in result["issues"]
    assert "line_1:candidate_runtime_takeover" in result["issues"]


def test_validate_endpointing_candidate_log_fails_on_unsafe_top_level_record(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(
                _candidate(),
                action_executed=True,
                full_stt_prevented=True,
                runtime_takeover=True,
            )
        ],
    )

    result = validate_endpointing_candidate_log(log_path=log_path)

    assert result["accepted"] is False
    assert result["unsafe_action_records"] == 1
    assert result["unsafe_full_stt_records"] == 1
    assert result["unsafe_takeover_records"] == 1
    assert "line_1:top_level_action_executed" in result["issues"]
    assert "line_1:top_level_full_stt_prevented" in result["issues"]
    assert "line_1:top_level_runtime_takeover" in result["issues"]


def test_cli_returns_zero_for_valid_candidate_log(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(log_path, [_record(_candidate())])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-candidates",
            "--require-candidate-present",
            "--require-endpoint-detected",
            "--require-pre-transcription-hook",
            "--require-capture-window-source",
            "--require-before-transcription-stage",
            "--require-latency-metrics",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["candidate_records"] == 1


def test_cli_returns_one_for_missing_required_candidate(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(log_path, [_record(None)])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-candidates",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "endpointing_candidate_records_missing" in payload["issues"]