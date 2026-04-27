from modules.core.command_intents.command_intent_resolver import (
    CommandIntentResolver,
)
from modules.core.voice_engine.command_first_pipeline import CommandFirstPipeline
from modules.core.voice_engine.execution import (
    IntentExecutionAdapter,
    IntentExecutionRequest,
    IntentExecutionStatus,
    VisualActionFirstExecutor,
)
from modules.core.voice_engine.voice_engine import VoiceEngine
from modules.core.voice_engine.voice_engine_settings import VoiceEngineSettings
from modules.core.voice_engine.voice_turn import VoiceTurnInput, VoiceTurnRoute
from modules.devices.audio.command_asr.command_grammar import (
    build_default_command_grammar,
)
from modules.devices.audio.command_asr.command_language import CommandLanguage
from modules.devices.audio.command_asr.command_recognizer import (
    GrammarCommandRecognizer,
)


def _engine() -> VoiceEngine:
    pipeline = CommandFirstPipeline(
        command_recognizer=GrammarCommandRecognizer(
            build_default_command_grammar()
        ),
        intent_resolver=CommandIntentResolver(),
        clock=lambda: 1.0,
    )

    return VoiceEngine(
        settings=VoiceEngineSettings(
            enabled=True,
            mode="v2",
            command_first_enabled=True,
        ),
        command_first_pipeline=pipeline,
    )


def test_visual_shell_command_executes_action_before_tts_acknowledgement() -> None:
    engine = _engine()
    turn = engine.process_turn(
        VoiceTurnInput(
            turn_id="turn-1",
            transcript="show desktop",
            started_monotonic=1.0,
            speech_end_monotonic=1.0,
            language_hint=CommandLanguage.ENGLISH,
        )
    )

    executed_requests: list[IntentExecutionRequest] = []
    adapter = IntentExecutionAdapter()

    def handler(request: IntentExecutionRequest):
        executed_requests.append(request)
        return {"visual_shell_command": request.intent.action}

    adapter.register_action("show_desktop", handler)

    execution = VisualActionFirstExecutor(adapter).execute_turn(turn)

    assert turn.route == VoiceTurnRoute.COMMAND
    assert execution.status == IntentExecutionStatus.EXECUTED
    assert execution.executed is True
    assert execution.action == "show_desktop"
    assert execution.action_first is True
    assert execution.executed_before_tts is True
    assert execution.spoken_acknowledgement_allowed is False
    assert execution.payload["visual_shell_command"] == "show_desktop"
    assert executed_requests[0].allow_spoken_acknowledgement is False


def test_system_command_can_allow_spoken_acknowledgement_after_action() -> None:
    engine = _engine()
    turn = engine.process_turn(
        VoiceTurnInput(
            turn_id="turn-2",
            transcript="battery",
            started_monotonic=1.0,
            speech_end_monotonic=1.0,
            language_hint=CommandLanguage.ENGLISH,
        )
    )

    adapter = IntentExecutionAdapter()
    adapter.register_action(
        "report_battery",
        lambda request: {"system_command": request.intent.action},
    )

    execution = VisualActionFirstExecutor(adapter).execute_turn(turn)

    assert execution.status == IntentExecutionStatus.EXECUTED
    assert execution.action == "report_battery"
    assert execution.action_first is True
    assert execution.executed_before_tts is True
    assert execution.spoken_acknowledgement_allowed is True


def test_visual_action_first_executor_rejects_fallback_turns() -> None:
    engine = _engine()
    turn = engine.process_turn(
        VoiceTurnInput(
            turn_id="turn-3",
            transcript="czym jest czarna dziura",
            started_monotonic=1.0,
            speech_end_monotonic=1.0,
            language_hint=CommandLanguage.POLISH,
        )
    )

    execution = VisualActionFirstExecutor(IntentExecutionAdapter()).execute_turn(turn)

    assert turn.route == VoiceTurnRoute.FALLBACK
    assert execution.status == IntentExecutionStatus.REJECTED
    assert execution.detail == "turn_is_not_command"


def test_visual_action_first_executor_returns_no_handler_for_unregistered_action() -> None:
    engine = _engine()
    turn = engine.process_turn(
        VoiceTurnInput(
            turn_id="turn-4",
            transcript="show desktop",
            started_monotonic=1.0,
            speech_end_monotonic=1.0,
            language_hint=CommandLanguage.ENGLISH,
        )
    )

    execution = VisualActionFirstExecutor(IntentExecutionAdapter()).execute_turn(turn)

    assert execution.status == IntentExecutionStatus.NO_HANDLER
    assert execution.detail == "no_handler"