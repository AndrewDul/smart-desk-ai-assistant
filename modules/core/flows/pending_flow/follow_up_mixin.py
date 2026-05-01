from __future__ import annotations

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

        self.assistant.pending_follow_up = None

        try:
            memory_id = remember_text_method(
                memory_text,
                language=language,
                source="guided_memory_follow_up",
            )
        except TypeError:
            try:
                memory_id = remember_text_method(memory_text, language=language)
            except TypeError:
                memory_id = remember_text_method(memory_text)
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
            memory_text,
        )

        return self.assistant.deliver_text_response(
            self.assistant._localized(
                language,
                f"Zapamiętałam: {memory_text}.",
                f"I remembered: {memory_text}.",
            ),
            language=language,
            route_kind=RouteKind.ACTION,
            source="pending_memory_message_saved",
            metadata={
                "follow_up_type": "memory_message",
                "memory_id": str(memory_id or "").strip(),
                "language": language,
            },
        )

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