from __future__ import annotations

import re
from typing import Any

from modules.runtime.contracts import RouteKind
from modules.shared.logging.logger import get_logger

from .models import PendingFlowDecision

LOGGER = get_logger(__name__)


class PendingFlowFollowUpMixin:
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

        if follow_type == "clarification_repeat":
            return self._handle_clarification_repeat_follow_up(
                text=routing_text,
                language=lang,
            )

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

        if follow_type == "focus_start_offer":
            result = self._handle_focus_start_offer(text=routing_text, language=lang)
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:focus_start_offer",
            )

        if follow_type == "focus_extend_offer":
            result = self._handle_focus_extend_offer(text=routing_text, language=lang)
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:focus_extend_offer",
            )

        if follow_type == "break_extend_offer":
            result = self._handle_break_extend_offer(text=routing_text, language=lang)
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:break_extend_offer",
            )

        if follow_type == "break_to_focus_offer":
            result = self._handle_break_to_focus_offer(text=routing_text, language=lang)
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:break_to_focus_offer",
            )

        if follow_type == "post_focus_break_offer":
            result = self._handle_post_focus_break_offer(text=routing_text, language=lang)
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:post_focus_break_offer",
            )

        if follow_type == "reminder_time":
            result = self._handle_reminder_time_follow_up(text=routing_text, language=lang)
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:reminder_time",
            )

        if follow_type == "reminder_message":
            result = self._handle_reminder_message_follow_up(text=routing_text, language=lang)
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:reminder_message",
            )

        if follow_type == "memory_message":
            result = self._handle_memory_message_follow_up(text=routing_text, language=lang)
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:memory_message",
            )

        if follow_type == "memory_person_name":
            result = self._handle_memory_person_name_follow_up(text=routing_text, language=lang)
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:memory_person_name",
            )

        if follow_type == "memory_object_name":
            result = self._handle_memory_object_name_follow_up(text=routing_text, language=lang)
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:memory_object_name",
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

    def _handle_clarification_repeat_follow_up(
        self,
        *,
        text: str,
        language: str,
    ) -> PendingFlowDecision:
        follow_up = dict(self.assistant.pending_follow_up or {})
        try:
            retry_count = max(0, int(follow_up.get("retry_count", 0) or 0))
        except (TypeError, ValueError):
            retry_count = 0
        try:
            max_retries = max(1, int(follow_up.get("max_retries", 1) or 1))
        except (TypeError, ValueError):
            max_retries = 1

        if self._is_no(text) or self._looks_like_cancel_request(text):
            self.assistant.pending_follow_up = None
            result = self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Dobrze, anuluję.",
                    "Okay, I’ll cancel it.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_clarification_cancelled",
                metadata={"follow_up_type": "clarification_repeat"},
            )
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:clarification_repeat_cancel",
            )

        if self._is_yes(text):
            if retry_count >= max_retries:
                self.assistant.pending_follow_up = None
                self.assistant._return_to_wake_standby_after_response = True
                result = self.assistant.deliver_text_response(
                    self.assistant._localized(
                        language,
                        "Dobrze, anuluję.",
                        "Okay, I’ll cancel it.",
                    ),
                    language=language,
                    route_kind=RouteKind.CONVERSATION,
                    source="pending_clarification_retry_exhausted",
                    metadata={"follow_up_type": "clarification_repeat"},
                )
                return PendingFlowDecision(
                    handled=True,
                    response=result,
                    consumed_by="follow_up:clarification_repeat_exhausted",
                )

            self.assistant.pending_follow_up = {
                **follow_up,
                "type": "clarification_repeat",
                "language": language,
                "retry_count": retry_count + 1,
                "max_retries": max_retries,
                "window_seconds": float(follow_up.get("window_seconds", 5.5) or 5.5),
            }
            result = self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Powtórz proszę komendę.",
                    "Please repeat the command.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_clarification_retry_prompt",
                metadata={
                    "follow_up_type": "clarification_repeat",
                    "retry_count": retry_count + 1,
                    "max_retries": max_retries,
                },
            )
            return PendingFlowDecision(
                handled=True,
                response=result,
                consumed_by="follow_up:clarification_repeat_retry",
            )

        self.assistant._last_clarification_repeat_context = {
            "retry_count": retry_count,
            "max_retries": max_retries,
        }
        self.assistant.pending_follow_up = None
        return PendingFlowDecision(handled=False)

    def _handle_duration_follow_up(
        self,
        *,
        follow_type: str,
        text: str,
        language: str,
    ) -> bool:
        minutes = self._extract_minutes_from_text(text)
        if minutes is None or minutes <= 0:
            if follow_type in {"focus_duration", "break_duration"} and self._is_unknown_duration_answer(text):
                follow_up = self.assistant.pending_follow_up or {}
                fallback = (
                    getattr(self.assistant, "default_focus_minutes", 25.0)
                    if follow_type == "focus_duration"
                    else getattr(self.assistant, "default_break_minutes", 5.0)
                )
                minutes = float(follow_up.get("default_minutes", fallback) or fallback)
                LOGGER.info(
                    "Default duration selected from unknown answer: follow_up_type=%s minutes=%s language=%s",
                    follow_type,
                    minutes,
                    language,
                )
            else:
                return self.assistant.deliver_text_response(
                    self.assistant._localized(
                        language,
                        "Powiedz czas, na przykład: dwadzieścia pięć minut. Możesz też powiedzieć: nie wiem.",
                        "Tell me the duration, for example: twenty five minutes. You can also say: I don't know.",
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

    def _handle_focus_start_offer(self, *, text: str, language: str) -> bool:
        if self._is_yes(text):
            default_focus = float(getattr(self.assistant, "default_focus_minutes", 25.0))
            self.assistant.pending_follow_up = {
                "type": "focus_duration",
                "language": language,
                "mode": "focus",
                "default_minutes": default_focus,
                "source": "pending_focus_start_offer_yes",
            }
            LOGGER.info(
                "Focus start accepted; asking for duration: language=%s default_minutes=%s",
                language,
                default_focus,
            )
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Ile czasu chcesz się skupić?",
                    "How long do you want to focus?",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_focus_start_duration_prompt",
                metadata={"follow_up_type": "focus_duration"},
            )

        if self._is_no(text):
            self.assistant.pending_follow_up = None
            return self._deliver_ready_after_decline(
                language=language,
                source="pending_focus_start_declined",
                follow_up_type="focus_start_offer",
            )

        return self._deliver_yes_no_retry(
            language=language,
            source="pending_focus_start_retry",
            follow_up_type="focus_start_offer",
            polish_text="Powiedz tak albo nie. Chcesz uruchomić skupienie?",
            english_text="Say yes or no. Do you want to start focus mode?",
        )

    def _handle_focus_extend_offer(self, *, text: str, language: str) -> bool:
        if self._is_yes(text):
            default_focus = float(getattr(self.assistant, "default_focus_minutes", 25.0))
            self.assistant.pending_follow_up = {
                "type": "focus_duration",
                "language": language,
                "mode": "focus",
                "default_minutes": default_focus,
                "source": "pending_focus_extend_yes",
            }
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Na ile przedłużamy skupienie?",
                    "How long do you want to extend focus mode?",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_focus_extend_duration_prompt",
                metadata={"follow_up_type": "focus_duration"},
            )

        if self._is_no(text):
            self.assistant.pending_follow_up = {
                "type": "post_focus_break_offer",
                "language": language,
                "default_minutes": float(getattr(self.assistant, "default_break_minutes", 5.0)),
                "source": "pending_focus_extend_declined",
            }
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Chcesz teraz odpocząć?",
                    "Do you want to take a break?",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_focus_break_offer_prompt",
                metadata={"follow_up_type": "post_focus_break_offer"},
            )

        return self._deliver_yes_no_retry(
            language=language,
            source="pending_focus_extend_retry",
            follow_up_type="focus_extend_offer",
            polish_text="Powiedz tak albo nie. Chcesz przedłużyć skupienie?",
            english_text="Say yes or no. Do you want to extend focus mode?",
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
            default_break = float(getattr(self.assistant, "default_break_minutes", 5.0))
            self.assistant.pending_follow_up = {
                "type": "break_duration",
                "language": language,
                "mode": "break",
                "default_minutes": default_break,
                "source": "pending_post_focus_break_yes",
            }
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Na ile ustawiam odpoczynek?",
                    "How long do you want to take a break?",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_break_duration_prompt",
                metadata={"follow_up_type": "break_duration"},
            )

        if self._is_no(text):
            self.assistant.pending_follow_up = None
            return self._deliver_ready_after_decline(
                language=language,
                source="pending_post_focus_break_declined",
                follow_up_type="post_focus_break_offer",
            )

        return self._deliver_yes_no_retry(
            language=language,
            source="pending_post_focus_break_retry",
            follow_up_type="post_focus_break_offer",
            polish_text="Powiedz tak, nie albo od razu podaj długość odpoczynku.",
            english_text="Say yes, no, or tell me the break duration right away.",
        )

    def _handle_break_extend_offer(self, *, text: str, language: str) -> bool:
        if self._is_yes(text):
            default_break = float(getattr(self.assistant, "default_break_minutes", 5.0))
            self.assistant.pending_follow_up = {
                "type": "break_duration",
                "language": language,
                "mode": "break",
                "default_minutes": default_break,
                "source": "pending_break_extend_yes",
            }
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Na ile przedłużamy odpoczynek?",
                    "How long do you want to extend your break?",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_break_extend_duration_prompt",
                metadata={"follow_up_type": "break_duration"},
            )

        if self._is_no(text):
            self.assistant.pending_follow_up = {
                "type": "break_to_focus_offer",
                "language": language,
                "default_minutes": float(getattr(self.assistant, "default_focus_minutes", 25.0)),
                "source": "pending_break_extend_declined",
            }
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Chcesz wrócić do skupienia?",
                    "Do you want to return to focus mode?",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_break_to_focus_offer_prompt",
                metadata={"follow_up_type": "break_to_focus_offer"},
            )

        return self._deliver_yes_no_retry(
            language=language,
            source="pending_break_extend_retry",
            follow_up_type="break_extend_offer",
            polish_text="Powiedz tak albo nie. Chcesz przedłużyć odpoczynek?",
            english_text="Say yes or no. Do you want to extend your break?",
        )

    def _handle_break_to_focus_offer(self, *, text: str, language: str) -> bool:
        if self._is_yes(text):
            default_focus = float(getattr(self.assistant, "default_focus_minutes", 25.0))
            self.assistant.pending_follow_up = {
                "type": "focus_duration",
                "language": language,
                "mode": "focus",
                "default_minutes": default_focus,
                "source": "pending_break_to_focus_yes",
            }
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Ile czasu chcesz się skupić?",
                    "How long do you want to focus?",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_break_to_focus_duration_prompt",
                metadata={"follow_up_type": "focus_duration"},
            )

        if self._is_no(text):
            self.assistant.pending_follow_up = None
            return self._deliver_ready_after_decline(
                language=language,
                source="pending_break_to_focus_declined",
                follow_up_type="break_to_focus_offer",
            )

        return self._deliver_yes_no_retry(
            language=language,
            source="pending_break_to_focus_retry",
            follow_up_type="break_to_focus_offer",
            polish_text="Powiedz tak albo nie. Chcesz wrócić do skupienia?",
            english_text="Say yes or no. Do you want to return to focus mode?",
        )

    def _deliver_ready_after_decline(self, *, language: str, source: str, follow_up_type: str) -> bool:
        return self.assistant.deliver_text_response(
            self.assistant._localized(
                language,
                "Jasne. Zostaję w gotowości.",
                "Okay. I will stay ready.",
            ),
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source=source,
            metadata={"follow_up_type": follow_up_type},
        )

    def _deliver_yes_no_retry(
        self,
        *,
        language: str,
        source: str,
        follow_up_type: str,
        polish_text: str,
        english_text: str,
    ) -> bool:
        return self.assistant.deliver_text_response(
            self.assistant._localized(language, polish_text, english_text),
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source=source,
            metadata={"follow_up_type": follow_up_type},
        )

    def _handle_reminder_time_follow_up(self, *, text: str, language: str) -> bool:
        parsed = self._parse_reminder_time_answer(text, language=language)
        if parsed is None:
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Nie złapałam czasu. Powiedz na przykład: za 15 minut albo o 18:30.",
                    "I did not catch the time. Say for example: in 15 minutes or at 6:30 PM.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_reminder_time_retry",
                metadata={"follow_up_type": "reminder_time"},
            )

        follow_up = self.assistant.pending_follow_up or {}
        existing_message = str(follow_up.get("message", "") or "").strip()
        if existing_message:
            return self._save_guided_reminder(
                seconds=parsed.seconds,
                message=existing_message,
                language=language,
                time_label=parsed.display_phrase,
                source="pending_reminder_time_with_existing_message",
            )

        self.assistant.pending_follow_up = {
            "type": "reminder_message",
            "language": language,
            "seconds": parsed.seconds,
            "time_label": parsed.display_phrase,
            "due_at": parsed.due_at.isoformat(),
        }
        return self.assistant.deliver_text_response(
            self.assistant._localized(
                language,
                "Dobrze. Co przypomnieć?",
                "Okay. What should I remind you?",
            ),
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="pending_reminder_message_prompt",
            metadata={
                "follow_up_type": "reminder_message",
                "seconds": parsed.seconds,
                "time_label": parsed.display_phrase,
            },
        )

    def _handle_reminder_message_follow_up(self, *, text: str, language: str) -> bool:
        follow_up = self.assistant.pending_follow_up or {}
        seconds = int(follow_up.get("seconds", 0) or 0)
        time_label = str(follow_up.get("time_label", "") or "").strip()
        message = self._clean_reminder_message_answer(text)

        if seconds <= 0:
            self.assistant.pending_follow_up = None
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Zgubiłam czas przypomnienia. Zacznijmy jeszcze raz.",
                    "I lost the reminder time. Let us start again.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_reminder_message_missing_time",
                metadata={"follow_up_type": "reminder_message"},
            )

        if not message:
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Powiedz proszę, co mam Ci przypomnieć.",
                    "Please tell me what I should remind you about.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_reminder_message_retry",
                metadata={"follow_up_type": "reminder_message", "seconds": seconds},
            )

        return self._save_guided_reminder(
            seconds=seconds,
            message=message,
            language=language,
            time_label=time_label,
            source="pending_reminder_message_saved",
        )

    def _save_guided_reminder(
        self,
        *,
        seconds: int,
        message: str,
        language: str,
        time_label: str,
        source: str,
    ) -> bool:
        reminders = getattr(self.assistant, "reminders", None)
        add_method = self._first_callable(
            reminders,
            "add_after_seconds",
            "add_in_seconds",
            "create_after_seconds",
        )
        if add_method is None:
            self.assistant.pending_follow_up = None
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Moduł przypomnień nie jest jeszcze gotowy.",
                    "The reminders module is not ready yet.",
                ),
                language=language,
                route_kind=RouteKind.UNCLEAR,
                source=f"{source}_missing_reminder_service",
                metadata={"follow_up_type": "reminder_message"},
            )

        clean_message = self._clean_reminder_message_answer(message)
        try:
            reminder = add_method(
                seconds=int(seconds),
                message=clean_message,
                language=language,
            )
        except Exception as error:
            self.assistant.pending_follow_up = None
            LOGGER.warning("Guided reminder save failed: %s", error)
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Nie udało mi się zapisać przypomnienia.",
                    "I could not save the reminder.",
                ),
                language=language,
                route_kind=RouteKind.UNCLEAR,
                source=f"{source}_save_failed",
                metadata={"follow_up_type": "reminder_message"},
            )

        self.assistant.pending_follow_up = None
        reminder_id = ""
        if isinstance(reminder, dict):
            reminder_id = str(reminder.get("id", "") or "").strip()

        spoken_time = time_label or self.assistant._localized(
            language,
            "w podanym czasie",
            "at the requested time",
        )
        return self.assistant.deliver_text_response(
            self.assistant._localized(
                language,
                f"Gotowe. Przypomnę {spoken_time}.",
                f"Done. Reminder set {spoken_time}.",
            ),
            language=language,
            route_kind=RouteKind.ACTION,
            source=source,
            metadata={
                "follow_up_type": "reminder_message",
                "seconds": int(seconds),
                "message": clean_message,
                "reminder_id": reminder_id,
            },
        )

    def _handle_memory_message_follow_up(self, *, text: str, language: str) -> bool:
        memory_text = str(text or "").strip()

        if not memory_text:
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Powiedz proszę, co mam zapamiętać.",
                    "Please tell me what I should remember.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_memory_message_retry",
                metadata={"follow_up_type": "memory_message"},
            )

        if self._is_no(memory_text):
            self.assistant.pending_follow_up = None
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Dobrze. Nie zapisuję tego w pamięci.",
                    "Okay. I will not save that to memory.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_memory_message_cancelled",
                metadata={"follow_up_type": "memory_message"},
            )

        memory = getattr(self.assistant, "memory", None)
        remember_text_method = getattr(memory, "remember_text", None)
        if not callable(remember_text_method):
            self.assistant.pending_follow_up = None
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Moduł pamięci nie jest jeszcze gotowy.",
                    "The memory module is not ready yet.",
                ),
                language=language,
                route_kind=RouteKind.UNCLEAR,
                source="pending_memory_message_unavailable",
                metadata={"follow_up_type": "memory_message"},
            )

        suspicious_method = getattr(memory, "looks_like_suspicious_memory_text", None)
        if callable(suspicious_method) and suspicious_method(memory_text, language=language):
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Nie jestem pewna, czy dobrze usłyszałam. Powiedz proszę jeszcze raz, co mam zapamiętać.",
                    "I am not sure I heard that correctly. Please tell me again what I should remember.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_memory_message_suspicious_retry",
                metadata={
                    "follow_up_type": "memory_message",
                    "raw_text": memory_text,
                },
            )

        prepare_method = getattr(memory, "prepare_memory_text", None)
        prepared_memory_text = memory_text
        if callable(prepare_method):
            prepared_memory_text = str(prepare_method(memory_text, language=language) or "").strip()
        if not prepared_memory_text:
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Powiedz proszę, co mam zapamiętać.",
                    "Please tell me what I should remember.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_memory_message_retry",
                metadata={"follow_up_type": "memory_message"},
            )

        self.assistant.pending_follow_up = None

        try:
            memory_id = remember_text_method(
                prepared_memory_text,
                language=language,
                source="guided_memory_follow_up",
            )
        except TypeError:
            try:
                memory_id = remember_text_method(prepared_memory_text, language=language)
            except TypeError:
                memory_id = remember_text_method(prepared_memory_text)
        except Exception as error:
            LOGGER.warning("Guided memory save failed: %s", error)
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Nie udało mi się zapisać tego w pamięci.",
                    "I could not save that to memory.",
                ),
                language=language,
                route_kind=RouteKind.UNCLEAR,
                source="pending_memory_message_failed",
                metadata={"follow_up_type": "memory_message"},
            )

        LOGGER.info(
            "Guided memory saved: language=%s memory_id=%s text=%s",
            language,
            str(memory_id or ""),
            prepared_memory_text,
        )

        return self.assistant.deliver_text_response(
            self.assistant._localized(
                language,
                f"Zapamiętałam: {prepared_memory_text}.",
                f"I remembered: {prepared_memory_text}.",
            ),
            language=language,
            route_kind=RouteKind.ACTION,
            source="pending_memory_message_saved",
            metadata={
                "follow_up_type": "memory_message",
                "memory_id": str(memory_id or "").strip(),
                "language": language,
                "raw_text": memory_text,
                "stored_text": prepared_memory_text,
            },
        )

    def _handle_memory_object_name_follow_up(self, *, text: str, language: str) -> bool:
        pending_follow_up = dict(getattr(self.assistant, "pending_follow_up", {}) or {})
        object_hint = str(pending_follow_up.get("object_hint", "") or "").strip()
        display_name = self._clean_object_memory_display_name(text)
        owner = self._object_owner_from_text(text)

        if not display_name:
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Nie usłyszałam wyraźnie nazwy obiektu. Powiedz proszę, jak mam go nazwać.",
                    "I did not catch the object name clearly. Please tell me what I should call it.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_memory_object_name_retry",
                metadata={"follow_up_type": "memory_object_name"},
            )

        rejection_reason = self._object_memory_name_rejection_reason(
            text=text,
            display_name=display_name,
            object_hint=object_hint,
        )
        if rejection_reason:
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "To nie brzmi jak nazwa obiektu. Powiedz proszę jeszcze raz, jak mam go nazwać.",
                    "That does not sound like an object name. Please tell me again what I should call it.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_memory_object_name_rejected",
                metadata={
                    "follow_up_type": "memory_object_name",
                    "rejection_reason": rejection_reason,
                    "object_hint": object_hint,
                    "raw_text": text,
                    "display_name": display_name,
                },
            )

        memory = getattr(self.assistant, "memory", None)
        prepare_object_slot_method = getattr(memory, "prepare_object_image_capture_slot", None)
        capture_object_method = getattr(memory, "capture_object_image_reference", None)
        remember_object_method = getattr(memory, "remember_object", None)
        if not callable(prepare_object_slot_method) and not callable(remember_object_method):
            self.assistant.pending_follow_up = None
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Moduł pamięci obiektów nie jest jeszcze gotowy.",
                    "The object memory module is not ready yet.",
                ),
                language=language,
                route_kind=RouteKind.UNCLEAR,
                source="pending_memory_object_name_unavailable",
                metadata={"follow_up_type": "memory_object_name"},
            )

        aliases = ["object", "thing"] if str(language).lower().startswith("en") else ["obiekt", "rzecz"]
        object_slot: dict[str, Any] = {}
        self.assistant.pending_follow_up = None
        try:
            if callable(prepare_object_slot_method):
                prepared_slot = prepare_object_slot_method(
                    display_name,
                    aliases=aliases,
                    language=language,
                    owner=owner,
                    source="guided_object_enrollment",
                    metadata={"enrollment_flow": "voice_guided_object"},
                )
                object_slot = dict(prepared_slot or {})
                object_id = str(
                    object_slot.get("object_entity_id")
                    or object_slot.get("object_id")
                    or ""
                ).strip()
            else:
                object_id = remember_object_method(
                    display_name,
                    aliases=aliases,
                    language=language,
                    owner=owner,
                    source="guided_object_enrollment",
                    metadata={"enrollment_flow": "voice_guided_object"},
                )
        except TypeError:
            object_id = remember_object_method(display_name, aliases=aliases, language=language, owner=owner)
        except Exception as error:
            LOGGER.warning("Guided object memory save failed: %s", error)
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Nie udało mi się zapisać tego obiektu w pamięci.",
                    "I could not save that object to memory.",
                ),
                language=language,
                route_kind=RouteKind.UNCLEAR,
                source="pending_memory_object_name_failed",
                metadata={"follow_up_type": "memory_object_name"},
            )

        object_capture_ready = bool(object_slot.get("object_capture_ready", False))
        object_capture_result: dict[str, Any] = {}
        if object_capture_ready and callable(capture_object_method):
            try:
                object_capture_result = dict(
                    capture_object_method(
                        display_name=display_name,
                        aliases=aliases,
                        language=language,
                        owner=owner,
                        source="guided_object_image_capture",
                        slot=object_slot,
                        vision_backend=getattr(self.assistant, "vision", None),
                    )
                    or {}
                )
            except Exception as error:  # pragma: no cover - defensive runtime fallback
                LOGGER.warning("Guided object image capture failed: %s", error)
                object_capture_result = {"ok": False, "reason": error.__class__.__name__}

        object_capture_saved = bool(object_capture_result.get("ok", False))
        response_text = self.assistant._localized(
            language,
            f"Dobrze. Będę pamiętać ten obiekt jako {display_name}.",
            f"Okay. I will remember this object as {display_name}.",
        )
        metadata = {
            "follow_up_type": "memory_object_name",
            "object_id": str(object_id or "").strip(),
            "display_name": display_name,
            "language": language,
            "owner": owner,
            "object_capture_ready": object_capture_ready,
            "object_capture_saved": object_capture_saved,
        }
        if object_slot:
            metadata.update(
                {
                    key: value
                    for key, value in object_slot.items()
                    if key in {
                        "object_entity_id",
                        "object_assets_dir",
                        "next_object_asset_path",
                        "existing_object_asset_count",
                    }
                }
            )
        if object_capture_result:
            metadata.update(
                {
                    "object_capture_reason": str(object_capture_result.get("reason", "") or ""),
                    "object_asset_id": str(object_capture_result.get("asset_id", "") or ""),
                    "object_asset_path": str(object_capture_result.get("path", "") or ""),
                    "object_capture_backend": str(object_capture_result.get("backend", "") or ""),
                    "object_capture_width": int(object_capture_result.get("width", 0) or 0),
                    "object_capture_height": int(object_capture_result.get("height", 0) or 0),
                }
            )

        return self.assistant.deliver_text_response(
            response_text,
            language=language,
            route_kind=RouteKind.ACTION,
            source="pending_memory_object_name_saved",
            metadata=metadata,
        )

    def _handle_memory_person_name_follow_up(self, *, text: str, language: str) -> bool:
        display_name = self._clean_person_memory_display_name(text)

        if not display_name:
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Nie usłyszałam wyraźnie imienia. Powiedz proszę, jak mam Cię nazywać.",
                    "I did not catch the name clearly. Please tell me what I should call you.",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="pending_memory_person_name_retry",
                metadata={"follow_up_type": "memory_person_name"},
            )

        memory = getattr(self.assistant, "memory", None)
        remember_person_method = getattr(memory, "remember_person", None)
        prepare_face_slot_method = getattr(memory, "prepare_person_face_capture_slot", None)
        capture_face_method = getattr(memory, "capture_person_face_reference", None)
        if not callable(remember_person_method):
            self.assistant.pending_follow_up = None
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Moduł pamięci osób nie jest jeszcze gotowy.",
                    "The people memory module is not ready yet.",
                ),
                language=language,
                route_kind=RouteKind.UNCLEAR,
                source="pending_memory_person_name_unavailable",
                metadata={"follow_up_type": "memory_person_name"},
            )

        aliases = ["user", "me", "myself"] if str(language).lower().startswith("en") else ["user", "ja", "mnie", "sobie"]
        face_slot: dict[str, Any] = {}
        self.assistant.pending_follow_up = None
        try:
            if callable(prepare_face_slot_method):
                prepared_slot = prepare_face_slot_method(
                    display_name,
                    aliases=aliases,
                    language=language,
                    source="guided_person_enrollment",
                    metadata={"person_scope": "user", "enrollment_flow": "voice_guided"},
                )
                face_slot = dict(prepared_slot or {})
                person_id = str(
                    face_slot.get("person_entity_id")
                    or face_slot.get("person_id")
                    or ""
                ).strip()
            else:
                person_id = remember_person_method(
                    display_name,
                    aliases=aliases,
                    language=language,
                    source="guided_person_enrollment",
                    metadata={"person_scope": "user", "enrollment_flow": "voice_guided"},
                )
        except TypeError:
            person_id = remember_person_method(display_name, aliases=aliases, language=language)
        except Exception as error:
            LOGGER.warning("Guided person memory save failed: %s", error)
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Nie udało mi się zapisać tej osoby w pamięci.",
                    "I could not save that person to memory.",
                ),
                language=language,
                route_kind=RouteKind.UNCLEAR,
                source="pending_memory_person_name_failed",
                metadata={"follow_up_type": "memory_person_name"},
            )

        face_capture_ready = bool(face_slot.get("face_capture_ready", False))
        face_capture_result: dict[str, Any] = {}
        if face_capture_ready and callable(capture_face_method):
            try:
                face_capture_result = dict(
                    capture_face_method(
                        display_name=display_name,
                        aliases=aliases,
                        language=language,
                        source="guided_person_face_capture",
                        slot=face_slot,
                        vision_backend=getattr(self.assistant, "vision", None),
                    )
                    or {}
                )
            except Exception as error:  # pragma: no cover - defensive runtime fallback
                LOGGER.warning("Guided person face capture failed: %s", error)
                face_capture_result = {"ok": False, "reason": error.__class__.__name__}

        face_capture_saved = bool(face_capture_result.get("ok", False))
        if face_capture_saved:
            response_text = self.assistant._localized(
                language,
                f"Dobrze, {display_name}. Będę Cię już pamiętać.",
                f"Okay, {display_name}. I will remember you now.",
            )
        elif face_capture_ready:
            response_text = self.assistant._localized(
                language,
                f"Dobrze, {display_name}. Będę Cię już pamiętać.",
                f"Okay, {display_name}. I will remember you now.",
            )
        else:
            response_text = self.assistant._localized(
                language,
                f"Dobrze, {display_name}. Będę Cię już pamiętać.",
                f"Okay, {display_name}. I will remember you now.",
            )

        metadata = {
            "follow_up_type": "memory_person_name",
            "person_id": str(person_id or "").strip(),
            "display_name": display_name,
            "language": language,
            "face_capture_ready": face_capture_ready,
            "face_capture_saved": face_capture_saved,
        }
        if face_slot:
            metadata.update(
                {
                    key: value
                    for key, value in face_slot.items()
                    if key in {
                        "person_entity_id",
                        "person_faces_dir",
                        "next_face_asset_path",
                        "existing_face_asset_count",
                    }
                }
            )
        if face_capture_result:
            metadata.update(
                {
                    "face_capture_reason": str(face_capture_result.get("reason", "") or ""),
                    "face_asset_id": str(face_capture_result.get("asset_id", "") or ""),
                    "face_asset_path": str(face_capture_result.get("path", "") or ""),
                    "face_capture_backend": str(face_capture_result.get("backend", "") or ""),
                    "face_capture_width": int(face_capture_result.get("width", 0) or 0),
                    "face_capture_height": int(face_capture_result.get("height", 0) or 0),
                    "face_detected": bool(face_capture_result.get("face_detected", False)),
                    "face_count": int(face_capture_result.get("face_count", 0) or 0),
                    "face_confidence": float(face_capture_result.get("face_confidence", 0.0) or 0.0),
                }
            )

        return self.assistant.deliver_text_response(
            response_text,
            language=language,
            route_kind=RouteKind.ACTION,
            source="pending_memory_person_name_saved",
            metadata=metadata,
        )

    @classmethod
    def _clean_object_memory_display_name(cls, text: str) -> str:
        raw = " ".join(str(text or "").strip().split())
        if not raw:
            return ""

        trim_chars = " .,!?:;" + chr(92) + chr(34) + chr(39)
        normalized = raw.lower().strip(trim_chars)

        prefixes = (
            "to jest mój ",
            "to jest moj ",
            "to jest moja ",
            "to jest moje ",
            "to jest ",
            "nazywa się ",
            "nazywa sie ",
            "nazwij go ",
            "nazwij to ",
            "mój ",
            "moj ",
            "moja ",
            "moje ",
            "this is my ",
            "this is the ",
            "this is ",
            "call it ",
            "call this ",
            "my ",
            "the ",
        )

        for prefix in prefixes:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):].strip()
                break

        normalized = normalized.strip(trim_chars)
        if normalized in {"object", "thing", "obiekt", "rzecz", "to", "this", "that", "it"}:
            return ""

        canonical_name = cls._canonical_object_memory_display_name(normalized)
        if canonical_name:
            return canonical_name

        return cls._title_display_name(normalized)

    @classmethod
    def _canonical_object_memory_display_name(cls, text: str) -> str:
        trim_chars = " .,!?:;" + chr(92) + chr(34) + chr(39)
        normalized = cls._normalize_object_guard_text(text)
        normalized = normalized.strip(trim_chars)

        object_name_corrections = {
            "vape": "Vape",
            "wipe": "Vape",
            "wejp": "Vape",
            "wajp": "Vape",
            "wape": "Vape",
            "vejp": "Vape",
            "e papieros": "E-papieros",
            "epapieros": "E-papieros",
            "e-papieros": "E-papieros",
        }

        return object_name_corrections.get(normalized, "")

    @classmethod
    def _object_memory_name_rejection_reason(
        cls,
        *,
        text: str,
        display_name: str,
        object_hint: str = "",
    ) -> str:
        normalized_text = cls._normalize_object_guard_text(text)
        normalized_display = cls._normalize_object_guard_text(display_name)
        normalized_hint = cls._normalize_object_guard_text(object_hint)
        if not normalized_text or not normalized_display:
            return ""

        command_like_phrases = {
            "pomoc",
            "help",
            "exit",
            "wyjdz",
            "wylacz nexa",
            "pokaż pulpit",
            "pokaz pulpit",
            "show desktop",
            "schowaj pulpit",
            "hide desktop",
            "pokaż sie",
            "pokaz sie",
            "show yourself",
            "pokaż oczy",
            "pokaz oczy",
            "show eyes",
            "spojrz na mnie",
            "patrz na mnie",
            "look at me",
            "co pamietasz",
            "co pamiętasz",
            "what do you remember",
            "kogo znasz",
            "who do you know",
            "jakie obiekty znasz",
            "what objects do you know",
            "zapamietaj",
            "zapamiętaj",
            "remember",
        }
        for phrase in command_like_phrases:
            normalized_phrase = cls._normalize_object_guard_text(phrase)
            if (
                normalized_text == normalized_phrase
                or normalized_text.startswith(normalized_phrase + " ")
                or normalized_display == normalized_phrase
                or normalized_display.startswith(normalized_phrase + " ")
            ):
                return "command_like_object_name"

        if normalized_hint and normalized_hint not in normalized_text and normalized_hint not in normalized_display:
            tokens = normalized_text.split()
            filler_tokens = {
                "ale",
                "but",
                "w",
                "we",
                "na",
                "do",
                "i",
                "a",
                "the",
                "to",
                "in",
                "on",
                "of",
                "for",
                "from",
                "form",
            }
            filler_count = sum(1 for token in tokens if token in filler_tokens)
            if len(tokens) >= 2 and (tokens[0] in {"ale", "but"} or filler_count >= max(2, len(tokens) - 1)):
                return "low_quality_object_name"

        return ""

    @staticmethod
    def _normalize_object_guard_text(text: str) -> str:
        normalized = " ".join(str(text or "").strip().lower().split())
        translation = str.maketrans({
            "ą": "a",
            "ć": "c",
            "ę": "e",
            "ł": "l",
            "ń": "n",
            "ó": "o",
            "ś": "s",
            "ź": "z",
            "ż": "z",
        })
        normalized = normalized.translate(translation)
        return re.sub(r"[^a-z0-9 ]+", "", normalized).strip()

    @staticmethod
    def _object_owner_from_text(text: str) -> str:
        normalized = " ".join(str(text or "").strip().lower().split())
        if not normalized:
            return ""
        user_markers = (
            "mój ",
            "moj ",
            "moja ",
            "moje ",
            "to jest mój ",
            "to jest moj ",
            "to jest moja ",
            "to jest moje ",
            "my ",
            "this is my ",
        )
        return "user" if any(normalized.startswith(marker) for marker in user_markers) else ""

    @staticmethod
    def _title_display_name(text: str) -> str:
        clean = " ".join(str(text or "").split()).strip()
        if not clean:
            return ""
        return " ".join(part[:1].upper() + part[1:] for part in clean.split())

    @staticmethod
    def _clean_person_memory_display_name(text: str) -> str:
        raw = " ".join(str(text or "").strip().split()).strip(" .")
        if not raw:
            return ""

        raw = re.sub(
            r"^(?:mam na imie|mam na imię|nazywam sie|nazywam się|jestem|my name is|i am|i'm|call me)\s+",
            "",
            raw,
            flags=re.IGNORECASE,
        ).strip(" .")
        if not raw:
            return ""

        blocked = {"tak", "nie", "yes", "no", "cancel", "anuluj", "stop"}
        if raw.lower() in blocked:
            return ""

        tokens = re.findall(r"[A-Za-zÀ-ÿ'’-]{2,32}", raw)
        if not tokens or len(tokens) > 4:
            return ""

        normalized_tokens = []
        for token in tokens:
            cleaned = token.strip(" '-’")
            if not cleaned:
                continue
            normalized_tokens.append(cleaned[:1].upper() + cleaned[1:].lower())
        return " ".join(normalized_tokens).strip()

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

    def _handle_confirm_exit(self, *, text: str, language: str) -> bool:
        if self._is_yes(text):
            self.assistant.pending_follow_up = None

            display = getattr(self.assistant, "display", None)
            if display is not None:
                try:
                    display.show_block(
                        self.assistant._localized(language, "DO WIDZENIA", "GOODBYE"),
                        [self.assistant._localized(language, "zamykam asystenta", "closing assistant")],
                        duration=1.0,
                    )
                except Exception:
                    pass

            self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Zamykam.",
                    "Closing.",
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
                    "Zostaję.",
                    "Staying on.",
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
                "Tak albo nie.",
                "Yes or no.",
            ),
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="pending_retry_shutdown",
            metadata={"follow_up_type": "confirm_shutdown"},
        )
