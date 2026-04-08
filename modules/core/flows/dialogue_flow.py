from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.runtime.contracts import (
    ChunkKind,
    ResponsePlan,
    RouteDecision,
    RouteKind,
    StreamMode,
    ToolInvocation,
    create_turn_id,
)
from modules.shared.logging.logger import get_logger

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class DialogueRouteBridge:
    """
    Lightweight adapter for dialogue services that still expect the older
    route-like shape while the rest of the runtime uses RouteDecision.
    """

    kind: str
    reply_mode: str
    language: str
    raw_text: str
    normalized_text: str
    action_result: Any | None = None
    confidence: float = 0.0
    conversation_topics: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def has_action(self) -> bool:
        return self.action_result is not None


class DialogueFlowOrchestrator:
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

        return bool(
            assistant.deliver_response_plan(
                plan,
                source="dialogue_flow",
                remember=True,
                extra_metadata=self._route_memory_metadata(route, lang, source="dialogue_flow"),
            )
        )

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

    # ------------------------------------------------------------------
    # Plan building
    # ------------------------------------------------------------------

    def _build_dialogue_plan(
        self,
        *,
        route: RouteDecision,
        route_bridge: DialogueRouteBridge,
        user_profile: dict[str, Any],
        language: str,
    ) -> ResponsePlan:
        dialogue_service = self.assistant.dialogue

        build_response_plan = getattr(dialogue_service, "build_response_plan", None)
        if callable(build_response_plan):
            try:
                return build_response_plan(
                    route_bridge,
                    user_profile,
                    stream_mode=self.assistant.stream_mode,
                )
            except TypeError:
                try:
                    return build_response_plan(route_bridge, user_profile)
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
                route_bridge=route_bridge,
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
                route_bridge=route_bridge,
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
        route_bridge: DialogueRouteBridge,
        user_profile: dict[str, Any],
    ) -> Any:
        try:
            return build_reply(route_bridge, user_profile)
        except TypeError:
            try:
                return build_reply(route, user_profile)
            except TypeError:
                try:
                    return build_reply(route_bridge)
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
                "Nie złapałam jeszcze dokładnie, o co chodzi. Powiedz to jeszcze raz trochę inaczej, a spróbuję lepiej to uchwycić.",
                "I did not catch exactly what you meant yet. Say it again a little differently, and I will try to catch it better.",
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

    # ------------------------------------------------------------------
    # Route adaptation
    # ------------------------------------------------------------------

    def _build_dialogue_route_bridge(
        self,
        route: RouteDecision,
        language: str,
    ) -> DialogueRouteBridge:
        suggested_actions = self._suggested_action_names(route)
        action_result = None

        immediate_invocations = self._immediate_tool_invocations(route)
        if immediate_invocations:
            action_result = self._payload_from_invocation(
                immediate_invocations[0],
                route.normalized_text,
            )

        return DialogueRouteBridge(
            kind=route.kind.value,
            reply_mode=self._reply_mode_for_route(route),
            language=language,
            raw_text=route.raw_text,
            normalized_text=route.normalized_text,
            action_result=action_result,
            confidence=float(route.confidence),
            conversation_topics=list(route.conversation_topics),
            suggested_actions=suggested_actions,
            notes=list(route.notes),
        )

    def _reply_mode_for_route(self, route: RouteDecision) -> str:
        if route.kind == RouteKind.ACTION:
            return "execute"
        if route.kind == RouteKind.MIXED:
            return "reply_then_offer"
        if route.kind == RouteKind.CONVERSATION:
            return "reply"
        return "clarify"

    def _route_with_invocations(
        self,
        *,
        route: RouteDecision,
        invocations: list[ToolInvocation],
        force_kind: RouteKind,
    ) -> RouteDecision:
        primary = route.primary_intent
        if invocations:
            primary = self._action_name_from_tool(invocations[0].tool_name)

        return RouteDecision(
            turn_id=route.turn_id,
            raw_text=route.raw_text,
            normalized_text=route.normalized_text,
            language=route.language,
            kind=force_kind,
            confidence=route.confidence,
            primary_intent=primary,
            intents=list(route.intents),
            conversation_topics=list(route.conversation_topics),
            tool_invocations=list(invocations),
            notes=list(route.notes),
            metadata=dict(route.metadata),
        )

    def _route_memory_metadata(
        self,
        route: RouteDecision,
        language: str,
        *,
        source: str,
    ) -> dict[str, Any]:
        return {
            "source": source,
            "route_kind": route.kind.value,
            "language": language,
            "topics": list(route.conversation_topics),
            "primary_intent": route.primary_intent,
            "suggested_actions": self._suggested_action_names(route),
            "notes": list(route.notes),
        }

    # ------------------------------------------------------------------
    # Tool/action helpers
    # ------------------------------------------------------------------

    def _immediate_tool_invocations(self, route: RouteDecision) -> list[ToolInvocation]:
        return [
            invocation
            for invocation in route.tool_invocations
            if bool(getattr(invocation, "execute_immediately", True))
        ]

    def _suggested_tool_invocations(self, route: RouteDecision) -> list[ToolInvocation]:
        return [
            invocation
            for invocation in route.tool_invocations
            if not bool(getattr(invocation, "execute_immediately", True))
        ]

    def _suggested_action_names(self, route: RouteDecision) -> list[str]:
        actions: list[str] = []
        for invocation in self._suggested_tool_invocations(route):
            action_name = self._action_name_from_tool(invocation.tool_name)
            if action_name and action_name not in actions:
                actions.append(action_name)
        return actions

    def _payload_from_invocation(self, invocation: ToolInvocation, normalized_text: str) -> Any:
        class _Payload:
            def __init__(self, action: str, data: dict[str, Any], normalized_text: str) -> None:
                self.action = action
                self.data = data
                self.normalized_text = normalized_text
                self.confidence = 1.0
                self.needs_confirmation = False
                self.suggestions = []

        return _Payload(
            action=self._action_name_from_tool(invocation.tool_name),
            data=dict(invocation.payload or {}),
            normalized_text=normalized_text,
        )

    @staticmethod
    def _action_name_from_tool(tool_name: str) -> str:
        mapping = {
            "system.help": "help",
            "system.status": "status",
            "memory.list": "memory_list",
            "memory.clear": "memory_clear",
            "memory.store": "memory_store",
            "memory.recall": "memory_recall",
            "memory.forget": "memory_forget",
            "reminders.list": "reminders_list",
            "reminders.clear": "reminders_clear",
            "reminders.create": "reminder_create",
            "reminders.delete": "reminder_delete",
            "timer.start": "timer_start",
            "timer.stop": "timer_stop",
            "focus.start": "focus_start",
            "break.start": "break_start",
            "assistant.introduce": "introduce_self",
            "clock.time": "ask_time",
            "clock.date": "ask_date",
            "clock.day": "ask_day",
            "clock.month": "ask_month",
            "clock.year": "ask_year",
            "system.sleep": "exit",
            "system.shutdown": "shutdown",
        }
        normalized = str(tool_name or "").strip().lower()
        return mapping.get(normalized, normalized)

    # ------------------------------------------------------------------
    # Unclear request helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _looks_like_feature_request(normalized_text: str) -> bool:
        phrases = [
            "can you",
            "could you",
            "will you",
            "czy mozesz",
            "czy możesz",
            "mozesz",
            "możesz",
            "potrafisz",
            "zrob",
            "zrób",
            "zrobisz",
            "uruchom",
            "wlacz",
            "włącz",
            "wlaczysz",
            "włączysz",
            "turn on",
            "start",
            "open",
            "show",
        ]
        lowered = str(normalized_text or "").strip().lower()
        return any(phrase in lowered for phrase in phrases)


__all__ = [
    "DialogueFlowOrchestrator",
    "DialogueRouteBridge",
]