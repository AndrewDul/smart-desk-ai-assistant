import json

from modules.devices.audio.command_asr import CommandLanguage
from modules.runtime.voice_engine_v2 import build_voice_engine_v2_runtime


def _bundle_with_shadow_path(path: str, *, shadow_mode_enabled: bool = True):
    return build_voice_engine_v2_runtime(
        {
            "voice_engine": {
                "enabled": True,
                "version": "v2",
                "mode": "v2",
                "realtime_audio_bus_enabled": True,
                "vad_endpointing_enabled": True,
                "command_first_enabled": True,
                "fallback_to_legacy_enabled": True,
                "metrics_enabled": True,
                "shadow_mode_enabled": shadow_mode_enabled,
                "shadow_log_path": path,
                "legacy_removal_stage": "after_acceptance",
            }
        }
    )


def test_shadow_mode_persists_enabled_observation_to_jsonl(tmp_path) -> None:
    shadow_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    bundle = _bundle_with_shadow_path(str(shadow_path))

    result = bundle.shadow_mode_adapter.observe_transcript(
        turn_id="turn-shadow-persisted",
        transcript="show desktop",
        legacy_route="visual_shell",
        legacy_intent_key="visual_shell.show_desktop",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.enabled is True
    assert result.action_executed is False
    assert shadow_path.exists()

    lines = shadow_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 1

    record = json.loads(lines[0])

    assert record["turn_id"] == "turn-shadow-persisted"
    assert record["transcript"] == "show desktop"
    assert record["legacy_route"] == "visual_shell"
    assert record["legacy_intent_key"] == "visual_shell.show_desktop"
    assert record["voice_engine_route"] == "command"
    assert record["voice_engine_intent_key"] == "visual_shell.show_desktop"
    assert record["voice_engine_language"] == "en"
    assert record["matched_legacy_intent"] is True
    assert record["action_executed"] is False
    assert record["command_recognition_ms"] is not None
    assert record["intent_resolution_ms"] is not None
    assert record["speech_end_to_finish_ms"] is not None


def test_shadow_mode_does_not_persist_when_shadow_mode_is_disabled(tmp_path) -> None:
    shadow_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    bundle = _bundle_with_shadow_path(
        str(shadow_path),
        shadow_mode_enabled=False,
    )

    result = bundle.shadow_mode_adapter.observe_transcript(
        turn_id="turn-shadow-disabled",
        transcript="show desktop",
        legacy_route="visual_shell",
        legacy_intent_key="visual_shell.show_desktop",
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.enabled is False
    assert result.reason == "shadow_mode_disabled"
    assert shadow_path.exists() is False


def test_shadow_mode_appends_multiple_observations(tmp_path) -> None:
    shadow_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    bundle = _bundle_with_shadow_path(str(shadow_path))

    bundle.shadow_mode_adapter.observe_transcript(
        turn_id="turn-shadow-1",
        transcript="show desktop",
        legacy_route="visual_shell",
        legacy_intent_key="visual_shell.show_desktop",
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )
    bundle.shadow_mode_adapter.observe_transcript(
        turn_id="turn-shadow-2",
        transcript="battery",
        legacy_route="system",
        legacy_intent_key="system.battery",
        started_monotonic=2.0,
        speech_end_monotonic=2.0,
    )

    lines = shadow_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 2

    first = json.loads(lines[0])
    second = json.loads(lines[1])

    assert first["turn_id"] == "turn-shadow-1"
    assert second["turn_id"] == "turn-shadow-2"
    assert second["voice_engine_intent_key"] == "system.battery"