from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_recognition_permission_contract import (
    main,
    validate_recognition_permission_contract,
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


def _capture_window_record(
    *,
    preflight: dict[str, object] | None = None,
    attempt: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "hook": "capture_window_pre_transcription",
        "turn_id": "turn-permission",
        "phase": "command",
        "capture_mode": "wake_command",
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "vad_shadow": {
            "stale_audio_observed": False,
            "pcm_profile_signal_level": "high",
            "frame_source_counts": {
                "faster_whisper_capture_window_shadow_tap": 26,
                "faster_whisper_callback_shadow_tap": 21,
            },
        },
        "metadata": {
            "vosk_shadow_recognition_preflight": preflight or _preflight(),
            "vosk_shadow_invocation_attempt": attempt or _attempt(),
        },
    }


def test_permission_contract_accepts_blocked_capture_window_contract(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_capture_window_record()])

    result = validate_recognition_permission_contract(
        log_path=log_path,
        require_records=True,
        require_permission_contracts=True,
    )

    assert result["accepted"] is True
    assert result["permission_contract_records"] == 1
    assert result["blocked_permission_records"] == 1
    assert result["permission_grant_records"] == 0
    assert result["unsafe_permission_records"] == 0
    assert result["missing_preflight_records"] == 0
    assert result["decision"] == "recognition_permission_contract_blocked_and_ready"
    assert result["readiness"]["accepted"] is True
    assert result["safety"]["unsafe_field_counts"] == {}


def test_permission_contract_rejects_permission_grant(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(
        log_path,
        [
            _capture_window_record(
                attempt=_attempt(
                    recognition_allowed=True,
                    recognition_invocation_allowed=True,
                )
            )
        ],
    )

    result = validate_recognition_permission_contract(
        log_path=log_path,
        require_records=True,
        require_permission_contracts=True,
    )

    assert result["accepted"] is False
    assert result["permission_grant_records"] == 1
    assert "recognition_permission_granted" in result["issues"]
    assert "unsafe_recognition_permission_records_present" in result["issues"]
    assert result["unsafe_field_counts"]["recognition_allowed"] == 1


def test_permission_contract_rejects_missing_preflight(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    record = _capture_window_record()
    metadata = record["metadata"]
    assert isinstance(metadata, dict)
    metadata.pop("vosk_shadow_recognition_preflight")

    _write_log(log_path, [record])

    result = validate_recognition_permission_contract(
        log_path=log_path,
        require_records=True,
        require_permission_contracts=True,
    )

    assert result["accepted"] is False
    assert result["missing_preflight_records"] == 1
    assert "recognition_preflight_missing_for_permission_contract" in result["issues"]


def test_permission_contract_rejects_missing_records_when_required(
    tmp_path: Path,
) -> None:
    result = validate_recognition_permission_contract(
        log_path=tmp_path / "missing.jsonl",
        require_records=True,
        require_permission_contracts=True,
    )

    assert result["accepted"] is False
    assert "log_file_missing" in result["issues"]


def test_permission_contract_rejects_missing_contracts_when_required(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    record = _capture_window_record()
    metadata = record["metadata"]
    assert isinstance(metadata, dict)
    metadata.pop("vosk_shadow_invocation_attempt")
    _write_log(log_path, [record])

    result = validate_recognition_permission_contract(
        log_path=log_path,
        require_records=True,
        require_permission_contracts=True,
    )

    assert result["accepted"] is False
    assert "blocked_recognition_permission_contracts_missing" in result["issues"]


def test_permission_contract_cli_accepts_blocked_contract(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_log(log_path, [_capture_window_record()])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-permission-contracts",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["blocked_permission_records"] == 1
