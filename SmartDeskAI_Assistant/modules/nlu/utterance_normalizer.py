from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(slots=True)
class NormalizedUtterance:
    original_text: str
    normalized_text: str
    canonical_text: str
    detected_language_hint: str | None = None
    corrections_applied: list[str] | None = None


class UtteranceNormalizer:
    """
    Conservative speech-aware normalization for NeXa.

    Goals:
    - repair light STT distortions
    - keep important intent distinctions intact
    - improve routing robustness without rewriting the whole sentence
    - stay safe and conservative on Raspberry Pi runtime
    """

    def __init__(self) -> None:
        self._phrase_rules: list[tuple[str, str, str]] = [
            # Polish temporal
            ("ktora jest godzina", "ktora jest godzina", "pl"),
            ("ktora godzina", "ktora jest godzina", "pl"),
            ("jaka jest godzina", "jaka jest godzina", "pl"),
            ("podaj godzine", "podaj godzine", "pl"),
            ("jaki jest czas", "jaki jest czas", "pl"),
            ("pokaz godzine", "pokaz godzine", "pl"),
            ("wyswietl godzine", "wyswietl godzine", "pl"),

            # Polish identity
            ("kim jestes", "kim jestes", "pl"),
            ("jak sie nazywasz", "jak sie nazywasz", "pl"),
            ("przedstaw sie", "przedstaw sie", "pl"),

            # Polish humour / fun
            ("powiedz cos zabawnego", "powiedz cos smiesznego", "pl"),
            ("powiedz cos smiesznego", "powiedz cos smiesznego", "pl"),
            ("opowiedz cos smiesznego", "powiedz cos smiesznego", "pl"),
            ("powiedz zart", "powiedz cos smiesznego", "pl"),
            ("powiedz dowcip", "powiedz cos smiesznego", "pl"),

            # Polish riddles
            ("zadaj mi zagadke", "zadaj mi zagadke", "pl"),
            ("opowiedz zagadke", "zadaj mi zagadke", "pl"),

            # Polish talk / support
            ("mozemy porozmawiac chwile", "mozemy porozmawiac chwile", "pl"),
            ("porozmawiaj ze mna chwile", "mozemy porozmawiac chwile", "pl"),
            ("czuje sie zmeczony", "i feel tired", "pl"),
            ("czuje sie zmeczona", "i feel tired", "pl"),
            ("jestem zmeczony", "i feel tired", "pl"),
            ("jestem zmeczona", "i feel tired", "pl"),
            ("czuje sie zle", "i feel tired", "pl"),
            ("czuje sie bardzo zle", "i feel tired", "pl"),
            ("nie czuje sie dobrze", "i feel tired", "pl"),
            ("zle sie czuje", "i feel tired", "pl"),

            # Polish shutdown
            ("wylacz nexa", "wylacz nexa", "pl"),
            ("wylacz nexta", "wylacz nexa", "pl"),
            ("wylacz nexe", "wylacz nexa", "pl"),
            ("wylacz asystenta", "wylacz asystenta", "pl"),
            ("zamknij asystenta", "wylacz asystenta", "pl"),
            ("wylacz system", "wylacz system", "pl"),
            ("zamknij system", "wylacz system", "pl"),
            ("wylacz raspberry pi", "wylacz system", "pl"),
            ("wylacz komputer", "wylacz system", "pl"),

            # Polish decline
            ("nie dziekuje", "no", "pl"),
            ("nie dzieki", "no", "pl"),
            ("nie chce", "no", "pl"),
            ("nie teraz", "no", "pl"),

            # English temporal
            ("what time is it", "what time is it", "en"),
            ("what is the time", "what time is it", "en"),
            ("tell me the time", "what time is it", "en"),
            ("show the time", "show the time", "en"),
            ("display the time", "show the time", "en"),

            # English identity
            ("who are you", "who are you", "en"),
            ("what is your name", "what is your name", "en"),
            ("what s your name", "what is your name", "en"),
            ("tell me your name", "what is your name", "en"),
            ("say your name", "what is your name", "en"),
            ("introduce yourself", "introduce yourself", "en"),

            # English small talk / support
            ("can we talk for a minute", "can we talk for a minute", "en"),
            ("can we talk", "can we talk for a minute", "en"),
            ("tell me something funny", "tell me something funny", "en"),
            ("tell me a joke", "tell me something funny", "en"),
            ("give me a riddle", "give me a riddle", "en"),
            ("tell me a riddle", "give me a riddle", "en"),
            ("i feel tired", "i feel tired", "en"),
            ("i feel so tired", "i feel tired", "en"),
            ("im tired", "i feel tired", "en"),
            ("i am tired", "i feel tired", "en"),
            ("i feel bad", "i feel tired", "en"),
            ("i dont feel well", "i feel tired", "en"),
            ("i do not feel well", "i feel tired", "en"),

            # English shutdown
            ("turn off nexa", "turn off nexa", "en"),
            ("turn off nexta", "turn off nexa", "en"),
            ("turn off assistant", "turn off assistant", "en"),
            ("close assistant", "turn off assistant", "en"),
            ("turn off system", "turn off system", "en"),
            ("close system", "turn off system", "en"),
            ("turn off raspberry pi", "turn off system", "en"),
            ("shut down system", "turn off system", "en"),
            ("shutdown system", "turn off system", "en"),

            # English decline
            ("no thanks", "no", "en"),
            ("no thank you", "no", "en"),
            ("not now", "no", "en"),
            ("i dont want that", "no", "en"),
            ("i do not want that", "no", "en"),
        ]

        self._word_replacements = {
            "pl": {
                # Temporal / identity
                "godzinna": "godzina",
                "goddzina": "godzina",
                "godzinaa": "godzina",
                "nazywa": "nazywasz",
                "nazywaz": "nazywasz",

                # Humour
                "myznego": "smiesznego",
                "mieznego": "smiesznego",
                "mieszynego": "smiesznego",
                "miesznego": "smiesznego",
                "miscnego": "smiesznego",
                "misznego": "smiesznego",
                "miscnegogo": "smiesznego",
                "miszcznego": "smiesznego",
                "micznego": "smiesznego",
                "micznegoo": "smiesznego",
                "misznegoo": "smiesznego",
                "miscnegoo": "smiesznego",
                "smieszneco": "smiesznego",
                "smesznego": "smiesznego",
                "smiesznego": "smiesznego",
                "smieszna": "smiesznego",

                # Shutdown / naming
                "wylacza": "wylacz",
                "wylancz": "wylacz",
                "wylocz": "wylacz",
                "asystent": "asystenta",
                "asystenta": "asystenta",
                "nexa": "nexa",
                "nexta": "nexa",
                "nekse": "nexa",
                "neksa": "nexa",
                "neksae": "nexa",

                # Wellbeing
                "zmeczamy": "zmeczony",
                "zmeczomy": "zmeczony",
                "zmeczony": "zmeczony",
                "zmeczona": "zmeczona",
                "zmeczonyy": "zmeczony",
                "meczony": "zmeczony",
                "meczona": "zmeczona",

                # Misc
                "dzieki": "dziekuje",
            },
            "en": {
                "im": "i am",
                "wanna": "want to",
                "gonna": "going to",
                "nexta": "nexa",
                "shutdown": "shut down",
            },
        }

        self._canonical_targets_by_language = {
            "pl": [
                "ktora jest godzina",
                "jaka jest godzina",
                "pokaz godzine",
                "kim jestes",
                "jak sie nazywasz",
                "przedstaw sie",
                "powiedz cos smiesznego",
                "zadaj mi zagadke",
                "mozemy porozmawiac chwile",
                "wylacz nexa",
                "wylacz asystenta",
                "wylacz system",
                "ustaw timer",
                "ustaw przypomnienie",
                "i feel tired",
                "no",
            ],
            "en": [
                "what time is it",
                "show the time",
                "who are you",
                "what is your name",
                "introduce yourself",
                "tell me something funny",
                "give me a riddle",
                "can we talk for a minute",
                "turn off nexa",
                "turn off assistant",
                "turn off system",
                "set timer",
                "set reminder",
                "i feel tired",
                "no",
            ],
            "generic": [
                "ktora jest godzina",
                "kim jestes",
                "jak sie nazywasz",
                "przedstaw sie",
                "powiedz cos smiesznego",
                "zadaj mi zagadke",
                "mozemy porozmawiac chwile",
                "wylacz nexa",
                "wylacz asystenta",
                "wylacz system",
                "what time is it",
                "who are you",
                "what is your name",
                "introduce yourself",
                "tell me something funny",
                "give me a riddle",
                "can we talk for a minute",
                "turn off nexa",
                "turn off assistant",
                "turn off system",
                "i feel tired",
                "no",
            ],
        }

    def normalize(self, text: str) -> NormalizedUtterance:
        original_text = str(text or "").strip()
        lowered = self._basic_normalize(original_text)

        corrections: list[str] = []
        initial_language_hint = self._guess_language(lowered)

        collapsed = self._collapse_multiword_variants(lowered, corrections)
        repaired = self._replace_words(collapsed, initial_language_hint, corrections)
        canonical = self._apply_phrase_rules(repaired, initial_language_hint, corrections)

        final_language_hint = (
            self._guess_language(canonical)
            or self._guess_language(repaired)
            or initial_language_hint
        )

        canonical = self._fuzzy_map_canonical(canonical, final_language_hint, corrections)

        final_language_hint = (
            self._guess_language(canonical)
            or self._guess_language(repaired)
            or initial_language_hint
        )

        return NormalizedUtterance(
            original_text=original_text,
            normalized_text=repaired,
            canonical_text=canonical,
            detected_language_hint=final_language_hint,
            corrections_applied=corrections,
        )

    def _basic_normalize(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text)
        normalized = normalized.encode("ascii", "ignore").decode("ascii")
        normalized = normalized.lower()
        normalized = re.sub(r"[^\w\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _collapse_multiword_variants(self, text: str, corrections: list[str]) -> str:
        collapsed = text

        replacements = [
            (r"\bz meczony\b", "zmeczony"),
            (r"\bz meczona\b", "zmeczona"),
            (r"\bnie dzieki\b", "nie dziekuje"),
            (r"\bshut\s+down\b", "shutdown"),

            # Observed temporal distortions
            (r"\bktora jest godzinna\b", "ktora jest godzina"),
            (r"\bjaka jest godzinna\b", "jaka jest godzina"),

            # Observed identity distortions
            (r"\bjak sie nazywa\b", "jak sie nazywasz"),
            (r"\bkim jest dac\b", "kim jestes"),
            (r"\bkim jest tez\b", "kim jestes"),
            (r"\bkim jest to\b", "kim jestes"),

            # Observed Polish speech -> English STT distortions
            (r"\bkimi is such a\b", "kim jestes"),
            (r"\bthey won t assist enter\b", "wylacz asystenta"),
            (r"\bthey won t assistant\b", "wylacz asystenta"),
            (r"\bthey wont assistant\b", "wylacz asystenta"),
            (r"\bthey won t just stand up\b", "wylacz asystenta"),
            (r"\band they want system\b", "wylacz system"),
            (r"\bthey won t system\b", "wylacz system"),
            (r"\bthey wont system\b", "wylacz system"),
        ]

        for pattern, replacement in replacements:
            updated = re.sub(pattern, replacement, collapsed)
            if updated != collapsed:
                corrections.append(f"multiword:{pattern}->{replacement}")
                collapsed = updated

        collapsed = re.sub(r"\s+", " ", collapsed).strip()
        return collapsed

    def _guess_language(self, text: str) -> str | None:
        polish_markers = {
            "powiedz",
            "cos",
            "zagadke",
            "zabawnego",
            "smiesznego",
            "wylacz",
            "ustaw",
            "przypomnienie",
            "czuje",
            "zmeczony",
            "zmeczona",
            "zle",
            "jestem",
            "dziekuje",
            "porozmawiac",
            "chwile",
            "asystenta",
            "system",
            "ktora",
            "godzina",
            "godzine",
            "czas",
            "kim",
            "jestes",
            "nazywasz",
            "przedstaw",
            "pokaz",
            "wyswietl",
            "date",
            "dzien",
            "rok",
        }
        english_markers = {
            "tell",
            "funny",
            "joke",
            "riddle",
            "turn",
            "off",
            "talk",
            "minute",
            "tired",
            "feel",
            "thanks",
            "thank",
            "assistant",
            "system",
            "shut",
            "down",
            "who",
            "name",
            "time",
            "date",
            "day",
            "year",
            "show",
            "display",
            "introduce",
        }

        tokens = set(text.split())

        pl_score = len(tokens & polish_markers)
        en_score = len(tokens & english_markers)

        if pl_score > en_score:
            return "pl"
        if en_score > pl_score:
            return "en"
        return None

    def _replace_words(self, text: str, language_hint: str | None, corrections: list[str]) -> str:
        tokens = text.split()
        replaced_tokens: list[str] = []

        for token in tokens:
            replacement = token

            preferred_map = self._word_replacements.get(language_hint or "", {})
            if token in preferred_map:
                replacement = preferred_map[token]
            else:
                for language_map in self._word_replacements.values():
                    if token in language_map:
                        replacement = language_map[token]
                        break

            if replacement != token:
                corrections.append(f"word:{token}->{replacement}")

            replaced_tokens.append(replacement)

        return " ".join(replaced_tokens).strip()

    def _apply_phrase_rules(self, text: str, language_hint: str | None, corrections: list[str]) -> str:
        for source, target, rule_lang in self._phrase_rules:
            if source == text and self._language_rule_applies(rule_lang, language_hint):
                if source != target:
                    corrections.append(f"phrase:{source}->{target}")
                return target

        for source, target, rule_lang in self._phrase_rules:
            if not self._language_rule_applies(rule_lang, language_hint):
                continue

            if text.startswith(source + " ") or text == source:
                if source != target:
                    corrections.append(f"phrase_prefix:{source}->{target}")
                return target

        return text

    def _fuzzy_map_canonical(
        self,
        text: str,
        language_hint: str | None,
        corrections: list[str],
    ) -> str:
        candidates = list(self._canonical_targets_by_language.get(language_hint or "", []))
        if not candidates:
            candidates = list(self._canonical_targets_by_language["generic"])

        best_target = text
        best_score = 0.0

        for target in candidates:
            score = SequenceMatcher(None, text, target).ratio()
            if score > best_score:
                best_score = score
                best_target = target

        if best_target == text:
            return text

        if not self._is_safe_fuzzy_upgrade(text, best_target, best_score):
            return text

        corrections.append(f"fuzzy:{text}->{best_target}:{best_score:.2f}")
        return best_target

    @staticmethod
    def _language_rule_applies(rule_lang: str, language_hint: str | None) -> bool:
        if language_hint is None:
            return True
        return rule_lang == language_hint

    @staticmethod
    def _is_safe_fuzzy_upgrade(text: str, target: str, score: float) -> bool:
        if score < 0.88:
            return False

        shutdown_forms = {
            "wylacz nexa",
            "wylacz asystenta",
            "wylacz system",
            "turn off nexa",
            "turn off assistant",
            "turn off system",
        }
        if text in shutdown_forms or target in shutdown_forms:
            return text == target

        if len(text.split()) > 5 or len(target.split()) > 5:
            return False

        return True