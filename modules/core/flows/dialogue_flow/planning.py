from __future__ import annotations

from typing import Any

from modules.runtime.contracts import (
    ChunkKind,
    ResponsePlan,
    RouteDecision,
    RouteKind,
    StreamMode,
    create_turn_id,
)
from modules.shared.logging.logger import get_logger

from .models import DialogueRequest

LOGGER = get_logger(__name__)


class DialogueFlowPlanning:
    """Dialogue plan construction helpers."""

    assistant: Any

    def _build_dialogue_plan(
        self,
        *,
        route: RouteDecision,
        request: DialogueRequest,
        user_profile: dict[str, Any],
        language: str,
    ) -> ResponsePlan:
        dialogue_service = self.assistant.dialogue

        build_response_plan = getattr(dialogue_service, "build_response_plan", None)
        if callable(build_response_plan):
            try:
                return build_response_plan(
                    request,
                    user_profile,
                    stream_mode=self.assistant.stream_mode,
                )
            except TypeError:
                try:
                    return build_response_plan(request, user_profile)
                except TypeError:
                    try:
                        return build_response_plan(
                            route,
                            user_profile,
                            stream_mode=self.assistant.stream_mode,
                        )
                    except TypeError:
                        return build_response_plan(route, user_profile)

        build_reply = getattr(dialogue_service, "build_reply", None)
        reply_to_plan = getattr(dialogue_service, "reply_to_plan", None)

        if callable(build_reply) and callable(reply_to_plan):
            reply = self._build_dialogue_reply(
                build_reply=build_reply,
                route=route,
                request=request,
                user_profile=user_profile,
            )
            return self._reply_to_plan(
                reply_to_plan=reply_to_plan,
                reply=reply,
                route_kind=route.kind,
            )

        if callable(build_reply):
            reply = self._build_dialogue_reply(
                build_reply=build_reply,
                route=route,
                request=request,
                user_profile=user_profile,
            )
            return self._reply_to_generic_plan(
                reply=reply,
                route=route,
                language=language,
            )

        LOGGER.warning(
            "Dialogue service does not expose build_response_plan() or build_reply(). Using fallback plan."
        )
        return self._build_dialogue_fallback_plan(
            route=route,
            language=language,
            reason="dialogue_service_missing_api",
        )

    def _build_dialogue_reply(
        self,
        *,
        build_reply: Any,
        route: RouteDecision,
        request: DialogueRequest,
        user_profile: dict[str, Any],
    ) -> Any:
        try:
            return build_reply(request, user_profile)
        except TypeError:
            try:
                return build_reply(route, user_profile)
            except TypeError:
                try:
                    return build_reply(request)
                except TypeError:
                    return build_reply(route)

    def _reply_to_plan(
        self,
        *,
        reply_to_plan: Any,
        reply: Any,
        route_kind: RouteKind,
    ) -> ResponsePlan:
        try:
            return reply_to_plan(
                reply,
                route_kind=route_kind.value,
                stream_mode=self.assistant.stream_mode,
            )
        except TypeError:
            try:
                return reply_to_plan(reply, route_kind=route_kind.value)
            except TypeError:
                try:
                    return reply_to_plan(reply, route_kind.value)
                except TypeError:
                    return reply_to_plan(reply)

    def _reply_to_generic_plan(
        self,
        *,
        reply: Any,
        route: RouteDecision,
        language: str,
    ) -> ResponsePlan:
        spoken_text = str(getattr(reply, "spoken_text", "") or "").strip()
        follow_up_text = str(getattr(reply, "follow_up_text", "") or "").strip()
        display_title = str(getattr(reply, "display_title", "") or "").strip()
        display_lines = list(getattr(reply, "display_lines", []) or [])
        suggested_actions = list(getattr(reply, "suggested_actions", []) or [])
        source = str(getattr(reply, "source", "dialogue_reply") or "dialogue_reply")

        plan = ResponsePlan(
            turn_id=create_turn_id(prefix="reply"),
            language=language,
            route_kind=route.kind,
            stream_mode=self.assistant.stream_mode,
            metadata={
                "display_title": display_title,
                "display_lines": display_lines,
                "reply_source": source,
                "conversation_topics": list(route.conversation_topics),
                "suggested_actions": suggested_actions,
                "route_confidence": float(route.confidence),
            },
        )

        if spoken_text:
            primary_kind = ChunkKind.CONTENT if route.kind != RouteKind.UNCLEAR else ChunkKind.FOLLOW_UP
            plan.add_text(spoken_text, kind=primary_kind, mode=self.assistant.stream_mode)

        if follow_up_text:
            plan.add_text(follow_up_text, kind=ChunkKind.FOLLOW_UP, mode=self.assistant.stream_mode)

        if suggested_actions:
            plan.follow_up_suggestions.extend(suggested_actions)

        return plan

    def _build_dialogue_fallback_plan(
        self,
        *,
        route: RouteDecision,
        language: str,
        reason: str,
    ) -> ResponsePlan:
        if route.kind == RouteKind.MIXED:
            text = self.assistant._localized(
                language,
                "Rozumiem. Brzmi to jak coś, przy czym mogę pomóc praktycznie. Powiedz mi, co mam zrobić jako pierwszy krok.",
                "I understand. This sounds like something I can help with practically. Tell me what you want me to do as the first step.",
            )
            title = self.assistant._localized(language, "POMOC", "SUPPORT")
        elif route.kind == RouteKind.UNCLEAR:
            text = self.assistant._localized(
                language,
                "Powtórz.",
                "Repeat.",
            )
            title = self.assistant._localized(language, "NIEJASNE", "UNCLEAR")
        else:
            text = self.assistant._localized(
                language,
                "Jestem tutaj. Powiedz, czego teraz najbardziej potrzebujesz.",
                "I am here. Tell me what you need most right now.",
            )
            title = self.assistant._localized(language, "ROZMOWA", "CHAT")

        plan = ResponsePlan(
            turn_id=create_turn_id(prefix="dialogue"),
            language=language,
            route_kind=route.kind,
            stream_mode=self.assistant.stream_mode,
            metadata={
                "display_title": title,
                "display_lines": self.assistant._display_lines(text),
                "reply_source": "dialogue_fallback",
                "fallback_reason": reason,
                "conversation_topics": list(route.conversation_topics),
            },
        )
        plan.add_text(text, kind=ChunkKind.CONTENT, mode=self.assistant.stream_mode)
        return plan


__all__ = ["DialogueFlowPlanning"]