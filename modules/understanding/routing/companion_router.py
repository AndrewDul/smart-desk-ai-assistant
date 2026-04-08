from __future__ import annotations

import re
from typing import Any

from modules.runtime.contracts import (
    EntityValue,
    IntentMatch,
    RouteDecision,
    RouteKind,
    ToolInvocation,
    create_turn_id,
    normalize_text,
)
from modules.shared.logging.logger import append_log


class SemanticCompanionRouter:
    """
    Final semantic companion router for NeXa.

    Responsibilities:
    - reuse the deterministic IntentParser for explicit commands
    - detect conversational / supportive / playful requests
    - distinguish between action, conversation, mixed, and unclear
    - emit modern RouteDecision objects for the new assistant core

    Design rule:
    conversational suggestions become non-immediate tool suggestions.
    They must never silently execute on their own.
    """

    _ACTION_TO_TOOL: dict[str, str] = {
        "help": "system.help",
        "status": "system.status",
        "memory_list": "memory.list",
        "memory_clear": "memory.clear",
        "memory_store": "memory.store",
        "memory_recall": "memory.recall",
        "memory_forget": "memory.forget",
        "reminders_list": "reminders.list",
        "reminders_clear": "reminders.clear",
        "reminder_create": "reminders.create",
        "reminder_delete": "reminders.delete",
        "timer_start": "timer.start",
        "timer_stop": "timer.stop",
        "focus_start": "focus.start",
        "break_start": "break.start",
        "introduce_self": "assistant.introduce",
        "ask_time": "clock.time",
        "show_time": "clock.time",
        "ask_date": "clock.date",
        "show_date": "clock.date",
        "ask_day": "clock.day",
        "show_day": "clock.day",
        "ask_month": "clock.month",
        "show_month": "clock.month",
        "ask_year": "clock.year",
        "show_year": "clock.year",
        "exit": "system.sleep",
        "shutdown": "system.shutdown",
        "confirm_yes": "dialogue.confirm",
        "confirm_no": "dialogue.confirm",
    }

    _DIRECT_ACTIONS = {
        "help",
        "status",
        "memory_list",
        "memory_clear",
        "memory_store",
        "memory_recall",
        "memory_forget",
        "reminders_list",
        "reminders_clear",
        "reminder_create",
        "reminder_delete",
        "timer_start",
        "timer_stop",
        "focus_start",
        "break_start",
        "introduce_self",
        "ask_time",
        "show_time",
        "ask_date",
        "show_date",
        "ask_day",
        "show_day",
        "ask_month",
        "show_month",
        "ask_year",
        "show_year",
        "exit",
        "shutdown",
    }

    _ALWAYS_EXPLICIT_ACTIONS = {
        "status",
        "memory_list",
        "memory_clear",
        "memory_store",
        "memory_recall",
        "memory_forget",
        "reminders_list",
        "reminders_clear",
        "reminder_create",
        "reminder_delete",
        "timer_start",
        "timer_stop",
        "introduce_self",
        "ask_time",
        "show_time",
        "ask_date",
        "show_date",
        "ask_day",
        "show_day",
        "ask_month",
        "show_month",
        "ask_year",
        "show_year",
        "exit",
        "shutdown",
        "confirm_yes",
        "confirm_no",
    }

    _EXPLICIT_FOCUS_PATTERNS = (
        r"\bstart focus\b",
        r"\bstart focus mode\b",
        r"\bfocus mode\b",
        r"\bfocus session\b",
        r"\bwlacz focus\b",
        r"\bwłącz focus\b",
        r"\bzacznij focus\b",
        r"\bsesja focus\b",
        r"\btryb skupienia\b",
        r"\bsesja nauki\b",
    )

    _EXPLICIT_BREAK_PATTERNS = (
        r"\bstart break\b",
        r"\bstart break mode\b",
        r"\bbreak mode\b",
        r"\btake a break\b",
        r"\bwlacz przerwe\b",
        r"\bwłącz przerwę\b",
        r"\bzacznij przerwe\b",
        r"\bzacznij przerwę\b",
        r"\btryb przerwy\b",
        r"\bprzerwa\b",
    )

    _EXPLICIT_HELP_PATTERNS = (
        r"^help$",
        r"^show help$",
        r"^open help$",
        r"^show menu$",
        r"^open menu$",
        r"^what can you do$",
        r"^how can you help me$",
        r"^pomoc$",
        r"^pokaz pomoc$",
        r"^pokaż pomoc$",
        r"^pokaz menu$",
        r"^pokaż menu$",
        r"^co potrafisz$",
        r"^co umiesz$",
        r"^jak mozesz mi pomoc$",
        r"^jak możesz mi pomóc$",
    )

    _CONVERSATION_TOPIC_PATTERNS: dict[str, tuple[str, ...]] = {
        "low_energy": (
            r"\bi am tired\b",
            r"\bi feel tired\b",
            r"\bi m tired\b",
            r"\bi am exhausted\b",
            r"\bi feel exhausted\b",
            r"\bi am sleepy\b",
            r"\bi feel sleepy\b",
            r"\bi do not feel well\b",
            r"\bi dont feel well\b",
            r"\bjestem zmeczony\b",
            r"\bjestem zmeczona\b",
            r"\bczuje sie zmeczony\b",
            r"\bczuje sie zmeczona\b",
            r"\bczuje sie zle\b",
            r"\bnie czuje sie dobrze\b",
            r"\bzle sie czuje\b",
            r"\bchce mi sie spac\b",
            r"\bjestem senny\b",
            r"\bjestem senna\b",
        ),
        "focus_struggle": (
            r"\bi cannot focus\b",
            r"\bi cant focus\b",
            r"\bi can not focus\b",
            r"\bi cannot concentrate\b",
            r"\bi cant concentrate\b",
            r"\bi can not concentrate\b",
            r"\bi am distracted\b",
            r"\bi feel distracted\b",
            r"\bnie moge sie skupic\b",
            r"\bnie umiem sie skupic\b",
            r"\bnie moge sie skoncentrowac\b",
            r"\bnie moge sie dzisiaj skupic\b",
            r"\bciezko mi sie skupic\b",
            r"\bnie mam skupienia\b",
            r"\brozprasza mnie\b",
        ),
        "overwhelmed": (
            r"\bi feel overwhelmed\b",
            r"\bi am overwhelmed\b",
            r"\bi have too much to do\b",
            r"\btoo much to do\b",
            r"\bi feel stressed\b",
            r"\bi am stressed\b",
            r"\bmam za duzo do zrobienia\b",
            r"\bmam duzo do zrobienia\b",
            r"\bjestem przytloczony\b",
            r"\bjestem przytloczona\b",
            r"\bczuje sie przytloczony\b",
            r"\bczuje sie przytlocona\b",
            r"\bstresuje sie\b",
        ),
        "study_help": (
            r"\bi need help studying\b",
            r"\bhelp me study\b",
            r"\bi need help with studying\b",
            r"\bcan you help me study\b",
            r"\bmusze sie uczyc\b",
            r"\bpotrzebuje pomocy w nauce\b",
            r"\bpomoz mi sie uczyc\b",
            r"\bpomoz mi w nauce\b",
            r"\bmusze sie skupic na nauce\b",
        ),
        "encouragement": (
            r"\bcheer me up\b",
            r"\bmotivate me\b",
            r"\bi feel lazy\b",
            r"\bi am lazy\b",
            r"\bi need motivation\b",
            r"\bpodnies mnie na duchu\b",
            r"\bzmotywuj mnie\b",
            r"\bnie chce mi sie\b",
            r"\bjestem leniwy\b",
            r"\bjestem leniwa\b",
            r"\bpotrzebuje motywacji\b",
        ),
        "small_talk": (
            r"\bcan we talk\b",
            r"\bcan we talk for a minute\b",
            r"\btalk to me\b",
            r"\bcan you talk with me\b",
            r"\bcan you stay with me\b",
            r"\bi had a difficult day\b",
            r"\bi had a hard day\b",
            r"\bi feel bad\b",
            r"\bpogadaj ze mna\b",
            r"\bmozemy pogadac\b",
            r"\bmozemy porozmawiac chwile\b",
            r"\bporozmawiaj ze mna chwile\b",
            r"\bchce pogadac\b",
            r"\bmialem trudny dzien\b",
            r"\bmialam trudny dzien\b",
            r"\bslaby dzien\b",
        ),
        "humour": (
            r"\btell me a joke\b",
            r"\btell me something funny\b",
            r"\bsay something funny\b",
            r"\bpowiedz cos smiesznego\b",
            r"\bpowiedz cos zabawnego\b",
            r"\bpowiedz dowcip\b",
            r"\bopowiedz dowcip\b",
            r"\brozsmiesz mnie\b",
            r"\bzart\b",
        ),
        "riddle": (
            r"\btell me a riddle\b",
            r"\bgive me a riddle\b",
            r"\bask me a riddle\b",
            r"\bzadaj mi zagadke\b",
            r"\bpowiedz zagadke\b",
            r"\bopowiedz zagadke\b",
            r"\bdaj mi zagadke\b",
            r"\bzagadka\b",
        ),
        "interesting_fact": (
            r"\btell me something interesting\b",
            r"\btell me something interesting about animals\b",
            r"\btell me an animal fact\b",
            r"\bpowiedz mi cos ciekawego\b",
            r"\bopowiedz mi cos ciekawego\b",
            r"\bopowiedz mi cos ciekawego o zwierzetach\b",
            r"\bciekawostka\b",
        ),
    }

    _TOPIC_PRIORITY = {
        "humour": 100,
        "riddle": 95,
        "interesting_fact": 90,
        "knowledge_query": 80,
        "small_talk": 70,
        "overwhelmed": 65,
        "focus_struggle": 64,
        "low_energy": 63,
        "study_help": 62,
        "encouragement": 61,
    }

    _DIRECT_CONVERSATION_CUES = {
        "pl": {
            "pogadaj ze mna",
            "mozemy pogadac",
            "mozemy porozmawiac chwile",
            "porozmawiaj ze mna chwile",
            "chce pogadac",
            "powiedz cos smiesznego",
            "zadaj mi zagadke",
            "opowiedz mi cos ciekawego",
            "opowiedz mi cos ciekawego o zwierzetach",
            "zmotywuj mnie",
            "podnies mnie na duchu",
        },
        "en": {
            "can we talk",
            "can we talk for a minute",
            "talk to me",
            "can you talk with me for a minute",
            "tell me a joke",
            "tell me something funny",
            "say something funny",
            "tell me a riddle",
            "give me a riddle",
            "tell me something interesting",
            "tell me something interesting about animals",
            "cheer me up",
            "motivate me",
        },
    }

    _QUESTION_STARTERS = {
        "pl": (
            "ile",
            "co",
            "czym",
            "kim",
            "kto",
            "gdzie",
            "kiedy",
            "dlaczego",
            "jak",
            "po co",
            "czy",
            "wytlumacz",
            "wyjasnij",
            "opowiedz",
        ),
        "en": (
            "what",
            "who",
            "where",
            "when",
            "why",
            "how",
            "how much",
            "how many",
            "can you explain",
            "explain",
            "tell me about",
        ),
    }

    _GENERIC_KNOWLEDGE_PATTERNS = (
        r"\bhow much is\b",
        r"\bwhat is\b",
        r"\bwho is\b",
        r"\bwhere is\b",
        r"\bwhen is\b",
        r"\bwhy is\b",
        r"\bwhy does\b",
        r"\bhow does\b",
        r"\bhow do\b",
        r"\bexplain\b",
        r"\btell me about\b",
        r"\bile to jest\b",
        r"\bco to jest\b",
        r"\bczym jest\b",
        r"\bkim jest\b",
        r"\bgdzie jest\b",
        r"\bkiedy jest\b",
        r"\bdlaczego\b",
        r"\bjak dziala\b",
        r"\bwyjasnij\b",
        r"\bwytlumacz\b",
        r"\bopowiedz o\b",
    )

    _MATH_PATTERNS = (
        r"^\s*\d+\s*[\+\-\*x/]\s*\d+\s*$",
        r"\b\d+\s*(plus|minus|times|multiplied by|divided by)\s*\d+\b",
        r"\b\d+\s*(dodac|dodać|minus|razy|podzielic przez|podzielić przez)\s*\d+\b",
        r"\bhow much is\b.*\d+",
        r"\bile to jest\b.*\d+",
    )

    def __init__(self, parser: Any) -> None:
        self.parser = parser

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
                intents=intent_matches + [
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

    # ------------------------------------------------------------------
    # Explicit action logic
    # ------------------------------------------------------------------

    def _should_treat_parser_action_as_explicit(
        self,
        *,
        normalized_text: str,
        parser_result: Any,
        conversation_topics: list[str],
    ) -> bool:
        action = str(getattr(parser_result, "action", "") or "").strip()
        if action in {"unknown", "unclear"}:
            return False

        if action in self._ALWAYS_EXPLICIT_ACTIONS:
            return True

        if action == "help":
            return any(re.search(pattern, normalized_text) for pattern in self._EXPLICIT_HELP_PATTERNS)

        if action == "focus_start":
            if getattr(parser_result, "data", {}).get("minutes") is not None:
                return True
            if any(re.search(pattern, normalized_text) for pattern in self._EXPLICIT_FOCUS_PATTERNS):
                return True
            if conversation_topics:
                return False
            return normalized_text in {
                "focus",
                "focus mode",
                "focus session",
                "skupienie",
                "tryb skupienia",
                "sesja focus",
                "sesja nauki",
            }

        if action == "break_start":
            if getattr(parser_result, "data", {}).get("minutes") is not None:
                return True
            if any(re.search(pattern, normalized_text) for pattern in self._EXPLICIT_BREAK_PATTERNS):
                return True
            if conversation_topics:
                return False
            return normalized_text in {
                "break",
                "break mode",
                "przerwa",
                "tryb przerwy",
            }

        return action in self._DIRECT_ACTIONS

    # ------------------------------------------------------------------
    # Intent / entity projection
    # ------------------------------------------------------------------

    def _build_intent_matches(
        self,
        parser_result: Any,
        conversation_topics: list[str],
    ) -> list[IntentMatch]:
        matches: list[IntentMatch] = []

        action = str(getattr(parser_result, "action", "") or "").strip()
        if action and action not in {"unknown", "unclear"}:
            matches.append(
                IntentMatch(
                    name=action,
                    confidence=float(getattr(parser_result, "confidence", 1.0) or 1.0),
                    entities=self._entities_from_parser_data(getattr(parser_result, "data", {}) or {}),
                    requires_clarification=bool(getattr(parser_result, "needs_confirmation", False)),
                    metadata={
                        "source": "intent_parser",
                        "normalized_text": str(getattr(parser_result, "normalized_text", "") or ""),
                        "suggestions": list(getattr(parser_result, "suggestions", []) or []),
                    },
                )
            )

        for topic in conversation_topics:
            matches.append(
                IntentMatch(
                    name=topic,
                    confidence=0.72,
                    entities=[],
                    requires_clarification=False,
                    metadata={"source": "semantic_topic_match"},
                )
            )

        return matches

    @staticmethod
    def _entities_from_parser_data(data: dict[str, Any]) -> list[EntityValue]:
        entities: list[EntityValue] = []
        for key, value in (data or {}).items():
            if value in ("", None):
                continue
            entities.append(
                EntityValue(
                    name=str(key),
                    value=value,
                    confidence=1.0,
                    source_text=str(value),
                )
            )
        return entities

    # ------------------------------------------------------------------
    # Tool invocations
    # ------------------------------------------------------------------

    def _build_explicit_tool_invocations(self, parser_result: Any) -> list[ToolInvocation]:
        action = str(getattr(parser_result, "action", "") or "").strip()
        tool_name = self._ACTION_TO_TOOL.get(action)
        if not tool_name:
            return []

        payload = dict(getattr(parser_result, "data", {}) or {})

        if action == "confirm_yes":
            payload.setdefault("answer", "yes")
        elif action == "confirm_no":
            payload.setdefault("answer", "no")
        elif action.startswith("show_"):
            payload.setdefault("show", True)
            payload.setdefault("display", True)

        return [
            ToolInvocation(
                tool_name=tool_name,
                payload=payload,
                reason=f"explicit_user_request:{action}",
                confidence=max(float(getattr(parser_result, "confidence", 1.0) or 1.0), 0.75),
                execute_immediately=True,
            )
        ]

    def _build_suggested_tool_invocations(self, topics: list[str]) -> list[ToolInvocation]:
        suggestions: list[ToolInvocation] = []

        def add(tool_name: str, reason: str) -> None:
            if any(existing.tool_name == tool_name for existing in suggestions):
                return
            suggestions.append(
                ToolInvocation(
                    tool_name=tool_name,
                    payload={},
                    reason=reason,
                    confidence=0.65,
                    execute_immediately=False,
                )
            )

        topic_set = set(topics)

        if "focus_struggle" in topic_set:
            add("focus.start", "suggested_from_focus_struggle")
            add("break.start", "suggested_from_focus_struggle")

        if "study_help" in topic_set:
            add("focus.start", "suggested_from_study_help")
            add("reminders.create", "suggested_from_study_help")

        if "overwhelmed" in topic_set:
            add("focus.start", "suggested_from_overwhelmed")
            add("break.start", "suggested_from_overwhelmed")
            add("reminders.create", "suggested_from_overwhelmed")

        if "low_energy" in topic_set:
            add("break.start", "suggested_from_low_energy")
            add("focus.start", "suggested_from_low_energy")

        if "encouragement" in topic_set:
            add("focus.start", "suggested_from_encouragement")

        return suggestions

    # ------------------------------------------------------------------
    # Topic detection
    # ------------------------------------------------------------------

    def _detect_conversation_topics(self, normalized_text: str) -> list[str]:
        found: list[str] = []

        for topic, patterns in self._CONVERSATION_TOPIC_PATTERNS.items():
            if any(re.search(pattern, normalized_text) for pattern in patterns):
                found.append(topic)

        if not found:
            return []

        unique = list(dict.fromkeys(found))
        unique.sort(key=lambda item: self._TOPIC_PRIORITY.get(item, 0), reverse=True)
        return unique

    # ------------------------------------------------------------------
    # Conversation heuristics
    # ------------------------------------------------------------------

    def _looks_like_general_question(
        self,
        raw_text: str,
        normalized_text: str,
        language: str,
    ) -> bool:
        raw_lower = str(raw_text or "").strip().lower()

        if "?" in raw_text:
            return True

        starters = self._QUESTION_STARTERS.get(language, ())
        if any(normalized_text.startswith(starter) for starter in starters):
            return True

        if any(re.search(pattern, normalized_text) for pattern in self._GENERIC_KNOWLEDGE_PATTERNS):
            return True

        if any(re.search(pattern, normalized_text) for pattern in self._MATH_PATTERNS):
            return True

        if raw_lower.startswith(("explain ", "wyjasnij ", "wyjaśnij ", "wytlumacz ", "wytłumacz ")):
            return True

        return False

    def _looks_like_conversation_request(self, normalized_text: str, language: str) -> bool:
        cues = self._DIRECT_CONVERSATION_CUES.get(language, set())
        return normalized_text in cues

    # ------------------------------------------------------------------
    # Language
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_language(normalized_text: str, preferred_language: str | None) -> str:
        preferred = str(preferred_language or "").strip().lower()
        if preferred in {"pl", "en"}:
            return preferred

        polish_score = 0
        english_score = 0

        polish_markers = {
            "jestem",
            "czuje",
            "pomoz",
            "pomoc",
            "powiedz",
            "zagadke",
            "zwierzetach",
            "przypomnij",
            "zapamietaj",
            "usun",
            "wylacz",
            "godzine",
            "czas",
            "przerwe",
            "skupic",
            "nauce",
            "ze",
            "mi",
        }
        english_markers = {
            "what",
            "who",
            "where",
            "when",
            "why",
            "how",
            "help",
            "remember",
            "delete",
            "turn",
            "off",
            "time",
            "break",
            "focus",
            "study",
        }

        tokens = set(normalized_text.split())
        polish_score += len(tokens & polish_markers)
        english_score += len(tokens & english_markers)

        if polish_score > english_score:
            return "pl"
        return "en"


__all__ = ["SemanticCompanionRouter"]