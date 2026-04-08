from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from modules.runtime.contracts import RouteKind, normalize_text
from modules.shared.logging.logger import get_logger

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class PendingFlowDecision:
    handled: bool
    response: bool | None = None
    consumed_by: str = ""


@dataclass(slots=True)
class PendingIntentPayload:
    """
    Lightweight action payload compatible with the old parser IntentResult shape.
    """

    action: str
    data: dict[str, Any]
    normalized_text: str
    confidence: float = 1.0
    needs_confirmation: bool = False
    suggestions: list[dict[str, Any]] | None = None


class PendingFlowOrchestrator:
    """
    Final pending-state flow for NeXa.

    Responsibilities:
    - intercept explicit cancel requests
    - allow a fresh command to override stale pending state
    - resolve parser-suggestion confirmations
    - execute follow-up confirmations and short follow-up dialogues
    - keep all pending-state branching out of assistant.py
    """

    def __init__(self, assistant: Any) -> None:
        self.assistant = assistant

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Stage 1: explicit cancel
    # ------------------------------------------------------------------

    def cancel_if_requested(self, routing_text: str, command_lang: str) -> PendingFlowDecision:
        if not self.has_pending_state():
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

    # ------------------------------------------------------------------
    # Stage 2: explicit fresh-command override
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Stage 3: parser-suggestion confirmation
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Stage 4: pending follow-ups
    # ------------------------------------------------------------------

    def handle_pending_follow_up(
        self,
        routing_text: str,
        command_lang: str,
    ) -> PendingFlowDecision:
        assistant = self.assistant
        follow_up = assistant.pending_follow_up
        if not follow_up:
            return PendingFlowDecision(handled=False)

        follow_type = str(follow_up.get("type", "")).strip()
        lang = self._follow_up_language(command_lang)
        assistant._commit_language(lang)

        if follow_type in {"timer_duration", "focus_duration", "break_duration"}:
            result = self._handle_duration_follow_up(
                follow_type=follow_type,
                text=routing_text,
                language=lang,
            )
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by=f"follow_up:{follow_type}",
            )

        if follow_type == "post_focus_break_offer":
            result = self._handle_post_focus_break_offer(text=routing_text, language=lang)
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:post_focus_break_offer",
            )

        if follow_type == "capture_name":
            result = self._handle_capture_name(text=routing_text, language=lang)
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:capture_name",
            )

        if follow_type == "confirm_save_name":
            result = self._handle_confirm_save_name(text=routing_text, language=lang)
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:confirm_save_name",
            )

        if follow_type == "confirm_memory_clear":
            result = self._handle_confirm_memory_clear(text=routing_text, language=lang)
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:confirm_memory_clear",
            )

        if follow_type == "confirm_reminders_clear":
            result = self._handle_confirm_reminders_clear(text=routing_text, language=lang)
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:confirm_reminders_clear",
            )

        if follow_type == "confirm_reminder_delete":
            result = self._handle_confirm_reminder_delete(text=routing_text, language=lang)
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:confirm_reminder_delete",
            )

        if follow_type == "confirm_exit":
            result = self._handle_confirm_exit(text=routing_text, language=lang)
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:confirm_exit",
            )

        if follow_type == "confirm_shutdown":
            result = self._handle_confirm_shutdown(text=routing_text, language=lang)
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:confirm_shutdown",
            )

        assistant.pending_follow_up = None
        LOGGER.warning("Unknown pending follow-up cleared: type=%s", follow_type)
        return PendingFlowDecision(handled=False)

    # ------------------------------------------------------------------
    # Duration follow-ups
    # ------------------------------------------------------------------

    def _handle_duration_follow_up(
        self,
        *,
        follow_type: str,
        text: str,
        language: str,
    ) -> bool:
        minutes = self._extract_minutes_from_text(text)
        if minutes is None or minutes <= 0:
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Podaj proszę czas w minutach albo sekundach.",
                    "Please tell me the duration in minutes or seconds.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_duration_retry",
                metadata={"follow_up_type": follow_type},
            )

        self.assistant.pending_follow_up = None

        if follow_type == "timer_duration":
            mode = "timer"
        elif follow_type == "focus_duration":
            mode = "focus"
        else:
            mode = "break"

        return self._start_timer_mode(
            minutes=minutes,
            mode=mode,
            language=language,
            source=f"pending_{follow_type}",
        )

    def _handle_post_focus_break_offer(self, *, text: str, language: str) -> bool:
        direct_minutes = self._extract_minutes_from_text(text)

        if direct_minutes is not None and direct_minutes > 0 and not self._is_no(text):
            self.assistant.pending_follow_up = None
            return self._start_timer_mode(
                minutes=direct_minutes,
                mode="break",
                language=language,
                source="pending_post_focus_break_duration",
            )

        if self._is_yes(text):
            self.assistant.pending_follow_up = None
            default_break = float(getattr(self.assistant, "default_break_minutes", 5.0))
            return self._start_timer_mode(
                minutes=default_break,
                mode="break",
                language=language,
                source="pending_post_focus_break_default",
            )

        if self._is_no(text):
            self.assistant.pending_follow_up = None
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Dobrze. Nie uruchamiam przerwy.",
                    "Okay. I will not start a break.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_post_focus_break_declined",
                metadata={"follow_up_type": "post_focus_break_offer"},
            )

        return self.assistant.deliver_text_response(
            self.assistant._localized(
                language,
                "Powiedz tak, nie albo od razu podaj długość przerwy.",
                "Say yes, no, or tell me the break duration right away.",
            ),
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="pending_post_focus_break_retry",
            metadata={"follow_up_type": "post_focus_break_offer"},
        )

    # ------------------------------------------------------------------
    # Name capture
    # ------------------------------------------------------------------

    def _handle_capture_name(self, *, text: str, language: str) -> bool:
        name = self._extract_name(text)
        if not name:
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Nie usłyszałam wyraźnie imienia. Powiedz proszę jeszcze raz swoje imię.",
                    "I did not catch your name clearly. Please say your name again.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_capture_name_retry",
                metadata={"follow_up_type": "capture_name"},
            )

        self.assistant.pending_follow_up = {
            "type": "confirm_save_name",
            "lang": language,
            "name": name,
        }

        display = getattr(self.assistant, "display", None)
        if display is not None:
            try:
                display.show_block(
                    self.assistant._localized(language, "ZAPISAĆ IMIĘ?", "SAVE NAME?"),
                    [
                        name,
                        self.assistant._localized(language, "powiedz tak lub nie", "say yes or no"),
                    ],
                    duration=8.0,
                )
            except Exception:
                pass

        return self.assistant.deliver_text_response(
            self.assistant._localized(
                language,
                f"Miło mi, {name}. Czy chcesz, żebym zapamiętała twoje imię?",
                f"Nice to meet you, {name}. Would you like me to remember your name?",
            ),
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="pending_offer_save_name",
            metadata={"follow_up_type": "confirm_save_name", "name": name},
        )

    def _handle_confirm_save_name(self, *, text: str, language: str) -> bool:
        follow_up = self.assistant.pending_follow_up or {}
        name = str(follow_up.get("name", "")).strip()

        if self._is_yes(text):
            self.assistant.user_profile["conversation_partner_name"] = name
            self.assistant._save_user_profile()
            self.assistant.pending_follow_up = None
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    f"Dobrze. Zapamiętałam, że masz na imię {name}.",
                    f"Okay. I remembered that your name is {name}.",
                ),
                language=language,
                route_kind=RouteKind.ACTION,
                source="pending_saved_name",
                metadata={"follow_up_type": "confirm_save_name", "name": name},
            )

        if self._is_no(text):
            self.assistant.pending_follow_up = None
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Dobrze. Nie zapisuję imienia.",
                    "Okay. I will not save the name.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_save_name_declined",
                metadata={"follow_up_type": "confirm_save_name", "name": name},
            )

        return self.assistant.deliver_text_response(
            self.assistant._localized(
                language,
                "Powiedz tak albo nie.",
                "Please say yes or no.",
            ),
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="pending_save_name_retry",
            metadata={"follow_up_type": "confirm_save_name", "name": name},
        )

    # ------------------------------------------------------------------
    # Confirm memory/reminders
    # ------------------------------------------------------------------

    def _handle_confirm_memory_clear(self, *, text: str, language: str) -> bool:
        if self._is_yes(text):
            self.assistant.pending_follow_up = None
            removed = self._memory_clear_count()
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    f"Dobrze. Wyczyściłam pamięć. Usunięto {removed}.",
                    f"Okay. I cleared memory. Removed {removed}.",
                ),
                language=language,
                route_kind=RouteKind.ACTION,
                source="pending_memory_clear_confirmed",
                metadata={"follow_up_type": "confirm_memory_clear", "removed": removed},
            )

        if self._is_no(text):
            self.assistant.pending_follow_up = None
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Dobrze. Nie czyszczę pamięci.",
                    "Okay. I will not clear memory.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_memory_clear_declined",
                metadata={"follow_up_type": "confirm_memory_clear"},
            )

        return self.assistant.deliver_text_response(
            self.assistant._localized(
                language,
                "Powiedz tak albo nie.",
                "Please say yes or no.",
            ),
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="pending_memory_clear_retry",
            metadata={"follow_up_type": "confirm_memory_clear"},
        )

    def _handle_confirm_reminders_clear(self, *, text: str, language: str) -> bool:
        if self._is_yes(text):
            self.assistant.pending_follow_up = None
            removed = self._reminders_clear_count()
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    f"Dobrze. Usunęłam wszystkie przypomnienia. Usunięto {removed}.",
                    f"Okay. I deleted all reminders. Removed {removed}.",
                ),
                language=language,
                route_kind=RouteKind.ACTION,
                source="pending_reminders_clear_confirmed",
                metadata={"follow_up_type": "confirm_reminders_clear", "removed": removed},
            )

        if self._is_no(text):
            self.assistant.pending_follow_up = None
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Dobrze. Nie usuwam przypomnień.",
                    "Okay. I will not delete reminders.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_reminders_clear_declined",
                metadata={"follow_up_type": "confirm_reminders_clear"},
            )

        return self.assistant.deliver_text_response(
            self.assistant._localized(
                language,
                "Powiedz tak albo nie.",
                "Please say yes or no.",
            ),
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="pending_reminders_clear_retry",
            metadata={"follow_up_type": "confirm_reminders_clear"},
        )

    def _handle_confirm_reminder_delete(self, *, text: str, language: str) -> bool:
        follow_up = self.assistant.pending_follow_up or {}
        reminder_id = str(follow_up.get("reminder_id", "")).strip()
        reminder_message = str(follow_up.get("message", "")).strip()

        if self._is_yes(text):
            self.assistant.pending_follow_up = None
            deleted = self._reminder_delete(reminder_id)

            if not deleted:
                return self.assistant.deliver_text_response(
                    self.assistant._localized(
                        language,
                        "Nie mogę już znaleźć tego przypomnienia.",
                        "I cannot find that reminder anymore.",
                    ),
                    language=language,
                    route_kind=RouteKind.CONVERSATION,
                    source="pending_reminder_delete_missing",
                    metadata={"follow_up_type": "confirm_reminder_delete", "reminder_id": reminder_id},
                )

            label = reminder_message or reminder_id
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    f"Dobrze. Usunęłam przypomnienie {label}.",
                    f"Okay. I deleted the reminder {label}.",
                ),
                language=language,
                route_kind=RouteKind.ACTION,
                source="pending_reminder_delete_confirmed",
                metadata={
                    "follow_up_type": "confirm_reminder_delete",
                    "reminder_id": reminder_id,
                    "message": reminder_message,
                },
            )

        if self._is_no(text):
            self.assistant.pending_follow_up = None
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Dobrze. Nie usuwam przypomnienia.",
                    "Okay. I will not delete the reminder.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_reminder_delete_declined",
                metadata={"follow_up_type": "confirm_reminder_delete", "reminder_id": reminder_id},
            )

        return self.assistant.deliver_text_response(
            self.assistant._localized(
                language,
                "Powiedz tak albo nie.",
                "Please say yes or no.",
            ),
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="pending_reminder_delete_retry",
            metadata={"follow_up_type": "confirm_reminder_delete", "reminder_id": reminder_id},
        )

    # ------------------------------------------------------------------
    # Exit / shutdown
    # ------------------------------------------------------------------

    def _handle_confirm_exit(self, *, text: str, language: str) -> bool:
        if self._is_yes(text):
            self.assistant.pending_follow_up = None

            display = getattr(self.assistant, "display", None)
            if display is not None:
                try:
                    display.show_block(
                        self.assistant._localized(language, "DO WIDZENIA", "GOODBYE"),
                        [self.assistant._localized(language, "zamykam asystenta", "closing assistant")],
                        duration=4.0,
                    )
                except Exception:
                    pass

            self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Dobrze. Zamykam asystenta.",
                    "Okay. Closing the assistant.",
                ),
                language=language,
                route_kind=RouteKind.ACTION,
                source="pending_confirm_exit",
                metadata={"follow_up_type": "confirm_exit"},
            )
            return False

        if self._is_no(text):
            self.assistant.pending_follow_up = None
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Dobrze. Zostaję włączona.",
                    "Okay. I will stay on.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_decline_exit",
                metadata={"follow_up_type": "confirm_exit"},
            )

        return self.assistant.deliver_text_response(
            self.assistant._localized(
                language,
                "Powiedz tak albo nie.",
                "Please say yes or no.",
            ),
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="pending_retry_exit",
            metadata={"follow_up_type": "confirm_exit"},
        )

    def _handle_confirm_shutdown(self, *, text: str, language: str) -> bool:
        if self._is_yes(text):
            self.assistant.pending_follow_up = None
            self.assistant.shutdown_requested = True

            display = getattr(self.assistant, "display", None)
            if display is not None:
                try:
                    display.show_block(
                        self.assistant._localized(language, "WYŁĄCZANIE", "SHUTTING DOWN"),
                        [
                            self.assistant._localized(language, "zamykam asystenta", "closing assistant"),
                            self.assistant._localized(language, "i system", "and system"),
                        ],
                        duration=2.2,
                    )
                except Exception:
                    pass

            self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Dobrze. Zamykam asystenta i wyłączam system.",
                    "Okay. I am closing the assistant and shutting down the system.",
                ),
                language=language,
                route_kind=RouteKind.ACTION,
                source="pending_confirm_shutdown",
                metadata={"follow_up_type": "confirm_shutdown"},
            )
            return False

        if self._is_no(text):
            self.assistant.pending_follow_up = None
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Dobrze. Nie wyłączam systemu.",
                    "Okay. I will not shut down the system.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_decline_shutdown",
                metadata={"follow_up_type": "confirm_shutdown"},
            )

        return self.assistant.deliver_text_response(
            self.assistant._localized(
                language,
                "Powiedz tak albo nie.",
                "Please say yes or no.",
            ),
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="pending_retry_shutdown",
            metadata={"follow_up_type": "confirm_shutdown"},
        )

    # ------------------------------------------------------------------
    # Internal execution helpers
    # ------------------------------------------------------------------

    def _execute_action_intent(self, payload: PendingIntentPayload, language: str) -> bool:
        action_flow = getattr(self.assistant, "action_flow", None)
        if action_flow is None:
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Moduł akcji nie jest jeszcze gotowy.",
                    "The action module is not ready yet.",
                ),
                language=language,
                route_kind=RouteKind.UNCLEAR,
                source="pending_action_module_missing",
                metadata={"action": payload.action},
            )

        execute_intent = getattr(action_flow, "execute_intent", None)
        if callable(execute_intent):
            return bool(execute_intent(payload, language))

        execute = getattr(action_flow, "execute", None)
        if callable(execute):
            return bool(execute(payload=payload, language=language))

        return self.assistant.deliver_text_response(
            self.assistant._localized(
                language,
                "Moduł akcji nie ma właściwej metody wykonania.",
                "The action module does not expose a valid execution method.",
            ),
            language=language,
            route_kind=RouteKind.UNCLEAR,
            source="pending_action_execute_missing",
            metadata={"action": payload.action},
        )

    def _extract_pending_override_intent(self, text: str) -> PendingIntentPayload | None:
        command_flow = getattr(self.assistant, "command_flow", None)
        extractor = getattr(command_flow, "extract_pending_override_intent", None)
        if callable(extractor):
            try:
                result = extractor(text)
                payload = self._coerce_intent_payload(result)
                if payload is not None:
                    return payload
            except Exception as error:
                LOGGER.warning("Pending override probe via command flow failed: %s", error)

        parser = getattr(self.assistant, "parser", None)
        parse_method = getattr(parser, "parse", None)
        if not callable(parse_method):
            return None

        try:
            result = parse_method(text)
        except Exception as error:
            LOGGER.warning("Pending override probe via parser failed: %s", error)
            return None

        return self._coerce_intent_payload(result)

    def _coerce_intent_payload(self, result: Any) -> PendingIntentPayload | None:
        if result is None:
            return None

        action = str(getattr(result, "action", "") or "").strip().lower()
        if not action and isinstance(result, dict):
            action = str(result.get("action", "") or "").strip().lower()

        if action in {"", "unknown", "unclear", "confirm_yes", "confirm_no"}:
            return None

        if isinstance(result, dict):
            data = dict(result.get("data", result.get("payload", {})) or {})
            normalized_text = str(result.get("normalized_text", "") or "")
            confidence = float(result.get("confidence", 1.0) or 1.0)
            needs_confirmation = bool(result.get("needs_confirmation", False))
            suggestions = list(result.get("suggestions", []) or [])
        else:
            data = dict(getattr(result, "data", {}) or {})
            normalized_text = str(getattr(result, "normalized_text", "") or "")
            confidence = float(getattr(result, "confidence", 1.0) or 1.0)
            needs_confirmation = bool(getattr(result, "needs_confirmation", False))
            suggestions = list(getattr(result, "suggestions", []) or [])

        return PendingIntentPayload(
            action=action,
            data=data,
            normalized_text=normalized_text or normalize_text(action),
            confidence=confidence,
            needs_confirmation=needs_confirmation,
            suggestions=suggestions,
        )

    def _find_action_in_text(
        self,
        text: str,
        *,
        allowed_actions: list[str] | None = None,
    ) -> str | None:
        parser = getattr(self.assistant, "parser", None)
        find_method = getattr(parser, "find_action_in_text", None)
        if callable(find_method):
            try:
                action = find_method(text, allowed_actions=allowed_actions)
                clean = str(action or "").strip()
                return clean or None
            except Exception:
                pass

        normalized = normalize_text(text)
        for action in allowed_actions or []:
            action_text = str(action).replace("_", " ")
            if action_text in normalized:
                return action
        return None

    def _start_timer_mode(
        self,
        *,
        minutes: float,
        mode: str,
        language: str,
        source: str,
    ) -> bool:
        timer = getattr(self.assistant, "timer", None)
        start_method = getattr(timer, "start", None)

        if not callable(start_method):
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Moduł timera nie jest jeszcze gotowy.",
                    "The timer module is not ready yet.",
                ),
                language=language,
                route_kind=RouteKind.UNCLEAR,
                source=f"{source}_missing_timer",
                metadata={"mode": mode, "minutes": minutes},
            )

        try:
            result = start_method(float(minutes), mode)
        except TypeError:
            result = start_method(mode=mode, minutes=float(minutes))
        except Exception as error:
            LOGGER.warning("Timer start failed from pending flow: mode=%s error=%s", mode, error)
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Nie udało mi się uruchomić timera.",
                    "I could not start the timer.",
                ),
                language=language,
                route_kind=RouteKind.UNCLEAR,
                source=f"{source}_timer_error",
                metadata={"mode": mode, "minutes": minutes},
            )

        if self._result_ok(result):
            LOGGER.info("Timer started from pending flow: mode=%s minutes=%s source=%s", mode, minutes, source)
            return True

        fallback_message = self._result_message(result) or self.assistant._localized(
            language,
            "Nie mogę teraz uruchomić timera.",
            "I cannot start the timer right now.",
        )
        return self.assistant.deliver_text_response(
            fallback_message,
            language=language,
            route_kind=RouteKind.ACTION,
            source=f"{source}_timer_not_started",
            metadata={"mode": mode, "minutes": minutes},
        )

    def _memory_clear_count(self) -> int:
        memory = getattr(self.assistant, "memory", None)
        clear_method = self._first_callable(memory, "clear", "wipe", "delete_all")
        if clear_method is None:
            return 0
        try:
            return int(clear_method() or 0)
        except Exception:
            return 0

    def _reminders_clear_count(self) -> int:
        reminders = getattr(self.assistant, "reminders", None)
        clear_method = self._first_callable(reminders, "clear", "delete_all", "clear_all", "remove_all")
        if clear_method is None:
            return 0
        try:
            return int(clear_method() or 0)
        except Exception:
            return 0

    def _reminder_delete(self, reminder_id: str) -> bool:
        reminders = getattr(self.assistant, "reminders", None)
        delete_method = self._first_callable(reminders, "delete", "delete_by_id", "remove_by_id")
        if delete_method is None:
            return False
        try:
            return bool(delete_method(reminder_id))
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Pending state helpers
    # ------------------------------------------------------------------

    def _follow_up_language(self, command_lang: str) -> str:
        follow_up = self.assistant.pending_follow_up or {}
        stored = str(follow_up.get("lang", follow_up.get("language", ""))).strip().lower()
        if stored in {"pl", "en"}:
            return stored
        return self._normalize_language(command_lang)

    def _is_yes(self, text: str) -> bool:
        return self._parse_confirmation_action(text) == "confirm_yes"

    def _is_no(self, text: str) -> bool:
        return self._parse_confirmation_action(text) == "confirm_no"

    def _parse_confirmation_action(self, text: str) -> str | None:
        parser = getattr(self.assistant, "parser", None)
        parse_method = getattr(parser, "parse", None)
        if callable(parse_method):
            try:
                result = parse_method(text)
                action = str(getattr(result, "action", "")).strip().lower()
                if action in {"confirm_yes", "confirm_no"}:
                    return action
                if isinstance(result, dict):
                    action = str(result.get("action", "")).strip().lower()
                    if action in {"confirm_yes", "confirm_no"}:
                        return action
            except Exception:
                pass

        normalized = normalize_text(text)
        yes_tokens = {
            "yes",
            "yeah",
            "yep",
            "sure",
            "correct",
            "tak",
            "jasne",
            "pewnie",
            "zgadza sie",
            "zgadza się",
            "potwierdzam",
        }
        no_tokens = {
            "no",
            "nope",
            "cancel",
            "stop",
            "never mind",
            "nie",
            "nie teraz",
            "anuluj",
            "zostaw to",
            "nieważne",
            "niewazne",
        }

        if normalized in yes_tokens:
            return "confirm_yes"
        if normalized in no_tokens:
            return "confirm_no"
        return None

    def _looks_like_cancel_request(self, text: str) -> bool:
        cancel_method = getattr(self.assistant, "_looks_like_cancel_request", None)
        if callable(cancel_method):
            try:
                return bool(cancel_method(text))
            except Exception:
                pass
        return self._is_no(text)

    def _parse_confirmation_choice(self, text: str) -> int | None:
        normalized = normalize_text(text)
        direct_map = {
            "1": 0,
            "one": 0,
            "first": 0,
            "pierwsza": 0,
            "pierwszy": 0,
            "pierwsze": 0,
            "1st": 0,
            "2": 1,
            "two": 1,
            "second": 1,
            "druga": 1,
            "drugi": 1,
            "drugie": 1,
            "2nd": 1,
        }
        return direct_map.get(normalized)

    def _extract_minutes_from_text(self, text: str) -> float | None:
        raw = str(text or "").strip()
        if not raw:
            return None

        normalized_ascii = self._normalize_for_numbers(raw)

        seconds_match = re.search(
            r"\b(\d+(?:[.,]\d+)?)\s*(?:s|sec|secs|second|seconds|sekunda|sekundy|sekund)\b",
            normalized_ascii,
        )
        if seconds_match:
            value = self._safe_float(seconds_match.group(1))
            if value is not None and value > 0:
                return max(value / 60.0, 1.0 / 60.0)

        minutes_match = re.search(
            r"\b(\d+(?:[.,]\d+)?)\s*(?:m|min|mins|minute|minutes|minuta|minuty|minut)\b",
            normalized_ascii,
        )
        if minutes_match:
            value = self._safe_float(minutes_match.group(1))
            if value is not None and value > 0:
                return value

        plain_number_match = re.search(r"\b(\d+(?:[.,]\d+)?)\b", normalized_ascii)
        if plain_number_match:
            value = self._safe_float(plain_number_match.group(1))
            if value is not None and value > 0:
                return value

        spoken_map = {
            "one": 1,
            "two": 2,
            "three": 3,
            "four": 4,
            "five": 5,
            "six": 6,
            "seven": 7,
            "eight": 8,
            "nine": 9,
            "ten": 10,
            "jeden": 1,
            "jedna": 1,
            "dwa": 2,
            "dwie": 2,
            "trzy": 3,
            "cztery": 4,
            "piec": 5,
            "pięć": 5,
            "szesc": 6,
            "sześć": 6,
            "siedem": 7,
            "osiem": 8,
            "dziewiec": 9,
            "dziewięć": 9,
            "dziesiec": 10,
            "dziesięć": 10,
        }

        for token in normalized_ascii.split():
            if token in spoken_map:
                return float(spoken_map[token])

        return None

    def _extract_name(self, text: str) -> str | None:
        raw = str(text or "").strip()
        if not raw:
            return None

        patterns = [
            r"\b(?:mam na imie|mam na imię|nazywam sie|nazywam się|jestem)\s+([A-Za-zÀ-ÿ' -]{2,})$",
            r"\b(?:my name is|i am|i'm)\s+([A-Za-zÀ-ÿ' -]{2,})$",
        ]

        for pattern in patterns:
            match = re.search(pattern, raw, flags=re.IGNORECASE)
            if not match:
                continue
            first_token = match.group(1).strip().split()[0]
            normalized = self._normalize_name_token(first_token)
            if normalized:
                return normalized

        simple_tokens = re.findall(r"[A-Za-zÀ-ÿ'-]+", raw)
        if len(simple_tokens) == 1:
            return self._normalize_name_token(simple_tokens[0])

        return None

    @staticmethod
    def _normalize_name_token(token: str) -> str | None:
        cleaned = str(token or "").strip(" '-")
        if not cleaned:
            return None

        lowered = cleaned.lower()
        blocked = {
            "assistant",
            "timer",
            "focus",
            "break",
            "time",
            "date",
            "day",
            "help",
            "yes",
            "no",
            "tak",
            "nie",
        }
        if lowered in blocked:
            return None

        if not re.fullmatch(r"[A-Za-zÀ-ÿ'-]{2,20}", cleaned):
            return None

        return cleaned[:1].upper() + cleaned[1:].lower()

    @staticmethod
    def _normalize_for_numbers(text: str) -> str:
        lowered = str(text or "").strip().lower()
        lowered = unicodedata.normalize("NFKD", lowered)
        lowered = "".join(ch for ch in lowered if not unicodedata.combining(ch))
        lowered = lowered.replace("ł", "l")
        lowered = re.sub(r"[^a-z0-9\s.,]", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered

    @staticmethod
    def _safe_float(value: str) -> float | None:
        raw = str(value or "").replace(",", ".").strip()
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = str(language or "").strip().lower()
        return "pl" if normalized.startswith("pl") else "en"

    @staticmethod
    def _first_callable(obj: Any, *names: str):
        for name in names:
            method = getattr(obj, name, None)
            if callable(method):
                return method
        return None

    @staticmethod
    def _result_ok(result: Any) -> bool:
        if isinstance(result, tuple) and result:
            return bool(result[0])
        if isinstance(result, bool):
            return result
        if isinstance(result, dict):
            if "ok" in result:
                return bool(result["ok"])
            if "success" in result:
                return bool(result["success"])
        return bool(result)

    @staticmethod
    def _result_message(result: Any) -> str:
        if isinstance(result, tuple) and len(result) >= 2:
            return str(result[1] or "").strip()
        if isinstance(result, dict):
            for key in ("message", "detail", "error"):
                value = result.get(key)
                if value:
                    return str(value).strip()
        return ""

    @staticmethod
    def _coerce_suggestions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        suggestions: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            action = str(item.get("action", "")).strip().lower()
            if not action:
                continue
            normalized = {
                "action": action,
                "payload": dict(item.get("payload", {}) or {}),
                "confidence": float(item.get("confidence", 1.0) or 1.0),
            }
            label = str(item.get("label", "")).strip()
            if label:
                normalized["label"] = label
            suggestions.append(normalized)
        return suggestions


__all__ = [
    "PendingFlowDecision",
    "PendingFlowOrchestrator",
]