import json

from modules.devices.audio.command_asr import CommandLanguage
from modules.runtime.voice_engine_v2 import (
    VoiceEngineV2ShadowRuntimeObservation,
    build_voice_engine_v2_runtime,
)


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


def test_shadow_runtime_hook_observes_legacy_transcript_without_executing_action(
    tmp_path,
) -> None:
    shadow_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    bundle = _bundle_with_shadow_path(str(shadow_path))

    result = bundle.shadow_runtime_hook.observe_legacy_turn(
        turn_id="turn-hook-1",
        transcript="show desktop",
        legacy_route="visual_shell",
        legacy_intent_key="visual_shell.show_desktop",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
        metadata={"source": "legacy_runtime"},
    )

    assert result is not None
    assert result.enabled is True
    assert result.action_executed is False
    assert result.reason == "matched_legacy_intent"
    assert result.voice_engine_intent_key == "visual_shell.show_desktop"

    lines = shadow_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 1

    record = json.loads(lines[0])

    assert record["turn_id"] == "turn-hook-1"
    assert record["voice_engine_intent_key"] == "visual_shell.show_desktop"
    assert record["action_executed"] is False
    assert record["metadata"]["shadow_runtime_hook"] is True
    assert record["metadata"]["action_safe"] is True


def test_shadow_runtime_hook_ignores_empty_transcripts(tmp_path) -> None:
    shadow_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    bundle = _bundle_with_shadow_path(str(shadow_path))

    result = bundle.shadow_runtime_hook.observe_legacy_turn(
        turn_id="turn-hook-empty",
        transcript="   ",
        legacy_route="",
        legacy_intent_key=None,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result is None
    assert shadow_path.exists() is False


def test_shadow_runtime_hook_uses_observation_object(tmp_path) -> None:
    shadow_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    bundle = _bundle_with_shadow_path(str(shadow_path))

    observation = VoiceEngineV2ShadowRuntimeObservation(
        turn_id="turn-hook-observation",
        transcript="battery",
        legacy_route="system",
        legacy_intent_key="system.battery",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=2.0,
        speech_end_monotonic=2.0,
        metadata={"source": "unit_test"},
    )

    result = bundle.shadow_runtime_hook.observe(observation)

    assert result is not None
    assert result.reason == "matched_legacy_intent"
    assert result.voice_engine_intent_key == "system.battery"
    assert result.action_executed is False

    record = json.loads(shadow_path.read_text(encoding="utf-8").splitlines()[0])

    assert record["turn_id"] == "turn-hook-observation"
    assert record["voice_engine_intent_key"] == "system.battery"
    assert record["metadata"]["source"] == "unit_test"
    assert record["metadata"]["shadow_runtime_hook"] is True


def test_shadow_runtime_hook_keeps_legacy_primary_when_shadow_mode_disabled(
    tmp_path,
) -> None:
    shadow_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    bundle = _bundle_with_shadow_path(
        str(shadow_path),
        shadow_mode_enabled=False,
    )

    result = bundle.shadow_runtime_hook.observe_legacy_turn(
        turn_id="turn-hook-disabled",
        transcript="show desktop",
        legacy_route="visual_shell",
        legacy_intent_key="visual_shell.show_desktop",
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result is not None
    assert result.enabled is False
    assert result.reason == "shadow_mode_disabled"
    assert result.legacy_runtime_primary is True
    assert result.action_executed is False
    assert shadow_path.exists() is False




def test_shadow_runtime_hook_writes_telemetry_when_legacy_runtime_is_primary(
    tmp_path,
) -> None:
    shadow_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    bundle = build_voice_engine_v2_runtime(
        {
            "voice_engine": {
                "enabled": False,
                "version": "v2",
                "mode": "legacy",
                "command_first_enabled": False,
                "fallback_to_legacy_enabled": True,
                "shadow_mode_enabled": True,
                "shadow_log_path": str(shadow_path),
            }
        }
    )

    assert bundle.settings.command_pipeline_can_run is False
    assert bundle.settings.shadow_mode_can_run is True

    result = bundle.shadow_runtime_hook.observe_legacy_turn(
        turn_id="turn-hook-legacy-primary",
        transcript="show desktop",
        legacy_route="action",
        legacy_intent_key="visual_shell.show_desktop",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
        metadata={"source": "legacy_runtime_transcript_tap"},
    )

    assert result is not None
    assert result.enabled is True
    assert result.reason == "matched_legacy_intent"
    assert result.legacy_runtime_primary is True
    assert result.voice_engine_intent_key == "visual_shell.show_desktop"
    assert result.action_executed is False

    lines = shadow_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["turn_id"] == "turn-hook-legacy-primary"
    assert record["legacy_runtime_primary"] is True
    assert record["legacy_route"] == "action"
    assert record["legacy_intent_key"] == "visual_shell.show_desktop"
    assert record["voice_engine_intent_key"] == "visual_shell.show_desktop"
    assert record["action_executed"] is False
    assert record["metadata"]["shadow_runtime_hook"] is True
    assert record["metadata"]["action_safe"] is True