from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_stale_audio_backlog import (
    CATEGORY_CALLBACK_ONLY_BACKLOG,
    CATEGORY_HIGH_SUBSCRIPTION_BACKLOG,
    CATEGORY_NEAR_SILENT_STALE,
    CATEGORY_POST_CAPTURE_STALE,
    CATEGORY_SLOW_SPEECH_END_TO_OBSERVE,
    main,
    validate_stale_audio_backlog,
)


def _write_log(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _record(
    *,
    hook: str = "post_capture",
    stale_audio_observed: bool = True,
    subscription_backlog_frames: int = 47,
    last_frame_age_ms: float = 2900.211,
    latest_speech_end_to_observe_ms: float = 3335.492,
    signal_level: str = "near_silent",
    frame_source_counts: dict[str, int] | None = None,
) -> dict[str, object]:
    return {
        "hook": hook,
        "turn_id": "turn-test",
        "phase": "command",
        "capture_mode": "wake_command",
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "vad_shadow": {
            "stale_audio_observed": stale_audio_observed,
            "cadence_diagnostic_reason": (
                "stale_audio_backlog_observed"
                if stale_audio_observed
                else "fresh_audio_backlog_observed"
            ),
            "subscription_backlog_frames": subscription_backlog_frames,
            "last_frame_age_ms": last_frame_age_ms,
            "latest_speech_end_to_observe_ms": latest_speech_end_to_observe_ms,
            "audio_window_duration_ms": 2944.589,
            "audio_bus_frame_count": 46,
            "pcm_profile_signal_level": signal_level,
            "frame_source_counts": frame_source_counts
            or {"faster_whisper_callback_shadow_tap": 46},
        },
        "metadata": {
            "vosk_shadow_invocation_attempt": {
                "recognition_invocation_performed": False,
                "recognition_attempted": False,
                "result_present": False,
                "raw_pcm_included": False,
                "action_executed": False,
                "runtime_takeover": False,
            }
        },
    }


def test_stale_audio_backlog_accepts_safe_log_and_classifies_backlog(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(
        log_path,
        [
            _record(),
            _record(hook="capture_window_pre_transcription", stale_audio_observed=False),
        ],
    )

    result = validate_stale_audio_backlog(
        log_path=log_path,
        require_records=True,
        require_stale_audio_records=True,
    )

    assert result["accepted"] is True
    assert result["records"] == 2
    assert result["stale_audio_records"] == 1
    assert result["post_capture_stale_records"] == 1
    assert result["capture_window_stale_records"] == 0
    assert result["category_counts"][CATEGORY_POST_CAPTURE_STALE] == 1
    assert result["category_counts"][CATEGORY_HIGH_SUBSCRIPTION_BACKLOG] == 1
    assert result["category_counts"][CATEGORY_SLOW_SPEECH_END_TO_OBSERVE] == 1
    assert result["category_counts"][CATEGORY_CALLBACK_ONLY_BACKLOG] == 1
    assert result["category_counts"][CATEGORY_NEAR_SILENT_STALE] == 1
    assert result["stale_metrics"]["subscription_backlog_frames"]["p95"] == 47.0
    assert result["safety"]["unsafe_field_counts"] == {}
    assert result["issues"] == []


def test_stale_audio_backlog_can_fail_when_backlog_ratio_is_high(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_record(), _record(stale_audio_observed=False)])

    result = validate_stale_audio_backlog(
        log_path=log_path,
        require_records=True,
        require_stale_audio_records=True,
        max_stale_audio_ratio=0.2,
        fail_on_backlog=True,
    )

    assert result["accepted"] is False
    assert "stale_audio_ratio_above_threshold" in result["issues"]


def test_stale_audio_backlog_rejects_missing_records_when_required(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "missing.jsonl"

    result = validate_stale_audio_backlog(
        log_path=log_path,
        require_records=True,
    )

    assert result["accepted"] is False
    assert "log_file_missing" in result["issues"]


def test_stale_audio_backlog_rejects_missing_stale_records_when_required(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_record(stale_audio_observed=False)])

    result = validate_stale_audio_backlog(
        log_path=log_path,
        require_records=True,
        require_stale_audio_records=True,
    )

    assert result["accepted"] is False
    assert "stale_audio_records_missing" in result["issues"]


def test_stale_audio_backlog_rejects_unsafe_observe_only_fields(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    record = _record()
    record["action_executed"] = True

    _write_log(log_path, [record])

    result = validate_stale_audio_backlog(
        log_path=log_path,
        require_records=True,
        require_stale_audio_records=True,
    )

    assert result["accepted"] is False
    assert "unsafe_observe_only_fields_present" in result["issues"]
    assert result["safety"]["unsafe_field_counts"]["action_executed"] == 1


def test_stale_audio_backlog_cli_accepts_safe_log(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_record(), _record(stale_audio_observed=False)])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-stale-audio-records",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["stale_audio_records"] == 1


def test_stale_audio_backlog_cli_fails_on_backlog_gate(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_record(), _record(stale_audio_observed=False)])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-stale-audio-records",
            "--max-stale-audio-ratio",
            "0.2",
            "--fail-on-backlog",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "stale_audio_ratio_above_threshold" in payload["issues"]
