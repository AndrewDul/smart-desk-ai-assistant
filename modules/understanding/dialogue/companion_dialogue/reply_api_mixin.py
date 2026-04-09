from __future__ import annotations

from typing import Any

from modules.runtime.contracts import (
    ChunkKind,
    ResponsePlan,
    RouteKind,
    StreamMode,
    create_turn_id,
)

from .models import DialogueReply


class CompanionDialogueReplyApiMixin:
    """
    Public dialogue API for building replies and response plans.
    """

    def build_reply(self, route: Any, user_profile: dict | None = None) -> DialogueReply:
        lang = self._normalize_language(getattr(route, "language", "en"))
        kind = self._route_kind_value(getattr(route, "kind", "conversation"))
        topics = list(getattr(route, "conversation_topics", []) or [])
        normalized_text = str(getattr(route, "normalized_text", "") or "").strip()
        suggested_actions = list(getattr(route, "suggested_actions", []) or [])

        if "humour" in topics:
            spoken = self._next_humour(lang)
            return self._reply(
                lang,
                spoken,
                display_title=self._text(lang, "HUMOR", "HUMOUR"),
                source="template_humour",
            )

        if "riddle" in topics:
            spoken = self._next_riddle(lang)
            return self._reply(
                lang,
                spoken,
                display_title=self._text(lang, "ZAGADKA", "RIDDLE"),
                source="template_riddle",
            )

        if "interesting_fact" in topics:
            spoken = self._next_fact(lang)
            return self._reply(
                lang,
                spoken,
                display_title=self._text(lang, "CIEKAWOSTKA", "FACT"),
                source="template_fact",
            )

        deterministic = self._try_deterministic_reply(
            normalized_text=normalized_text,
            language=lang,
            user_profile=user_profile,
            topics=topics,
        )
        if deterministic is not None:
            return deterministic

        if kind == "mixed":
            return self._build_mixed_reply(
                route=route,
                language=lang,
                user_profile=user_profile,
                topics=topics,
                suggested_actions=suggested_actions,
            )

        if kind == "unclear":
            contextual_unclear = self._build_unclear_reply(
                normalized_text=normalized_text,
                language=lang,
                user_profile=user_profile,
            )
            if contextual_unclear is not None:
                return contextual_unclear

        llm_reply = self._try_local_llm(
            normalized_text=normalized_text,
            language=lang,
            topics=topics,
            user_profile=user_profile,
            route_kind=kind,
        )
        if llm_reply is not None:
            return llm_reply

        if kind == "conversation":
            return self._build_conversation_reply(
                normalized_text=normalized_text,
                language=lang,
                user_profile=user_profile,
                topics=topics,
            )

        if kind == "unclear":
            return self._build_unclear_generic_reply(lang)

        return self._build_action_bridge_reply(language=lang)

    def build_response_plan(
        self,
        route: Any,
        user_profile: dict | None = None,
        *,
        stream_mode: StreamMode | None = None,
    ) -> ResponsePlan:
        reply = self.build_reply(route, user_profile)
        plan = self.reply_to_plan(
            reply,
            route_kind=self._route_kind_value(getattr(route, "kind", "conversation")),
            stream_mode=stream_mode,
        )

        plan.metadata.update(
            {
                "reply_source": reply.source,
                "display_title": reply.display_title,
                "display_lines": list(reply.display_lines),
                "conversation_topics": list(getattr(route, "conversation_topics", []) or []),
                "suggested_actions": list(reply.suggested_actions),
                "route_confidence": float(getattr(route, "confidence", 0.0) or 0.0),
            }
        )

        return plan

    def reply_to_plan(
        self,
        reply: DialogueReply,
        *,
        route_kind: str,
        stream_mode: StreamMode | None = None,
    ) -> ResponsePlan:
        normalized_language = self._normalize_language(reply.language)
        selected_stream_mode = stream_mode or self.default_stream_mode
        normalized_route_kind = self._resolve_route_kind(route_kind)
        primary_kind = self._primary_chunk_kind_for_route(route_kind)

        plan = ResponsePlan(
            turn_id=create_turn_id("reply"),
            language=normalized_language,
            route_kind=normalized_route_kind,
            stream_mode=selected_stream_mode,
            metadata={
                "display_title": reply.display_title,
                "display_lines": list(reply.display_lines),
                "reply_source": reply.source,
            },
        )

        if reply.spoken_text:
            plan.add_text(
                reply.spoken_text,
                kind=primary_kind,
                mode=selected_stream_mode,
            )

        if reply.follow_up_text:
            plan.add_text(
                reply.follow_up_text,
                kind=ChunkKind.FOLLOW_UP,
                mode=selected_stream_mode,
            )

        if reply.suggested_actions:
            plan.follow_up_suggestions.extend(reply.suggested_actions)

        return plan


__all__ = ["CompanionDialogueReplyApiMixin"]