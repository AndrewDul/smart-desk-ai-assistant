from __future__ import annotations

import json
from pathlib import Path

from modules.runtime.voice_engine_v2.command_asr_shadow_bridge import (
    CommandAsrShadowBridgeSettings,
    enrich_record_with_command_asr_shadow,
)
from scripts.run_voice_engine_v2_stage24w_observation import (
    enable_stage24w_observation,
    main,
    restore_stage24w_observation,
    status_stage24w_observation,
    validate_stage24w_observation,
)


def _write_settings(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "voice_engine": {
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
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _read_settings(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _endpointing_candidate(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "hook": "capture_window_pre_transcription",
        "candidate_present": True,
        "endpoint_detected": True,
        "reason": "endpoint_detected",
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "frames_processed": 47,
        "speech_score_max": 0.99,
        "capture_finished_to_vad_observed_ms": 228.0,
        "capture_window_publish_to_vad_observed_ms": 226.0,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
    }
    payload.update(overrides)
    return payload


def _capture_window(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source": "faster_whisper_capture_window_shadow_tap",
        "publish_stage": "before_transcription",
        "sample_rate": 16_000,
        "channels": 1,
        "audio_sample_count": 32_000,
        "audio_duration_seconds": 2.0,
        "published_frame_count": 32,
        "published_byte_count": 64_000,
        "capture_finished_to_publish_start_ms": 10.0,
    }
    payload.update(overrides)
    return payload


def _vad_timing_record() -> dict[str, object]:
    return {
        "timestamp_utc": "2026-04-28T00:00:00+00:00",
        "timestamp_monotonic": 1000.0,
        "enabled": True,
        "observed": True,
        "reason": "vad_timing_bridge_pre_transcription_observed_audio",
        "hook": "capture_window_pre_transcription",
        "turn_id": "turn-stage24w-observation",
        "phase": "command",
        "capture_mode": "wake_command",
        "legacy_runtime_primary": True,
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "transcript_present": False,
        "vad_shadow": {},
        "metadata": {
            "capture_window_shadow_tap": _capture_window(),
            "endpointing_candidate": _endpointing_candidate(),
        },
    }


def _enriched_vad_timing_record() -> dict[str, object]:
    return enrich_record_with_command_asr_shadow(
        record=_vad_timing_record(),
        settings=CommandAsrShadowBridgeSettings(enabled=True),
    )


def test_enable_stage24w_observation_writes_backup_and_enables_observe_only_flags(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "config" / "settings.json"
    backup_path = tmp_path / "var" / "data" / "stage24w_backup.json"
    _write_settings(settings_path)

    result = enable_stage24w_observation(
        settings_path=settings_path,
        backup_path=backup_path,
    )

    settings = _read_settings(settings_path)
    voice_engine = settings["voice_engine"]

    assert result["accepted"] is True
    assert backup_path.exists()

    assert voice_engine["enabled"] is False
    assert voice_engine["mode"] == "legacy"
    assert voice_engine["command_first_enabled"] is False
    assert voice_engine["fallback_to_legacy_enabled"] is True
    assert voice_engine["runtime_candidates_enabled"] is False

    assert voice_engine["pre_stt_shadow_enabled"] is True
    assert voice_engine["faster_whisper_audio_bus_tap_enabled"] is True
    assert voice_engine["vad_shadow_enabled"] is True
    assert voice_engine["vad_timing_bridge_enabled"] is True
    assert voice_engine["command_asr_shadow_bridge_enabled"] is True


def test_enable_stage24w_observation_refuses_existing_backup_without_overwrite(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "config" / "settings.json"
    backup_path = tmp_path / "var" / "data" / "stage24w_backup.json"
    _write_settings(settings_path)

    first = enable_stage24w_observation(
        settings_path=settings_path,
        backup_path=backup_path,
    )
    second = enable_stage24w_observation(
        settings_path=settings_path,
        backup_path=backup_path,
    )

    assert first["accepted"] is True
    assert second["accepted"] is False
    assert second["issues"] == ["backup_already_exists"]


def test_restore_stage24w_observation_restores_backup_and_disables_observation_flags(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "config" / "settings.json"
    backup_path = tmp_path / "var" / "data" / "stage24w_backup.json"
    _write_settings(settings_path)

    enable_stage24w_observation(
        settings_path=settings_path,
        backup_path=backup_path,
    )
    result = restore_stage24w_observation(
        settings_path=settings_path,
        backup_path=backup_path,
    )

    settings = _read_settings(settings_path)
    voice_engine = settings["voice_engine"]

    assert result["accepted"] is True
    assert result["backup_used"] is True

    assert voice_engine["enabled"] is False
    assert voice_engine["mode"] == "legacy"
    assert voice_engine["command_first_enabled"] is False
    assert voice_engine["fallback_to_legacy_enabled"] is True
    assert voice_engine["runtime_candidates_enabled"] is False

    assert voice_engine["pre_stt_shadow_enabled"] is False
    assert voice_engine["faster_whisper_audio_bus_tap_enabled"] is False
    assert voice_engine["vad_shadow_enabled"] is False
    assert voice_engine["vad_timing_bridge_enabled"] is False
    assert voice_engine["command_asr_shadow_bridge_enabled"] is False


def test_status_stage24w_observation_reports_backup_and_log_state(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "config" / "settings.json"
    backup_path = tmp_path / "var" / "data" / "stage24w_backup.json"
    log_path = tmp_path / "var" / "data" / "voice_engine_v2_vad_timing_bridge.jsonl"
    _write_settings(settings_path)

    result = status_stage24w_observation(
        settings_path=settings_path,
        backup_path=backup_path,
        log_path=log_path,
    )

    assert result["accepted"] is True
    assert result["backup_exists"] is False
    assert result["log_exists"] is False
    assert result["voice_engine_snapshot"]["enabled"] is False
    assert result["voice_engine_snapshot"]["vad_timing_bridge_enabled"] is False
    assert (
        result["voice_engine_snapshot"]["command_asr_shadow_bridge_enabled"]
        is False
    )


def test_validate_stage24w_observation_accepts_embedded_shadow_records(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "voice_engine_v2_vad_timing_bridge.jsonl"
    _write_jsonl(log_path, [_enriched_vad_timing_record()])

    result = validate_stage24w_observation(log_path=log_path)

    assert result["accepted"] is True
    assert result["stage"] == "24W"
    assert result["expected_runtime_mode"] == "legacy_observe_only"
    assert result["bridge_records"] == 1
    assert result["candidate_attached_records"] == 1
    assert result["recognizer_enabled_records"] == 0
    assert result["recognition_attempted_records"] == 0
    assert result["recognized_records"] == 0
    assert result["issues"] == []


def test_validate_stage24w_observation_fails_when_log_missing(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "missing.jsonl"

    result = validate_stage24w_observation(log_path=log_path)

    assert result["accepted"] is False
    assert f"log_missing:{log_path}" in result["issues"]


def test_cli_enable_and_restore(tmp_path: Path, capsys) -> None:
    settings_path = tmp_path / "config" / "settings.json"
    backup_path = tmp_path / "var" / "data" / "stage24w_backup.json"
    _write_settings(settings_path)

    enable_exit = main(
        [
            "enable",
            "--settings-path",
            str(settings_path),
            "--backup-path",
            str(backup_path),
        ]
    )
    enable_output = json.loads(capsys.readouterr().out)

    restore_exit = main(
        [
            "restore",
            "--settings-path",
            str(settings_path),
            "--backup-path",
            str(backup_path),
        ]
    )
    restore_output = json.loads(capsys.readouterr().out)

    assert enable_exit == 0
    assert enable_output["accepted"] is True
    assert restore_exit == 0
    assert restore_output["accepted"] is True

    settings = _read_settings(settings_path)
    voice_engine = settings["voice_engine"]

    assert voice_engine["vad_timing_bridge_enabled"] is False
    assert voice_engine["command_asr_shadow_bridge_enabled"] is False


def test_cli_validate_returns_zero_for_valid_shadow_records(
    tmp_path: Path,
    capsys,
) -> None:
    log_path = tmp_path / "voice_engine_v2_vad_timing_bridge.jsonl"
    _write_jsonl(log_path, [_enriched_vad_timing_record()])

    exit_code = main(
        [
            "validate",
            "--log-path",
            str(log_path),
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["bridge_records"] == 1