from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.set_voice_engine_v2_vad_shadow import (
    DEFAULT_MAX_FRAMES_PER_OBSERVATION,
    DEFAULT_MIN_SILENCE_MS,
    DEFAULT_MIN_SPEECH_MS,
    DEFAULT_SPEECH_THRESHOLD,
    disable_vad_shadow,
    enable_vad_shadow,
    load_settings,
    main,
    status_from_settings,
)


def _write_settings(
    path: Path,
    *,
    voice_engine_overrides: dict[str, object] | None = None,
) -> None:
    settings = {
        "voice_engine": {
            "enabled": False,
            "version": "v2",
            "mode": "legacy",
            "realtime_audio_bus_enabled": False,
            "faster_whisper_audio_bus_tap_enabled": True,
            "faster_whisper_audio_bus_tap_max_duration_seconds": 3.0,
            "vad_shadow_enabled": False,
            "vad_shadow_max_frames_per_observation": (
                DEFAULT_MAX_FRAMES_PER_OBSERVATION
            ),
            "vad_shadow_speech_threshold": DEFAULT_SPEECH_THRESHOLD,
            "vad_shadow_min_speech_ms": DEFAULT_MIN_SPEECH_MS,
            "vad_shadow_min_silence_ms": DEFAULT_MIN_SILENCE_MS,
            "vad_endpointing_enabled": False,
            "command_first_enabled": False,
            "fallback_to_legacy_enabled": True,
            "metrics_enabled": True,
            "shadow_mode_enabled": False,
            "shadow_log_path": "var/data/voice_engine_v2_shadow.jsonl",
            "pre_stt_shadow_enabled": True,
            "pre_stt_shadow_log_path": (
                "var/data/voice_engine_v2_pre_stt_shadow.jsonl"
            ),
            "runtime_candidate_log_path": (
                "var/data/voice_engine_v2_runtime_candidates.jsonl"
            ),
            "runtime_candidates_enabled": False,
            "runtime_candidate_intent_allowlist": [
                "assistant.identity",
                "system.current_time",
            ],
            "legacy_removal_stage": "after_voice_engine_v2_runtime_acceptance",
        }
    }
    if voice_engine_overrides:
        settings["voice_engine"].update(voice_engine_overrides)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def test_status_reports_safe_when_shadow_dependencies_are_enabled(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path)

    settings = load_settings(settings_path)
    status = status_from_settings(settings_path=settings_path, settings=settings)

    assert status.safe_to_enable_vad_shadow is True
    assert status.reason == "safe"
    assert status.pre_stt_shadow_enabled is True
    assert status.faster_whisper_audio_bus_tap_enabled is True
    assert status.vad_shadow_enabled is False


def test_enable_vad_shadow_sets_only_guarded_fields(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path)

    result = enable_vad_shadow(
        settings_path=settings_path,
        create_config_backup=False,
    )

    updated = load_settings(settings_path)
    voice_engine = updated["voice_engine"]

    assert result["changed"] is True
    assert result["action"] == "enable"
    assert result["backup_path"] is None

    assert voice_engine["enabled"] is False
    assert voice_engine["mode"] == "legacy"
    assert voice_engine["command_first_enabled"] is False
    assert voice_engine["fallback_to_legacy_enabled"] is True
    assert voice_engine["runtime_candidates_enabled"] is False
    assert voice_engine["pre_stt_shadow_enabled"] is True
    assert voice_engine["faster_whisper_audio_bus_tap_enabled"] is True
    assert voice_engine["vad_shadow_enabled"] is True
    assert (
        voice_engine["vad_shadow_max_frames_per_observation"]
        == DEFAULT_MAX_FRAMES_PER_OBSERVATION
    )
    assert voice_engine["vad_shadow_speech_threshold"] == DEFAULT_SPEECH_THRESHOLD
    assert voice_engine["vad_shadow_min_speech_ms"] == DEFAULT_MIN_SPEECH_MS
    assert voice_engine["vad_shadow_min_silence_ms"] == DEFAULT_MIN_SILENCE_MS


