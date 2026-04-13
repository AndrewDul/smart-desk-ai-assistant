from __future__ import annotations

from typing import Any

from modules.runtime.contracts import (
    IntentMatch,
    RouteDecision,
    RouteKind,
    create_turn_id,
    normalize_text,
)


class CompanionRouterRouteMixin:
    """
    Public routing flow for semantic companion decisions.
    """

    def _normalize_route_context(self, context: dict[str, Any] | None) -> dict[str, str]:
        raw = dict(context or {})
        return {
            "input_source": str(raw.get("input_source", "voice") or "voice").strip().lower() or "voice",
            "capture_phase": str(raw.get("capture_phase", "") or "").strip(),
            "capture_mode": str(raw.get("capture_mode", "") or "").strip(),
            "capture_backend": str(raw.get("capture_backend", "") or "").strip(),
        }

    def _build_context_notes(self, route_context: dict[str, str]) -> list[str]:
        notes: list[str] = []
        capture_phase = route_context.get("capture_phase", "")
        capture_mode = route_context.get("capture_mode", "")
        capture_backend = route_context.get("capture_backend", "")

        if capture_phase:
            notes.append(f"capture_phase:{capture_phase}")
        if capture_mode and capture_mode != capture_phase:
            notes.append(f"capture_mode:{capture_mode}")
        if capture_backend:
            notes.append(f"capture_backend:{capture_backend}")
        return notes

    def route(
        self,
        text: str,
        preferred_language: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> RouteDecision:
        raw_text = str(text or "").strip()
        normalized_text = normalize_text(raw_text)
        language = self._resolve_language(normalized_text, preferred_language)

        route_context = self._normalize_route_context(context)
        context_notes = self._build_context_notes(route_context)

        if not normalized_text:
            return RouteDecision(
                turn_id=create_turn_id(),
                raw_text=raw_text,
                normalized_text=normalized_text,
                language=language,
                kind=RouteKind.UNCLEAR,
                confidence=0.0,
                primary_intent="unknown",
                intents=[],
                conversation_topics=[],
                tool_invocations=[],
                notes=["empty_input", *context_notes],
                metadata=dict(route_context),
            )

        parser_result = self.parser.parse(raw_text)
        conversation_topics = self._detect_conversation_topics(normalized_text)
        intent_matches = self._build_intent_matches(parser_result, conversation_topics)

        parser_action = str(getattr(parser_result, "action", "") or "").strip()
        route_metadata = {
            **route_context,
            "parser_action": parser_action,
        }

        explicit_action = self._should_treat_parser_action_as_explicit(
            normalized_text=normalized_text,
            parser_result=parser_result,
            conversation_topics=conversation_topics,
        )

        explicit_tool_invocations = (
            self._build_explicit_tool_invocations(parser_result)
            if explicit_action
            else []
        )

        capture_phase = route_context.get("capture_phase", "")
        inline_after_wake = capture_phase == "inline_command_after_wake"
        follow_up_like = capture_phase in {"follow_up", "grace"}

        if parser_action in {"confirm_yes", "confirm_no"}:
            return RouteDecision(
                turn_id=create_turn_id(),
                raw_text=raw_text,
                normalized_text=normalized_text,
                language=language,
                kind=RouteKind.ACTION,
                confidence=1.0,
                primary_intent=parser_action,
                intents=intent_matches,
                conversation_topics=[],
                tool_invocations=explicit_tool_invocations,
                notes=[*context_notes, "confirmation_turn"],
                metadata=route_metadata,
            )

        if explicit_action:
            if conversation_topics:
                return RouteDecision(
                    turn_id=create_turn_id(),
                    raw_text=raw_text,
                    normalized_text=normalized_text,
                    language=language,
                    kind=RouteKind.MIXED,
                    confidence=max(float(parser_result.confidence), 0.89 if inline_after_wake else 0.88),
                    primary_intent=parser_action,
                    intents=intent_matches,
                    conversation_topics=conversation_topics,
                    tool_invocations=explicit_tool_invocations,
                    notes=[*context_notes, "explicit_action_plus_conversation_context"],
                    metadata=route_metadata,
                )

            return RouteDecision(
                turn_id=create_turn_id(),
                raw_text=raw_text,
                normalized_text=normalized_text,
                language=language,
                kind=RouteKind.ACTION,
                confidence=max(float(parser_result.confidence), 0.92 if inline_after_wake else 0.90),
                primary_intent=parser_action,
                intents=intent_matches,
                conversation_topics=[],
                tool_invocations=explicit_tool_invocations,
                notes=[*context_notes, "explicit_action"],
                metadata=route_metadata,
            )

        inferred_suggestions = self._build_suggested_tool_invocations(conversation_topics)

        if conversation_topics:
            primary_topic = conversation_topics[0]
            kind = RouteKind.MIXED if inferred_suggestions else RouteKind.CONVERSATION
            confidence = 0.74 if inferred_suggestions else 0.68

            return RouteDecision(
                turn_id=create_turn_id(),
                raw_text=raw_text,
                normalized_text=normalized_text,
                language=language,
                kind=kind,
                confidence=confidence,
                primary_intent=primary_topic,
                intents=intent_matches,
                conversation_topics=conversation_topics,
                tool_invocations=inferred_suggestions,
                notes=[*context_notes, "conversation_semantic_match"],
                metadata=route_metadata,
            )

        if self._looks_like_general_question(raw_text, normalized_text, language):
            return RouteDecision(
                turn_id=create_turn_id(),
                raw_text=raw_text,
                normalized_text=normalized_text,
                language=language,
                kind=RouteKind.CONVERSATION,
                confidence=0.66,
                primary_intent="knowledge_query",
                intents=intent_matches,
                conversation_topics=["knowledge_query"],
                tool_invocations=[],
                notes=[*context_notes, "general_question"],
                metadata=route_metadata,
            )

        if self._looks_like_conversation_request(normalized_text, language):
            return RouteDecision(
                turn_id=create_turn_id(),
                raw_text=raw_text,
                normalized_text=normalized_text,
                language=language,
                kind=RouteKind.CONVERSATION,
                confidence=0.62,
                primary_intent="small_talk",
                intents=intent_matches
                + [
                    IntentMatch(
                        name="small_talk",
                        confidence=0.62,
                        entities=[],
                        requires_clarification=False,
                        metadata={"source": "direct_conversation_cue"},
                    )
                ],
                conversation_topics=["small_talk"],
                tool_invocations=[],
                notes=[*context_notes, "direct_conversation_cue"],
                metadata=route_metadata,
            )

        if follow_up_like and parser_action == "unclear":
            return RouteDecision(
                turn_id=create_turn_id(),
                raw_text=raw_text,
                normalized_text=normalized_text,
                language=language,
                kind=RouteKind.CONVERSATION,
                confidence=max(float(parser_result.confidence), 0.44),
                primary_intent="follow_up_conversation",
                intents=intent_matches,
                conversation_topics=["follow_up_conversation"],
                tool_invocations=[],
                notes=[*context_notes, "follow_up_context_bias"],
                metadata={
                    **route_metadata,
                    "context_bias": "follow_up_conversation",
                },
            )

        if parser_action == "unclear":
            notes = [*context_notes, "parser_unclear"]
            if getattr(parser_result, "suggestions", None):
                notes.append("parser_has_suggestions")

            return RouteDecision(
                turn_id=create_turn_id(),
                raw_text=raw_text,
                normalized_text=normalized_text,
                language=language,
                kind=RouteKind.UNCLEAR,
                confidence=float(parser_result.confidence),
                primary_intent="unclear",
                intents=intent_matches,
                conversation_topics=[],
                tool_invocations=[],
                notes=notes,
                metadata={
                    **route_metadata,
                    "parser_suggestions": list(getattr(parser_result, "suggestions", []) or []),
                },
            )

        return RouteDecision(
            turn_id=create_turn_id(),
            raw_text=raw_text,
            normalized_text=normalized_text,
            language=language,
            kind=RouteKind.UNCLEAR,
            confidence=0.20,
            primary_intent="unknown",
            intents=intent_matches,
            conversation_topics=[],
            tool_invocations=[],
            notes=[*context_notes, "no_confident_route"],
            metadata=route_metadata,
        )


__all__ = ["CompanionRouterRouteMixin"]