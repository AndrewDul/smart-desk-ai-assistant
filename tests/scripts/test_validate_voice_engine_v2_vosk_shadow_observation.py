from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_vosk_shadow_observation import (
    main,
    validate_vosk_shadow_observation,
)


def _write_settings(
    path: Path,
    *,
    voice_engine_overrides: dict[str, object] | None = None,
) -> None:
    voice_engine = {
        "enabled": False,
        "mode": "legacy",
        "command_first_enabled": False,
        "fallback_to_legacy_enabled": True,
        "runtime_candidates_enabled": False,
        "pre_stt_shadow_enabled": False,
        "faster_whisper_audio_bus_tap_enabled": False,
        "vad_shadow_enabled": False,
        "vad_timing_bridge_enabled": False,
        "command_asr_shadow_bridge_enabled": False,
        "vosk_live_shadow_contract_enabled": False,
    }
    if voice_engine_overrides:
        voice_engine.update(voice_engine_overrides)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"voice_engine": voice_engine}, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_contract_log(path: Path, *, observed: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "hook": "capture_window_pre_transcription",
        "metadata": {
            "vosk_live_shadow": {
                "enabled": True,
                "observed": observed,
                "reason": "vosk_live_shadow_result_missing",
                "recognition_attempted": False,
                "recognized": False,
                "command_matched": False,
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
        },
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def test_validator_accepts_restored_config_and_attached_contract(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    log_path = tmp_path / "vad_timing.jsonl"
    _write_settings(settings_path)
    _write_contract_log(log_path)

    result = validate_vosk_shadow_observation(
        settings_path=settings_path,
        log_path=log_path,
        require_contract_attached=True,
        require_restored_config=True,
    )

    assert result["accepted"] is True
    assert result["config"]["accepted"] is True
    assert result["telemetry"]["contract_records"] == 1
    assert result["issues"] == []


def test_validator_rejects_active_observation_flag_after_restore(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    log_path = tmp_path / "vad_timing.jsonl"
    _write_settings(
        settings_path,
        voice_engine_overrides={"vosk_live_shadow_contract_enabled": True},
    )
    _write_contract_log(log_path)

    result = validate_vosk_shadow_observation(
        settings_path=settings_path,
        log_path=log_path,
        require_contract_attached=True,
        require_restored_config=True,
    )

    assert result["accepted"] is False
    assert (
        "config:voice_engine.vosk_live_shadow_contract_enabled_must_be_false_after_observation"
        in result["issues"]
    )


def test_validator_can_allow_active_observation_config_before_restore(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.json"
    log_path = tmp_path / "vad_timing.jsonl"
    _write_settings(
        settings_path,
        voice_engine_overrides={"vosk_live_shadow_contract_enabled": True},
    )
    _write_contract_log(log_path)

    result = validate_vosk_shadow_observation(
        settings_path=settings_path,
        log_path=log_path,
        require_contract_attached=True,
        require_restored_config=False,
    )

    assert result["accepted"] is True


def test_validator_rejects_observed_recognition_shape(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    log_path = tmp_path / "vad_timing.jsonl"
    _write_settings(settings_path)
    _write_contract_log(log_path, observed=True)

    result = validate_vosk_shadow_observation(
        settings_path=settings_path,
        log_path=log_path,
        require_contract_attached=True,
        require_restored_config=True,
    )

    assert result["accepted"] is False
    assert "telemetry:line_1:contract_observed" in result["issues"]


def test_cli_returns_zero_for_valid_observation(tmp_path: Path, capsys) -> None:
    settings_path = tmp_path / "settings.json"
    log_path = tmp_path / "vad_timing.jsonl"
    _write_settings(settings_path)
    _write_contract_log(log_path)

    exit_code = main(
        [
            "--settings",
            str(settings_path),
            "--log-path",
            str(log_path),
            "--require-contract-attached",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["validator"] == "vosk_shadow_observation"