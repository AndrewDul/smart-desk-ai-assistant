from __future__ import annotations

import time
from typing import Any

from modules.core.session.voice_session import (
    VOICE_STATE_SPEAKING,
    VOICE_STATE_STANDBY,
)
from modules.runtime.contracts import ChunkKind, ResponsePlan, RouteKind, create_turn_id
from modules.shared.logging.logger import append_log, log_exception, get_logger

LOGGER = get_logger(__name__)


class NotificationFlowOrchestrator:
    """
    Premium async notification delivery for NeXa.

    Responsibilities:
    - interrupt current interaction safely when a higher-priority notification appears
    - keep display + spoken output aligned
    - deliver timer/reminder notifications without corrupting session state
    - remember notification turns in dialogue memory
    - stay resilient even when one subsystem is temporarily degraded
    """

    def __init__(self, assistant: Any) -> None:
        self.assistant = assistant
        coordination_cfg = getattr(assistant, "settings", {}).get("audio_coordination", {})
        self.interrupt_settle_seconds = max(
            float(coordination_cfg.get("notification_interrupt_settle_seconds", 0.05)),
            0.0,
        )

    # ------------------------------------------------------------------
    # Context control
    # ------------------------------------------------------------------

    def clear_interaction_context(
        self,
        *,
        reason: str,
        close_active_window: bool = True,
        interrupt_output: bool = True,
    ) -> None:
        assistant = self.assistant

        had_pending_confirmation = assistant.pending_confirmation is not None
        had_pending_follow_up = assistant.pending_follow_up is not None

        assistant.pending_confirmation = None
        assistant.pending_follow_up = None

        if interrupt_output:
            self._request_interrupt(reason=reason)
            self._stop_current_playback()
            if self.interrupt_settle_seconds > 0:
                time.sleep(self.interrupt_settle_seconds)

        if close_active_window:
            try:
                assistant.voice_session.close_active_window()
            except Exception as error:
                log_exception("Failed to close active voice window for notification", error)

        try:
            assistant.voice_session.set_state(VOICE_STATE_STANDBY, detail=reason)
        except Exception as error:
            log_exception("Failed to set standby state before notification", error)

        if had_pending_confirmation or had_pending_follow_up:
            append_log(
                "Interaction context cleared for notification: "
                f"reason={reason}, "
                f"had_pending_confirmation={had_pending_confirmation}, "
                f"had_pending_follow_up={had_pending_follow_up}"
            )

    # ------------------------------------------------------------------
    # Reminder helpers
    # ------------------------------------------------------------------

    def reminder_language(self, reminder: dict[str, Any]) -> str:
        assistant = self.assistant
        stored = reminder.get("language") or reminder.get("lang")

        normalize_lang = getattr(assistant, "_normalize_lang", None)
        if callable(normalize_lang):
            try:
                return str(normalize_lang(stored or assistant.last_language))
            except Exception:
                pass

        normalized = str(stored or getattr(assistant, "last_language", "en")).strip().lower()
        return "pl" if normalized.startswith("pl") else "en"

    def deliver_due_reminder(self, reminder: dict[str, Any]) -> None:
        assistant = self.assistant
        message = str(reminder.get("message", "Reminder triggered.")).strip() or "Reminder triggered."
        lang = self.reminder_language(reminder)

        localized = getattr(assistant, "_localized")
        spoken_text = localized(
            lang,
            f"Przypomnienie. {message}",
            f"Reminder. {message}",
        )

        self.deliver_async_notification(
            lang=lang,
            spoken_text=spoken_text,
            display_title=localized(lang, "PRZYPOMNIENIE", "REMINDER"),
            display_lines=[message],
            source="reminder",
            route_kind="reminder",
            action="reminder_due",
            display_duration=max(float(getattr(assistant, "default_overlay_seconds", 8.0)), 12.0),
            extra_metadata={
                "reminder_id": reminder.get("id"),
                "reminder_status": reminder.get("status"),
                "reminder_due_at": reminder.get("due_at"),
                "triggered_at": reminder.get("triggered_at"),
            },
        )

        append_log(
            f"Reminder delivered: id={reminder.get('id')}, lang={lang}, message={message}"
        )

    # ------------------------------------------------------------------
    # Main delivery
    # ------------------------------------------------------------------

    def deliver_async_notification(
        self,
        *,
        lang: str,
        spoken_text: str,
        display_title: str,
        display_lines: list[str],
        source: str,
        route_kind: str,
        action: str | None = None,
        display_duration: float | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        assistant = self.assistant
        normalize_lang = getattr(assistant, "_normalize_lang")
        normalized_lang = str(normalize_lang(lang))

        cleaned_spoken_text = self._clean_text(spoken_text)
        if not cleaned_spoken_text:
            LOGGER.debug("Notification ignored because spoken text is empty: source=%s", source)
            return

        shown_lines = self._clean_lines(display_lines)
        if not shown_lines:
            shown_lines = self._fallback_display_lines(cleaned_spoken_text)

        metadata = {
            "source": source,
            "route_kind": route_kind,
            "delivery_mode": "async_notification",
        }
        if action:
            metadata["action"] = action
        if extra_metadata:
            metadata.update(extra_metadata)

        self.clear_interaction_context(
            reason=f"async_notification:{source}",
            close_active_window=True,
            interrupt_output=True,
        )

        self._remember_notification_turn(
            text=cleaned_spoken_text,
            language=normalized_lang,
            metadata=metadata,
        )

        self._show_display_block(
            title=display_title,
            lines=shown_lines,
            duration=display_duration,
        )

        self._speak_notification(
            text=cleaned_spoken_text,
            language=normalized_lang,
            detail=f"async_notification:{source}",
        )

        append_log(
            "Async notification delivered: "
            f"source={source}, "
            f"lang={normalized_lang}, "
            f"action={action or ''}, "
            f"text={cleaned_spoken_text}"
        )

    def build_response_plan(
        self,
        *,
        language: str,
        text: str,
        source: str,
        route_kind: RouteKind = RouteKind.CONVERSATION,
        metadata: dict[str, Any] | None = None,
    ) -> ResponsePlan:
        """
        Optional helper for future notification routing through the standard
        response pipeline. Current timer/reminder notifications still use the
        direct async path to stay immediate and interruption-safe.
        """
        plan = ResponsePlan(
            turn_id=create_turn_id(prefix="notify"),
            language=language,
            route_kind=route_kind,
            stream_mode=getattr(self.assistant, "stream_mode"),
            metadata=dict(metadata or {}),
        )
        plan.add_text(text, kind=ChunkKind.CONTENT)
        plan.metadata.setdefault("source", source)
        return plan

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _request_interrupt(self, *, reason: str) -> None:
        request_interrupt = getattr(self.assistant, "request_interrupt", None)
        if not callable(request_interrupt):
            return

        try:
            request_interrupt(
                reason=f"notification:{reason}",
                source="notification_flow",
                metadata={"reason": reason},
            )
        except TypeError:
            try:
                request_interrupt()
            except Exception as error:
                log_exception("Failed to request interrupt for notification", error)
        except Exception as error:
            log_exception("Failed to request interrupt for notification", error)

    def _stop_current_playback(self) -> None:
        voice_out = getattr(self.assistant, "voice_out", None)
        if voice_out is None:
            return

        stop_method = getattr(voice_out, "stop_playback", None)
        if not callable(stop_method):
            return

        try:
            stop_method()
        except Exception as error:
            log_exception("Failed to stop current playback for notification", error)

    def _remember_notification_turn(
        self,
        *,
        text: str,
        language: str,
        metadata: dict[str, Any],
    ) -> None:
        remember_method = getattr(self.assistant, "_remember_assistant_turn", None)
        if not callable(remember_method):
            return

        try:
            remember_method(text, language=language, metadata=metadata)
        except TypeError:
            try:
                remember_method(text, language, metadata)
            except Exception as error:
                log_exception("Failed to remember async notification turn", error)
        except Exception as error:
            log_exception("Failed to remember async notification turn", error)

    def _show_display_block(
        self,
        *,
        title: str,
        lines: list[str],
        duration: float | None,
    ) -> None:
        display = getattr(self.assistant, "display", None)
        if display is None:
            return

        show_block = getattr(display, "show_block", None)
        if not callable(show_block):
            return

        safe_title = self._clean_text(title) or "NEXA"
        safe_duration = (
            float(duration)
            if duration is not None
            else float(getattr(self.assistant, "default_overlay_seconds", 8.0))
        )

        try:
            show_block(safe_title, lines, duration=safe_duration)
        except Exception as error:
            log_exception("Failed to show async notification display block", error)

    def _speak_notification(
        self,
        *,
        text: str,
        language: str,
        detail: str,
    ) -> None:
        assistant = self.assistant

        try:
            assistant.voice_session.set_state(VOICE_STATE_SPEAKING, detail=detail)
        except Exception as error:
            log_exception("Failed to set speaking state for notification", error)

        try:
            assistant.voice_out.speak(text, language=language)
        except Exception as error:
            log_exception("Failed to speak async notification", error)
        finally:
            try:
                assistant.voice_session.close_active_window()
            except Exception as error:
                log_exception("Failed to close active window after notification", error)

            try:
                assistant.voice_session.set_state(
                    VOICE_STATE_STANDBY,
                    detail=f"{detail}:complete",
                )
            except Exception as error:
                log_exception("Failed to return to standby after notification", error)

    def _fallback_display_lines(self, text: str) -> list[str]:
        display_lines_method = getattr(self.assistant, "_display_lines", None)
        if callable(display_lines_method):
            try:
                return list(display_lines_method(text))
            except Exception:
                pass

        compact = self._clean_text(text)
        if not compact:
            return [""]

        max_chars = int(
            getattr(self.assistant, "settings", {})
            .get("streaming", {})
            .get("max_display_chars_per_line", 20)
        )

        if len(compact) <= max_chars:
            return [compact]

        first = compact[:max_chars].rstrip()
        second = compact[max_chars : max_chars * 2].strip()
        return [first, second] if second else [first]

    @staticmethod
    def _clean_text(text: Any) -> str:
        return " ".join(str(text or "").split()).strip()

    def _clean_lines(self, lines: list[Any]) -> list[str]:
        cleaned = [self._clean_text(line) for line in lines]
        cleaned = [line for line in cleaned if line]
        if not cleaned:
            return []

        max_lines = int(
            getattr(self.assistant, "settings", {})
            .get("streaming", {})
            .get("max_display_lines", 2)
        )
        return cleaned[: max(1, max_lines)]


__all__ = ["NotificationFlowOrchestrator"]