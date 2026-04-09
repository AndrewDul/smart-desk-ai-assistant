from __future__ import annotations

from typing import Any

from modules.shared.logging.logger import get_logger

from .confirmation_mixin import PendingFlowConfirmationMixin
from .execution_helpers_mixin import PendingFlowExecutionHelpersMixin
from .follow_up_mixin import PendingFlowFollowUpMixin
from .models import PendingFlowDecision
from .parsing_helpers_mixin import PendingFlowParsingHelpersMixin

LOGGER = get_logger(__name__)


class PendingFlowOrchestrator(
    PendingFlowParsingHelpersMixin,
    PendingFlowExecutionHelpersMixin,
    PendingFlowConfirmationMixin,
    PendingFlowFollowUpMixin,
):
    """
    Final pending-state flow for NeXa.

    Responsibilities:
    - intercept explicit cancel requests
    - allow a fresh command to override stale pending state
    - resolve parser-suggestion confirmations
    - execute follow-up confirmations and short follow-up dialogues
    - keep all pending-state branching out of assistant.py
    """

    LOGGER = LOGGER

    def __init__(self, assistant: Any) -> None:
        self.assistant = assistant

    def has_pending_state(self) -> bool:
        assistant = self.assistant
        return bool(assistant.pending_confirmation or assistant.pending_follow_up)

    def process(
        self,
        *,
        prepared: dict[str, Any],
        language: str,
    ) -> bool | None:
        decision = self.process_pending_state(
            routing_text=str(prepared.get("routing_text", "")),
            command_lang=str(language),
        )
        if not decision.handled:
            return None
        return decision.response

    def process_pending_state(
        self,
        *,
        routing_text: str,
        command_lang: str,
    ) -> PendingFlowDecision:
        if not self.has_pending_state():
            return PendingFlowDecision(handled=False)

        cancel_decision = self.cancel_if_requested(routing_text, command_lang)
        if cancel_decision.handled:
            return cancel_decision

        override_decision = self.interrupt_with_new_intent(routing_text, command_lang)
        if override_decision.handled:
            return override_decision

        confirmation_decision = self.handle_pending_confirmation(routing_text, command_lang)
        if confirmation_decision.handled:
            return confirmation_decision

        follow_up_decision = self.handle_pending_follow_up(routing_text, command_lang)
        if follow_up_decision.handled:
            return follow_up_decision

        return PendingFlowDecision(handled=False)