from __future__ import annotations

import time

from modules.shared.logging.logger import log_exception


class CoreAssistantMemoryBackgroundMixin:
    def _remember_user_turn(
        self,
        text: str,
        *,
        language: str,
        metadata: dict | None = None,
    ) -> None:
        memory = getattr(self.dialogue, "conversation_memory", None)
        remember_method = getattr(memory, "remember_user_turn", None)
        if callable(remember_method):
            try:
                remember_method(text=text, language=language, metadata=metadata or {})
            except TypeError:
                remember_method(text, language)

    def _remember_assistant_turn(
        self,
        text: str,
        *,
        language: str,
        metadata: dict | None = None,
    ) -> None:
        memory = getattr(self.dialogue, "conversation_memory", None)
        remember_method = getattr(memory, "remember_assistant_turn", None)
        if callable(remember_method):
            try:
                remember_method(text=text, language=language, metadata=metadata or {})
            except TypeError:
                remember_method(text, language)

    def _build_dialogue_user_profile(self, preferred_language: str) -> dict:
        profile = dict(self.user_profile)
        profile["preferred_language"] = self._normalize_lang(preferred_language)

        memory = getattr(self.dialogue, "conversation_memory", None)
        if memory is not None:
            build_method = getattr(memory, "build_recent_context", None)
            if callable(build_method):
                try:
                    profile["recent_conversation_context"] = build_method(
                        limit=6,
                        preferred_language=preferred_language,
                        include_timestamps=False,
                    )
                except TypeError:
                    profile["recent_conversation_context"] = build_method(6)

        return profile

    def _reminder_loop(self) -> None:
        while not self._stop_background.is_set():
            try:
                checker = getattr(self.reminders, "check_due_reminders", None)
                due_reminders = checker() if callable(checker) else []

                for reminder in due_reminders or []:
                    deliver_method = getattr(self.notification_flow, "deliver_due_reminder", None)
                    if callable(deliver_method):
                        deliver_method(reminder)
            except Exception as error:
                log_exception("Reminder loop iteration failed", error)

            time.sleep(1.0)