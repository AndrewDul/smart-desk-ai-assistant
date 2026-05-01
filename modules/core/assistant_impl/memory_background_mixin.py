from __future__ import annotations

import time
from typing import Any

from modules.shared.logging.logger import log_exception


class CoreAssistantMemoryBackgroundMixin:
    """
    Bridge the assistant layer to the dialogue memory API.

    This mixin intentionally prefers the public dialogue-service helpers
    (add_user_turn / add_assistant_turn) and only falls back to the raw
    conversation-memory object when needed.
    """

    def _remember_user_turn(
        self,
        text: str,
        *,
        language: str,
        metadata: dict | None = None,
    ) -> None:
        self._store_dialogue_turn(
            role="user",
            text=text,
            language=language,
            metadata=metadata,
        )

    def _remember_assistant_turn(
        self,
        text: str,
        *,
        language: str,
        metadata: dict | None = None,
    ) -> None:
        self._store_dialogue_turn(
            role="assistant",
            text=text,
            language=language,
            metadata=metadata,
        )

    def _store_dialogue_turn(
        self,
        *,
        role: str,
        text: str,
        language: str,
        metadata: dict | None = None,
    ) -> None:
        cleaned_text = " ".join(str(text or "").split()).strip()
        if not cleaned_text:
            return

        normalized_language = self._normalize_lang(language)
        safe_metadata = dict(metadata or {})

        primary_name = "add_user_turn" if role == "user" else "add_assistant_turn"
        dialogue = getattr(self, "dialogue", None)

        if self._call_memory_method(
            target=dialogue,
            method_name=primary_name,
            text=cleaned_text,
            language=normalized_language,
            metadata=safe_metadata,
        ):
            return

        memory = getattr(dialogue, "conversation_memory", None)
        if self._call_memory_method(
            target=memory,
            method_name=primary_name,
            text=cleaned_text,
            language=normalized_language,
            metadata=safe_metadata,
        ):
            return

        generic_add_turn = getattr(memory, "add_turn", None)
        if callable(generic_add_turn):
            try:
                generic_add_turn(
                    role=role,
                    text=cleaned_text,
                    language=normalized_language,
                    metadata=safe_metadata,
                )
            except Exception as error:
                log_exception("Dialogue memory add_turn failed", error)

    def _call_memory_method(
        self,
        *,
        target: Any,
        method_name: str,
        text: str,
        language: str,
        metadata: dict,
    ) -> bool:
        method = getattr(target, method_name, None)
        if not callable(method):
            return False

        try:
            method(text, language=language, metadata=metadata)
            return True
        except TypeError:
            try:
                method(text=text, language=language, metadata=metadata)
                return True
            except TypeError:
                try:
                    method(text, language)
                    return True
                except Exception as error:
                    log_exception(f"Dialogue memory method '{method_name}' failed", error)
                    return False
        except Exception as error:
            log_exception(f"Dialogue memory method '{method_name}' failed", error)
            return False

    def _build_dialogue_user_profile(self, preferred_language: str) -> dict:
        normalized_language = self._normalize_lang(preferred_language)
        profile = dict(self.user_profile)
        profile["preferred_language"] = normalized_language

        dialogue = getattr(self, "dialogue", None)
        memory = getattr(dialogue, "conversation_memory", None)

        recent_context = self._build_recent_conversation_context(
            dialogue=dialogue,
            memory=memory,
            preferred_language=normalized_language,
        )
        if recent_context:
            profile["recent_conversation_context"] = recent_context

        memory_payload = self._build_recent_conversation_payload(memory=memory)
        if memory_payload:
            profile["recent_conversation_payload"] = memory_payload

        return profile

    def _build_recent_conversation_context(
        self,
        *,
        dialogue: Any,
        memory: Any,
        preferred_language: str,
    ) -> str:
        for target, method_name in (
            (memory, "summary_for_prompt"),
            (memory, "build_context_block"),
            (memory, "build_recent_context"),
            (dialogue, "build_recent_context"),
        ):
            method = getattr(target, method_name, None)
            if not callable(method):
                continue

            try:
                context = method(
                    limit=6,
                    preferred_language=preferred_language,
                    include_timestamps=False,
                )
            except TypeError:
                try:
                    context = method(limit=6, preferred_language=preferred_language)
                except TypeError:
                    try:
                        context = method(6)
                    except Exception as error:
                        log_exception(
                            f"Dialogue context builder '{method_name}' failed",
                            error,
                        )
                        continue
                except Exception as error:
                    log_exception(f"Dialogue context builder '{method_name}' failed", error)
                    continue
            except Exception as error:
                log_exception(f"Dialogue context builder '{method_name}' failed", error)
                continue

            cleaned_context = "\n".join(
                line.rstrip()
                for line in str(context or "").splitlines()
                if line.strip()
            ).strip()
            if cleaned_context:
                return cleaned_context

        return ""

    def _build_recent_conversation_payload(self, *, memory: Any) -> list[dict]:
        payload_method = getattr(memory, "build_context_payload", None)
        if not callable(payload_method):
            return []

        try:
            payload = payload_method(limit=6)
        except TypeError:
            try:
                payload = payload_method(6)
            except Exception as error:
                log_exception("Dialogue context payload build failed", error)
                return []
        except Exception as error:
            log_exception("Dialogue context payload build failed", error)
            return []

        if not isinstance(payload, list):
            return []

        safe_payload: list[dict] = []
        for item in payload:
            if isinstance(item, dict):
                safe_payload.append(dict(item))
        return safe_payload

    def _reminder_loop(self) -> None:
        reminder_settings = dict(getattr(self, "settings", {}).get("reminders", {}))
        startup_grace_seconds = float(
            reminder_settings.get("startup_grace_seconds", 10.0)
        )
        notification_cooldown_seconds = float(
            reminder_settings.get("notification_cooldown_seconds", 6.0)
        )
        poll_interval_seconds = float(
            reminder_settings.get("poll_interval_seconds", 0.5)
        )

        if startup_grace_seconds > 0:
            self._stop_background.wait(startup_grace_seconds)

        next_notification_at = 0.0

        while not self._stop_background.is_set():
            try:
                now_monotonic = time.monotonic()
                if now_monotonic < next_notification_at:
                    wait_seconds = min(
                        poll_interval_seconds,
                        max(0.05, next_notification_at - now_monotonic),
                    )
                    self._stop_background.wait(wait_seconds)
                    continue

                checker = getattr(self.reminders, "check_due_reminders", None)
                if not callable(checker):
                    due_reminders = []
                else:
                    try:
                        due_reminders = checker(limit=1)
                    except TypeError:
                        due_reminders = checker()

                deliver_method = getattr(
                    self.notification_flow,
                    "deliver_due_reminder",
                    None,
                )
                if callable(deliver_method):
                    for reminder in list(due_reminders or [])[:1]:
                        deliver_method(reminder)
                        next_notification_at = (
                            time.monotonic() + notification_cooldown_seconds
                        )
                        break
            except Exception as error:
                log_exception("Reminder loop iteration failed", error)

            self._stop_background.wait(poll_interval_seconds)
