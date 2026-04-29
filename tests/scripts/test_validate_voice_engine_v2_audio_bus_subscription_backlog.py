from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_audio_bus_subscription_backlog import (
    CATEGORY_CALLBACK_ONLY_CURSOR_BACKLOG,
    CATEGORY_HIGH_CURSOR_GAP,
    CATEGORY_HIGH_SUBSCRIPTION_BACKLOG,
    CATEGORY_NEAR_SILENT_CURSOR_BACKLOG,
    CATEGORY_POST_CAPTURE_CURSOR_BACKLOG,
    main,
    validate_audio_bus_subscription_backlog,
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
    latest_sequence: int = 1624,
    next_before: int = 1578,
    next_after: int = 1625,
    reported_backlog: int = 47,
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
            "audio_bus_latest_sequence": latest_sequence,
            "subscription_next_sequence_before": next_before,
            "subscription_next_sequence_after": next_after,
            "subscription_backlog_frames": reported_backlog,
            "latest_frame_sequence": latest_sequence,
            "last_frame_age_ms": 108.627,
            "latest_speech_end_to_observe_ms": 3856.789,
            "pcm_profile_signal_level": signal_level,
            "stale_audio_observed": True,
            "cadence_diagnostic_reason": "stale_audio_backlog_observed",
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


def _fresh_record() -> dict[str, object]:
    return _record(
        hook="capture_window_pre_transcription",
        latest_sequence=120,
        next_before=119,
        next_after=121,
        reported_backlog=2,
        signal_level="high",
        frame_source_counts={"faster_whisper_capture_window_shadow_tap": 14},
    )


def test_audio_bus_subscription_backlog_accepts_safe_log_and_classifies_cursor_gap(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_record(), _fresh_record()])

    result = validate_audio_bus_subscription_backlog(
        log_path=log_path,
        require_records=True,
        require_backlog_records=True,
    )

    assert result["accepted"] is True
    assert result["records"] == 2
    assert result["backlog_records"] == 1
    assert result["backlog_hook_counts"]["post_capture"] == 1
    assert result["category_counts"][CATEGORY_HIGH_SUBSCRIPTION_BACKLOG] == 1
    assert result["category_counts"][CATEGORY_HIGH_CURSOR_GAP] == 1
    assert result["category_counts"][CATEGORY_POST_CAPTURE_CURSOR_BACKLOG] == 1
    assert result["category_counts"][CATEGORY_CALLBACK_ONLY_CURSOR_BACKLOG] == 1
    assert result["category_counts"][CATEGORY_NEAR_SILENT_CURSOR_BACKLOG] == 1
    assert result["metrics"]["subscription_backlog_frames"]["p95"] == 47.0
    assert result["metrics"]["cursor_gap_before_frames"]["p95"] == 47.0
    assert result["metrics"]["cursor_advanced_frames"]["p95"] == 47.0
    assert result["metrics"]["cursor_remaining_after_frames"]["p95"] == 0.0
    assert result["safety"]["unsafe_field_counts"] == {}
    assert result["issues"] == []
    assert (
        result["decision"]
        == "investigate_post_capture_callback_subscription_cursor"
    )


def test_audio_bus_subscription_backlog_can_fail_on_backlog_ratio(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_record(), _fresh_record()])

    result = validate_audio_bus_subscription_backlog(
        log_path=log_path,
        require_records=True,
        require_backlog_records=True,
        max_backlog_ratio=0.2,
        fail_on_backlog=True,
    )

    assert result["accepted"] is False
    assert "audio_bus_subscription_backlog_ratio_above_threshold" in result["issues"]


def test_audio_bus_subscription_backlog_rejects_missing_records_when_required(
    tmp_path: Path,
) -> None:
    result = validate_audio_bus_subscription_backlog(
        log_path=tmp_path / "missing.jsonl",
        require_records=True,
    )

    assert result["accepted"] is False
    assert "log_file_missing" in result["issues"]


def test_audio_bus_subscription_backlog_rejects_missing_backlog_when_required(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_fresh_record()])

    result = validate_audio_bus_subscription_backlog(
        log_path=log_path,
        require_records=True,
        require_backlog_records=True,
    )

    assert result["accepted"] is False
    assert "audio_bus_subscription_backlog_records_missing" in result["issues"]


def test_audio_bus_subscription_backlog_rejects_unsafe_observe_only_fields(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    record = _record()
    record["action_executed"] = True
    _write_log(log_path, [record])

    result = validate_audio_bus_subscription_backlog(
        log_path=log_path,
        require_records=True,
        require_backlog_records=True,
    )

    assert result["accepted"] is False
    assert "unsafe_observe_only_fields_present" in result["issues"]
    assert result["safety"]["unsafe_field_counts"]["action_executed"] == 1


def test_audio_bus_subscription_backlog_cli_accepts_safe_log(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_record(), _fresh_record()])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-backlog-records",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["backlog_records"] == 1


def test_audio_bus_subscription_backlog_cli_fails_on_backlog_gate(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_record(), _fresh_record()])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-backlog-records",
            "--max-backlog-ratio",
            "0.2",
            "--fail-on-backlog",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "audio_bus_subscription_backlog_ratio_above_threshold" in payload["issues"]
