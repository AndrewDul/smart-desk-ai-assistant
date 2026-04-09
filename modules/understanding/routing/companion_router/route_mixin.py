from __future__ import annotations

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

    def route(self, text: str, preferred_language: str | None = None) -> RouteDecision:
        raw_text = str(text or "").strip()
        normalized_text = normalize_text(raw_text)
        language = self._resolve_language(normalized_text, preferred_language)

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
                notes=["empty_input"],
                metadata={},
            )

        parser_result = self.parser.parse(raw_text)
        conversation_topics = self._detect_conversation_topics(normalized_text)
        intent_matches = self._build_intent_matches(parser_result, conversation_topics)

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

        if parser_result.action in {"confirm_yes", "confirm_no"}:
            return RouteDecision(
                turn_id=create_turn_id(),
                raw_text=raw_text,
                normalized_text=normalized_text,
                language=language,
                kind=RouteKind.ACTION,
                confidence=1.0,
                primary_intent=parser_result.action,
                intents=intent_matches,
                conversation_topics=[],
                tool_invocations=explicit_tool_invocations,
                notes=["confirmation_turn"],
                metadata={"parser_action": parser_result.action},
            )

        if explicit_action:
            if conversation_topics:
                return RouteDecision(
                    turn_id=create_turn_id(),
                    raw_text=raw_text,
                    normalized_text=normalized_text,
                    language=language,
                    kind=RouteKind.MIXED,
                    confidence=max(float(parser_result.confidence), 0.88),
                    primary_intent=parser_result.action,
                    intents=intent_matches,
                    conversation_topics=conversation_topics,
                    tool_invocations=explicit_tool_invocations,
                    notes=["explicit_action_plus_conversation_context"],
                    metadata={"parser_action": parser_result.action},
                )

            return RouteDecision(
                turn_id=create_turn_id(),
                raw_text=raw_text,
                normalized_text=normalized_text,
                language=language,
                kind=RouteKind.ACTION,
                confidence=max(float(parser_result.confidence), 0.90),
                primary_intent=parser_result.action,
                intents=intent_matches,
                conversation_topics=[],
                tool_invocations=explicit_tool_invocations,
                notes=["explicit_action"],
                metadata={"parser_action": parser_result.action},
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
                notes=["conversation_semantic_match"],
                metadata={"parser_action": parser_result.action},
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
                notes=["general_question"],
                metadata={"parser_action": parser_result.action},
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
                notes=["direct_conversation_cue"],
                metadata={"parser_action": parser_result.action},
            )

        if parser_result.action == "unclear":
            notes = ["parser_unclear"]
            if parser_result.suggestions:
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
                    "parser_action": parser_result.action,
                    "parser_suggestions": list(parser_result.suggestions),
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
            notes=["no_confident_route"],
            metadata={"parser_action": parser_result.action},
        )


__all__ = ["CompanionRouterRouteMixin"]