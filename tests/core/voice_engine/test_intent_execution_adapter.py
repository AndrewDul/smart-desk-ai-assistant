from modules.core.command_intents.command_intent_resolver import (
    CommandIntentResolver,
)
from modules.core.voice_engine.execution import (
    IntentExecutionAdapter,
    IntentExecutionRequest,
    IntentExecutionStatus,
)
from modules.devices.audio.command_asr.command_grammar import (
    build_default_command_grammar,
)


def _request(action_text: str = "show desktop") -> IntentExecutionRequest:
    grammar = build_default_command_grammar()
    recognition = grammar.match(action_text)
    resolution = CommandIntentResolver().resolve(recognition)

    assert resolution.intent is not None

    return IntentExecutionRequest(
        intent=resolution.intent,
        turn_id="turn-1",
        action_first=True,
        allow_spoken_acknowledgement=False,
    )


def test_intent_execution_adapter_executes_registered_action() -> None:
    adapter = IntentExecutionAdapter()

    adapter.register_action(
        "show_desktop",
        lambda request: {"executed_action": request.intent.action},
    )

    result = adapter.execute(_request())

    assert result.status == IntentExecutionStatus.EXECUTED
    assert result.executed is True
    assert result.action == "show_desktop"
    assert result.executed_before_tts is True
    assert result.payload["executed_action"] == "show_desktop"


def test_intent_execution_adapter_returns_no_handler_for_unknown_action() -> None:
    adapter = IntentExecutionAdapter()

    result = adapter.execute(_request())

    assert result.status == IntentExecutionStatus.NO_HANDLER
    assert result.executed is False
    assert result.executed_before_tts is False


def test_intent_execution_adapter_converts_handler_error_to_failed_result() -> None:
    adapter = IntentExecutionAdapter()

    def broken_handler(request: IntentExecutionRequest):
        raise RuntimeError("boom")

    adapter.register_action("show_desktop", broken_handler)

    result = adapter.execute(_request())

    assert result.status == IntentExecutionStatus.FAILED
    assert result.executed is False
    assert "RuntimeError" in result.detail