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
            self.assistant._last_pending_flow_snapshot = {}
            return None

        self.assistant._last_pending_flow_snapshot = {
            "consumed_by": str(decision.consumed_by or "").strip(),
            "pending_kind": str(decision.pending_kind or "").strip(),
            "pending_type": str(decision.pending_type or "").strip(),
            "language": str(decision.language or "").strip().lower(),
            "keeps_pending_state": bool(decision.keeps_pending_state),
            "metadata": dict(decision.metadata or {}),
        }
        return decision.response


    def _current_pending_type(self) -> str:
        assistant = self.assistant

        follow_up = getattr(assistant, "pending_follow_up", None)
        if isinstance(follow_up, dict):
            follow_type = str(follow_up.get("type", "") or "").strip()
            if follow_type:
                return follow_type

        confirmation = getattr(assistant, "pending_confirmation", None)
        if confirmation:
            return "suggestion_confirmation"

        return ""

    def _finalize_pending_decision(
        self,
        *,
        decision: PendingFlowDecision,
        command_lang: str,
        pending_type_before: str,
    ) -> PendingFlowDecision:
        consumed_by = str(decision.consumed_by or "").strip()
        pending_kind = str(decision.pending_kind or "").strip()
        pending_type = str(decision.pending_type or "").strip()
        metadata = dict(decision.metadata or {})

        if not pending_kind:
            if consumed_by.startswith("follow_up:"):
                pending_kind = "follow_up"
            elif consumed_by.startswith("pending_confirmation"):
                pending_kind = "confirmation"
            elif consumed_by == "cancel_request":
                pending_kind = "cancel"
            elif consumed_by == "new_intent_override":
                pending_kind = "override"

        if not pending_type:
            if consumed_by.startswith("follow_up:"):
                pending_type = consumed_by.split(":", 1)[1].strip()
            elif pending_kind == "confirmation":
                pending_type = pending_type_before or "suggestion_confirmation"
            else:
                pending_type = pending_type_before

        keeps_pending_state = bool(
            getattr(self.assistant, "pending_confirmation", None)
            or getattr(self.assistant, "pending_follow_up", None)
        )

        metadata.update(
            {
                "pending_confirmation_active": bool(getattr(self.assistant, "pending_confirmation", None)),
                "pending_follow_up_active": bool(getattr(self.assistant, "pending_follow_up", None)),
            }
        )

        return PendingFlowDecision(
            handled=bool(decision.handled),
            response=decision.response,
            consumed_by=consumed_by,
            pending_kind=pending_kind,
            pending_type=pending_type,
            language=str(command_lang or "").strip().lower(),
            keeps_pending_state=keeps_pending_state,
            metadata=metadata,
        )




    def process_pending_state(
        self,
        *,
        routing_text: str,
        command_lang: str,
    ) -> PendingFlowDecision:
        if not self.has_pending_state():
            return PendingFlowDecision(handled=False)

        pending_type_before = self._current_pending_type()

        cancel_decision = self.cancel_if_requested(routing_text, command_lang)
        if cancel_decision.handled:
            return self._finalize_pending_decision(
                decision=cancel_decision,
                command_lang=command_lang,
                pending_type_before=pending_type_before,
            )

        override_decision = self.interrupt_with_new_intent(routing_text, command_lang)
        if override_decision.handled:
            return self._finalize_pending_decision(
                decision=override_decision,
                command_lang=command_lang,
                pending_type_before=pending_type_before,
            )

        confirmation_decision = self.handle_pending_confirmation(routing_text, command_lang)
        if confirmation_decision.handled:
            return self._finalize_pending_decision(
                decision=confirmation_decision,
                command_lang=command_lang,
                pending_type_before=pending_type_before,
            )

        follow_up_decision = self.handle_pending_follow_up(routing_text, command_lang)
        if follow_up_decision.handled:
            return self._finalize_pending_decision(
                decision=follow_up_decision,
                command_lang=command_lang,
                pending_type_before=pending_type_before,
            )

        return PendingFlowDecision(handled=False)