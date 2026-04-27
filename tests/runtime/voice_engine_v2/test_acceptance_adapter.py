from modules.devices.audio.command_asr import CommandLanguage
from modules.runtime.voice_engine_v2 import build_voice_engine_v2_runtime


def _enabled_bundle():
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
                "legacy_removal_stage": "after_acceptance",
            }
        }
    )


def _disabled_bundle():
    return build_voice_engine_v2_runtime(
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


def test_acceptance_adapter_refuses_to_run_when_voice_engine_v2_is_disabled() -> None:
    bundle = _disabled_bundle()

    result = bundle.acceptance_adapter.process_transcript(
        turn_id="turn-disabled",
        transcript="show desktop",
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is False
    assert result.reason == "voice_engine_v2_disabled"
    assert result.legacy_runtime_primary is True
    assert result.turn_result is None
    assert result.execution_result is None


def test_acceptance_adapter_executes_registered_visual_shell_command() -> None:
    bundle = _enabled_bundle()

    bundle.acceptance_adapter.register_action(
        "show_desktop",
        lambda request: {"handled_action": request.intent.action},
    )

    result = bundle.acceptance_adapter.process_transcript(
        turn_id="turn-show-desktop",
        transcript="show desktop",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is True
    assert result.reason == "accepted"
    assert result.legacy_runtime_primary is False
    assert result.command_executed is True
    assert result.turn_result is not None
    assert result.turn_result.intent is not None
    assert result.turn_result.intent.key == "visual_shell.show_desktop"
    assert result.execution_result is not None
    assert result.execution_result.action == "show_desktop"
    assert result.execution_result.executed_before_tts is True
    assert result.execution_result.spoken_acknowledgement_allowed is False
    assert result.execution_result.payload["handled_action"] == "show_desktop"


def test_acceptance_adapter_reports_no_handler_for_unregistered_command() -> None:
    bundle = _enabled_bundle()

    result = bundle.acceptance_adapter.process_transcript(
        turn_id="turn-no-handler",
        transcript="show desktop",
        language_hint=CommandLanguage.ENGLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is False
    assert result.reason == "no_handler"
    assert result.execution_result is not None
    assert result.execution_result.detail == "no_handler"


def test_acceptance_adapter_sends_open_question_to_fallback() -> None:
    bundle = _enabled_bundle()

    result = bundle.acceptance_adapter.process_transcript(
        turn_id="turn-open-question",
        transcript="czym jest czarna dziura",
        language_hint=CommandLanguage.POLISH,
        started_monotonic=1.0,
        speech_end_monotonic=1.0,
    )

    assert result.accepted is False
    assert result.reason == "fallback_required:no_match"
    assert result.turn_result is not None
    assert result.turn_result.fallback is not None
    assert result.execution_result is None
    assert result.metadata["fallback_used"] is True