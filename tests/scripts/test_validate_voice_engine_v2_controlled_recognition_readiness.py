from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_controlled_recognition_readiness import (
    main,
    validate_controlled_recognition_readiness,
)


def _write_log(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _preflight(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "preflight_ready": True,
        "recognition_allowed": False,
        "recognition_blocked": True,
        "reason": "recognition_invocation_blocked_by_stage_policy",
        "recognition_invocation_allowed": False,
        "recognition_invocation_performed": False,
        "recognition_attempted": False,
        "result_present": False,
        "recognized": False,
        "command_matched": False,
        "raw_pcm_included": False,
        "pcm_retrieval_performed": False,
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


def _attempt(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "attempt_ready": True,
        "invocation_allowed": False,
        "invocation_blocked": True,
        "reason": "recognition_invocation_blocked_by_stage_policy",
        "recognition_allowed": False,
        "recognition_invocation_allowed": False,
        "recognition_invocation_performed": False,
        "recognition_attempted": False,
        "result_present": False,
        "recognized": False,
        "command_matched": False,
        "raw_pcm_included": False,
        "pcm_retrieval_performed": False,
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
    *,
    phase: str = "command",
    capture_mode: str = "wake_command",
    stale_audio_observed: bool = False,
    capture_window_source_frames: int = 24,
    preflight: dict[str, object] | None = None,
    attempt: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "hook": "capture_window_pre_transcription",
        "turn_id": f"turn-{phase}-{capture_mode}",
        "phase": phase,
        "capture_mode": capture_mode,
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
                "faster_whisper_callback_shadow_tap": 21,
            },
        },
        "metadata": {
            "vosk_shadow_recognition_preflight": preflight or _preflight(),
            "vosk_shadow_invocation_attempt": attempt or _attempt(),
        },
    }


def test_controlled_recognition_readiness_accepts_command_only_candidates(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(
        log_path,
        [
            _record(),
            _record(phase="follow_up", capture_mode="follow_up"),
        ],
    )

    result = validate_controlled_recognition_readiness(
        log_path=log_path,
        require_records=True,
        require_command_candidates=True,
    )

    assert result["accepted"] is True
    assert result["command_candidate_records"] == 1
    assert result["follow_up_candidate_records"] == 1
    assert result["safe_command_candidate_records"] == 1
    assert result["rejected_command_candidate_records"] == 0
    assert result["permission"]["accepted"] is True
    assert (
        result["decision"]
        == "future_controlled_recognition_preconditions_ready_but_current_stage_blocked"
    )
    assert result["policy"]["current_stage_recognition_invocation_allowed"] is False


def test_controlled_recognition_readiness_rejects_missing_command_candidates(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_record(phase="follow_up", capture_mode="follow_up")])

    result = validate_controlled_recognition_readiness(
        log_path=log_path,
        require_records=True,
        require_command_candidates=True,
    )

    assert result["accepted"] is False
    assert result["command_candidate_records"] == 0
    assert "safe_command_recognition_candidates_missing" in result["issues"]


def test_controlled_recognition_readiness_rejects_permission_grant(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(
        log_path,
        [
            _record(
                attempt=_attempt(
                    recognition_allowed=True,
                    recognition_invocation_allowed=True,
                )
            )
        ],
    )

    result = validate_controlled_recognition_readiness(
        log_path=log_path,
        require_records=True,
        require_command_candidates=True,
    )

    assert result["accepted"] is False
    assert "recognition_permission_contract_not_accepted" in result["issues"]
    assert "recognition_allowed_must_be_false" in result["rejection_reason_counts"]
    assert result["unsafe_field_counts"]["recognition_allowed"] == 1


def test_controlled_recognition_readiness_rejects_stale_command_candidate(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_record(stale_audio_observed=True)])

    result = validate_controlled_recognition_readiness(
        log_path=log_path,
        require_records=True,
        require_command_candidates=True,
    )

    assert result["accepted"] is False
    assert "rejected_command_recognition_candidates_present" in result["issues"]
    assert "stale_audio_observed_must_be_false" in result["rejection_reason_counts"]


def test_controlled_recognition_readiness_rejects_missing_capture_window_source(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_record(capture_window_source_frames=0)])

    result = validate_controlled_recognition_readiness(
        log_path=log_path,
        require_records=True,
        require_command_candidates=True,
    )

    assert result["accepted"] is False
    assert "capture_window_source_frames_missing" in result["rejection_reason_counts"]


def test_controlled_recognition_readiness_rejects_missing_records_when_required(
    tmp_path: Path,
) -> None:
    result = validate_controlled_recognition_readiness(
        log_path=tmp_path / "missing.jsonl",
        require_records=True,
        require_command_candidates=True,
    )

    assert result["accepted"] is False
    assert "log_file_missing" in result["issues"]


def test_controlled_recognition_readiness_cli_accepts_command_candidate(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_record()])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-command-candidates",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["safe_command_candidate_records"] == 1
