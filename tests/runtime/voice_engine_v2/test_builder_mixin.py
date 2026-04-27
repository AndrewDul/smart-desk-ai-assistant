from modules.runtime.builder.voice_engine_v2_mixin import (
    RuntimeBuilderVoiceEngineV2Mixin,
)


class _BuilderProbe(RuntimeBuilderVoiceEngineV2Mixin):
    def __init__(self, settings: dict[str, object]) -> None:
        self.settings = settings


def test_builder_mixin_builds_disabled_voice_engine_v2_bundle() -> None:
    builder = _BuilderProbe(
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

    bundle = builder._build_voice_engine_v2()

    assert bundle.status.selected_backend == "disabled"
    assert bundle.settings.command_pipeline_can_run is False
    assert bundle.status.metadata["legacy_runtime_primary"] is True


def test_builder_mixin_builds_enabled_voice_engine_v2_bundle() -> None:
    builder = _BuilderProbe(
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

    bundle = builder._build_voice_engine_v2()

    assert bundle.status.selected_backend == "command_first_pipeline"
    assert bundle.settings.command_pipeline_can_run is True
    assert bundle.status.metadata["legacy_runtime_primary"] is False