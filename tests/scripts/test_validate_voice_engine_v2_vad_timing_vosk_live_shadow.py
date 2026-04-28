from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_vad_timing_vosk_live_shadow import (
    main,
    validate_vad_timing_vosk_live_shadow_log,
)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _record_with_contract(**contract_overrides: object) -> dict[str, object]:
    contract = {
        "contract_stage": "vosk_live_shadow_contract",
        "contract_version": "vosk_live_shadow_contract_v1",
        "enabled": True,
        "observed": False,
        "reason": "vosk_live_shadow_result_missing",
        "metadata_key": "vosk_live_shadow",
        "input_source": "existing_command_audio_segment",
        "recognizer_name": "vosk_command_asr_shadow",
        "recognizer_enabled": False,
        "recognition_attempted": False,
        "recognized": False,
        "transcript": "",
        "normalized_text": "",
        "language": None,
        "confidence": None,
        "alternatives": [],
        "command_matched": False,
        "command_intent_key": None,
        "command_language": None,
        "command_matched_phrase": None,
        "command_confidence": None,
        "command_alternatives": [],
        "runtime_integration": False,
        "command_execution_enabled": False,
        "faster_whisper_bypass_enabled": False,
        "microphone_stream_started": False,
        "independent_microphone_stream_started": False,
        "live_command_recognition_enabled": False,
        "raw_pcm_included": False,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }
    contract.update(contract_overrides)

    return {
        "hook": "capture_window_pre_transcription",
        "metadata": {
            "command_asr_shadow_bridge": {
                "enabled": True,
                "observed": True,
            },
            "vosk_live_shadow": contract,
        },
        "legacy_runtime_primary": True,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }


def test_validator_accepts_enabled_waiting_contract_shape(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record_with_contract()])

    result = validate_vad_timing_vosk_live_shadow_log(
        log_path=log_path,
        require_records=True,
        require_contract_attached=True,
    )

    assert result["accepted"] is True
    assert result["records"] == 1
    assert result["contract_records"] == 1
    assert result["enabled_contract_records"] == 1
    assert result["observed_contract_records"] == 0
    assert result["recognition_attempted_records"] == 0
    assert result["recognized_records"] == 0
    assert result["command_matched_records"] == 0
    assert result["unsafe_action_records"] == 0
    assert result["unsafe_microphone_records"] == 0
    assert result["unsafe_independent_microphone_records"] == 0
    assert result["unsafe_live_command_records"] == 0
    assert result["raw_pcm_records"] == 0
    assert result["issues"] == []


def test_validator_rejects_missing_required_contract(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(
        log_path,
        [
            {
                "hook": "capture_window_pre_transcription",
                "metadata": {},
                "legacy_runtime_primary": True,
            }
        ],
    )

    result = validate_vad_timing_vosk_live_shadow_log(
        log_path=log_path,
        require_records=True,
        require_contract_attached=True,
    )

    assert result["accepted"] is False
    assert "vosk_live_shadow_records_missing" in result["issues"]


def test_validator_rejects_recognition_without_explicit_allowance(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(
        log_path,
        [
            _record_with_contract(
                observed=True,
                recognition_attempted=True,
                recognized=True,
                transcript="show desktop",
            )
        ],
    )

    result = validate_vad_timing_vosk_live_shadow_log(log_path=log_path)

    assert result["accepted"] is False
    assert "line_1:contract_observed" in result["issues"]
    assert "line_1:recognition_attempted" in result["issues"]
    assert "line_1:recognized" in result["issues"]


def test_validator_rejects_unsafe_flags(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(
        log_path,
        [
            _record_with_contract(
                command_execution_enabled=True,
                microphone_stream_started=True,
                independent_microphone_stream_started=True,
                runtime_takeover=True,
            )
        ],
    )

    result = validate_vad_timing_vosk_live_shadow_log(log_path=log_path)

    assert result["accepted"] is False
    assert "line_1:action_executed" not in result["issues"]
    assert "line_1:microphone_stream_started" in result["issues"]
    assert "line_1:independent_microphone_stream_started" in result["issues"]
    assert "line_1:runtime_takeover" in result["issues"]


def test_cli_returns_zero_for_valid_contract_log(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [_record_with_contract()])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-contract-attached",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["contract_records"] == 1


def test_cli_returns_one_for_missing_required_contract(tmp_path: Path, capsys) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_jsonl(log_path, [{"hook": "capture_window_pre_transcription", "metadata": {}}])

    exit_code = main(
        [
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-contract-attached",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["accepted"] is False
    assert "vosk_live_shadow_records_missing" in payload["issues"]