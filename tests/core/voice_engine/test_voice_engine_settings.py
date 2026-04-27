from modules.core.voice_engine.voice_engine_settings import VoiceEngineSettings


def test_voice_engine_settings_from_full_settings_reads_voice_engine_block() -> None:
    settings = VoiceEngineSettings.from_settings(
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

    assert settings.enabled is True
    assert settings.mode == "v2"
    assert settings.realtime_audio_bus_enabled is True
    assert settings.vad_endpointing_enabled is True
    assert settings.command_first_enabled is True
    assert settings.command_pipeline_can_run is True


def test_voice_engine_settings_keep_command_pipeline_disabled_by_default() -> None:
    settings = VoiceEngineSettings()

    assert settings.enabled is False
    assert settings.mode == "legacy"
    assert settings.command_first_enabled is False
    assert settings.command_pipeline_can_run is False