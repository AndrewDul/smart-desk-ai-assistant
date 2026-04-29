from __future__ import annotations

import json
from pathlib import Path

from scripts.run_voice_engine_v2_vosk_shadow_observation import (
    OBSERVATION_FLAGS,
    main,
    prepare_observation,
    restore_observation,
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


def _read_voice_engine(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))["voice_engine"]


def _write_contract_log(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "hook": "capture_window_pre_transcription",
        "metadata": {
            "vosk_live_shadow": {
                "enabled": True,
                "observed": False,
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


def test_prepare_observation_enables_only_observation_flags(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    backup_dir = tmp_path / "backups"
    log_path = tmp_path / "vad_timing.jsonl"
    _write_settings(settings_path)

    result = prepare_observation(
        settings_path=settings_path,
        backup_dir=backup_dir,
        log_path=log_path,
        archive_log=False,
        dry_run=False,
    )

    voice_engine = _read_voice_engine(settings_path)
    assert result["accepted"] is True
    assert result["backup_path"] is not None
    for key, expected_value in OBSERVATION_FLAGS.items():
        assert voice_engine[key] is expected_value

    assert voice_engine["enabled"] is False
    assert voice_engine["mode"] == "legacy"
    assert voice_engine["command_first_enabled"] is False
    assert voice_engine["fallback_to_legacy_enabled"] is True
    assert voice_engine["runtime_candidates_enabled"] is False


def test_prepare_observation_refuses_runtime_takeover_config(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path, voice_engine_overrides={"enabled": True})

    exit_code = main(
        [
            "--prepare",
            "--settings",
            str(settings_path),
            "--backup-dir",
            str(tmp_path / "backups"),
            "--log-path",
            str(tmp_path / "vad_timing.jsonl"),
        ]
    )

    assert exit_code == 2
    voice_engine = _read_voice_engine(settings_path)
    assert voice_engine["enabled"] is True
    assert voice_engine["vosk_live_shadow_contract_enabled"] is False


def test_restore_observation_returns_to_safe_config(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    backup_dir = tmp_path / "backups"
    _write_settings(settings_path, voice_engine_overrides=dict(OBSERVATION_FLAGS))

    result = restore_observation(
        settings_path=settings_path,
        backup_dir=backup_dir,
        dry_run=False,
    )

    voice_engine = _read_voice_engine(settings_path)
    assert result["accepted"] is True
    for key in OBSERVATION_FLAGS:
        assert voice_engine[key] is False

    assert voice_engine["enabled"] is False
    assert voice_engine["mode"] == "legacy"
    assert voice_engine["command_first_enabled"] is False
    assert voice_engine["fallback_to_legacy_enabled"] is True
    assert voice_engine["runtime_candidates_enabled"] is False


def test_validate_observation_log_accepts_attached_waiting_contract(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "vad_timing.jsonl"
    _write_contract_log(log_path)

    exit_code = main(
        [
            "--validate",
            "--log-path",
            str(log_path),
            "--require-contract-attached",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["telemetry"]["live_shadow"]["contract_records"] == 1
    assert payload["telemetry"]["asr_result"]["result_records"] == 0
    assert payload["telemetry"]["live_shadow"]["recognition_attempted_records"] == 0