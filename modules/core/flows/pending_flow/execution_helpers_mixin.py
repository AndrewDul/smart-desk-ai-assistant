from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RouteKind, normalize_text
from modules.shared.logging.logger import get_logger

from .models import PendingIntentPayload

LOGGER = get_logger(__name__)


class PendingFlowExecutionHelpersMixin:
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
            LOGGER.info(
                "Timer started from pending flow: mode=%s minutes=%s source=%s",
                mode,
                minutes,
                source,
            )
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