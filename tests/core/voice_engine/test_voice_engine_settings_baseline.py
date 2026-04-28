from modules.shared.config.settings_core.defaults import DEFAULT_SETTINGS


def test_voice_engine_v2_defaults_are_present_and_safe() -> None:
    voice_engine = DEFAULT_SETTINGS.get("voice_engine")

    assert isinstance(voice_engine, dict)
    assert voice_engine["enabled"] is False
    assert voice_engine["version"] == "v2"
    assert voice_engine["mode"] == "legacy"


def test_voice_engine_v2_does_not_replace_legacy_runtime_by_default() -> None:
    voice_engine = DEFAULT_SETTINGS["voice_engine"]

    assert voice_engine["realtime_audio_bus_enabled"] is False
    assert voice_engine["vad_shadow_enabled"] is False
    assert voice_engine["vosk_shadow_asr_result_enabled"] is False
    assert voice_engine["vad_endpointing_enabled"] is False
    assert voice_engine["command_first_enabled"] is False
    assert voice_engine["fallback_to_legacy_enabled"] is True
    assert voice_engine["metrics_enabled"] is True


def test_voice_engine_v2_has_explicit_legacy_removal_stage() -> None:
    voice_engine = DEFAULT_SETTINGS["voice_engine"]

    assert (
        voice_engine["legacy_removal_stage"]
        == "after_voice_engine_v2_runtime_acceptance"
    )



def test_voice_engine_v2_shadow_mode_defaults_are_safe() -> None:
    voice_engine = DEFAULT_SETTINGS["voice_engine"]

    assert voice_engine["shadow_mode_enabled"] is False
    assert voice_engine["shadow_log_path"] == "var/data/voice_engine_v2_shadow.jsonl"