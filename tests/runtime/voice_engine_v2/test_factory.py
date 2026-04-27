from modules.core.voice_engine import VoiceTurnInput, VoiceTurnRoute
from modules.devices.audio.command_asr import CommandLanguage
from modules.runtime.voice_engine_v2 import build_voice_engine_v2_runtime


def test_voice_engine_v2_factory_keeps_legacy_runtime_primary_when_disabled() -> None:
    bundle = build_voice_engine_v2_runtime(
        {
            "voice_engine": {
                "enabled": False,
                "version": "v2",
                "mode": "legacy",
                "command_first_enabled": False,
                "fallback_to_legacy_enabled": True,
            }
        }
    )

    assert bundle.enabled is False
    assert bundle.command_pipeline_can_run is False
    assert bundle.status.ok is True
    assert bundle.status.selected_backend == "disabled"
    assert bundle.status.metadata["legacy_runtime_primary"] is True


def test_voice_engine_v2_factory_builds_command_pipeline_when_enabled() -> None:
    bundle = build_voice_engine_v2_runtime(
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
                "legacy_removal_stage": "after_acceptance",
            }
        }
    )

    assert bundle.enabled is True
    assert bundle.command_pipeline_can_run is True
    assert bundle.status.selected_backend == "command_first_pipeline"
    assert bundle.status.metadata["legacy_runtime_primary"] is False

    result = bundle.engine.process_turn(
        VoiceTurnInput(
            turn_id="turn-1",
            transcript="show desktop",
            started_monotonic=1.0,
            speech_end_monotonic=1.0,
            language_hint=CommandLanguage.UNKNOWN,
        )
    )

    assert result.route == VoiceTurnRoute.COMMAND
    assert result.intent is not None
    assert result.intent.key == "visual_shell.show_desktop"


def test_voice_engine_v2_bundle_exports_safe_metadata() -> None:
    bundle = build_voice_engine_v2_runtime(
        {
            "voice_engine": {
                "enabled": False,
                "version": "v2",
                "mode": "legacy",
                "fallback_to_legacy_enabled": True,
            }
        }
    )

    metadata = bundle.to_metadata()

    assert metadata["enabled"] is False
    assert metadata["mode"] == "legacy"
    assert metadata["command_pipeline_can_run"] is False
    assert metadata["status"]["selected_backend"] == "disabled"