def test_enable_vad_shadow_creates_backup_by_default(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path)

    result = enable_vad_shadow(
        settings_path=settings_path,
        create_config_backup=True,
    )

    backup_path = result["backup_path"]
    assert backup_path is not None
    assert Path(str(backup_path)).exists()


@pytest.mark.parametrize(
    ("override", "expected_reason"),
    [
        ({"enabled": True}, "voice_engine_enabled_must_remain_false"),
        ({"mode": "v2"}, "voice_engine_mode_must_remain_legacy"),
        ({"command_first_enabled": True}, "command_first_enabled_must_remain_false"),
        (
            {"fallback_to_legacy_enabled": False},
            "fallback_to_legacy_enabled_must_remain_true",
        ),
        (
            {"runtime_candidates_enabled": True},
            "runtime_candidates_enabled_must_remain_false_for_vad_shadow",
        ),
        (
            {"pre_stt_shadow_enabled": False},
            "pre_stt_shadow_enabled_must_be_true_for_vad_shadow_validation",
        ),
        (
            {"faster_whisper_audio_bus_tap_enabled": False},
            "audio_bus_tap_enabled_must_be_true_for_vad_shadow_validation",
        ),
    ],
)
def test_enable_vad_shadow_refuses_unsafe_states(
    tmp_path: Path,
    override: dict[str, object],
    expected_reason: str,
) -> None:
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path, voice_engine_overrides=override)

    with pytest.raises(RuntimeError, match=expected_reason):
        enable_vad_shadow(
            settings_path=settings_path,
            create_config_backup=False,
        )

    settings = load_settings(settings_path)
    assert settings["voice_engine"]["vad_shadow_enabled"] is False


def test_disable_vad_shadow_preserves_threshold_settings(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.json"
    _write_settings(
        settings_path,
        voice_engine_overrides={
            "vad_shadow_enabled": True,
            "vad_shadow_speech_threshold": 0.7,
            "vad_shadow_min_speech_ms": 180,
            "vad_shadow_min_silence_ms": 340,
        },
    )

    result = disable_vad_shadow(
        settings_path=settings_path,
        create_config_backup=False,
    )

    updated = load_settings(settings_path)
    voice_engine = updated["voice_engine"]

    assert result["changed"] is True
    assert result["action"] == "disable"
    assert voice_engine["vad_shadow_enabled"] is False
    assert voice_engine["vad_shadow_speech_threshold"] == 0.7
    assert voice_engine["vad_shadow_min_speech_ms"] == 180
    assert voice_engine["vad_shadow_min_silence_ms"] == 340


def test_cli_status_returns_success(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path)

    exit_code = main(["--status", "--settings-path", str(settings_path)])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["changed"] is False
    assert payload["status"]["safe_to_enable_vad_shadow"] is True


def test_cli_enable_and_disable_return_success(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings_path = tmp_path / "settings.json"
    _write_settings(settings_path)

    enable_exit = main(
        [
            "--enable",
            "--settings-path",
            str(settings_path),
            "--no-backup",
        ]
    )
    enable_output = json.loads(capsys.readouterr().out)

    disable_exit = main(
        [
            "--disable",
            "--settings-path",
            str(settings_path),
            "--no-backup",
        ]
    )
    disable_output = json.loads(capsys.readouterr().out)

    assert enable_exit == 0
    assert enable_output["ok"] is True
    assert enable_output["status"]["voice_engine.vad_shadow_enabled"] is True

    assert disable_exit == 0
    assert disable_output["ok"] is True
    assert disable_output["status"]["voice_engine.vad_shadow_enabled"] is False


def test_cli_enable_refuses_when_audio_bus_tap_is_disabled(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings_path = tmp_path / "settings.json"
    _write_settings(
        settings_path,
        voice_engine_overrides={"faster_whisper_audio_bus_tap_enabled": False},
    )

    exit_code = main(
        [
            "--enable",
            "--settings-path",
            str(settings_path),
            "--no-backup",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert exit_code == 1
    assert payload["ok"] is False
    assert payload["error"] == "RuntimeError"
    assert (
        "audio_bus_tap_enabled_must_be_true_for_vad_shadow_validation"
        in payload["message"]
    )