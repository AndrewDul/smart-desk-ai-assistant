from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal

from modules.parsing.intent_parser import IntentParser, IntentResult


RouteKind = Literal["action", "conversation", "mixed", "unclear"]
ReplyMode = Literal["execute", "reply", "reply_then_offer", "clarify"]


@dataclass(slots=True)
class CompanionRoute:
    kind: RouteKind
    reply_mode: ReplyMode
    language: str
    raw_text: str
    normalized_text: str
    action_result: IntentResult
    confidence: float = 0.0
    conversation_topics: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def has_action(self) -> bool:
        return self.action_result.action not in {"unknown", "unclear", "confirm_yes", "confirm_no"}


class CompanionRouter:
    """
    Offline-first routing layer for NeXa.

    This router sits above the current IntentParser.
    It reuses the working action parser and adds a higher-level decision:
    - action
    - conversation
    - mixed
    - unclear

    Main design goal:
    preserve the current working architecture while making routing more semantic
    and more conversation-friendly.
    """

    _ACTIONABLE_INTENTS = {
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
        "ask_year",
        "show_year",
        "exit",
        "shutdown",
    }

    _TOPIC_PATTERNS: dict[str, tuple[str, ...]] = {
        "low_energy": (
            r"\bi am tired\b",
            r"\bi feel tired\b",
            r"\bi m tired\b",
            r"\bi am exhausted\b",
            r"\bi feel exhausted\b",
            r"\bi am sleepy\b",
            r"\bi feel sleepy\b",
            r"\bjestem zmeczony\b",
            r"\bjestem zmeczona\b",
            r"\bczuje sie zmeczony\b",
            r"\bczuje sie zmeczona\b",
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
            r"\bczuje sie przytloczona\b",
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
            r"\btalk to me\b",
            r"\bi had a difficult day\b",
            r"\bi had a hard day\b",
            r"\bi feel bad\b",
            r"\bcan you stay with me\b",
            r"\bpogadaj ze mna\b",
            r"\bmozemy pogadac\b",
            r"\bchce pogadac\b",
            r"\bmialem trudny dzien\b",
            r"\bmialam trudny dzien\b",
            r"\bslaby dzien\b",
        ),
        "humour": (
            r"\btell me a joke\b",
            r"\bsay something funny\b",
            r"\bpowiedz cos smiesznego\b",
            r"\bpowiedz cos zabawnego\b",
            r"\brozsmiesz mnie\b",
            r"\bzart\b",
        ),
        "riddle": (
            r"\btell me a riddle\b",
            r"\bgive me a riddle\b",
            r"\bzadaj mi zagadke\b",
            r"\bpowiedz zagadke\b",
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

    _DIRECT_CONVERSATION_CUES = {
        "pl": {
            "pogadaj ze mna",
            "mozemy pogadac",
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
            "talk to me",
            "tell me a joke",
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
        r"\bjak działa\b",
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

    def __init__(self, parser: IntentParser) -> None:
        self.parser = parser

    def route(self, text: str, preferred_language: str | None = None) -> CompanionRoute:
        raw_text = str(text or "").strip()
        normalized = self._normalize_text(raw_text)
        language = self._resolve_language(normalized, preferred_language)

        if not normalized:
            return CompanionRoute(
                kind="unclear",
                reply_mode="clarify",
                language=language,
                raw_text=raw_text,
                normalized_text=normalized,
                action_result=IntentResult(action="unknown", confidence=0.0, normalized_text=normalized),
                confidence=0.0,
                notes=["empty_input"],
            )

        action_result = self.parser.parse(raw_text)
        topics = self._detect_conversation_topics(normalized)
        suggested_actions = self._suggest_actions(topics)

        if action_result.action in self._ACTIONABLE_INTENTS and not topics:
            return CompanionRoute(
                kind="action",
                reply_mode="execute",
                language=language,
                raw_text=raw_text,
                normalized_text=normalized,
                action_result=action_result,
                confidence=max(action_result.confidence, 0.9),
                notes=["direct_action"],
            )

        if action_result.action in self._ACTIONABLE_INTENTS and topics:
            return CompanionRoute(
                kind="mixed",
                reply_mode="reply_then_offer",
                language=language,
                raw_text=raw_text,
                normalized_text=normalized,
                action_result=action_result,
                confidence=max(action_result.confidence, 0.88),
                conversation_topics=topics,
                suggested_actions=suggested_actions,
                notes=["action_and_conversation"],
            )

        if action_result.action in {"confirm_yes", "confirm_no"}:
            return CompanionRoute(
                kind="action",
                reply_mode="execute",
                language=language,
                raw_text=raw_text,
                normalized_text=normalized,
                action_result=action_result,
                confidence=1.0,
                notes=["confirmation_turn"],
            )

        if topics:
            kind: RouteKind = "mixed" if suggested_actions else "conversation"
            reply_mode: ReplyMode = "reply_then_offer" if suggested_actions else "reply"
            confidence = 0.72 if suggested_actions else 0.68

            return CompanionRoute(
                kind=kind,
                reply_mode=reply_mode,
                language=language,
                raw_text=raw_text,
                normalized_text=normalized,
                action_result=action_result,
                confidence=confidence,
                conversation_topics=topics,
                suggested_actions=suggested_actions,
                notes=["conversation_semantic_match"],
            )

        if self._looks_like_general_question(raw_text, normalized, language):
            return CompanionRoute(
                kind="conversation",
                reply_mode="reply",
                language=language,
                raw_text=raw_text,
                normalized_text=normalized,
                action_result=action_result,
                confidence=0.66,
                notes=["generic_question_to_llm"],
            )

        if action_result.action == "unclear":
            if self._should_prefer_conversation_over_unclear(raw_text, normalized, action_result, language):
                return CompanionRoute(
                    kind="conversation",
                    reply_mode="reply",
                    language=language,
                    raw_text=raw_text,
                    normalized_text=normalized,
                    action_result=action_result,
                    confidence=0.58,
                    notes=["unclear_but_question_like"],
                )

            return CompanionRoute(
                kind="unclear",
                reply_mode="clarify",
                language=language,
                raw_text=raw_text,
                normalized_text=normalized,
                action_result=action_result,
                confidence=action_result.confidence,
                conversation_topics=topics,
                suggested_actions=suggested_actions,
                notes=["ambiguous_action_match"],
            )

        if self._looks_like_conversation_request(normalized, language):
            return CompanionRoute(
                kind="conversation",
                reply_mode="reply",
                language=language,
                raw_text=raw_text,
                normalized_text=normalized,
                action_result=action_result,
                confidence=0.55,
                notes=["direct_conversation_cue"],
            )

        return CompanionRoute(
            kind="unclear",
            reply_mode="clarify",
            language=language,
            raw_text=raw_text,
            normalized_text=normalized,
            action_result=action_result,
            confidence=0.2,
            notes=["no_action_no_conversation_match"],
        )

    def _detect_conversation_topics(self, normalized: str) -> list[str]:
        topics: list[str] = []

        for topic, patterns in self._TOPIC_PATTERNS.items():
            if any(re.search(pattern, normalized) for pattern in patterns):
                topics.append(topic)

        return topics

    def _suggest_actions(self, topics: list[str]) -> list[str]:
        suggestions: list[str] = []

        def add(action: str) -> None:
            if action not in suggestions:
                suggestions.append(action)

        if "focus_struggle" in topics:
            add("focus_start")
            add("break_start")

        if "study_help" in topics:
            add("focus_start")
            add("reminder_create")

        if "overwhelmed" in topics:
            add("focus_start")
            add("reminder_create")
            add("break_start")

        if "low_energy" in topics:
            add("break_start")
            add("focus_start")

        return suggestions

    def _looks_like_general_question(self, raw_text: str, normalized: str, language: str) -> bool:
        raw = str(raw_text or "").strip().lower()

        if "?" in raw_text:
            return True

        starters = self._QUESTION_STARTERS.get(language, ())
        if any(normalized.startswith(starter) for starter in starters):
            return True

        if any(re.search(pattern, normalized) for pattern in self._GENERIC_KNOWLEDGE_PATTERNS):
            return True

        if any(re.search(pattern, normalized) for pattern in self._MATH_PATTERNS):
            return True

        return False

    def _should_prefer_conversation_over_unclear(
        self,
        raw_text: str,
        normalized: str,
        action_result: IntentResult,
        language: str,
    ) -> bool:
        if not self._looks_like_general_question(raw_text, normalized, language):
            return False

        if not action_result.suggestions:
            return True

        top_score = float(action_result.suggestions[0].get("score", 0.0))
        top_action = str(action_result.suggestions[0].get("action", "")).strip()

        if top_action in {"help", "introduce_self", "ask_time", "show_time"} and top_score >= 0.9:
            return False

        return top_score < 0.9

    def _looks_like_conversation_request(self, normalized: str, language: str) -> bool:
        cues = self._DIRECT_CONVERSATION_CUES.get(language, set())
        return normalized in cues

    @staticmethod
    def _resolve_language(normalized: str, preferred_language: str | None) -> str:
        preferred = str(preferred_language or "").strip().lower()
        if preferred in {"pl", "en"}:
            return preferred

        polish_score = 0
        english_score = 0

        if any(char in normalized for char in "ąćęłńóśźż"):
            polish_score += 4

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
            "moge",
            "ile",
            "co",
            "jak",
            "dlaczego",
        }
        english_markers = {
            "i",
            "am",
            "feel",
            "help",
            "tell",
            "joke",
            "riddle",
            "interesting",
            "animals",
            "remind",
            "remember",
            "delete",
            "turn",
            "time",
            "break",
            "focus",
            "study",
            "can",
            "talk",
            "what",
            "how",
            "why",
        }

        tokens = set(normalized.split())
        polish_score += len(tokens & polish_markers)
        english_score += len(tokens & english_markers)

        return "pl" if polish_score > english_score else "en"

    @staticmethod
    def _normalize_text(text: str) -> str:
        lowered = text.lower().strip()
        lowered = unicodedata.normalize("NFKC", lowered)
        lowered = re.sub(r"[^\w\sąćęłńóśźż'-]", " ", lowered, flags=re.IGNORECASE)
        lowered = re.sub(r"\s+", " ", lowered).strip()
        return lowered