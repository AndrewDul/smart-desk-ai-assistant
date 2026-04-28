from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_command_readiness import (
    main,
    validate_command_readiness_log,
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
        "speech_score_max": 0.99,
        "capture_finished_to_vad_observed_ms": 228.0,
        "capture_window_publish_to_vad_observed_ms": 226.0,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }
    payload.update(overrides)
    return payload


def _record(
    candidate: dict[str, object] | None,
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


def test_validate_command_readiness_log_accepts_ready_record(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(log_path, [_record(_candidate())])

    result = validate_command_readiness_log(
        log_path=log_path,
        require_readiness_records=True,
        require_ready=True,
        require_no_not_ready=True,
    )

    assert result["accepted"] is True
    assert result["readiness_records"] == 1
    assert result["ready_records"] == 1
    assert result["not_ready_records"] == 0
    assert result["readiness_reason_counts"] == {
        "ready_for_command_recognition": 1
    }
    assert result["hook_counts"] == {"capture_window_pre_transcription": 1}
    assert result["source_counts"] == {
        "faster_whisper_capture_window_shadow_tap": 1
    }
    assert result["publish_stage_counts"] == {"before_transcription": 1}
    assert result["candidate_reason_counts"] == {"endpoint_detected": 1}
    assert result["max_speech_score"] == 0.99
    assert result["max_frames_processed"] == 7
    assert result["max_capture_finished_to_vad_observed_ms"] == 228.0
    assert result["max_capture_window_publish_to_vad_observed_ms"] == 226.0
    assert result["max_capture_finished_to_vad_observed_ms_threshold"] == 750.0
    assert result["unsafe_action_records"] == 0
    assert result["unsafe_full_stt_records"] == 0
    assert result["unsafe_takeover_records"] == 0
    assert result["issues"] == []


def test_validate_command_readiness_log_allows_not_ready_when_not_required(
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

    result = validate_command_readiness_log(
        log_path=log_path,
        require_readiness_records=True,
        require_ready=False,
        require_no_not_ready=False,
    )

    assert result["accepted"] is True
    assert result["readiness_records"] == 1
    assert result["ready_records"] == 0
    assert result["not_ready_records"] == 1
    assert result["readiness_reason_counts"] == {
        "not_ready:endpoint_detected": 1
    }


def test_validate_command_readiness_log_fails_when_ready_required_but_missing(
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

    result = validate_command_readiness_log(
        log_path=log_path,
        require_readiness_records=True,
        require_ready=True,
    )

    assert result["accepted"] is False
    assert result["ready_records"] == 0
    assert "command_readiness_ready_records_missing" in result["issues"]


def test_validate_command_readiness_log_fails_when_no_not_ready_required(
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

    result = validate_command_readiness_log(
        log_path=log_path,
        require_readiness_records=True,
        require_ready=True,
        require_no_not_ready=True,
    )

    assert result["accepted"] is False
    assert result["ready_records"] == 1
    assert result["not_ready_records"] == 1
    assert "command_readiness_not_ready_records_present" in result["issues"]


def test_validate_command_readiness_log_fails_on_unsafe_top_level_record(
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

    result = validate_command_readiness_log(log_path=log_path)

    assert result["accepted"] is False
    assert any(
        "unsafe_readiness" in issue and "must never execute actions" in issue
        for issue in result["issues"]
    )


def test_cli_returns_zero_for_ready_log(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(log_path, [_record(_candidate())])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-readiness-records",
            "--require-ready",
            "--require-no-not-ready",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["ready_records"] == 1


def test_cli_returns_one_when_readiness_records_missing(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(log_path, [_record(None)])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-readiness-records",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "command_readiness_records_missing" in payload["issues"]



def test_validate_command_readiness_log_rejects_latency_above_threshold(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    _write_jsonl(
        log_path,
        [
            _record(
                _candidate(
                    capture_finished_to_vad_observed_ms=228.0,
                )
            )
        ],
    )

    result = validate_command_readiness_log(
        log_path=log_path,
        require_readiness_records=True,
        require_ready=True,
        max_capture_finished_to_vad_observed_ms=100.0,
    )

    assert result["accepted"] is False
    assert result["readiness_records"] == 1
    assert result["ready_records"] == 0
    assert result["not_ready_records"] == 1
    assert result["max_capture_finished_to_vad_observed_ms"] == 228.0
    assert result["max_capture_finished_to_vad_observed_ms_threshold"] == 100.0
    assert result["readiness_reason_counts"] == {
        "not_ready:latency_ready": 1
    }
    assert "command_readiness_ready_records_missing" in result["issues"]