from __future__ import annotations

from modules.runtime.contracts import RouteKind, normalize_text
from modules.shared.logging.logger import get_logger

from .models import PendingFlowDecision, PendingIntentPayload

LOGGER = get_logger(__name__)


class PendingFlowConfirmationMixin:
    def cancel_if_requested(self, routing_text: str, command_lang: str) -> PendingFlowDecision:
        if not self.has_pending_state():
            return PendingFlowDecision(handled=False)

        pending_type = self._current_pending_type()
        if pending_type in {"focus_duration", "break_duration", "timer_duration"}:
            is_unknown_duration = getattr(self, "_is_unknown_duration_answer", None)
            if callable(is_unknown_duration) and is_unknown_duration(routing_text):
                return PendingFlowDecision(handled=False)

        if not self._looks_like_cancel_request(routing_text):
            return PendingFlowDecision(handled=False)

        lang = self.assistant._commit_language(command_lang)
        result = self.assistant._cancel_active_request(lang)

        LOGGER.info("Pending flow cancelled by explicit user request: text=%s", routing_text)
        return PendingFlowDecision(
            handled=True,
            response=result,
            consumed_by="cancel_request",
        )

    def interrupt_with_new_intent(
        self,
        routing_text: str,
        command_lang: str,
    ) -> PendingFlowDecision:
        if not self.has_pending_state():
            return PendingFlowDecision(handled=False)

        override_intent = self._extract_pending_override_intent(routing_text)
        if override_intent is None:
            return PendingFlowDecision(handled=False)

        LOGGER.info(
            "Pending state interrupted by a new command: action=%s payload_keys=%s",
            override_intent.action,
            sorted(override_intent.data.keys()),
        )

        self.assistant.pending_confirmation = None
        self.assistant.pending_follow_up = None
        lang = self.assistant._commit_language(command_lang)

        result = self._execute_action_intent(override_intent, lang)

        return PendingFlowDecision(
            handled=True,
            response=result,
            consumed_by="new_intent_override",
        )

    def handle_pending_confirmation(
        self,
        routing_text: str,
        command_lang: str,
    ) -> PendingFlowDecision:
        assistant = self.assistant
        pending = assistant.pending_confirmation
        if not pending:
            return PendingFlowDecision(handled=False)

        lang = self._normalize_language(pending.get("language", command_lang))
        suggestions = self._coerce_suggestions(list(pending.get("suggestions", []) or []))
        allowed_actions = [item["action"] for item in suggestions]

        assistant._commit_language(lang)

        if self._is_yes(routing_text):
            assistant.pending_confirmation = None
            chosen = suggestions[0] if suggestions else None
            if chosen is None:
                return PendingFlowDecision(
                    handled=True,
                    response=True,
                    consumed_by="pending_confirmation_yes_empty",
                )

            result = self._execute_action_intent(
                PendingIntentPayload(
                    action=chosen["action"],
                    data=dict(chosen.get("payload", {})),
                    normalized_text=normalize_text(routing_text),
                    confidence=float(chosen.get("confidence", 1.0)),
                ),
                lang,
            )
            LOGGER.info("Pending confirmation accepted by yes: chosen=%s", chosen["action"])
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="pending_confirmation_yes",
            )

        if self._is_no(routing_text):
            assistant.pending_confirmation = None
            result = assistant.deliver_text_response(
                assistant._localized(
                    lang,
                    "Dobrze. Powiedz to jeszcze raz inaczej.",
                    "Okay. Please say it again in a different way.",
                ),
                language=lang,
                route_kind=RouteKind.CONVERSATION,
                source="pending_confirmation_declined",
                metadata={"pending_type": "confirmation"},
            )
            LOGGER.info("Pending confirmation declined by user.")
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="pending_confirmation_no",
            )

        ordinal_choice = self._parse_confirmation_choice(routing_text)
        if ordinal_choice is not None and ordinal_choice < len(suggestions):
            assistant.pending_confirmation = None
            chosen = suggestions[ordinal_choice]
            result = self._execute_action_intent(
                PendingIntentPayload(
                    action=chosen["action"],
                    data=dict(chosen.get("payload", {})),
                    normalized_text=normalize_text(routing_text),
                    confidence=float(chosen.get("confidence", 1.0)),
                ),
                lang,
            )
            LOGGER.info(
                "Pending confirmation chosen by ordinal: chosen=%s index=%s",
                chosen["action"],
                ordinal_choice,
            )
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="pending_confirmation_ordinal",
            )

        direct_choice = self._find_action_in_text(routing_text, allowed_actions=allowed_actions)
        if direct_choice:
            assistant.pending_confirmation = None
            chosen = next(
                (item for item in suggestions if item["action"] == direct_choice),
                {"action": direct_choice, "payload": {}},
            )
            result = self._execute_action_intent(
                PendingIntentPayload(
                    action=chosen["action"],
                    data=dict(chosen.get("payload", {})),
                    normalized_text=normalize_text(routing_text),
                    confidence=float(chosen.get("confidence", 1.0)),
                ),
                lang,
            )
            LOGGER.info("Pending confirmation chosen directly: chosen=%s", chosen["action"])
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="pending_confirmation_direct_choice",
            )

        retry_result = assistant.deliver_text_response(
            assistant._localized(
                lang,
                "Powiedz tak albo nie.",
                "Please say yes or no.",
            ),
            language=lang,
            route_kind=RouteKind.CONVERSATION,
            source="pending_confirmation_retry",
            metadata={"pending_type": "confirmation"},
        )
        return PendingFlowDecision(
            handled=True,
            response=retry_result,
            consumed_by="pending_confirmation_retry",
        )