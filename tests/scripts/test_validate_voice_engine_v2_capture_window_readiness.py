from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_capture_window_readiness import (
    main,
    validate_capture_window_readiness,
)


def _write_log(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _attempt_ready(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "attempt_ready": True,
        "invocation_allowed": False,
        "invocation_blocked": True,
        "reason": "recognition_invocation_blocked_by_stage_policy",
        "recognition_invocation_performed": False,
        "recognition_attempted": False,
        "result_present": False,
        "raw_pcm_included": False,
        "action_executed": False,
        "runtime_takeover": False,
        "faster_whisper_bypass_enabled": False,
        "independent_microphone_stream_started": False,
        "live_command_recognition_enabled": False,
    }
    payload.update(overrides)
    return payload


def _capture_window_record(
    *,
    attempt: dict[str, object] | None = None,
    stale_audio_observed: bool = False,
    capture_window_source_frames: int = 26,
    callback_source_frames: int = 21,
) -> dict[str, object]:
    return {
        "hook": "capture_window_pre_transcription",
        "turn_id": "turn-readiness",
        "phase": "command",
        "capture_mode": "wake_command",
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "vad_shadow": {
            "stale_audio_observed": stale_audio_observed,
            "pcm_profile_signal_level": "high",
            "frame_source_counts": {
                "faster_whisper_capture_window_shadow_tap": (
                    capture_window_source_frames
                ),
                "faster_whisper_callback_shadow_tap": callback_source_frames,
            },
        },
        "metadata": {
            "vosk_shadow_invocation_attempt": attempt or _attempt_ready(),
        },
    }


def _post_capture_record() -> dict[str, object]:
    return {
        "hook": "post_capture",
        "turn_id": "turn-post",
        "phase": "command",
        "capture_mode": "wake_command",
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "vad_shadow": {
            "stale_audio_observed": True,
            "pcm_profile_signal_level": "near_silent",
            "frame_source_counts": {
                "faster_whisper_callback_shadow_tap": 46,
            },
        },
        "metadata": {},
    }


def test_capture_window_readiness_accepts_safe_readiness_records(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_capture_window_record(), _post_capture_record()])

    result = validate_capture_window_readiness(
        log_path=log_path,
        require_records=True,
        require_readiness_records=True,
    )

    assert result["accepted"] is True
    assert result["records"] == 2
    assert result["capture_window_records"] == 1
    assert result["readiness_records"] == 1
    assert result["safe_readiness_records"] == 1
    assert result["rejected_readiness_records"] == 0
    assert result["stale_readiness_records"] == 0
    assert result["missing_capture_source_records"] == 0
    assert result["metrics"]["capture_window_source_frames"]["p95"] == 26.0
    assert result["metrics"]["callback_source_frames"]["p95"] == 21.0
    assert result["decision"] == "capture_window_readiness_summary_ready"
    assert result["safety"]["unsafe_field_counts"] == {}


def test_capture_window_readiness_rejects_unsafe_attempt(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(
        log_path,
        [
            _capture_window_record(
                attempt=_attempt_ready(
                    recognition_invocation_performed=True,
                    recognition_attempted=True,
                )
            )
        ],
    )

    result = validate_capture_window_readiness(
        log_path=log_path,
        require_records=True,
        require_readiness_records=True,
    )

    assert result["accepted"] is False
    assert result["safe_readiness_records"] == 0
    assert result["rejected_readiness_records"] == 1
    assert "rejected_capture_window_readiness_records_present" in result["issues"]
    assert (
        "recognition_invocation_performed_must_be_false"
        in result["rejection_reason_counts"]
    )


def test_capture_window_readiness_rejects_stale_readiness(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_capture_window_record(stale_audio_observed=True)])

    result = validate_capture_window_readiness(
        log_path=log_path,
        require_records=True,
        require_readiness_records=True,
    )

    assert result["accepted"] is False
    assert result["stale_readiness_records"] == 1
    assert "rejected_capture_window_readiness_records_present" in result["issues"]
    assert "stale_audio_observed_must_be_false" in result["rejection_reason_counts"]


def test_capture_window_readiness_rejects_missing_capture_window_source(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_capture_window_record(capture_window_source_frames=0)])

    result = validate_capture_window_readiness(
        log_path=log_path,
        require_records=True,
        require_readiness_records=True,
    )

    assert result["accepted"] is False
    assert result["missing_capture_source_records"] == 1
    assert (
        "capture_window_source_frames_missing"
        in result["rejection_reason_counts"]
    )


def test_capture_window_readiness_rejects_missing_records_when_required(
    tmp_path: Path,
) -> None:
    result = validate_capture_window_readiness(
        log_path=tmp_path / "missing.jsonl",
        require_records=True,
        require_readiness_records=True,
    )

    assert result["accepted"] is False
    assert "log_file_missing" in result["issues"]


def test_capture_window_readiness_rejects_missing_readiness_when_required(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_post_capture_record()])

    result = validate_capture_window_readiness(
        log_path=log_path,
        require_records=True,
        require_readiness_records=True,
    )

    assert result["accepted"] is False
    assert "safe_capture_window_readiness_records_missing" in result["issues"]


def test_capture_window_readiness_rejects_unsafe_record_fields(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    record = _capture_window_record()
    record["action_executed"] = True
    _write_log(log_path, [record])

    result = validate_capture_window_readiness(
        log_path=log_path,
        require_records=True,
        require_readiness_records=True,
    )

    assert result["accepted"] is False
    assert "unsafe_observe_only_fields_present" in result["issues"]
    assert result["safety"]["unsafe_field_counts"]["action_executed"] == 1


def test_capture_window_readiness_cli_accepts_safe_log(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_capture_window_record(), _post_capture_record()])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-readiness-records",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["safe_readiness_records"] == 1
