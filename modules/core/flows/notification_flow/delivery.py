from __future__ import annotations

from typing import Any

from modules.runtime.contracts import ChunkKind, ResponsePlan, RouteKind, create_turn_id
from modules.shared.logging.logger import append_log, get_logger

LOGGER = get_logger(__name__)


class NotificationFlowDelivery:
    """Main async notification delivery helpers."""

    assistant: Any

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

        # Async notifications are delivered from the background reminder loop.
        # They must not request a global audio/input interrupt because that can
        # disturb the wake/capture handoff and leave the runtime feeling frozen
        # after the reminder finishes. They must also preserve an active
        # confirmation/follow-up conversation if a reminder fires in the background.
        has_pending_interaction = (
            assistant.pending_confirmation is not None
            or assistant.pending_follow_up is not None
        )
        self.clear_interaction_context(
            reason=f"async_notification:{source}",
            close_active_window=not has_pending_interaction,
            interrupt_output=False,
            preserve_pending=has_pending_interaction,
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


__all__ = ["NotificationFlowDelivery"]