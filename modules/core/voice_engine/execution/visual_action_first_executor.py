from __future__ import annotations

from modules.core.voice_engine.execution.intent_execution import (
    IntentExecutionAdapter,
    IntentExecutionRequest,
    IntentExecutionResult,
    IntentExecutionStatus,
)
from modules.core.voice_engine.execution.visual_shell_actions import (
    is_visual_shell_action,
)
from modules.core.voice_engine.voice_turn import VoiceTurnResult, VoiceTurnRoute


class VisualActionFirstExecutor:
    """Executes resolved Voice Engine v2 commands before optional TTS.

    This class does not render Visual Shell directly and does not generate TTS.
    It only enforces the ordering rule: deterministic visual/system action first,
    optional spoken acknowledgement later.
    """

    def __init__(self, execution_adapter: IntentExecutionAdapter) -> None:
        self._execution_adapter = execution_adapter

    def execute_turn(self, turn_result: VoiceTurnResult) -> IntentExecutionResult:
        if turn_result.route is not VoiceTurnRoute.COMMAND:
            return self._rejected(turn_result, "turn_is_not_command")

        if turn_result.intent is None:
            return self._rejected(turn_result, "missing_intent")

        allow_spoken_acknowledgement = not is_visual_shell_action(
            turn_result.intent.action
        )

        request = IntentExecutionRequest(
            intent=turn_result.intent,
            turn_id=turn_result.turn_id,
            action_first=True,
            allow_spoken_acknowledgement=allow_spoken_acknowledgement,
            metadata={
                "route": turn_result.route.value,
                "language": turn_result.language.value,
                "source_text": turn_result.source_text,
            },
        )

        return self._execution_adapter.execute(request)

    @staticmethod
    def _rejected(
        turn_result: VoiceTurnResult,
        reason: str,
    ) -> IntentExecutionResult:
        if turn_result.intent is None:
            return IntentExecutionResult(
                status=IntentExecutionStatus.REJECTED,
                turn_id=turn_result.turn_id,
                intent_key="unknown",
                action="unknown",
                action_first=False,
                spoken_acknowledgement_allowed=False,
                executed_before_tts=False,
                detail=reason,
            )

        return IntentExecutionResult(
            status=IntentExecutionStatus.REJECTED,
            turn_id=turn_result.turn_id,
            intent_key=turn_result.intent.key,
            action=turn_result.intent.action,
            action_first=False,
            spoken_acknowledgement_allowed=False,
            executed_before_tts=False,
            detail=reason,
        )