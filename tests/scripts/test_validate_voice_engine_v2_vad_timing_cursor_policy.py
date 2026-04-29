from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_vad_timing_cursor_policy import (
    CATEGORY_CAPTURE_WINDOW_READINESS_CANDIDATE,
    CATEGORY_POST_CAPTURE_CALLBACK_ONLY_BACKLOG,
    CATEGORY_POST_CAPTURE_DIAGNOSTIC_ONLY,
    main,
    validate_vad_timing_cursor_policy,
)


def _write_log(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _attempt_ready() -> dict[str, object]:
    return {
        "attempt_stage": "vosk_shadow_invocation_attempt",
        "attempt_version": "vosk_shadow_invocation_attempt_v1",
        "enabled": True,
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
    }


def _capture_window_record(
    *,
    stale_audio_observed: bool = False,
    include_capture_window_source: bool = True,
) -> dict[str, object]:
    frame_source_counts: dict[str, int] = {"faster_whisper_callback_shadow_tap": 21}
    if include_capture_window_source:
        frame_source_counts["faster_whisper_capture_window_shadow_tap"] = 26

    return {
        "hook": "capture_window_pre_transcription",
        "turn_id": "turn-capture-window",
        "phase": "command",
        "capture_mode": "wake_command",
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "vad_shadow": {
            "stale_audio_observed": stale_audio_observed,
            "cadence_diagnostic_reason": "fresh_audio_backlog_observed",
            "pcm_profile_signal_level": "high",
            "frame_source_counts": frame_source_counts,
        },
        "metadata": {
            "vosk_shadow_invocation_attempt": _attempt_ready(),
        },
    }


def _post_capture_record(*, include_attempt: bool = False) -> dict[str, object]:
    metadata: dict[str, object] = {}
    if include_attempt:
        metadata["vosk_shadow_invocation_attempt"] = _attempt_ready()

    return {
        "hook": "post_capture",
        "turn_id": "turn-post-capture",
        "phase": "command",
        "capture_mode": "wake_command",
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "vad_shadow": {
            "stale_audio_observed": True,
            "cadence_diagnostic_reason": "stale_audio_backlog_observed",
            "pcm_profile_signal_level": "near_silent",
            "frame_source_counts": {"faster_whisper_callback_shadow_tap": 46},
        },
        "metadata": metadata,
    }


def test_cursor_policy_accepts_capture_window_readiness_and_post_capture_diagnostic(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_capture_window_record(), _post_capture_record()])

    result = validate_vad_timing_cursor_policy(
        log_path=log_path,
        require_records=True,
        require_readiness_candidates=True,
    )

    assert result["accepted"] is True
    assert result["capture_window_records"] == 1
    assert result["post_capture_records"] == 1
    assert result["readiness_candidate_records"] == 1
    assert result["accepted_readiness_records"] == 1
    assert result["rejected_readiness_records"] == 0
    assert result["post_capture_diagnostic_records"] == 1
    assert result["post_capture_callback_only_backlog_records"] == 1
    assert result["category_counts"][CATEGORY_CAPTURE_WINDOW_READINESS_CANDIDATE] == 1
    assert result["category_counts"][CATEGORY_POST_CAPTURE_DIAGNOSTIC_ONLY] == 1
    assert result["category_counts"][CATEGORY_POST_CAPTURE_CALLBACK_ONLY_BACKLOG] == 1
    assert result["policy"]["post_capture_is_readiness_proof"] is False
    assert result["safety"]["unsafe_field_counts"] == {}
    assert (
        result["decision"]
        == "use_capture_window_readiness_and_keep_post_capture_diagnostic_only"
    )


def test_cursor_policy_rejects_post_capture_readiness_by_default(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_capture_window_record(), _post_capture_record(include_attempt=True)])

    result = validate_vad_timing_cursor_policy(
        log_path=log_path,
        require_records=True,
        require_readiness_candidates=True,
    )

    assert result["accepted"] is False
    assert result["non_capture_window_readiness_records"] == 1
    assert "non_capture_window_readiness_records_present" in result["issues"]
    assert (
        result["decision"]
        == "reject_post_capture_readiness_before_runtime_changes"
    )


def test_cursor_policy_rejects_stale_capture_window_readiness(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_capture_window_record(stale_audio_observed=True)])

    result = validate_vad_timing_cursor_policy(
        log_path=log_path,
        require_records=True,
        require_readiness_candidates=True,
    )

    assert result["accepted"] is False
    assert result["capture_window_stale_readiness_records"] == 1
    assert "stale_capture_window_readiness_records_present" in result["issues"]


def test_cursor_policy_rejects_missing_capture_window_source_for_readiness(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(
        log_path,
        [_capture_window_record(include_capture_window_source=False)],
    )

    result = validate_vad_timing_cursor_policy(
        log_path=log_path,
        require_records=True,
        require_readiness_candidates=True,
    )

    assert result["accepted"] is False
    assert result["capture_window_missing_source_records"] == 1
    assert "capture_window_readiness_source_missing" in result["issues"]


def test_cursor_policy_rejects_missing_readiness_candidates_when_required(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_post_capture_record()])

    result = validate_vad_timing_cursor_policy(
        log_path=log_path,
        require_records=True,
        require_readiness_candidates=True,
    )

    assert result["accepted"] is False
    assert "accepted_readiness_candidates_missing" in result["issues"]
    assert result["decision"] == "capture_window_readiness_candidates_missing"


def test_cursor_policy_rejects_unsafe_observe_only_fields(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    record = _capture_window_record()
    record["action_executed"] = True
    _write_log(log_path, [record])

    result = validate_vad_timing_cursor_policy(
        log_path=log_path,
        require_records=True,
        require_readiness_candidates=True,
    )

    assert result["accepted"] is False
    assert "unsafe_observe_only_fields_present" in result["issues"]
    assert result["safety"]["unsafe_field_counts"]["action_executed"] == 1


def test_cursor_policy_cli_accepts_capture_window_readiness(
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
            "--require-readiness-candidates",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["accepted_readiness_records"] == 1
