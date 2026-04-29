from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_voice_engine_v2_controlled_recognition_boundary import (
    main,
    validate_controlled_recognition_boundary,
)


def _write_settings(path: Path, voice_engine_overrides: dict[str, object] | None = None) -> None:
    voice_engine: dict[str, object] = {
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
        "vosk_shadow_invocation_plan_enabled": False,
        "vosk_shadow_pcm_reference_enabled": False,
        "vosk_shadow_asr_result_enabled": False,
        "vosk_shadow_recognition_preflight_enabled": False,
        "vosk_shadow_invocation_attempt_enabled": False,
        "vosk_shadow_controlled_recognition_enabled": False,
        "vosk_shadow_controlled_recognition_dry_run_enabled": False,
        "vosk_shadow_controlled_recognition_result_enabled": False,
    }
    if voice_engine_overrides:
        voice_engine.update(voice_engine_overrides)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"voice_engine": voice_engine}, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_log(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _preflight() -> dict[str, object]:
    return {
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


def _attempt() -> dict[str, object]:
    return {
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


def _command_record() -> dict[str, object]:
    return {
        "hook": "capture_window_pre_transcription",
        "turn_id": "turn-command",
        "phase": "command",
        "capture_mode": "wake_command",
        "action_executed": False,
        "full_stt_prevented": False,
        "runtime_takeover": False,
        "vad_shadow": {
            "stale_audio_observed": False,
            "pcm_profile_signal_level": "high",
            "frame_source_counts": {
                "faster_whisper_capture_window_shadow_tap": 24,
                "faster_whisper_callback_shadow_tap": 21,
            },
        },
        "metadata": {
            "vosk_shadow_recognition_preflight": _preflight(),
            "vosk_shadow_invocation_attempt": _attempt(),
        },
    }


def test_boundary_accepts_safe_disabled_config_and_command_candidates(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.json"
    log_path = tmp_path / "vad_timing.jsonl"
    _write_settings(settings_path)
    _write_log(log_path, [_command_record()])

    result = validate_controlled_recognition_boundary(
        settings_path=settings_path,
        log_path=log_path,
        require_records=True,
        require_command_candidates=True,
    )

    assert result["accepted"] is True
    assert result["issues"] == []
    assert result["settings"]["accepted"] is True
    assert result["settings"]["controlled_flags_enabled"] == []
    assert result["controlled_recognition_readiness"]["accepted"] is True
    assert (
        result["decision"]
        == "controlled_recognition_boundary_ready_but_current_stage_disabled"
    )


def test_boundary_rejects_enabled_controlled_recognition_flag(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    log_path = tmp_path / "vad_timing.jsonl"
    _write_settings(
        settings_path,
        {"vosk_shadow_controlled_recognition_enabled": True},
    )
    _write_log(log_path, [_command_record()])

    result = validate_controlled_recognition_boundary(
        settings_path=settings_path,
        log_path=log_path,
        require_records=True,
        require_command_candidates=True,
    )

    assert result["accepted"] is False
    assert (
        "settings:controlled_recognition_flag_enabled_vosk_shadow_controlled_recognition_enabled"
        in result["issues"]
    )
    assert result["settings"]["controlled_flags_enabled"] == [
        "vosk_shadow_controlled_recognition_enabled"
    ]


def test_boundary_rejects_unsafe_baseline_config(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    log_path = tmp_path / "vad_timing.jsonl"
    _write_settings(settings_path, {"enabled": True})
    _write_log(log_path, [_command_record()])

    result = validate_controlled_recognition_boundary(
        settings_path=settings_path,
        log_path=log_path,
        require_records=True,
        require_command_candidates=True,
    )

    assert result["accepted"] is False
    assert "settings:unsafe_baseline_enabled" in result["issues"]


def test_boundary_rejects_active_observation_flag_when_restore_required(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.json"
    log_path = tmp_path / "vad_timing.jsonl"
    _write_settings(settings_path, {"vad_timing_bridge_enabled": True})
    _write_log(log_path, [_command_record()])

    result = validate_controlled_recognition_boundary(
        settings_path=settings_path,
        log_path=log_path,
        require_records=True,
        require_command_candidates=True,
    )

    assert result["accepted"] is False
    assert "settings:observation_flag_not_restored_vad_timing_bridge_enabled" in result["issues"]


def test_boundary_rejects_missing_command_candidates(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    log_path = tmp_path / "vad_timing.jsonl"
    _write_settings(settings_path)
    _write_log(log_path, [])

    result = validate_controlled_recognition_boundary(
        settings_path=settings_path,
        log_path=log_path,
        require_records=True,
        require_command_candidates=True,
    )

    assert result["accepted"] is False
    assert "readiness:records_missing" in result["issues"]


def test_boundary_cli_accepts_safe_boundary(tmp_path: Path, capsys) -> None:
    settings_path = tmp_path / "settings.json"
    log_path = tmp_path / "vad_timing.jsonl"
    _write_settings(settings_path)
    _write_log(log_path, [_command_record()])

    exit_code = main(
        [
            "--settings",
            str(settings_path),
            "--log-path",
            str(log_path),
            "--require-records",
            "--require-command-candidates",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["accepted"] is True
    assert payload["settings"]["controlled_flags_enabled"] == []
