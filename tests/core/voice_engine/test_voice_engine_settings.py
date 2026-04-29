import pytest

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
                "shadow_mode_enabled": True,
                "shadow_log_path": "var/data/test_shadow.jsonl",
                "legacy_removal_stage": "after_acceptance",
            }
        }
    )

    assert settings.enabled is True
    assert settings.mode == "v2"
    assert settings.realtime_audio_bus_enabled is True
    assert settings.vad_endpointing_enabled is True
    assert settings.command_first_enabled is True
    assert settings.shadow_mode_enabled is True
    assert settings.shadow_log_path == "var/data/test_shadow.jsonl"
    assert settings.command_pipeline_can_run is True
    assert settings.shadow_mode_can_run is True


def test_voice_engine_settings_keep_command_pipeline_disabled_by_default() -> None:
    settings = VoiceEngineSettings()

    assert settings.enabled is False
    assert settings.mode == "legacy"
    assert settings.command_first_enabled is False
    assert settings.shadow_mode_enabled is False
    assert settings.command_pipeline_can_run is False
    assert settings.shadow_mode_can_run is False
    assert settings.command_asr_shadow_can_run is False
    assert settings.vosk_live_shadow_contract_can_run is False
    assert settings.vosk_controlled_recognition_can_run is False


def test_shadow_mode_can_run_while_production_pipeline_stays_disabled() -> None:
    settings = VoiceEngineSettings.from_settings(
        {
            "voice_engine": {
                "enabled": False,
                "version": "v2",
                "mode": "legacy",
                "command_first_enabled": False,
                "fallback_to_legacy_enabled": True,
                "shadow_mode_enabled": True,
            }
        }
    )

    assert settings.command_pipeline_can_run is False
    assert settings.shadow_mode_can_run is True


def test_shadow_mode_refuses_when_legacy_fallback_is_disabled() -> None:
    settings = VoiceEngineSettings.from_settings(
        {
            "voice_engine": {
                "enabled": False,
                "version": "v2",
                "mode": "legacy",
                "fallback_to_legacy_enabled": False,
                "shadow_mode_enabled": True,
            }
        }
    )

    assert settings.command_pipeline_can_run is False
    assert settings.shadow_mode_can_run is False


def test_voice_engine_settings_reads_vosk_and_shadow_contract_fields() -> None:
    settings = VoiceEngineSettings.from_settings(
        {
            "voice_engine": {
                "enabled": False,
                "version": "v2",
                "mode": "legacy",
                "fallback_to_legacy_enabled": True,
                "faster_whisper_audio_bus_tap_enabled": True,
                "faster_whisper_audio_bus_tap_max_duration_seconds": 2.5,
                "vad_shadow_enabled": True,
                "vad_shadow_max_frames_per_observation": 64,
                "vad_shadow_speech_threshold": 0.42,
                "vad_shadow_min_speech_ms": 90,
                "vad_shadow_min_silence_ms": 180,
                "vad_timing_bridge_enabled": True,
                "vad_timing_bridge_log_path": "var/data/test_vad_timing.jsonl",
                "command_asr_shadow_bridge_enabled": True,
                "vosk_live_shadow_contract_enabled": True,
                "vosk_shadow_invocation_plan_enabled": True,
                "vosk_shadow_pcm_reference_enabled": True,
                "vosk_shadow_asr_result_enabled": True,
                "vosk_shadow_recognition_preflight_enabled": True,
                "vosk_shadow_invocation_attempt_enabled": True,
                "vosk_shadow_controlled_recognition_enabled": True,
                "vosk_shadow_controlled_recognition_dry_run_enabled": False,
                "vosk_shadow_controlled_recognition_result_enabled": True,
                "vosk_shadow_candidate_comparison_enabled": True,
                "vosk_command_model_paths": {
                    "en": "var/models/vosk/en-test",
                    "pl": "var/models/vosk/pl-test",
                },
                "vosk_command_sample_rate": 16000,
            }
        }
    )

    assert settings.audio_bus_observe_can_run is True
    assert settings.vad_shadow_can_run is True
    assert settings.vad_timing_bridge_can_run is True
    assert settings.command_asr_shadow_can_run is True
    assert settings.vosk_live_shadow_contract_can_run is True
    assert settings.vosk_controlled_recognition_can_run is True
    assert settings.vosk_command_model_paths == {
        "en": "var/models/vosk/en-test",
        "pl": "var/models/vosk/pl-test",
    }
    assert settings.vosk_command_sample_rate == 16000


def test_voice_engine_settings_blocks_observe_paths_when_live_engine_is_enabled() -> None:
    settings = VoiceEngineSettings.from_settings(
        {
            "voice_engine": {
                "enabled": True,
                "version": "v2",
                "mode": "v2",
                "fallback_to_legacy_enabled": True,
                "command_first_enabled": True,
                "faster_whisper_audio_bus_tap_enabled": True,
                "vad_shadow_enabled": True,
                "vad_timing_bridge_enabled": True,
                "command_asr_shadow_bridge_enabled": True,
                "vosk_live_shadow_contract_enabled": True,
                "vosk_shadow_recognition_preflight_enabled": True,
                "vosk_shadow_controlled_recognition_enabled": True,
            }
        }
    )

    assert settings.command_pipeline_can_run is True
    assert settings.audio_bus_observe_can_run is False
    assert settings.vad_shadow_can_run is False
    assert settings.vad_timing_bridge_can_run is False
    assert settings.command_asr_shadow_can_run is False
    assert settings.vosk_live_shadow_contract_can_run is False
    assert settings.vosk_controlled_recognition_can_run is False


def test_voice_engine_settings_reads_runtime_candidate_allowlist() -> None:
    settings = VoiceEngineSettings.from_settings(
        {
            "voice_engine": {
                "runtime_candidate_intent_allowlist": [
                    "assistant.identity",
                    "system.current_time",
                    "assistant.identity",
                    "",
                ]
            }
        }
    )

    assert settings.runtime_candidate_intent_allowlist == (
        "assistant.identity",
        "system.current_time",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("faster_whisper_audio_bus_tap_max_duration_seconds", 0),
        ("vad_shadow_max_frames_per_observation", 0),
        ("vad_shadow_speech_threshold", 1.5),
        ("vad_shadow_min_speech_ms", -1),
        ("vad_shadow_min_silence_ms", -1),
        ("vosk_command_sample_rate", 0),
    ],
)
def test_voice_engine_settings_rejects_invalid_numeric_values(
    field: str,
    value: int | float,
) -> None:
    with pytest.raises(ValueError):
        VoiceEngineSettings.from_settings({"voice_engine": {field: value}})


def test_voice_engine_settings_rejects_empty_vosk_model_paths() -> None:
    with pytest.raises(ValueError):
        VoiceEngineSettings.from_settings(
            {
                "voice_engine": {
                    "vosk_command_model_paths": {
                        "en": "",
                        "pl": "var/models/vosk/pl-test",
                    }
                }
            }
        )

    with pytest.raises(ValueError):
        VoiceEngineSettings.from_settings(
            {
                "voice_engine": {
                    "vosk_command_model_paths": {
                        "en": "var/models/vosk/en-test",
                        "pl": "",
                    }
                }
            }
        )
