from __future__ import annotations

from typing import Any

from modules.core.session.voice_session import (
    VOICE_STATE_SHUTDOWN,
    VOICE_STATE_SPEAKING,
    VOICE_STATE_STANDBY,
)
from modules.runtime.contracts import (
    ChunkKind,
    ResponsePlan,
    RouteKind,
    create_turn_id,
)


class CoreAssistantResponseMixin:
    def deliver_response_plan(
        self,
        plan: ResponsePlan,
        *,
        source: str,
        remember: bool = True,
        extra_metadata: dict[str, Any] | None = None,
    ) -> bool:
        if not plan.chunks and not plan.tool_results:
            return True

        route_kind_value = plan.route_kind.value
        self.voice_session.set_state(VOICE_STATE_SPEAKING, detail=f"response:{route_kind_value}")

        try:
            delivered = False

            execute_method = getattr(self.response_streamer, "execute", None)
            if callable(execute_method):
                execute_method(plan)
                delivered = True
            else:
                deliver_method = getattr(self.response_streamer, "deliver", None)
                if callable(deliver_method):
                    deliver_method(plan)
                    delivered = True
                else:
                    stream_method = getattr(self.response_streamer, "stream", None)
                    if callable(stream_method):
                        stream_method(plan)
                        delivered = True

            if not delivered:
                fallback_text = plan.full_text()
                if fallback_text:
                    self.voice_out.speak(fallback_text, language=plan.language)
                    self.display.show_block(
                        self.ASSISTANT_NAME,
                        self._display_lines(fallback_text),
                        duration=self.default_overlay_seconds,
                    )

            if remember:
                remembered_text = plan.full_text()
                if remembered_text:
                    metadata = {
                        "source": source,
                        "route_kind": route_kind_value,
                        "tool_count": len(plan.tool_results),
                    }
                    if extra_metadata:
                        metadata.update(extra_metadata)
                    self._remember_assistant_turn(
                        remembered_text,
                        language=plan.language,
                        metadata=metadata,
                    )

            return True
        finally:
            if self.shutdown_requested:
                self.voice_session.set_state(VOICE_STATE_SHUTDOWN, detail="shutdown_requested")
            else:
                self.voice_session.set_state(VOICE_STATE_STANDBY, detail="response_complete")

    def deliver_text_response(
        self,
        text: str,
        *,
        language: str,
        route_kind: RouteKind,
        source: str,
        remember: bool = True,
        chunk_kind: ChunkKind = ChunkKind.CONTENT,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        plan = ResponsePlan(
            turn_id=create_turn_id(),
            language=language,
            route_kind=route_kind,
            stream_mode=self.stream_mode,
        )
        plan.add_text(text, kind=chunk_kind, mode=self.stream_mode)
        return self.deliver_response_plan(
            plan,
            source=source,
            remember=remember,
            extra_metadata=metadata,
        )

    def _deliver_async_notification(
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
        deliver_method = getattr(self.notification_flow, "deliver_async_notification", None)
        if callable(deliver_method):
            deliver_method(
                lang=lang,
                spoken_text=spoken_text,
                display_title=display_title,
                display_lines=display_lines,
                source=source,
                route_kind=route_kind,
                action=action,
                display_duration=display_duration,
                extra_metadata=extra_metadata,
            )
            return

        self.deliver_text_response(
            spoken_text,
            language=lang,
            route_kind=RouteKind.CONVERSATION,
            source=source,
            remember=True,
            metadata=extra_metadata,
        )

    def _on_timer_started(self, **payload: Any) -> None:
        timer_type = self._timer_type_from_payload(payload)
        minutes = self._timer_minutes_from_payload(payload)
        lang = self._normalize_lang(payload.get("language") or self.last_language)

        self.state["current_timer"] = timer_type
        self.state["focus_mode"] = timer_type == "focus"
        self.state["break_mode"] = timer_type == "break"
        self._save_state()

        if timer_type == "focus":
            spoken = self._localized(
                lang,
                f"Rozpoczynam tryb skupienia na {self._minutes_text(minutes, 'pl')}.",
                f"Starting focus mode for {self._minutes_text(minutes, 'en')}.",
            )
            title = "FOCUS"
        elif timer_type == "break":
            spoken = self._localized(
                lang,
                f"Rozpoczynam przerwę na {self._minutes_text(minutes, 'pl')}.",
                f"Starting break mode for {self._minutes_text(minutes, 'en')}.",
            )
            title = "BREAK"
        else:
            spoken = self._localized(
                lang,
                f"Uruchamiam timer na {self._minutes_text(minutes, 'pl')}.",
                f"Starting a timer for {self._minutes_text(minutes, 'en')}.",
            )
            title = "TIMER"

        self._deliver_async_notification(
            lang=lang,
            spoken_text=spoken,
            display_title=title,
            display_lines=self._display_lines(spoken),
            source="timer_started",
            route_kind="timer_status",
            action=timer_type,
            extra_metadata={
                "minutes": minutes,
                "timer_type": timer_type,
            },
        )

    def _on_timer_finished(self, **payload: Any) -> None:
        timer_type = self._timer_type_from_payload(payload)
        minutes = self._timer_minutes_from_payload(payload)
        lang = self._normalize_lang(payload.get("language") or self.last_language)

        self.state["current_timer"] = None
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self._save_state()

        if timer_type == "focus":
            spoken = self._localized(
                lang,
                f"Tryb skupienia zakończony po {self._minutes_text(minutes, 'pl')}.",
                f"Focus mode finished after {self._minutes_text(minutes, 'en')}.",
            )
            title = "FOCUS DONE"
        elif timer_type == "break":
            spoken = self._localized(
                lang,
                f"Przerwa zakończona po {self._minutes_text(minutes, 'pl')}.",
                f"Break finished after {self._minutes_text(minutes, 'en')}.",
            )
            title = "BREAK DONE"
        else:
            spoken = self._localized(
                lang,
                f"Timer zakończył się po {self._minutes_text(minutes, 'pl')}.",
                f"Timer finished after {self._minutes_text(minutes, 'en')}.",
            )
            title = "TIMER DONE"

        self._deliver_async_notification(
            lang=lang,
            spoken_text=spoken,
            display_title=title,
            display_lines=self._display_lines(spoken),
            source="timer_finished",
            route_kind="timer_status",
            action=timer_type,
            extra_metadata={
                "minutes": minutes,
                "timer_type": timer_type,
            },
        )

    def _on_timer_stopped(self, **payload: Any) -> None:
        timer_type = self._timer_type_from_payload(payload)
        lang = self._normalize_lang(payload.get("language") or self.last_language)

        self.state["current_timer"] = None
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self._save_state()

        spoken = self._localized(
            lang,
            "Zatrzymałem aktywny timer.",
            "I stopped the active timer.",
        )

        self._deliver_async_notification(
            lang=lang,
            spoken_text=spoken,
            display_title="TIMER STOPPED",
            display_lines=self._display_lines(spoken),
            source="timer_stopped",
            route_kind="timer_status",
            action=timer_type,
            extra_metadata={"timer_type": timer_type},
        )