from modules.devices.audio.command_asr import CommandLanguage
from modules.runtime.voice_engine_v2 import build_voice_engine_v2_runtime


def _bundle(*, shadow_mode_enabled: bool):
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
                "shadow_log_path": "var/data/test_shadow.jsonl",
                "legacy_removal_stage": "after_acceptance",
            }
        }
    )


def test_shadow_mode_refuses_to_observe_when_disabled() -> None:
    bundle = _bundle(shadow_mode_enabled=False)

    result = bundle.shadow_mode_adapter.observe_transcript(
        turn_id="turn-shadow-disabled",
        transcript="show desktop",
        legacy_intent_key="visual_shell.show_desktop",
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.enabled is False
    assert result.reason == "shadow_mode_disabled"
    assert result.legacy_runtime_primary is True
    assert result.turn_result is None
    assert result.action_executed is False


def test_shadow_mode_observes_matching_legacy_command_without_execution() -> None:
    bundle = _bundle(shadow_mode_enabled=True)

    result = bundle.shadow_mode_adapter.observe_transcript(
        turn_id="turn-shadow-match",
        transcript="show desktop",
        legacy_route="visual_shell",
        legacy_intent_key="visual_shell.show_desktop",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.enabled is True
    assert result.reason == "matched_legacy_intent"
    assert result.legacy_runtime_primary is True
    assert result.matched_legacy_intent is True
    assert result.voice_engine_intent_key == "visual_shell.show_desktop"
    assert result.action_executed is False
    assert result.metadata["action_executed"] is False


def test_shadow_mode_reports_mismatch_against_legacy_intent() -> None:
    bundle = _bundle(shadow_mode_enabled=True)

    result = bundle.shadow_mode_adapter.observe_transcript(
        turn_id="turn-shadow-mismatch",
        transcript="battery",
        legacy_route="visual_shell",
        legacy_intent_key="visual_shell.show_desktop",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.enabled is True
    assert result.reason == "mismatched_legacy_intent"
    assert result.matched_legacy_intent is False
    assert result.voice_engine_intent_key == "system.battery"
    assert result.action_executed is False


def test_shadow_mode_observes_fallback_for_open_question() -> None:
    bundle = _bundle(shadow_mode_enabled=True)

    result = bundle.shadow_mode_adapter.observe_transcript(
        turn_id="turn-shadow-fallback",
        transcript="czym jest czarna dziura",
        legacy_route="llm",
        legacy_intent_key=None,
        language_hint=CommandLanguage.POLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.enabled is True
    assert result.reason == "fallback:no_match"
    assert result.matched_legacy_intent is None
    assert result.voice_engine_intent_key is None
    assert result.fallback_reason == "no_match"
    assert result.action_executed is False


def test_shadow_mode_refuses_when_pipeline_is_not_runnable() -> None:
    bundle = build_voice_engine_v2_runtime(
        {
            "voice_engine": {
                "enabled": False,
                "version": "v2",
                "mode": "legacy",
                "command_first_enabled": False,
                "shadow_mode_enabled": True,
            }
        }
    )

    result = bundle.shadow_mode_adapter.observe_transcript(
        turn_id="turn-shadow-not-runnable",
        transcript="show desktop",
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.enabled is False
    assert result.reason == "voice_engine_v2_not_runnable"
    assert result.legacy_runtime_primary is True