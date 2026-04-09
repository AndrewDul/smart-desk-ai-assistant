from __future__ import annotations

from modules.core.session.voice_session import VOICE_STATE_ROUTING


class CoreAssistantInteractionMixin:
    def handle_command(self, text: str) -> bool:
        self.interrupt_controller.clear()

        cleaned = str(text or "").strip()
        if not cleaned:
            return True

        prepared = self._prepare_command(cleaned)
        if prepared["ignore"]:
            return True

        command_lang = self._commit_language(prepared["language"])
        routing_text = prepared["routing_text"]

        if not prepared.get("already_remembered", False):
            self._remember_user_turn(
                cleaned,
                language=command_lang,
                metadata={
                    "source": prepared["source"].value,
                    "normalized_text": prepared["normalized_text"],
                },
            )

        if prepared["cancel_requested"]:
            return self._cancel_active_request(command_lang)

        pending_result = self._handle_pending_state(prepared)
        if pending_result is not None:
            return bool(pending_result)

        fast_lane_result = self._handle_fast_lane(prepared)
        if fast_lane_result is not None:
            return bool(fast_lane_result)

        self.voice_session.set_state(VOICE_STATE_ROUTING, detail="route_command")
        self._thinking_ack_start(language=command_lang, detail="route_command")
        try:
            routed = self.router.route(routing_text, preferred_language=command_lang)
        finally:
            self._thinking_ack_stop()

        route = self._coerce_route_decision(
            routed,
            raw_text=cleaned,
            normalized_text=prepared["normalized_text"],
            language=command_lang,
        )

        log_route_decision = getattr(self.command_flow, "log_route_decision", None)
        if callable(log_route_decision):
            try:
                log_route_decision(route)
            except Exception:
                pass

        if route.kind == self._route_kind_action():
            self.pending_confirmation = None
            return self._execute_action_route(route, command_lang)

        if route.kind == self._route_kind_mixed():
            self.pending_confirmation = None
            return self._handle_mixed_route(route, command_lang)

        if route.kind == self._route_kind_conversation():
            self.pending_confirmation = None
            return self._handle_conversation_route(route, command_lang)

        return self._handle_unclear_route(route, command_lang)

    def request_interrupt(
        self,
        *,
        reason: str = "manual_interrupt",
        source: str = "assistant",
        metadata: dict | None = None,
    ) -> None:
        self.interrupt_controller.request(
            reason=reason,
            source=source,
            metadata=metadata,
        )

    def _interrupt_requested(self) -> bool:
        return bool(self.interrupt_controller.is_requested())

    @staticmethod
    def _route_kind_action():
        from modules.runtime.contracts import RouteKind

        return RouteKind.ACTION

    @staticmethod
    def _route_kind_mixed():
        from modules.runtime.contracts import RouteKind

        return RouteKind.MIXED

    @staticmethod
    def _route_kind_conversation():
        from modules.runtime.contracts import RouteKind

        return RouteKind.CONVERSATION