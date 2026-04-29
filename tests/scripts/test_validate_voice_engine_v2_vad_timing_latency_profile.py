from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_vad_timing_latency_profile import (
    main,
    validate_vad_timing_latency_profile,
)


def _write_log(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _pre_transcription_record() -> dict[str, object]:
    return {
        "hook": "capture_window_pre_transcription",
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "vad_shadow": {
            "latest_speech_end_to_observe_ms": 481.084,
            "observation_duration_ms": 63.99,
            "stale_audio_observed": False,
        },
        "metadata": {
            "capture_window_shadow_tap": {
                "capture_finished_to_publish_start_ms": 1.457,
            },
            "endpointing_candidate": {
                "capture_finished_to_vad_observed_ms": 65.751,
                "capture_window_publish_to_vad_observed_ms": 64.293,
            },
            "vosk_shadow_invocation_attempt": {
                "recognition_invocation_performed": False,
                "recognition_attempted": False,
                "result_present": False,
                "raw_pcm_included": False,
                "action_executed": False,
                "runtime_takeover": False,
            },
        },
    }


def _post_capture_record() -> dict[str, object]:
    return {
        "hook": "post_capture",
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "vad_shadow": {
            "latest_speech_end_to_observe_ms": 3335.492,
            "observation_duration_ms": 75.549,
            "stale_audio_observed": True,
        },
        "metadata": {
            "transcript_metadata": {
                "transcription_elapsed_seconds": 2.866558,
                "realtime_audio_bus_capture_window_shadow_tap": {
                    "capture_finished_to_publish_start_ms": 1.457,
                    "capture_window_publish_to_transcription_finished_ms": 2983.774,
                },
            }
        },
    }


def test_latency_profile_accepts_safe_observation_log(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_pre_transcription_record(), _post_capture_record()])

    result = validate_vad_timing_latency_profile(
        log_path=log_path,
        require_records=True,
        require_capture_window_records=True,
    )

    assert result["accepted"] is True
    assert result["records"] == 2
    assert result["capture_window_records"] == 1
    assert result["post_capture_records"] == 1
    assert result["stale_audio_records"] == 1
    assert result["latency_ms"]["capture_finished_to_publish_start"]["count"] == 2
    assert (
        result["latency_ms"]["capture_window_publish_to_transcription_finished"]["p95"]
        == 2983.774
    )
    assert result["latency_ms"]["latest_speech_end_to_observe"]["p95"] == 3335.492
    assert result["latency_ms"]["transcription_elapsed"]["p95"] == 2866.558
    assert result["safety"]["unsafe_field_counts"] == {}
    assert result["issues"] == []


def test_latency_profile_rejects_missing_records_when_required(tmp_path: Path) -> None:
    log_path = tmp_path / "missing.jsonl"

    result = validate_vad_timing_latency_profile(
        log_path=log_path,
        require_records=True,
        require_capture_window_records=True,
    )

    assert result["accepted"] is False
    assert "log_file_missing" in result["issues"]


def test_latency_profile_rejects_missing_capture_window_records_when_required(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_post_capture_record()])

    result = validate_vad_timing_latency_profile(
        log_path=log_path,
        require_records=True,
        require_capture_window_records=True,
    )

    assert result["accepted"] is False
    assert "capture_window_records_missing" in result["issues"]


def test_latency_profile_rejects_unsafe_observe_only_fields(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    record = _pre_transcription_record()
    record["action_executed"] = True

    _write_log(log_path, [record])

    result = validate_vad_timing_latency_profile(
        log_path=log_path,
        require_records=True,
        require_capture_window_records=True,
    )

    assert result["accepted"] is False
    assert "unsafe_observe_only_fields_present" in result["issues"]
    assert result["safety"]["unsafe_field_counts"]["action_executed"] == 1


def test_latency_profile_thresholds_can_fail_slow_logs(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_pre_transcription_record(), _post_capture_record()])

    result = validate_vad_timing_latency_profile(
        log_path=log_path,
        require_records=True,
        require_capture_window_records=True,
        max_p95_capture_window_publish_to_transcription_ms=900.0,
        max_p95_speech_end_to_observe_ms=900.0,
        max_stale_audio_ratio=0.1,
    )

    assert result["accepted"] is False
    assert (
        "p95_capture_window_publish_to_transcription_above_threshold"
        in result["issues"]
    )
    assert "p95_speech_end_to_observe_above_threshold" in result["issues"]
    assert "stale_audio_ratio_above_threshold" in result["issues"]


def test_latency_profile_cli_accepts_safe_log(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_pre_transcription_record(), _post_capture_record()])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-capture-window-records",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["capture_window_records"] == 1
