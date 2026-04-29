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




def test_voice_engine_v2_bundle_exposes_acceptance_adapter_metadata() -> None:
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

    assert metadata["acceptance_adapter_available"] is True
    assert metadata["registered_acceptance_actions"] == []
    assert bundle.acceptance_adapter.settings.enabled is False




def test_voice_engine_v2_bundle_exposes_shadow_mode_metadata() -> None:
    bundle = build_voice_engine_v2_runtime(
        {
            "voice_engine": {
                "enabled": True,
                "version": "v2",
                "mode": "v2",
                "command_first_enabled": True,
                "shadow_mode_enabled": True,
                "shadow_log_path": "var/data/test_shadow.jsonl",
                "fallback_to_legacy_enabled": True,
            }
        }
    )

    metadata = bundle.to_metadata()

    assert metadata["shadow_mode_adapter_available"] is True
    assert metadata["shadow_mode_enabled"] is True
    assert metadata["shadow_mode_can_run"] is True
    assert metadata["shadow_log_path"] == "var/data/test_shadow.jsonl"
    assert bundle.shadow_mode_adapter.settings.shadow_mode_enabled is True




def test_voice_engine_v2_factory_attaches_shadow_telemetry_writer() -> None:
    bundle = build_voice_engine_v2_runtime(
        {
            "voice_engine": {
                "enabled": True,
                "version": "v2",
                "mode": "v2",
                "command_first_enabled": True,
                "shadow_mode_enabled": True,
                "shadow_log_path": "var/data/test_shadow.jsonl",
                "fallback_to_legacy_enabled": True,
            }
        }
    )

    writer = bundle.shadow_mode_adapter.telemetry_writer

    assert writer is not None
    assert writer.enabled is True
    assert str(writer.path) == "var/data/test_shadow.jsonl"



def test_voice_engine_v2_factory_exposes_shadow_runtime_hook_metadata() -> None:
    bundle = build_voice_engine_v2_runtime(
        {
            "voice_engine": {
                "enabled": True,
                "version": "v2",
                "mode": "v2",
                "command_first_enabled": True,
                "shadow_mode_enabled": True,
                "shadow_log_path": "var/data/test_shadow.jsonl",
                "fallback_to_legacy_enabled": True,
            }
        }
    )

    metadata = bundle.to_metadata()

    assert metadata["shadow_runtime_hook_available"] is True
    assert metadata["shadow_runtime_hook_action_safe"] is True
    assert bundle.shadow_runtime_hook.action_safe is True




def test_voice_engine_v2_factory_reports_shadow_can_run_while_legacy_primary() -> None:
    bundle = build_voice_engine_v2_runtime(
        {
            "voice_engine": {
                "enabled": False,
                "version": "v2",
                "mode": "legacy",
                "command_first_enabled": False,
                "fallback_to_legacy_enabled": True,
                "shadow_mode_enabled": True,
                "shadow_log_path": "var/data/test_shadow.jsonl",
            }
        }
    )

    metadata = bundle.to_metadata()

    assert bundle.enabled is False
    assert bundle.command_pipeline_can_run is False
    assert bundle.settings.shadow_mode_can_run is True
    assert metadata["enabled"] is False
    assert metadata["command_pipeline_can_run"] is False
    assert metadata["shadow_mode_enabled"] is True
    assert metadata["shadow_mode_can_run"] is True
    assert metadata["status"]["selected_backend"] == "disabled"
    assert metadata["status"]["metadata"]["legacy_runtime_primary"] is True
    assert metadata["status"]["metadata"]["shadow_mode_can_run"] is True


def test_voice_engine_v2_factory_reports_vosk_shadow_settings_metadata() -> None:
    bundle = build_voice_engine_v2_runtime(
        {
            "voice_engine": {
                "enabled": False,
                "version": "v2",
                "mode": "legacy",
                "fallback_to_legacy_enabled": True,
                "faster_whisper_audio_bus_tap_enabled": True,
                "vad_shadow_enabled": True,
                "vad_timing_bridge_enabled": True,
                "vad_timing_bridge_log_path": "var/data/test_vad_timing.jsonl",
                "command_asr_shadow_bridge_enabled": True,
                "vosk_live_shadow_contract_enabled": True,
                "vosk_shadow_recognition_preflight_enabled": True,
                "vosk_shadow_controlled_recognition_enabled": True,
                "vosk_shadow_controlled_recognition_dry_run_enabled": False,
                "vosk_command_model_paths": {
                    "en": "var/models/vosk/en-test",
                    "pl": "var/models/vosk/pl-test",
                },
                "vosk_command_sample_rate": 16000,
            }
        }
    )

    metadata = bundle.to_metadata()
    status_metadata = metadata["status"]["metadata"]

    assert bundle.enabled is False
    assert bundle.command_pipeline_can_run is False
    assert status_metadata["legacy_runtime_primary"] is True
    assert status_metadata["audio_bus_observe_can_run"] is True
    assert status_metadata["vad_shadow_can_run"] is True
    assert status_metadata["vad_timing_bridge_can_run"] is True
    assert status_metadata["command_asr_shadow_can_run"] is True
    assert status_metadata["vosk_live_shadow_contract_can_run"] is True
    assert status_metadata["vosk_controlled_recognition_can_run"] is True
    assert status_metadata["vosk_command_model_paths"] == {
        "en": "var/models/vosk/en-test",
        "pl": "var/models/vosk/pl-test",
    }
    assert status_metadata["vosk_command_sample_rate"] == 16000
    assert status_metadata["vosk_command_models_configured"] is True
