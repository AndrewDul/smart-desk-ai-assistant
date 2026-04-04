from __future__ import annotations

import re
from dataclasses import dataclass, field

from modules.nlu.router import CompanionRoute
from modules.runtime_contracts import ChunkKind, ResponsePlan, RouteKind, StreamMode, create_turn_id
from modules.services.local_llm import LLMContext, LocalLLMService
from modules.system.utils import append_log, load_settings


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
    - keep emotional support and practical mixed replies deterministic and fast
    - answer simple math and selected micro-knowledge deterministically
    - use recent short-term conversation context for follow-up knowledge turns
    - prefer a local LLM only where it adds real value
    - never execute tools here
    """

    def __init__(self) -> None:
        self.settings = load_settings()
        self.local_llm = LocalLLMService(self.settings)

        streaming_cfg = self.settings.get("streaming", {})
        raw_stream_mode = str(streaming_cfg.get("dialogue_stream_mode", "sentence")).strip().lower()
        self.default_stream_mode = self._resolve_stream_mode(raw_stream_mode)

        self._humour_index = 0
        self._riddle_index = 0
        self._fact_index = 0

        self._humour_bank = {
            "pl": [
                "Dlaczego komputer poszedł na przerwę? Bo miał za dużo okien otwartych.",
                "Dlaczego klawiatura jest spokojna? Bo zawsze ma spację na oddech.",
                "Dlaczego monitor był zadowolony? Bo w końcu zobaczył jaśniejszą stronę dnia.",
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
                "Zagadka: co rośnie, kiedy odejmujesz? Dziura.",
                "Zagadka: co ma ekran, ale niczego nie ogląda? Telefon, gdy leży na biurku.",
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
                "Ciekawostka: pszczoły potrafią przekazywać innym pszczołom informacje o kierunku pożywienia za pomocą tańca.",
                "Ciekawostka: wydry często trzymają się za łapy podczas snu, żeby nie odpłynąć od siebie.",
            ],
            "en": [
                "Interesting fact: octopuses have three hearts, and their blood appears bluish because it uses copper-based molecules.",
                "Interesting fact: bees can tell other bees where food is by using a dance.",
                "Interesting fact: sea otters often hold hands while sleeping so they do not drift away from each other.",
            ],
        }

    def build_reply(self, route: CompanionRoute, user_profile: dict | None = None) -> DialogueReply:
        lang = route.language if route.language in {"pl", "en"} else "en"
        topic_set = set(route.conversation_topics)

        if "humour" in topic_set:
            spoken = self._next_humour(lang)
            return self._reply(
                lang,
                spoken,
                display_title=self._text(lang, "HUMOR", "HUMOUR"),
                source="template",
            )

        if "riddle" in topic_set:
            spoken = self._next_riddle(lang)
            return self._reply(
                lang,
                spoken,
                display_title=self._text(lang, "ZAGADKA", "RIDDLE"),
                source="template",
            )

        if "interesting_fact" in topic_set:
            spoken = self._next_fact(lang)
            return self._reply(
                lang,
                spoken,
                display_title=self._text(lang, "CIEKAWOSTKA", "FACT"),
                source="template",
            )

        deterministic_reply = self._try_deterministic_reply(route, lang, user_profile)
        if deterministic_reply is not None:
            return deterministic_reply

        if route.kind == "conversation":
            if self._should_try_local_llm(route):
                llm_reply = self._try_local_llm(route, lang, user_profile)
                if llm_reply is not None:
                    return llm_reply

            return self._build_conversation_reply(route, lang, user_profile)

        if route.kind == "mixed":
            return self._build_mixed_reply(route, lang, user_profile)

        if route.kind == "unclear":
            contextual_follow_up_reply = self._try_contextual_unclear_follow_up(route, lang, user_profile)
            if contextual_follow_up_reply is not None:
                return contextual_follow_up_reply

            if self._should_try_local_llm(route):
                llm_reply = self._try_local_llm(route, lang, user_profile)
                if llm_reply is not None:
                    return llm_reply

            return self._build_unclear_reply(route, lang)

        return self._build_action_bridge_reply(route, lang)

    def build_response_plan(
        self,
        route: CompanionRoute,
        user_profile: dict | None = None,
        *,
        stream_mode: StreamMode | None = None,
    ) -> ResponsePlan:
        reply = self.build_reply(route, user_profile)
        plan = self.reply_to_plan(
            reply,
            route_kind=route.kind,
            stream_mode=stream_mode,
        )

        plan.metadata.update(
            {
                "reply_source": reply.source,
                "display_title": reply.display_title,
                "display_lines": list(reply.display_lines),
                "conversation_topics": list(route.conversation_topics),
                "suggested_actions": list(reply.suggested_actions),
                "reply_mode": route.reply_mode,
                "route_confidence": float(route.confidence),
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
        normalized_language = reply.language if reply.language in {"pl", "en"} else "en"
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

    def _should_try_local_llm(self, route: CompanionRoute) -> bool:
        topic_set = set(route.conversation_topics)

        if route.kind not in {"conversation", "unclear"}:
            return False

        if any(topic in topic_set for topic in {"humour", "riddle", "interesting_fact"}):
            return False

        if any(topic in topic_set for topic in {"low_energy", "focus_struggle", "overwhelmed", "encouragement"}):
            return False

        if "knowledge_query" in topic_set:
            return True

        if "small_talk" in topic_set:
            return True

        if route.kind == "unclear":
            return True

        if not topic_set:
            return True

        return False

    def _try_deterministic_reply(
        self,
        route: CompanionRoute,
        lang: str,
        user_profile: dict | None,
    ) -> DialogueReply | None:
        if route.kind not in {"conversation", "mixed"}:
            return None

        math_reply = self._try_simple_math_reply(route, lang)
        if math_reply is not None:
            return math_reply

        knowledge_reply = self._try_micro_knowledge_reply(route, lang, user_profile)
        if knowledge_reply is not None:
            return knowledge_reply

        return None

    def _try_simple_math_reply(self, route: CompanionRoute, lang: str) -> DialogueReply | None:
        raw = self._normalize_lookup_text(route.raw_text)

        patterns = [
            r"(-?\d+)\s*[\*x×]\s*(-?\d+)",
            r"(-?\d+)\s+razy\s+(-?\d+)",
            r"(-?\d+)\s+times\s+(-?\d+)",
            r"(-?\d+)\s*\+\s*(-?\d+)",
            r"(-?\d+)\s+(?:plus|dodac|doda[cć])\s+(-?\d+)",
            r"(-?\d+)\s*-\s*(-?\d+)",
            r"(-?\d+)\s+(?:minus|odjac|odjac)\s+(-?\d+)",
        ]

        detected = None
        for pattern in patterns:
            match = re.search(pattern, raw)
            if match:
                a = int(match.group(1))
                b = int(match.group(2))
                detected = (a, b, match.group(0))
                break

        if detected is None:
            return None

        a, b, expression = detected

        if any(symbol in expression for symbol in ["*", "x", "×", "razy", "times"]):
            result = a * b
        elif any(symbol in expression for symbol in ["+", "plus", "dodac", "dodać"]):
            result = a + b
        elif any(symbol in expression for symbol in ["-", "minus", "odjac", "odjąć"]):
            result = a - b
        else:
            return None

        spoken = self._text(
            lang,
            f"Wynik to {result}.",
            f"The result is {result}.",
        )

        return self._reply(
            lang,
            spoken_text=spoken,
            display_title=self._text(lang, "WYNIK", "RESULT"),
            source="deterministic_math",
        )

    def _try_micro_knowledge_reply(
        self,
        route: CompanionRoute,
        lang: str,
        user_profile: dict | None,
    ) -> DialogueReply | None:
        raw = self._normalize_lookup_text(route.raw_text)
        topic_set = set(route.conversation_topics)
        recent_context = self._normalize_lookup_text(self._extract_recent_context_block(user_profile))

        if "knowledge_query" not in topic_set and not self._looks_like_knowledge_follow_up(raw):
            return None

        if self._is_black_hole_topic(raw, recent_context):
            if self._asks_about_black_hole_formation(raw):
                spoken = self._text(
                    lang,
                    "Czarne dziury zwykle powstają wtedy, gdy bardzo masywna gwiazda kończy swoje życie, zapada się pod własnym ciężarem i po eksplozji supernowej zostawia po sobie niezwykle gęste jądro.",
                    "Black holes usually form when a very massive star reaches the end of its life, collapses under its own gravity, and after a supernova leaves behind an extremely dense core.",
                )
                follow_up = self._text(
                    lang,
                    "Jeśli chcesz, mogę też wyjaśnić to jeszcze prościej albo powiedzieć, czym różni się gwiazda neutronowa od czarnej dziury.",
                    "If you want, I can explain that even more simply or tell you how a neutron star differs from a black hole.",
                )
                return self._reply(
                    lang,
                    spoken_text=spoken,
                    follow_up_text=follow_up,
                    display_title=self._text(lang, "KOSMOS", "SPACE"),
                    source="deterministic_knowledge_follow_up",
                )

            if self._asks_to_simplify(raw):
                spoken = self._text(
                    lang,
                    "Najprościej: czarna dziura to miejsce w kosmosie, które przyciąga wszystko tak mocno, że nawet światło nie może uciec.",
                    "Put simply: a black hole is a place in space that pulls things in so strongly that even light cannot escape.",
                )
                follow_up = self._text(
                    lang,
                    "Mogę też powiedzieć to wersją bardziej naukową albo bardziej dziecinnie prostą.",
                    "I can also explain it in a more scientific way or in a very simple child-friendly way.",
                )
                return self._reply(
                    lang,
                    spoken_text=spoken,
                    follow_up_text=follow_up,
                    display_title=self._text(lang, "KOSMOS", "SPACE"),
                    source="deterministic_knowledge_follow_up",
                )

            spoken = self._text(
                lang,
                "Czarna dziura to obszar w kosmosie, gdzie grawitacja jest tak silna, że nawet światło nie może się stamtąd wydostać.",
                "A black hole is a region in space where gravity is so strong that even light cannot escape from it.",
            )
            follow_up = self._text(
                lang,
                "Jeśli chcesz, mogę wyjaśnić to jeszcze prościej albo powiedzieć, jak czarne dziury powstają.",
                "If you want, I can explain it even more simply or tell you how black holes are formed.",
            )
            return self._reply(
                lang,
                spoken_text=spoken,
                follow_up_text=follow_up,
                display_title=self._text(lang, "KOSMOS", "SPACE"),
                source="deterministic_knowledge",
            )

        if "rekurencja" in raw or "recursion" in raw:
            if self._asks_to_simplify(raw):
                spoken = self._text(
                    lang,
                    "Najprościej: rekurencja to sytuacja, gdy coś rozwiązuje problem, wywołując mniejszą wersję samego siebie.",
                    "Most simply: recursion is when something solves a problem by calling a smaller version of itself.",
                )
                follow_up = self._text(
                    lang,
                    "Jeśli chcesz, mogę od razu pokazać prosty przykład krok po kroku.",
                    "If you want, I can show a simple example step by step right away.",
                )
                return self._reply(
                    lang,
                    spoken_text=spoken,
                    follow_up_text=follow_up,
                    display_title=self._text(lang, "WYJASNIENIE", "EXPLANATION"),
                    source="deterministic_knowledge_follow_up",
                )

            spoken = self._text(
                lang,
                "Rekurencja to sytuacja, w której funkcja wywołuje samą siebie, zwykle na prostszej wersji tego samego problemu.",
                "Recursion is when a function calls itself, usually on a simpler version of the same problem.",
            )
            follow_up = self._text(
                lang,
                "Jeśli chcesz, mogę podać prosty przykład krok po kroku.",
                "If you want, I can give you a simple step by step example.",
            )
            return self._reply(
                lang,
                spoken_text=spoken,
                follow_up_text=follow_up,
                display_title=self._text(lang, "WYJASNIENIE", "EXPLANATION"),
                source="deterministic_knowledge",
            )

        return None

    def _try_contextual_unclear_follow_up(
        self,
        route: CompanionRoute,
        lang: str,
        user_profile: dict | None,
    ) -> DialogueReply | None:
        raw = self._normalize_lookup_text(route.raw_text)
        recent_context = self._normalize_lookup_text(self._extract_recent_context_block(user_profile))

        if self._is_black_hole_topic(raw, recent_context):
            return self._try_micro_knowledge_reply(route, lang, user_profile)

        if ("rekurencja" in recent_context or "recursion" in recent_context) and self._looks_like_knowledge_follow_up(raw):
            return self._try_micro_knowledge_reply(route, lang, user_profile)

        return None

    def _try_local_llm(
        self,
        route: CompanionRoute,
        lang: str,
        user_profile: dict | None,
    ) -> DialogueReply | None:
        if route.kind not in {"conversation", "unclear"}:
            return None

        user_name = self._extract_user_name(user_profile)
        recent_context_block = self._extract_recent_context_block(user_profile)
        llm_user_prompt = self._build_contextual_user_prompt(recent_context_block, route.raw_text)

        llm_context = LLMContext(
            user_name=user_name,
            assistant_name="NeXa",
            conversation_topics=list(route.conversation_topics),
            suggested_actions=list(route.suggested_actions),
            user_text=route.raw_text,
            route_kind=route.kind,
        )

        result = self.local_llm.generate_companion_reply(
            text=llm_user_prompt,
            language=lang,
            context=llm_context,
        )

        if not result.ok:
            if result.source not in {"disabled", "unavailable"}:
                append_log(
                    f"Local LLM unavailable for this turn: source={result.source}, error={result.error}"
                )
            return None

        spoken = str(result.text or "").strip()
        if not spoken:
            return None

        append_log(f"Local LLM reply accepted: source={result.source}, lang={lang}")

        return self._reply(
            lang,
            spoken_text=spoken,
            suggested_actions=route.suggested_actions,
            display_title=self._display_title_for_route(route, lang),
            display_lines=[],
            source="local_llm",
        )

    def _build_conversation_reply(
        self,
        route: CompanionRoute,
        lang: str,
        user_profile: dict | None,
    ) -> DialogueReply:
        topic_set = set(route.conversation_topics)

        if "knowledge_query" in topic_set:
            return self._build_knowledge_fallback_reply(route, lang, user_profile)

        intro = self._conversation_intro(route, lang, user_profile)
        content = self._conversation_content(route, lang, user_profile)
        message = self._join_lines(intro, content)

        return self._reply(
            lang,
            message,
            suggested_actions=route.suggested_actions,
            display_title=self._text(lang, "ROZMOWA", "CHAT"),
            source="template",
        )

    def _build_mixed_reply(
        self,
        route: CompanionRoute,
        lang: str,
        user_profile: dict | None,
    ) -> DialogueReply:
        intro = self._conversation_intro(route, lang, user_profile)
        offer = self._conversation_offer(route, lang, user_profile)
        follow_up = self._conversation_follow_up_question(route, lang)
        spoken = self._join_lines(intro, offer)

        return self._reply(
            lang,
            spoken,
            follow_up_text=follow_up,
            suggested_actions=route.suggested_actions,
            display_title=self._text(lang, "POMOC", "SUPPORT"),
            source="template",
        )

    def _build_knowledge_fallback_reply(
        self,
        route: CompanionRoute,
        lang: str,
        user_profile: dict | None,
    ) -> DialogueReply:
        recent_context_block = self._extract_recent_context_block(user_profile)

        intro = self._text(
            lang,
            "Jasne. To brzmi jak pytanie wyjaśniające.",
            "Of course. That sounds like an explanation question.",
        )

        if recent_context_block:
            content = self._text(
                lang,
                "Moja pełna warstwa odpowiedzi wiedzy lokalnej nie jest jeszcze gotowa, ale mogę nadal pomóc prostszą drogą i uwzględnić to, o czym przed chwilą mówiliśmy.",
                "My full local knowledge answer layer is not ready yet, but I can still help in a simpler way and take into account what we were just talking about.",
            )
        else:
            content = self._text(
                lang,
                "Moja pełna warstwa odpowiedzi wiedzy lokalnej nie jest jeszcze gotowa, ale mogę nadal pomóc prostszą drogą.",
                "My full local knowledge answer layer is not ready yet, but I can still help in a simpler way.",
            )

        follow_up = self._text(
            lang,
            "Możesz poprosić mnie o krótsze wyjaśnienie, prostą definicję albo przykład krok po kroku.",
            "You can ask me for a shorter explanation, a simple definition, or a step by step example.",
        )

        return self._reply(
            lang,
            self._join_lines(intro, content),
            follow_up_text=follow_up,
            display_title=self._text(lang, "WYJASNIENIE", "EXPLANATION"),
            source="template",
        )

    def _build_unclear_reply(self, route: CompanionRoute, lang: str) -> DialogueReply:
        if route.action_result.action == "unclear" and route.action_result.suggestions:
            spoken = self._text(
                lang,
                "Nie mam jeszcze pełnej pewności, o co chodzi, ale mam kilka sensownych opcji.",
                "I am not fully sure what you meant yet, but I have a few sensible options.",
            )
            return self._reply(
                lang,
                spoken,
                display_title=self._text(lang, "DOPRECYZUJ", "CLARIFY"),
                source="template",
            )

        spoken = self._text(
            lang,
            "Nie złapałam jeszcze dokładnie, o co chodzi, ale nadal mogę pomóc. Możesz powiedzieć to inaczej albo poprosić mnie o timer, przypomnienie, focus, przerwę lub pamięć.",
            "I did not catch exactly what you meant yet, but I can still help. You can say it differently or ask for a timer, reminder, focus, break, or memory help.",
        )
        return self._reply(
            lang,
            spoken,
            display_title=self._text(lang, "NIEJASNE", "UNCLEAR"),
            source="template",
        )

    def _build_action_bridge_reply(self, route: CompanionRoute, lang: str) -> DialogueReply:
        spoken = self._text(
            lang,
            "Dobrze. Przechodzę do działania.",
            "Alright. I am moving to the action.",
        )
        return self._reply(
            lang,
            spoken,
            display_title=self._text(lang, "AKCJA", "ACTION"),
            source="template",
        )

    def _conversation_intro(self, route: CompanionRoute, lang: str, user_profile: dict | None) -> str:
        topic_set = set(route.conversation_topics)
        has_recent_context = self._has_recent_context(user_profile)

        if "focus_struggle" in topic_set and "overwhelmed" in topic_set:
            return self._text(
                lang,
                "Rozumiem. Brzmi to jak za dużo rzeczy naraz.",
                "That makes sense. It sounds like too much at once.",
            )

        if "low_energy" in topic_set and "focus_struggle" in topic_set:
            return self._text(
                lang,
                "To ma sens. Gdy jesteś zmęczony i trudno się skupić, nie warto zaczynać od zbyt dużego kroku.",
                "That makes sense. When you are tired and cannot focus, it is better not to begin with too big a step.",
            )

        if "overwhelmed" in topic_set:
            return self._text(
                lang,
                "Rozumiem. To może naprawdę przytłaczać.",
                "I understand. That can feel genuinely overwhelming.",
            )

        if "focus_struggle" in topic_set:
            return self._text(
                lang,
                "Rozumiem. Brak skupienia czasem po prostu się zdarza.",
                "I understand. Losing focus just happens sometimes.",
            )

        if "study_help" in topic_set:
            return self._text(
                lang,
                "Jasne. Mogę pomóc Ci wejść spokojniej w tryb nauki.",
                "Of course. I can help you ease into study mode more calmly.",
            )

        if "low_energy" in topic_set:
            return self._text(
                lang,
                "Brzmi jak moment, w którym potrzebujesz trochę lżejszego startu.",
                "That sounds like one of those moments when you need a gentler start.",
            )

        if "encouragement" in topic_set:
            return self._text(
                lang,
                "Spokojnie. Nie musisz od razu zrobić wszystkiego idealnie.",
                "It is okay. You do not need to do everything perfectly right away.",
            )

        if "small_talk" in topic_set and has_recent_context:
            return self._text(
                lang,
                "Jasne. Jestem tutaj i możemy spokojnie kontynuować.",
                "Of course. I am here, and we can continue calmly.",
            )

        if "small_talk" in topic_set:
            return self._text(
                lang,
                "Jasne. Jestem tutaj.",
                "Of course. I am here.",
            )

        return self._text(
            lang,
            "Jestem tutaj i mogę pomóc.",
            "I am here and I can help.",
        )

    def _conversation_content(
        self,
        route: CompanionRoute,
        lang: str,
        user_profile: dict | None,
    ) -> str:
        topic_set = set(route.conversation_topics)
        has_recent_context = self._has_recent_context(user_profile)

        if "focus_struggle" in topic_set and "overwhelmed" in topic_set:
            return self._text(
                lang,
                "Możemy to uprościć i zacząć od jednej małej rzeczy.",
                "We can simplify it and start with one small thing.",
            )

        if "low_energy" in topic_set and "focus_struggle" in topic_set:
            return self._text(
                lang,
                "Najlepiej wybrać teraz coś krótkiego i prostego, zamiast próbować ogarnąć wszystko od razu.",
                "It is usually best to choose something short and simple now instead of trying to handle everything at once.",
            )

        if "overwhelmed" in topic_set:
            return self._text(
                lang,
                "Nie musisz porządkować całego dnia od razu. Wystarczy kolejny mały krok.",
                "You do not need to sort out the whole day at once. The next small step is enough.",
            )

        if "focus_struggle" in topic_set:
            return self._text(
                lang,
                "Czasem pomaga krótki start bez presji, nawet kilka spokojnych minut.",
                "Sometimes a small start without pressure helps, even just a few calm minutes.",
            )

        if "study_help" in topic_set:
            return self._text(
                lang,
                "Możemy podejść do tego lekko i praktycznie.",
                "We can approach it in a light and practical way.",
            )

        if "low_energy" in topic_set:
            return self._text(
                lang,
                "Nie potrzebujesz idealnej energii, żeby zacząć. Wystarczy trochę ruchu do przodu.",
                "You do not need perfect energy to begin. A little forward movement is enough.",
            )

        if "encouragement" in topic_set:
            return self._text(
                lang,
                "Wystarczy jeden mały krok. Potem będzie łatwiej złapać rytm.",
                "One small step is enough. After that, it is easier to catch a rhythm.",
            )

        if "small_talk" in topic_set and has_recent_context:
            return self._text(
                lang,
                "Nie musimy zaczynać od zera. Możemy po prostu iść dalej spokojnie, bez pośpiechu.",
                "We do not have to start from zero. We can simply keep going calmly, without rushing.",
            )

        if "small_talk" in topic_set:
            return self._text(
                lang,
                "Możemy po prostu chwilę pogadać, bez presji i bez pośpiechu.",
                "We can simply talk for a minute, without pressure and without rushing.",
            )

        return self._text(
            lang,
            "Mogę odpowiedzieć naturalnie albo pomóc czymś praktycznym.",
            "I can answer naturally or help with something practical.",
        )

    def _conversation_offer(
        self,
        route: CompanionRoute,
        lang: str,
        user_profile: dict | None,
    ) -> str:
        suggestions = route.suggested_actions
        suggestion_set = set(suggestions)
        has_recent_context = self._has_recent_context(user_profile)

        if not suggestions:
            if has_recent_context:
                return self._text(
                    lang,
                    "Mogę po prostu zostać przy rozmowie i podążać za tym, o czym już mówiliśmy.",
                    "I can simply stay with the conversation and follow what we were already talking about.",
                )
            return self._text(
                lang,
                "Mogę po prostu zostać przy rozmowie.",
                "I can simply stay with the conversation.",
            )

        if {"focus_start", "break_start", "reminder_create"}.issubset(suggestion_set):
            return self._text(
                lang,
                "Mogę pomóc praktycznie. Mogę włączyć krótki focus, krótką przerwę albo ustawić przypomnienie.",
                "I can help practically. I can start a short focus session, a short break, or set a reminder.",
            )

        if "focus_start" in suggestion_set and "break_start" in suggestion_set:
            return self._text(
                lang,
                "Mogę pomóc praktycznie. Mogę włączyć krótki focus albo krótką przerwę.",
                "I can help practically. I can start a short focus session or a short break.",
            )

        if "focus_start" in suggestion_set and "reminder_create" in suggestion_set:
            return self._text(
                lang,
                "Mogę pomóc praktycznie. Mogę włączyć focus albo ustawić przypomnienie.",
                "I can help practically. I can start focus mode or set a reminder.",
            )

        if "break_start" in suggestion_set:
            return self._text(
                lang,
                "Mogę od razu włączyć krótką przerwę.",
                "I can start a short break right away.",
            )

        if "focus_start" in suggestion_set:
            return self._text(
                lang,
                "Mogę od razu włączyć krótki focus.",
                "I can start a short focus session right away.",
            )

        if "reminder_create" in suggestion_set:
            return self._text(
                lang,
                "Mogę też ustawić przypomnienie, jeśli to pomoże.",
                "I can also set a reminder if that would help.",
            )

        return self._text(
            lang,
            "Mogę też pomóc czymś praktycznym.",
            "I can also help with something practical.",
        )

    def _conversation_follow_up_question(self, route: CompanionRoute, lang: str) -> str:
        suggestion_set = set(route.suggested_actions)

        if {"focus_start", "break_start", "reminder_create"}.issubset(suggestion_set):
            return self._text(
                lang,
                "Co będzie teraz najlepsze: focus, przerwa czy przypomnienie?",
                "What would help most right now: focus, break, or a reminder?",
            )

        if "focus_start" in suggestion_set and "break_start" in suggestion_set:
            return self._text(
                lang,
                "Co będzie teraz lepsze: krótki focus czy krótka przerwa?",
                "What would be better right now: a short focus session or a short break?",
            )

        if "focus_start" in suggestion_set and "reminder_create" in suggestion_set:
            return self._text(
                lang,
                "Co będzie teraz lepsze: focus czy przypomnienie?",
                "What would be better right now: focus or a reminder?",
            )

        if "focus_start" in suggestion_set:
            return self._text(
                lang,
                "Chcesz, żebym włączyła teraz krótki focus?",
                "Do you want me to start a short focus session now?",
            )

        if "break_start" in suggestion_set:
            return self._text(
                lang,
                "Chcesz, żebym włączyła teraz krótką przerwę?",
                "Do you want me to start a short break now?",
            )

        if "reminder_create" in suggestion_set:
            return self._text(
                lang,
                "Chcesz, żebym ustawiła przypomnienie?",
                "Do you want me to set a reminder?",
            )

        return self._text(
            lang,
            "Co będzie teraz najbardziej pomocne?",
            "What would help most right now?",
        )

    def _display_title_for_route(self, route: CompanionRoute, lang: str) -> str:
        if route.kind == "mixed":
            return self._text(lang, "POMOC", "SUPPORT")
        if route.kind == "unclear":
            return self._text(lang, "DOPRECYZUJ", "CLARIFY")

        topic_set = set(route.conversation_topics)
        if "humour" in topic_set:
            return self._text(lang, "HUMOR", "HUMOUR")
        if "riddle" in topic_set:
            return self._text(lang, "ZAGADKA", "RIDDLE")
        if "interesting_fact" in topic_set:
            return self._text(lang, "CIEKAWOSTKA", "FACT")
        if "knowledge_query" in topic_set:
            return self._text(lang, "WYJASNIENIE", "EXPLANATION")

        return self._text(lang, "ROZMOWA", "CHAT")

    def _build_contextual_user_prompt(self, recent_context_block: str, current_text: str) -> str:
        cleaned_current = str(current_text or "").strip()
        cleaned_context = str(recent_context_block or "").strip()

        if not cleaned_context:
            return cleaned_current

        return (
            "Recent conversation context:\n"
            f"{cleaned_context}\n\n"
            "Current user message:\n"
            f"{cleaned_current}"
        ).strip()

    @staticmethod
    def _extract_recent_context_block(user_profile: dict | None) -> str:
        if not isinstance(user_profile, dict):
            return ""

        candidate = user_profile.get("recent_conversation_context", "")
        return str(candidate or "").strip()

    def _has_recent_context(self, user_profile: dict | None) -> bool:
        return bool(self._extract_recent_context_block(user_profile))

    @staticmethod
    def _is_black_hole_topic(raw: str, recent_context: str) -> bool:
        haystack = f"{recent_context} || {raw}"
        return "czarna dziura" in haystack or "czarne dziury" in haystack or "black hole" in haystack or "black holes" in haystack

    @staticmethod
    def _asks_about_black_hole_formation(raw: str) -> bool:
        return any(
            phrase in raw
            for phrase in [
                "jak powstaja",
                "jak powstaje",
                "jak tworza sie",
                "jak sie tworza",
                "how do they form",
                "how are they formed",
                "how do black holes form",
                "how are black holes formed",
            ]
        )

    @staticmethod
    def _asks_to_simplify(raw: str) -> bool:
        return any(
            phrase in raw
            for phrase in [
                "prosciej",
                "latwiej",
                "w prosty sposob",
                "wyjasnij prosciej",
                "explain more simply",
                "simpler",
                "in a simpler way",
            ]
        )

    @staticmethod
    def _looks_like_knowledge_follow_up(raw: str) -> bool:
        return any(
            phrase in raw
            for phrase in [
                "jak powstaja",
                "jak powstaje",
                "wyjasnij",
                "prosciej",
                "a dlaczego",
                "co dalej",
                "how do they",
                "how are they",
                "explain",
                "why is that",
                "tell me more",
            ]
        )

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
        normalized_language = language if language in {"pl", "en"} else "en"
        cleaned_spoken_text = str(spoken_text or "").strip()
        cleaned_follow_up_text = str(follow_up_text or "").strip()
        cleaned_display_title = str(display_title or "").strip()

        normalized_display_lines: list[str] = []
        if display_lines:
            normalized_display_lines = [
                str(line).strip()
                for line in display_lines
                if str(line).strip()
            ]

        if not normalized_display_lines and cleaned_display_title and cleaned_spoken_text:
            normalized_display_lines = self._build_display_lines(cleaned_spoken_text)

        normalized_actions = self._normalize_suggested_actions(suggested_actions or [])

        return DialogueReply(
            language=normalized_language,
            spoken_text=cleaned_spoken_text,
            follow_up_text=cleaned_follow_up_text,
            suggested_actions=normalized_actions,
            display_title=cleaned_display_title,
            display_lines=normalized_display_lines,
            source=str(source or "template").strip() or "template",
        )

    def _next_humour(self, lang: str) -> str:
        entries = self._humour_bank.get(lang) or self._humour_bank["en"]
        if not entries:
            return self._text(lang, "Nie mam teraz żartu pod ręką.", "I do not have a joke ready right now.")

        index = self._humour_index % len(entries)
        self._humour_index += 1
        return entries[index]

    def _next_riddle(self, lang: str) -> str:
        entries = self._riddle_bank.get(lang) or self._riddle_bank["en"]
        if not entries:
            return self._text(lang, "Nie mam teraz zagadki pod ręką.", "I do not have a riddle ready right now.")

        index = self._riddle_index % len(entries)
        self._riddle_index += 1
        return entries[index]

    def _next_fact(self, lang: str) -> str:
        entries = self._fact_bank.get(lang) or self._fact_bank["en"]
        if not entries:
            return self._text(lang, "Nie mam teraz ciekawostki pod ręką.", "I do not have a fact ready right now.")

        index = self._fact_index % len(entries)
        self._fact_index += 1
        return entries[index]

    @staticmethod
    def _normalize_suggested_actions(actions: list[str]) -> list[str]:
        normalized: list[str] = []

        for action in actions:
            cleaned = str(action or "").strip()
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)

        return normalized

    @staticmethod
    def _build_display_lines(text: str, *, max_lines: int = 2, max_chars: int = 20) -> list[str]:
        cleaned = str(text or "").strip()
        if not cleaned:
            return []

        chunks = [
            part.strip()
            for part in re.split(r"[.!?,:;]", cleaned)
            if part and part.strip()
        ]

        if not chunks:
            chunks = [cleaned]

        lines: list[str] = []
        for chunk in chunks:
            shortened = chunk[:max_chars].rstrip()
            if len(chunk) > max_chars:
                shortened = shortened.rstrip() + "..."

            if shortened:
                lines.append(shortened)

            if len(lines) >= max_lines:
                break

        return lines

    @staticmethod
    def _extract_user_name(user_profile: dict | None) -> str:
        if not isinstance(user_profile, dict):
            return ""

        conversation_name = str(user_profile.get("conversation_partner_name", "")).strip()
        if conversation_name:
            return conversation_name.split()[0]

        return ""

    @staticmethod
    def _normalize_lookup_text(text: str) -> str:
        cleaned = str(text or "").lower()
        cleaned = cleaned.replace("×", "x")
        cleaned = cleaned.replace("ł", "l").replace("ą", "a").replace("ę", "e").replace("ś", "s").replace("ć", "c").replace("ż", "z").replace("ź", "z").replace("ó", "o").replace("ń", "n")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _join_lines(*parts: str) -> str:
        return " ".join(part.strip() for part in parts if part and part.strip()).strip()

    @staticmethod
    def _text(lang: str, pl_text: str, en_text: str) -> str:
        return pl_text if lang == "pl" else en_text

    @staticmethod
    def _resolve_stream_mode(raw_mode: str) -> StreamMode:
        normalized = str(raw_mode or "").strip().lower()

        if normalized == "whole_response":
            return StreamMode.WHOLE_RESPONSE
        if normalized == "paragraph":
            return StreamMode.PARAGRAPH

        return StreamMode.SENTENCE

    @staticmethod
    def _resolve_route_kind(route_kind: str) -> RouteKind:
        normalized = str(route_kind or "").strip().lower()

        if normalized == "action":
            return RouteKind.ACTION
        if normalized == "mixed":
            return RouteKind.MIXED
        if normalized == "unclear":
            return RouteKind.UNCLEAR

        return RouteKind.CONVERSATION

    @staticmethod
    def _primary_chunk_kind_for_route(route_kind: str) -> ChunkKind:
        normalized = str(route_kind or "").strip().lower()

        if normalized == "action":
            return ChunkKind.ACK
        if normalized == "mixed":
            return ChunkKind.ACK
        if normalized == "unclear":
            return ChunkKind.ERROR

        return ChunkKind.CONTENT