from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable


@dataclass(slots=True)
class IntentExample:
    intent_name: str
    text: str
    language: str
    route_hint: str
    priority: float = 1.0


@dataclass(slots=True)
class IntentMatch:
    intent_name: str
    score: float
    route_hint: str
    language: str
    example_text: str
    method: str


class SemanticIntentMatcher:
    """
    Fast semantic intent matcher for NeXa.

    Design goals:
    - improve recognition after STT noise
    - stay lighter than a full conversation model
    - keep shutdown / follow-up intents safe and conservative
    - work even when sentence-transformers is unavailable
    """

    def __init__(
        self,
        model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    ) -> None:
        self.model_name = model_name
        self._model = None
        self._model_error: str | None = None

        self.examples: list[IntentExample] = self._build_examples()
        self._normalized_example_texts = [self._normalize_text(example.text) for example in self.examples]
        self._example_embeddings = None

    def available(self) -> bool:
        if self._model is not None:
            return True

        if self._model_error is not None:
            return False

        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            self._example_embeddings = self._model.encode(
                self._normalized_example_texts,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            return True
        except Exception as error:
            self._model_error = str(error)
            return False

    def match(
        self,
        text: str,
        *,
        allowed_intents: Iterable[str] | None = None,
    ) -> IntentMatch | None:
        normalized = self._normalize_text(text)
        if not normalized:
            return None

        allowed = set(allowed_intents or [])

        lexical_match = self._lexical_match(normalized, allowed_intents=allowed)
        semantic_match = self._semantic_match(normalized, allowed_intents=allowed)

        candidates = [candidate for candidate in [lexical_match, semantic_match] if candidate is not None]
        if not candidates:
            return None

        candidates = [
            candidate
            for candidate in candidates
            if self._candidate_is_safe_for_text(normalized, candidate)
        ]
        if not candidates:
            return None

        candidates.sort(key=lambda item: item.score, reverse=True)

        best = candidates[0]

        if best.method == "semantic":
            if best.score < self._semantic_threshold_for_intent(best.intent_name):
                return lexical_match if lexical_match and self._candidate_is_safe_for_text(normalized, lexical_match) else None

        if best.method == "lexical":
            if best.score < self._lexical_threshold_for_intent(best.intent_name):
                return None

        return best

    def _semantic_match(
        self,
        normalized_text: str,
        *,
        allowed_intents: Iterable[str] | None = None,
    ) -> IntentMatch | None:
        if not self.available():
            return None

        assert self._model is not None
        assert self._example_embeddings is not None

        allowed = set(allowed_intents or [])
        text_embedding = self._model.encode(
            [normalized_text],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )[0]

        best_index = -1
        best_score = -1.0

        for index, example in enumerate(self.examples):
            if allowed and example.intent_name not in allowed:
                continue

            example_embedding = self._example_embeddings[index]
            score = float(text_embedding @ example_embedding)
            score *= example.priority
            score *= self._semantic_safety_multiplier(normalized_text, example)

            if score > best_score:
                best_score = score
                best_index = index

        if best_index < 0:
            return None

        best_example = self.examples[best_index]

        return IntentMatch(
            intent_name=best_example.intent_name,
            score=float(best_score),
            route_hint=best_example.route_hint,
            language=best_example.language,
            example_text=best_example.text,
            method="semantic",
        )

    def _lexical_match(
        self,
        normalized_text: str,
        *,
        allowed_intents: Iterable[str] | None = None,
    ) -> IntentMatch | None:
        allowed = set(allowed_intents or [])

        best_example: IntentExample | None = None
        best_score = -1.0

        input_tokens = normalized_text.split()
        input_token_set = set(input_tokens)

        for example in self.examples:
            if allowed and example.intent_name not in allowed:
                continue

            example_text = self._normalize_text(example.text)
            example_tokens = example_text.split()
            example_token_set = set(example_tokens)

            overlap = len(input_token_set & example_token_set)
            if overlap == 0:
                continue

            precision = overlap / max(len(input_token_set), 1)
            recall = overlap / max(len(example_token_set), 1)

            score = ((precision + recall) / 2.0) * example.priority

            if normalized_text == example_text:
                score += 0.55

            if example_text in normalized_text:
                score += 0.18

            if self._ordered_phrase_match(input_tokens, example_tokens):
                score += 0.12

            if self._contains_same_critical_target(normalized_text, example_text):
                score += 0.08

            score *= self._lexical_safety_multiplier(normalized_text, example)

            if score > best_score:
                best_score = score
                best_example = example

        if best_example is None:
            return None

        return IntentMatch(
            intent_name=best_example.intent_name,
            score=float(best_score),
            route_hint=best_example.route_hint,
            language=best_example.language,
            example_text=best_example.text,
            method="lexical",
        )

    def _build_examples(self) -> list[IntentExample]:
        return [
            # Support / tired / overwhelmed
            IntentExample("support_tired", "i feel tired", "en", "conversation", 1.08),
            IntentExample("support_tired", "i feel so tired", "en", "conversation", 1.05),
            IntentExample("support_tired", "i am tired", "en", "conversation", 1.04),
            IntentExample("support_tired", "i feel bad", "en", "conversation", 0.98),
            IntentExample("support_tired", "i do not feel well", "en", "conversation", 1.00),
            IntentExample("support_tired", "czuje sie zmeczony", "pl", "conversation", 1.08),
            IntentExample("support_tired", "czuje sie zmeczona", "pl", "conversation", 1.08),
            IntentExample("support_tired", "jestem zmeczony", "pl", "conversation", 1.02),
            IntentExample("support_tired", "jestem zmeczona", "pl", "conversation", 1.02),
            IntentExample("support_tired", "czuje sie zle", "pl", "conversation", 1.00),
            IntentExample("support_tired", "nie czuje sie dobrze", "pl", "conversation", 1.00),
            IntentExample("support_tired", "zle sie czuje", "pl", "conversation", 0.98),

            # Talk request
            IntentExample("talk_request", "can we talk for a minute", "en", "conversation", 1.10),
            IntentExample("talk_request", "can we talk", "en", "conversation", 1.02),
            IntentExample("talk_request", "can you talk with me for a minute", "en", "conversation", 1.00),
            IntentExample("talk_request", "mozemy porozmawiac chwile", "pl", "conversation", 1.08),
            IntentExample("talk_request", "porozmawiaj ze mna chwile", "pl", "conversation", 1.05),
            IntentExample("talk_request", "mozemy pogadac chwile", "pl", "conversation", 1.00),

            # Humour
            IntentExample("humour_request", "tell me something funny", "en", "conversation", 1.12),
            IntentExample("humour_request", "tell me a joke", "en", "conversation", 1.08),
            IntentExample("humour_request", "say something funny", "en", "conversation", 1.02),
            IntentExample("humour_request", "powiedz cos smiesznego", "pl", "conversation", 1.12),
            IntentExample("humour_request", "powiedz cos zabawnego", "pl", "conversation", 1.06),
            IntentExample("humour_request", "opowiedz dowcip", "pl", "conversation", 1.02),
            IntentExample("humour_request", "powiedz dowcip", "pl", "conversation", 1.00),

            # Riddle
            IntentExample("riddle_request", "give me a riddle", "en", "conversation", 1.10),
            IntentExample("riddle_request", "tell me a riddle", "en", "conversation", 1.08),
            IntentExample("riddle_request", "ask me a riddle", "en", "conversation", 1.00),
            IntentExample("riddle_request", "zadaj mi zagadke", "pl", "conversation", 1.10),
            IntentExample("riddle_request", "opowiedz zagadke", "pl", "conversation", 1.04),
            IntentExample("riddle_request", "daj mi zagadke", "pl", "conversation", 1.00),

            # Shutdown assistant
            IntentExample("shutdown_request", "turn off nexa", "en", "action", 1.18),
            IntentExample("shutdown_request", "turn off assistant", "en", "action", 1.12),
            IntentExample("shutdown_request", "disable assistant", "en", "action", 0.98),
            IntentExample("shutdown_request", "wylacz nexa", "pl", "action", 1.18),
            IntentExample("shutdown_request", "wylacz asystenta", "pl", "action", 1.12),

            # Shutdown system
            IntentExample("shutdown_request", "turn off system", "en", "action", 1.20),
            IntentExample("shutdown_request", "shutdown system", "en", "action", 1.20),
            IntentExample("shutdown_request", "turn off raspberry pi", "en", "action", 1.18),
            IntentExample("shutdown_request", "wylacz system", "pl", "action", 1.20),
            IntentExample("shutdown_request", "wylacz raspberry pi", "pl", "action", 1.18),
            IntentExample("shutdown_request", "wylacz komputer", "pl", "action", 1.05),

            # Follow-up choices
            IntentExample("break_choice", "break mode", "en", "follow_up", 1.15),
            IntentExample("break_choice", "short break", "en", "follow_up", 1.05),
            IntentExample("break_choice", "take a break", "en", "follow_up", 1.02),
            IntentExample("break_choice", "przerwa", "pl", "follow_up", 1.12),
            IntentExample("break_choice", "krotka przerwa", "pl", "follow_up", 1.15),
            IntentExample("break_choice", "zrob przerwe", "pl", "follow_up", 1.02),

            IntentExample("focus_choice", "focus mode", "en", "follow_up", 1.15),
            IntentExample("focus_choice", "focus session", "en", "follow_up", 1.05),
            IntentExample("focus_choice", "start focus", "en", "follow_up", 1.02),
            IntentExample("focus_choice", "focus", "pl", "follow_up", 1.08),
            IntentExample("focus_choice", "tryb focus", "pl", "follow_up", 1.15),
            IntentExample("focus_choice", "wlacz focus", "pl", "follow_up", 1.02),

            IntentExample("decline", "no thanks", "en", "follow_up", 1.12),
            IntentExample("decline", "no thank you", "en", "follow_up", 1.12),
            IntentExample("decline", "not now", "en", "follow_up", 1.02),
            IntentExample("decline", "no", "en", "follow_up", 1.00),
            IntentExample("decline", "nie dziekuje", "pl", "follow_up", 1.12),
            IntentExample("decline", "nie dzieki", "pl", "follow_up", 1.10),
            IntentExample("decline", "nie teraz", "pl", "follow_up", 1.02),
            IntentExample("decline", "nie chce", "pl", "follow_up", 1.00),
            IntentExample("decline", "nie", "pl", "follow_up", 1.00),
        ]

    def _semantic_safety_multiplier(self, normalized_text: str, example: IntentExample) -> float:
        if example.intent_name != "shutdown_request":
            return 1.0

        input_target = self._shutdown_target(normalized_text)
        example_target = self._shutdown_target(self._normalize_text(example.text))

        if input_target == "unknown" or example_target == "unknown":
            return 0.90

        if input_target != example_target:
            return 0.40

        return 1.10

    def _lexical_safety_multiplier(self, normalized_text: str, example: IntentExample) -> float:
        if example.intent_name != "shutdown_request":
            return 1.0

        input_target = self._shutdown_target(normalized_text)
        example_target = self._shutdown_target(self._normalize_text(example.text))

        if input_target == "unknown" or example_target == "unknown":
            return 0.92

        if input_target != example_target:
            return 0.35

        return 1.12

    def _candidate_is_safe_for_text(self, normalized_text: str, candidate: IntentMatch) -> bool:
        if candidate.intent_name != "shutdown_request":
            return True

        input_target = self._shutdown_target(normalized_text)
        matched_target = self._shutdown_target(self._normalize_text(candidate.example_text))

        if input_target == "unknown":
            return candidate.score >= 0.82

        return input_target == matched_target

    @staticmethod
    def _shutdown_target(text: str) -> str:
        normalized = SemanticIntentMatcher._normalize_text(text)
        tokens = set(normalized.split())

        if "system" in tokens or {"raspberry", "pi"}.issubset(tokens) or "komputer" in tokens:
            return "system"

        if "assistant" in tokens or "asystenta" in tokens or "nexa" in tokens:
            return "assistant"

        return "unknown"

    @staticmethod
    def _contains_same_critical_target(input_text: str, example_text: str) -> bool:
        input_target = SemanticIntentMatcher._shutdown_target(input_text)
        example_target = SemanticIntentMatcher._shutdown_target(example_text)

        if input_target == "unknown" or example_target == "unknown":
            return False

        return input_target == example_target

    @staticmethod
    def _ordered_phrase_match(input_tokens: list[str], example_tokens: list[str]) -> bool:
        if not input_tokens or not example_tokens:
            return False

        input_len = len(input_tokens)
        example_len = len(example_tokens)

        if example_len > input_len:
            return False

        for start in range(0, input_len - example_len + 1):
            if input_tokens[start : start + example_len] == example_tokens:
                return True

        return False

    @staticmethod
    def _semantic_threshold_for_intent(intent_name: str) -> float:
        thresholds = {
            "shutdown_request": 0.78,
            "break_choice": 0.68,
            "focus_choice": 0.68,
            "decline": 0.66,
            "talk_request": 0.66,
            "support_tired": 0.66,
            "humour_request": 0.68,
            "riddle_request": 0.68,
        }
        return thresholds.get(intent_name, 0.66)

    @staticmethod
    def _lexical_threshold_for_intent(intent_name: str) -> float:
        thresholds = {
            "shutdown_request": 0.62,
            "break_choice": 0.50,
            "focus_choice": 0.50,
            "decline": 0.48,
            "talk_request": 0.50,
            "support_tired": 0.50,
            "humour_request": 0.52,
            "riddle_request": 0.52,
        }
        return thresholds.get(intent_name, 0.50)

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", str(text or "").strip())
        normalized = normalized.encode("ascii", "ignore").decode("ascii")
        normalized = normalized.lower()
        normalized = re.sub(r"[^\w\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized