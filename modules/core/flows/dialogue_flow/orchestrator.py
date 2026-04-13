from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RouteDecision, RouteKind
from modules.shared.logging.logger import get_logger

from .actions import DialogueFlowActions
from .planning import DialogueFlowPlanning
from .routing import DialogueFlowRouting
from .unclear import DialogueFlowUnclear

LOGGER = get_logger(__name__)


class DialogueFlowOrchestrator(
    DialogueFlowPlanning,
    DialogueFlowRouting,
    DialogueFlowActions,
    DialogueFlowUnclear,
):
    """
    Final dialogue execution flow for NeXa.

    Responsibilities:
    - build dialogue response plans from RouteDecision
    - execute conversation / mixed / unclear branches
    - bridge the dialogue service cleanly to the new contracts
    - keep thinking-ack and response streaming orchestration out of assistant.py
    """

    def __init__(self, assistant: Any) -> None:
        self.assistant = assistant

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def execute_dialogue_route(self, route: RouteDecision, language: str) -> bool:
        assistant = self.assistant
        lang = assistant._commit_language(language)

        dialogue_profile = assistant._build_dialogue_user_profile(preferred_language=lang)
        route_bridge = self._build_dialogue_route_bridge(route, lang)

        assistant.voice_session.set_state(
            "routing",
            detail=f"dialogue_plan:{route.kind.value}",
        )

        assistant._thinking_ack_start(language=lang, detail="dialogue_plan")
        try:
            plan = self._build_dialogue_plan(
                route=route,
                route_bridge=route_bridge,
                user_profile=dialogue_profile,
                language=lang,
            )
        except Exception as error:
            LOGGER.exception("Dialogue plan build failed: %s", error)
            plan = self._build_dialogue_fallback_plan(
                route=route,
                language=lang,
                reason="dialogue_plan_build_failed",
            )
        finally:
            assistant._thinking_ack_stop()

        delivered = bool(
            assistant.deliver_response_plan(
                plan,
                source="dialogue_flow",
                remember=True,
                extra_metadata=self._route_memory_metadata(route, lang, source="dialogue_flow"),
            )
        )

        if not delivered:
            LOGGER.error(
                "Dialogue response delivery returned False. "
                "Keeping runtime alive. turn_id=%s route_kind=%s",
                route.turn_id,
                route.kind.value,
            )
            return True

        return True

    def handle_conversation_route(self, *, route: RouteDecision, language: str) -> bool:
        self.assistant.pending_follow_up = None
        return self.execute_dialogue_route(route, language)

    def handle_conversation(self, *, route: RouteDecision, language: str) -> bool:
        return self.handle_conversation_route(route=route, language=language)

    def handle_mixed_route(self, *, route: RouteDecision, language: str) -> bool:
        assistant = self.assistant
        lang = assistant._commit_language(language)

        assistant.pending_follow_up = None
        delivered = self.execute_dialogue_route(route, lang)

        immediate_invocations = self._immediate_tool_invocations(route)
        if not immediate_invocations:
            suggested_actions = self._suggested_action_names(route)
            if suggested_actions:
                LOGGER.info(
                    "Mixed dialogue route contains suggestion-only actions: %s",
                    suggested_actions,
                )
            return delivered

        LOGGER.info(
            "Mixed dialogue route contains %s immediate action invocation(s). Executing after dialogue.",
            len(immediate_invocations),
        )
        explicit_route = self._route_with_invocations(
            route=route,
            invocations=immediate_invocations,
            force_kind=RouteKind.ACTION,
        )
        return bool(assistant.action_flow.execute(route=explicit_route, language=lang))

    def handle_mixed(self, *, route: RouteDecision, language: str) -> bool:
        return self.handle_mixed_route(route=route, language=language)

    def handle_unclear_route(self, *, route: RouteDecision, language: str) -> bool:
        assistant = self.assistant
        lang = assistant._commit_language(language)

        assistant.pending_follow_up = None

        parser_suggestions = list(route.metadata.get("parser_suggestions", []) or [])
        ask_for_confirmation = getattr(assistant.action_flow, "_ask_for_confirmation", None)

        if parser_suggestions and callable(ask_for_confirmation):
            LOGGER.info(
                "Unclear route contains parser suggestions. Asking for confirmation: %s",
                parser_suggestions,
            )
            return bool(
                ask_for_confirmation(
                    suggestions=parser_suggestions,
                    language=lang,
                    original_text=route.normalized_text,
                )
            )

        if self._looks_like_feature_request(route.normalized_text):
            return bool(
                assistant.deliver_text_response(
                    assistant._localized(
                        lang,
                        (
                            "Nie mam jeszcze tej funkcji w obecnej wersji, ale nadal mogę pomóc. "
                            "Mogę ustawić timer, przypomnienie, tryb skupienia, przerwę albo coś zapamiętać."
                        ),
                        (
                            "I do not have that feature in this version yet, but I can still help. "
                            "I can set a timer, create a reminder, start focus mode, begin a break, or remember something."
                        ),
                    ),
                    language=lang,
                    route_kind=RouteKind.UNCLEAR,
                    source="dialogue_unclear_feature_fallback",
                    metadata=self._route_memory_metadata(
                        route,
                        lang,
                        source="dialogue_unclear_feature_fallback",
                    ),
                )
            )

        return self.execute_dialogue_route(route, lang)

    def handle_unclear(self, *, route: RouteDecision, language: str) -> bool:
        return self.handle_unclear_route(route=route, language=language)


__all__ = ["DialogueFlowOrchestrator"]