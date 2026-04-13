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

    Main policy:
    - keep fixed fast-paths for humour / riddles / facts
    - keep deterministic math fast
    - prefer the local LLM for normal conversation, mixed, and unclear turns
    - fall back to templates only when the LLM cannot answer
    """

    def build_reply(self, route: Any, user_profile: dict | None = None) -> DialogueReply:
        lang = self._normalize_language(getattr(route, "language", "en"))
        kind = self._route_kind_value(getattr(route, "kind", "conversation"))
        topics = list(getattr(route, "conversation_topics", []) or [])
        normalized_text = str(getattr(route, "normalized_text", "") or "").strip()
        suggested_actions = list(getattr(route, "suggested_actions", []) or [])

        special_reply = self._try_special_topic_reply(
            language=lang,
            topics=topics,
        )
        if special_reply is not None:
            return special_reply

        deterministic = self._try_deterministic_reply(
            normalized_text=normalized_text,
            language=lang,
            user_profile=user_profile,
            topics=topics,
        )

        if self._should_return_deterministic_first(
            deterministic=deterministic,
            route_kind=kind,
        ):
            return deterministic

        if kind in {"conversation", "mixed", "unclear"}:
            llm_reply = self._try_local_llm(
                normalized_text=normalized_text,
                language=lang,
                topics=topics,
                user_profile=user_profile,
                route_kind=kind,
            )
            if llm_reply is not None:
                return llm_reply

        if kind == "unclear":
            contextual_unclear = self._build_unclear_reply(
                normalized_text=normalized_text,
                language=lang,
                user_profile=user_profile,
            )
            if contextual_unclear is not None:
                return contextual_unclear

        if deterministic is not None:
            return deterministic

        if kind == "conversation":
            return self._build_conversation_reply(
                normalized_text=normalized_text,
                language=lang,
                user_profile=user_profile,
                topics=topics,
            )

        if kind == "mixed":
            return self._build_mixed_reply(
                route=route,
                language=lang,
                user_profile=user_profile,
                topics=topics,
                suggested_actions=suggested_actions,
            )

        if kind == "unclear":
            return self._build_unclear_generic_reply(lang)

        return self._build_action_bridge_reply(language=lang)

    def _try_special_topic_reply(
        self,
        *,
        language: str,
        topics: list[str],
    ) -> DialogueReply | None:
        if "humour" in topics:
            spoken = self._next_humour(language)
            return self._reply(
                language,
                spoken,
                display_title=self._text(language, "HUMOR", "HUMOUR"),
                source="template_humour",
            )

        if "riddle" in topics:
            spoken = self._next_riddle(language)
            return self._reply(
                language,
                spoken,
                display_title=self._text(language, "ZAGADKA", "RIDDLE"),
                source="template_riddle",
            )

        if "interesting_fact" in topics:
            spoken = self._next_fact(language)
            return self._reply(
                language,
                spoken,
                display_title=self._text(language, "CIEKAWOSTKA", "FACT"),
                source="template_fact",
            )

        return None

    def _should_return_deterministic_first(
        self,
        *,
        deterministic: DialogueReply | None,
        route_kind: str,
    ) -> bool:
        if deterministic is None:
            return False

        source = str(getattr(deterministic, "source", "") or "").strip().lower()

        if source == "deterministic_math":
            return True

        if route_kind not in {"conversation", "mixed", "unclear"}:
            return True

        return False

    def build_response_plan(
        self,
        route: Any,
        user_profile: dict | None = None,
        *,
        stream_mode: StreamMode | None = None,
    ) -> ResponsePlan:
        selected_stream_mode = stream_mode or self.default_stream_mode
        route_kind_value = self._route_kind_value(getattr(route, "kind", "conversation"))
        normalized_language = self._normalize_language(getattr(route, "language", "en"))
        conversation_topics = list(getattr(route, "conversation_topics", []) or [])
        normalized_text = str(getattr(route, "normalized_text", "") or "").strip()

        if route_kind_value in {"conversation", "mixed", "unclear"}:
            live_payload = self._try_local_llm_stream_payload(
                normalized_text=normalized_text,
                language=normalized_language,
                topics=conversation_topics,
                user_profile=user_profile,
                route_kind=route_kind_value,
                stream_mode=selected_stream_mode,
            )
            if live_payload is not None:
                return ResponsePlan(
                    turn_id=create_turn_id("reply"),
                    language=normalized_language,
                    route_kind=self._resolve_route_kind(route_kind_value),
                    stream_mode=selected_stream_mode,
                    metadata={
                        "display_title": live_payload["display_title"],
                        "display_lines": list(live_payload.get("display_lines", []) or []),
                        "reply_source": live_payload["source"],
                        "conversation_topics": conversation_topics,
                        "suggested_actions": [],
                        "route_confidence": float(getattr(route, "confidence", 0.0) or 0.0),
                        "live_chunk_factory": live_payload["factory"],
                        "live_streaming": True,
                    },
                )

        reply = self.build_reply(route, user_profile)
        plan = self.reply_to_plan(
            reply,
            route_kind=route_kind_value,
            stream_mode=selected_stream_mode,
        )

        plan.metadata.update(
            {
                "reply_source": reply.source,
                "display_title": reply.display_title,
                "display_lines": list(reply.display_lines),
                "conversation_topics": conversation_topics,
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