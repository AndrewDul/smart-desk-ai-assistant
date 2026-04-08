from __future__ import annotations

import importlib.util
import math
import re
from dataclasses import dataclass, field
from typing import Any

from modules.runtime.contracts import ChunkKind, ResponsePlan, RouteKind, StreamMode, create_turn_id
from modules.shared.config.settings import load_settings
from modules.shared.logging.logger import append_log
from modules.understanding.dialogue.conversation_memory import ConversationMemory


@dataclass(slots=True)
class DialogueReply:
    language: str
    spoken_text: str
    follow_up_text: str = ""
    suggested_actions: list[str] = field(default_factory=list)
    display_title: str = ""
    display_lines: list[str] = field(default_factory=list)
    source: str = "template"


class CompanionDialogueService:
    """
    Offline-first dialogue service for NeXa.

    Behaviour:
    - deterministic and fast by default
    - practical and supportive tone
    - optional local-LLM hook if available later
    - never executes tools by itself
    """

    def __init__(self) -> None:
        self.settings = load_settings()

        conversation_cfg = self.settings.get("conversation", {})
        streaming_cfg = self.settings.get("streaming", {})

        self.conversation_memory = ConversationMemory(
            max_turns=int(conversation_cfg.get("max_turns", 8)),
            max_total_chars=int(conversation_cfg.get("max_total_chars", 1800)),
            max_turn_chars=int(conversation_cfg.get("max_turn_chars", 260)),
        )

        self.default_stream_mode = self._resolve_stream_mode(
            streaming_cfg.get("dialogue_stream_mode", "sentence")
        )

        self._humour_index = 0
        self._riddle_index = 0
        self._fact_index = 0

        self._humour_bank = {
            "pl": [
                "Dlaczego komputer poszedł na przerwę? Bo miał za dużo okien otwartych.",
                "Dlaczego klawiatura jest spokojna? Bo zawsze ma spację na oddech.",
                "Dlaczego monitor miał lepszy humor? Bo w końcu zobaczył jaśniejszą stronę dnia.",
            ],
            "en": [
                "Why did the computer take a break? Because it had too many windows open.",
                "Why is the keyboard so calm? Because it always has space to breathe.",
                "Why was the monitor in a better mood? Because it finally saw the bright side.",
            ],
        }

        self._riddle_bank = {
            "pl": [
                "Zagadka: co ma klawisze, ale nie otwiera drzwi? Klawiatura.",
                "Zagadka: co rośnie, kiedy coś z niego zabierasz? Dziura.",
                "Zagadka: co ma ekran, ale niczego nie ogląda? Telefon leżący na biurku.",
            ],
            "en": [
                "Riddle: what has keys but cannot open doors? A keyboard.",
                "Riddle: what grows when you take away from it? A hole.",
                "Riddle: what has a screen but does not watch anything? A phone resting on a desk.",
            ],
        }

        self._fact_bank = {
            "pl": [
                "Ciekawostka: ośmiornice mają trzy serca, a ich krew jest niebieskawa dzięki związkom miedzi.",
                "Ciekawostka: pszczoły potrafią przekazywać informacje o kierunku pożywienia za pomocą tańca.",
                "Ciekawostka: wydry często trzymają się za łapy podczas snu, żeby nie odpłynąć od siebie.",
            ],
            "en": [
                "Interesting fact: octopuses have three hearts, and their blood looks bluish because it uses copper-based molecules.",
                "Interesting fact: bees can tell other bees where food is by using a dance.",
                "Interesting fact: sea otters often hold hands while sleeping so they do not drift away from each other.",
            ],
        }

        self.local_llm = self._try_build_local_llm()

    # ------------------------------------------------------------------
    # Public memory passthroughs
    # ------------------------------------------------------------------

    def add_user_turn(
        self,
        text: str,
        *,
        language: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.conversation_memory.add_user_turn(
            text,
            language=language,
            metadata=metadata,
        )

    def add_assistant_turn(
        self,
        text: str,
        *,
        language: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.conversation_memory.add_assistant_turn(
            text,
            language=language,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Public dialogue API
    # ------------------------------------------------------------------

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

        if kind == "mixed":
            return self._build_mixed_reply(
                route=route,
                language=lang,
                user_profile=user_profile,
                topics=topics,
                suggested_actions=suggested_actions,
            )

        if kind == "unclear":
            fallback_unclear = self._build_unclear_generic_reply(lang)
            return fallback_unclear

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

    # ------------------------------------------------------------------
    # Deterministic knowledge / micro-logic
    # ------------------------------------------------------------------

    def _try_deterministic_reply(
        self,
        *,
        normalized_text: str,
        language: str,
        user_profile: dict | None,
        topics: list[str],
    ) -> DialogueReply | None:
        del user_profile

        math_reply = self._try_math_reply(normalized_text, language)
        if math_reply is not None:
            return math_reply

        if "low_energy" in topics:
            return self._reply(
                language,
                self._text(
                    language,
                    "Brzmisz na zmęczonego. Mogę pomóc ci wejść w tryb focus albo zaproponować krótką przerwę, jeśli tego potrzebujesz.",
                    "You sound tired. I can help you enter focus mode or suggest a short break if you need it.",
                ),
                follow_up_text=self._text(
                    language,
                    "Jeśli chcesz, mogę uruchomić focus albo krótką przerwę.",
                    "If you want, I can start focus mode or a short break.",
                ),
                suggested_actions=["focus_start", "break_start"],
                display_title=self._text(language, "ENERGIA", "ENERGY"),
                source="template_low_energy",
            )

        if "focus_struggle" in topics:
            return self._reply(
                language,
                self._text(
                    language,
                    "Rozumiem. Gdy trudno się skupić, dobrze zacząć od jednego małego kroku i ograniczyć rozproszenia.",
                    "I understand. When it is hard to focus, it helps to start with one small step and reduce distractions.",
                ),
                follow_up_text=self._text(
                    language,
                    "Mogę uruchomić focus mode albo krótką przerwę, jeśli chcesz.",
                    "I can start focus mode or a short break if you want.",
                ),
                suggested_actions=["focus_start", "break_start"],
                display_title=self._text(language, "SKUPIENIE", "FOCUS"),
                source="template_focus_struggle",
            )

        if "overwhelmed" in topics:
            return self._reply(
                language,
                self._text(
                    language,
                    "Brzmi to jak przeciążenie. Dobrze będzie rozbić to na jeden mały krok i nie próbować ogarniać wszystkiego naraz.",
                    "That sounds like overload. It would help to reduce this to one small step instead of trying to handle everything at once.",
                ),
                follow_up_text=self._text(
                    language,
                    "Mogę uruchomić focus, przerwę albo przypomnienie do konkretnego zadania.",
                    "I can start focus mode, a break, or a reminder for one specific task.",
                ),
                suggested_actions=["focus_start", "break_start", "reminder_create"],
                display_title=self._text(language, "PLAN", "PLAN"),
                source="template_overwhelmed",
            )

        if "study_help" in topics:
            return self._reply(
                language,
                self._text(
                    language,
                    "Jasne. Najlepiej zacząć od jednego konkretnego celu na najbliższe kilkanaście minut.",
                    "Sure. The best start is one clear goal for the next several minutes.",
                ),
                follow_up_text=self._text(
                    language,
                    "Mogę uruchomić focus mode albo przypomnienie do następnego kroku.",
                    "I can start focus mode or create a reminder for the next step.",
                ),
                suggested_actions=["focus_start", "reminder_create"],
                display_title=self._text(language, "NAUKA", "STUDY"),
                source="template_study_help",
            )

        if "encouragement" in topics:
            return self._reply(
                language,
                self._text(
                    language,
                    "Nie musisz zrobić wszystkiego idealnie od razu. Wystarczy, że ruszysz z jednym małym krokiem.",
                    "You do not need to do everything perfectly right away. One small step is enough to begin.",
                ),
                follow_up_text=self._text(
                    language,
                    "Jeśli chcesz, mogę pomóc ci wejść w focus mode.",
                    "If you want, I can help you enter focus mode.",
                ),
                suggested_actions=["focus_start"],
                display_title=self._text(language, "MOTYWACJA", "MOTIVATION"),
                source="template_encouragement",
            )

        if "small_talk" in topics:
            partner_name = self._conversation_partner_name(user_profile, language)
            return self._reply(
                language,
                self._text(
                    language,
                    f"Jasne{partner_name}. Jestem tutaj. Powiedz, co najbardziej siedzi ci teraz w głowie.",
                    f"Of course{partner_name}. I am here. Tell me what is on your mind right now.",
                ),
                display_title=self._text(language, "ROZMOWA", "CHAT"),
                source="template_small_talk",
            )

        return None

    def _try_math_reply(self, normalized_text: str, language: str) -> DialogueReply | None:
        expression = normalized_text.strip()

        replacements = {
            "plus": "+",
            "minus": "-",
            "times": "*",
            "multiplied by": "*",
            "x": "*",
            "divided by": "/",
            "dodac": "+",
            "dodać": "+",
            "razy": "*",
            "podzielic przez": "/",
            "podzielić przez": "/",
        }

        compact = f" {expression} "
        for source, target in replacements.items():
            compact = compact.replace(f" {source} ", f" {target} ")
        compact = " ".join(compact.split()).strip()

        prefixes = (
            "how much is ",
            "ile to jest ",
            "what is ",
            "oblicz ",
            "policz ",
        )
        for prefix in prefixes:
            if compact.startswith(prefix):
                compact = compact[len(prefix) :].strip()
                break

        if not re.fullmatch(r"\d+(?:\.\d+)?\s*[\+\-\*/]\s*\d+(?:\.\d+)?", compact):
            return None

        left, operator, right = re.split(r"\s*([\+\-\*/])\s*", compact)
        a = float(left)
        b = float(right)

        if operator == "+":
            result = a + b
        elif operator == "-":
            result = a - b
        elif operator == "*":
            result = a * b
        else:
            if math.isclose(b, 0.0):
                text = self._text(
                    language,
                    "Nie można dzielić przez zero.",
                    "You cannot divide by zero.",
                )
                return self._reply(
                    language,
                    text,
                    display_title=self._text(language, "MATEMATYKA", "MATH"),
                    source="deterministic_math",
                )
            result = a / b

        pretty_result = self._format_number(result)
        text = self._text(
            language,
            f"Wynik to {pretty_result}.",
            f"The result is {pretty_result}.",
        )
        return self._reply(
            language,
            text,
            display_title=self._text(language, "MATEMATYKA", "MATH"),
            source="deterministic_math",
        )

    # ------------------------------------------------------------------
    # Conversation / mixed / unclear templates
    # ------------------------------------------------------------------

    def _build_conversation_reply(
        self,
        *,
        normalized_text: str,
        language: str,
        user_profile: dict | None,
        topics: list[str],
    ) -> DialogueReply:
        del topics

        partner_name = self._conversation_partner_name(user_profile, language)

        if normalized_text:
            if language == "pl":
                spoken = (
                    f"Rozumiem{partner_name}. "
                    "Powiedz mi trochę więcej, a postaram się odpowiedzieć jak najbardziej konkretnie."
                )
            else:
                spoken = (
                    f"I understand{partner_name}. "
                    "Tell me a little more, and I will try to respond as clearly as I can."
                )
        else:
            spoken = self._text(
                language,
                "Jestem tutaj. Powiedz, o czym chcesz porozmawiać.",
                "I am here. Tell me what you want to talk about.",
            )

        return self._reply(
            language,
            spoken,
            display_title=self._text(language, "ROZMOWA", "CHAT"),
            source="template_conversation",
        )

    def _build_mixed_reply(
        self,
        *,
        route: Any,
        language: str,
        user_profile: dict | None,
        topics: list[str],
        suggested_actions: list[str],
    ) -> DialogueReply:
        del route, user_profile, topics

        human_action_names = [self._human_action_name(item, language) for item in suggested_actions]
        human_action_names = [item for item in human_action_names if item]

        if human_action_names:
            joined = self._join_human_list(human_action_names, language)
            spoken = self._text(
                language,
                f"Rozumiem. Mogę pomóc ci praktycznie — na przykład przez {joined}.",
                f"I understand. I can help in a practical way — for example by {joined}.",
            )
            follow_up = self._text(
                language,
                "Powiedz tylko, od czego chcesz zacząć.",
                "Just tell me what you want to start with.",
            )
        else:
            spoken = self._text(
                language,
                "Rozumiem. Brzmi to jak coś, przy czym mogę pomóc praktycznie.",
                "I understand. This sounds like something I can help with practically.",
            )
            follow_up = self._text(
                language,
                "Powiedz mi, co mam zrobić jako pierwszy krok.",
                "Tell me what you want me to do as the first step.",
            )

        return self._reply(
            language,
            spoken,
            follow_up_text=follow_up,
            suggested_actions=suggested_actions,
            display_title=self._text(language, "POMOC", "SUPPORT"),
            source="template_mixed",
        )

    def _build_unclear_reply(
        self,
        *,
        normalized_text: str,
        language: str,
        user_profile: dict | None,
    ) -> DialogueReply | None:
        del user_profile

        if normalized_text and len(normalized_text.split()) <= 3:
            return self._reply(
                language,
                self._text(
                    language,
                    "Nie złapałam jeszcze dokładnie sensu tej komendy. Powiedz to trochę pełniej.",
                    "I did not catch the meaning of that command yet. Say it a little more fully.",
                ),
                display_title=self._text(language, "NIEJASNE", "UNCLEAR"),
                source="template_unclear_short",
            )

        return None

    def _build_unclear_generic_reply(self, language: str) -> DialogueReply:
        return self._reply(
            language,
            self._text(
                language,
                "Nie złapałam jeszcze dokładnie, o co chodzi. Powiedz to jeszcze raz trochę inaczej.",
                "I did not catch exactly what you meant yet. Say it again a little differently.",
            ),
            display_title=self._text(language, "NIEJASNE", "UNCLEAR"),
            source="template_unclear_generic",
        )

    def _build_action_bridge_reply(self, *, language: str) -> DialogueReply:
        return self._reply(
            language,
            self._text(
                language,
                "Rozumiem. Powiedz mi proszę jeszcze raz, co dokładnie mam zrobić.",
                "Understood. Please tell me again exactly what you want me to do.",
            ),
            display_title=self._text(language, "AKCJA", "ACTION"),
            source="template_action_bridge",
        )

    # ------------------------------------------------------------------
    # Optional local LLM hook
    # ------------------------------------------------------------------

    def _try_build_local_llm(self) -> Any | None:
        if importlib.util.find_spec("modules.understanding.dialogue.llm.local_llm") is None:
            return None

        try:
            module = __import__(
                "modules.understanding.dialogue.llm.local_llm",
                fromlist=["LocalLLMService"],
            )
            service_class = getattr(module, "LocalLLMService", None)
            if service_class is None:
                return None
            instance = service_class(self.settings)
            append_log("Local LLM service detected and initialized for dialogue layer.")
            return instance
        except Exception as error:
            append_log(f"Local LLM service initialization skipped: {error}")
            return None

    def _try_local_llm(
        self,
        *,
        normalized_text: str,
        language: str,
        topics: list[str],
        user_profile: dict | None,
        route_kind: str,
    ) -> DialogueReply | None:
        if self.local_llm is None:
            return None

        is_available = getattr(self.local_llm, "is_available", None)
        if callable(is_available):
            try:
                if not is_available():
                    return None
            except Exception:
                return None

        generate_reply = getattr(self.local_llm, "generate_companion_reply", None)
        if not callable(generate_reply):
            return None

        context = {
            "topics": topics,
            "route_kind": route_kind,
            "recent_context": self.conversation_memory.summary_for_prompt(
                limit=6,
                preferred_language=language,
            ),
            "user_profile": dict(user_profile or {}),
        }

        try:
            reply = generate_reply(
                normalized_text,
                language,
                context=context,
            )
        except TypeError:
            try:
                reply = generate_reply(normalized_text, language)
            except Exception:
                return None
        except Exception:
            return None

        if not reply:
            return None

        text = str(getattr(reply, "text", "") or getattr(reply, "spoken_text", "") or "").strip()
        if not text:
            return None

        return self._reply(
            language,
            text,
            display_title=self._text(language, "ODPOWIEDŹ", "REPLY"),
            source="local_llm",
        )

    # ------------------------------------------------------------------
    # Small content helpers
    # ------------------------------------------------------------------

    def _next_humour(self, language: str) -> str:
        bank = self._humour_bank[language]
        text = bank[self._humour_index % len(bank)]
        self._humour_index += 1
        return text

    def _next_riddle(self, language: str) -> str:
        bank = self._riddle_bank[language]
        text = bank[self._riddle_index % len(bank)]
        self._riddle_index += 1
        return text

    def _next_fact(self, language: str) -> str:
        bank = self._fact_bank[language]
        text = bank[self._fact_index % len(bank)]
        self._fact_index += 1
        return text

    def _reply(
        self,
        language: str,
        spoken_text: str,
        *,
        follow_up_text: str = "",
        suggested_actions: list[str] | None = None,
        display_title: str = "",
        display_lines: list[str] | None = None,
        source: str = "template",
    ) -> DialogueReply:
        cleaned_spoken = self._clean_text(spoken_text)
        cleaned_follow_up = self._clean_text(follow_up_text)

        lines = list(display_lines or [])
        if not lines and cleaned_spoken:
            lines = self._default_display_lines(cleaned_spoken)

        return DialogueReply(
            language=self._normalize_language(language),
            spoken_text=cleaned_spoken,
            follow_up_text=cleaned_follow_up,
            suggested_actions=list(suggested_actions or []),
            display_title=self._clean_text(display_title),
            display_lines=lines,
            source=source,
        )

    def _default_display_lines(self, text: str) -> list[str]:
        compact = self._clean_text(text)
        if not compact:
            return []

        max_chars = int(
            self.settings.get("streaming", {}).get("max_display_chars_per_line", 20)
        )
        if len(compact) <= max_chars:
            return [compact]

        first = compact[:max_chars].rstrip()
        second = compact[max_chars : max_chars * 2].strip()
        if second:
            return [first, second[:max_chars]]
        return [first]

    def _conversation_partner_name(
        self,
        user_profile: dict[str, Any] | None,
        language: str,
    ) -> str:
        profile = dict(user_profile or {})
        partner = str(profile.get("conversation_partner_name", "")).strip()
        if not partner:
            return ""
        return f", {partner}," if language == "en" else f", {partner},"

    def _human_action_name(self, action: str, language: str) -> str:
        mapping = {
            "focus_start": self._text(language, "uruchomienie focus mode", "starting focus mode"),
            "break_start": self._text(language, "uruchomienie przerwy", "starting a break"),
            "reminder_create": self._text(language, "ustawienie przypomnienia", "setting a reminder"),
            "memory_store": self._text(language, "zapamiętanie informacji", "remembering information"),
            "timer_start": self._text(language, "ustawienie timera", "setting a timer"),
        }
        return mapping.get(action, "")

    def _join_human_list(self, items: list[str], language: str) -> str:
        clean_items = [self._clean_text(item) for item in items if self._clean_text(item)]
        if not clean_items:
            return ""

        if len(clean_items) == 1:
            return clean_items[0]
        if len(clean_items) == 2:
            joiner = " i " if language == "pl" else " and "
            return f"{clean_items[0]}{joiner}{clean_items[1]}"

        joiner = ", "
        tail = " i " if language == "pl" else " and "
        return f"{joiner.join(clean_items[:-1])}{tail}{clean_items[-1]}"

    # ------------------------------------------------------------------
    # Contract helpers
    # ------------------------------------------------------------------

    def _resolve_stream_mode(self, raw_value: Any) -> StreamMode:
        normalized = str(raw_value or StreamMode.SENTENCE.value).strip().lower()
        for member in StreamMode:
            if member.value == normalized:
                return member
        return StreamMode.SENTENCE

    def _resolve_route_kind(self, raw_value: str | RouteKind) -> RouteKind:
        if isinstance(raw_value, RouteKind):
            return raw_value

        normalized = str(raw_value or "").strip().lower()
        for member in RouteKind:
            if member.value == normalized:
                return member
        return RouteKind.CONVERSATION

    def _primary_chunk_kind_for_route(self, route_kind: str | RouteKind) -> ChunkKind:
        normalized = self._route_kind_value(route_kind)
        if normalized == RouteKind.UNCLEAR.value:
            return ChunkKind.FOLLOW_UP
        if normalized == RouteKind.MIXED.value:
            return ChunkKind.CONTENT
        if normalized == RouteKind.ACTION.value:
            return ChunkKind.TOOL_STATUS
        return ChunkKind.CONTENT

    @staticmethod
    def _route_kind_value(route_kind: str | RouteKind) -> str:
        return route_kind.value if isinstance(route_kind, RouteKind) else str(route_kind or "").strip().lower()

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = str(language or "").strip().lower()
        if normalized.startswith("pl"):
            return "pl"
        return "en"

    @staticmethod
    def _clean_text(text: str) -> str:
        return " ".join(str(text or "").split()).strip()

    @staticmethod
    def _format_number(value: float) -> str:
        if math.isclose(value, round(value)):
            return str(int(round(value)))
        return f"{value:.2f}".rstrip("0").rstrip(".")

    @staticmethod
    def _text(language: str, polish_text: str, english_text: str) -> str:
        return polish_text if language == "pl" else english_text


__all__ = [
    "CompanionDialogueService",
    "DialogueReply",
]