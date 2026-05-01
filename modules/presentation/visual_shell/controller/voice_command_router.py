from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class VisualVoiceAction(StrEnum):
    """Deterministic visual actions recognized from voice text."""

    SHOW_TEMPERATURE = "SHOW_TEMPERATURE"
    SHOW_BATTERY = "SHOW_BATTERY"
    SHOW_TIME = "SHOW_TIME"
    SHOW_DATE = "SHOW_DATE"
    SHOW_DESKTOP = "SHOW_DESKTOP"
    HIDE_DESKTOP = "HIDE_DESKTOP"
    SHOW_SELF = "SHOW_SELF"
    SHOW_EYES = "SHOW_EYES"
    LOOK_AT_USER = "LOOK_AT_USER"
    SHOW_FACE_CONTOUR = "SHOW_FACE_CONTOUR"
    START_SCANNING = "START_SCANNING"
    RETURN_TO_IDLE = "RETURN_TO_IDLE"


@dataclass(frozen=True, slots=True)
class VisualVoiceCommandMatch:
    """Matched deterministic voice command intent for Visual Shell."""

    action: VisualVoiceAction
    matched_rule: str
    normalized_text: str


class VisualShellVoiceCommandRouter:
    """Maps Polish/English voice text to deterministic Visual Shell actions.

    This router intentionally uses deterministic phrase matching plus a small
    STT rescue layer for real misrecognitions observed on the Raspberry Pi.
    Rescue rules must stay narrow to avoid false positives in normal dialogue.
    """

    _CONCEPTUAL_DESKTOP_QUESTIONS = (
        "co to jest pulpit",
        "czym jest pulpit",
        "co znaczy pulpit",
        "wyjasnij pulpit",
        "opowiedz o pulpicie",
        "what is desktop",
        "what is a desktop",
        "explain desktop",
        "tell me about desktop",
    )

    _EXACT_STT_RESCUE = {
        # Real FasterWhisper captures observed for "pokaż pulpit" / desktop access.
        "or cars": "pokaz pulpit",
        "pokaz u lp": "pokaz pulpit",
        "show desk top": "show desktop",
        "show deskto p": "show desktop",
        "szal do skto": "show desktop",
        "show desk top": "show desktop",
        "show this stop": "show desktop",
        "show this stuff": "show desktop",
        "szal do skto": "show desktop",
        "pokaz i konie": "pokaz ikony",
        "daj dosy ten dolinow": "daj dostep do linuxa",
        "die dos temp do linux": "daj dostep do linuxa",

        # Real FasterWhisper captures observed for "schowaj pulpit".
        "zchowaj pul bit": "schowaj pulpit",
        "schowaj pul bit": "schowaj pulpit",
        "z chowaj pul bit": "schowaj pulpit",
        "skawaj pulbit": "schowaj pulpit",
        "skawaj pul bit": "schowaj pulpit",
        "slowaj pulbit": "schowaj pulpit",
        "slowaj pul bit": "schowaj pulpit",
        "sko wej pulpit": "schowaj pulpit",
        "sko wej pul bit": "schowaj pulpit",
        "sko wej pulbit": "schowaj pulpit",
        "slawaj pulpit": "schowaj pulpit",
        "slawaj pul bit": "schowaj pulpit",
        "slawaj pol bit": "schowaj pulpit",
        "sluchaj pulpit": "schowaj pulpit",
        "sluchaj pul bit": "schowaj pulpit",
        "skolwaj u lbid": "schowaj pulpit",
        "skolwaj ulbid": "schowaj pulpit",
        "skolawaj pol bit": "schowaj pulpit",
        "skolawaj pul bit": "schowaj pulpit",
        "so why pull bit": "schowaj pulpit",
        "so why pul bit": "schowaj pulpit",
        "so bye cool bit": "schowaj pulpit",
        "so bye pull bit": "schowaj pulpit",
        "scott viper pit": "schowaj pulpit",
    }

    _STT_PHRASE_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
        # Common English-looking captures for Polish "pokaż pulpit".
        (re.compile(r"\bcash\s*pour\s*pit\b"), "pokaz pulpit"),
        (re.compile(r"\bcashpour\s+pit\b"), "pokaz pulpit"),
        (re.compile(r"\bcash\s+for\s+beat\b"), "pokaz pulpit"),
        (re.compile(r"\bor\s+cash\s+for\s+beat\b"), "pokaz pulpit"),
        (re.compile(r"\bon\s+cash\s*pour\s*pit\b"), "pokaz pulpit"),
        (re.compile(r"\bon\s+cashpour\s+pit\b"), "pokaz pulpit"),

        # Common Polish-looking captures for "pokaż pulpit".
        (re.compile(r"\bpokaz\s+polpit\b"), "pokaz pulpit"),
        (re.compile(r"\bpokaz\s+pulpid\b"), "pokaz pulpit"),
        (re.compile(r"\bpokaz\s+pulbid\b"), "pokaz pulpit"),
        (re.compile(r"\bpokaz\s+pulbit\b"), "pokaz pulpit"),
        (re.compile(r"\bpokaz\s+pul\s+bit\b"), "pokaz pulpit"),
        (re.compile(r"\bpokaz\s+polbit\b"), "pokaz pulpit"),
        (re.compile(r"\bshow\s+desk\s+top\b"), "show desktop"),
        (re.compile(r"\bshow\s+deskto\s+p\b"), "show desktop"),
        (re.compile(r"\bszal\s+do\s+skto\b"), "show desktop"),
        (re.compile(r"\bpokaz\s+pol\s+bit\b"), "pokaz pulpit"),

        # Common Polish-looking captures for "schowaj pulpit".
        (re.compile(r"\bschowaj\s+polpit\b"), "schowaj pulpit"),
        (re.compile(r"\bschowaj\s+pulpid\b"), "schowaj pulpit"),
        (re.compile(r"\bschowaj\s+pulbit\b"), "schowaj pulpit"),
        (re.compile(r"\bzchowaj\s+pul\s+bit\b"), "schowaj pulpit"),
        (re.compile(r"\bzchowaj\s+pulbit\b"), "schowaj pulpit"),
        (re.compile(r"\bschowaj\s+pul\s+bit\b"), "schowaj pulpit"),
        (re.compile(r"\bz\s+chowaj\s+pul\s+bit\b"), "schowaj pulpit"),
        (re.compile(r"\bskawaj\s+pul\s+bit\b"), "schowaj pulpit"),
        (re.compile(r"\bskawaj\s+pulbit\b"), "schowaj pulpit"),
        (re.compile(r"\bslowaj\s+pul\s+bit\b"), "schowaj pulpit"),
        (re.compile(r"\bslowaj\s+pulbit\b"), "schowaj pulpit"),
        (re.compile(r"\bsko\s+wej\s+pulpit\b"), "schowaj pulpit"),
        (re.compile(r"\bsko\s+wej\s+pul\s+bit\b"), "schowaj pulpit"),
        (re.compile(r"\bsko\s+wej\s+pulbit\b"), "schowaj pulpit"),
        (re.compile(r"\bslawaj\s+pulpit\b"), "schowaj pulpit"),
        (re.compile(r"\bslawaj\s+pul\s+bit\b"), "schowaj pulpit"),
        (re.compile(r"\bslawaj\s+pol\s+bit\b"), "schowaj pulpit"),
        (re.compile(r"\bsluchaj\s+pulpit\b"), "schowaj pulpit"),
        (re.compile(r"\bsluchaj\s+pul\s+bit\b"), "schowaj pulpit"),
        (re.compile(r"\bskolwaj\s+u\s+lbid\b"), "schowaj pulpit"),
        (re.compile(r"\bskolwaj\s+ulbid\b"), "schowaj pulpit"),
        (re.compile(r"\bskolawaj\s+pol\s+bit\b"), "schowaj pulpit"),
        (re.compile(r"\bskolawaj\s+pul\s+bit\b"), "schowaj pulpit"),
        (re.compile(r"\bso\s+why\s+pull\s+bit\b"), "schowaj pulpit"),
        (re.compile(r"\bso\s+why\s+pul\s+bit\b"), "schowaj pulpit"),
        (re.compile(r"\bso\s+bye\s+cool\s+bit\b"), "schowaj pulpit"),
        (re.compile(r"\bso\s+bye\s+pull\s+bit\b"), "schowaj pulpit"),
        (re.compile(r"\bscott\s+viper\s+pit\b"), "schowaj pulpit"),

        # Real captures for Linux/desktop access commands.
        (re.compile(r"\bdie\s+dos\s+temp\s+do\s+linux\b"), "daj dostep do linuxa"),
        (re.compile(r"\bdaj\s+dosy\s+ten\s+dolinow\b"), "daj dostep do linuxa"),
        (re.compile(r"\bdaj\s+dosy\s+do\s+linuxa?\b"), "daj dostep do linuxa"),
        (re.compile(r"\bdaj\s+dos\s+temp\s+do\s+linuxa?\b"), "daj dostep do linuxa"),

        # Real captures for "pokaż ikony".
        (re.compile(r"\bpokaz\s+i\s+konie\b"), "pokaz ikony"),
    )

    _STT_TOKEN_REPLACEMENTS = {
        "polpit": "pulpit",
        "pulpid": "pulpit",
        "pulbid": "pulpit",
        "pulbit": "pulpit",
        "polbit": "pulpit",
        "pulpet": "pulpit",
        "pulped": "pulpit",
        "pulpit": "pulpit",
        "pokarz": "pokaz",
        "pokasz": "pokaz",
        "pokas": "pokaz",
        "poka": "pokaz",
        "pokaz": "pokaz",
        "schoway": "schowaj",
        "schovaj": "schowaj",
        "zchowaj": "schowaj",
        "skawaj": "schowaj",
        "slowaj": "schowaj",
        "slawaj": "schowaj",
        "skolawaj": "schowaj",
        "spojz": "spojrz",
        "spoj": "spojrz",
    }

    def match(self, text: str) -> VisualVoiceCommandMatch | None:
        normalized = self.normalize(text)
        if not normalized:
            return None

        if self._is_conceptual_desktop_question(normalized):
            return None

        normalized = self._apply_stt_rescue(normalized)

        ordered_rules: list[tuple[VisualVoiceAction, str, tuple[str, ...]]] = [
            (
                VisualVoiceAction.HIDE_DESKTOP,
                "hide_desktop",
                (
                    "schowaj pulpit",
                    "ukryj pulpit",
                    "zamknij pulpit",
                    "zaslon pulpit",
                    "nie chce pulpitu",
                    "nie potrzebuje pulpitu",
                    "juz nie potrzebuje pulpitu",
                    "wroc do siebie",
                    "wroc na ekran nexa",
                    "wroc do nexa",
                    "schowaj desktop",
                    "hide",
                    "hide desktop",
                    "close desktop",
                    "no desktop",
                    "i do not need desktop",
                    "i dont need desktop",
                    "back to nexa",
                    "return to nexa",
                    "show nexa screen",
                ),
            ),
            (
                VisualVoiceAction.SHOW_DESKTOP,
                "show_desktop",
                (
                    "pulpit",
                    "daj pulpit",
                    "pokaz pulpit",
                    "odslon pulpit",
                    "odkryj pulpit",
                    "gdzie moj pulpit",
                    "przejdz do pulpitu",
                    "wlacz pulpit",
                    "pokaz ikony",
                    "zdejmij shell",
                    "odsun shell",
                    "odslon komputer",
                    "daj dostep do komputera",
                    "daj dostep do linuxa",
                    "chce zobaczyc pulpit",
                    "chce dostep do komputera",
                    "chce dostep do linuxa",
                    "desktop",
                    "show desktop",
                    "give me desktop",
                    "where is my desktop",
                    "open desktop",
                    "switch to desktop",
                    "show icons",
                    "give me access to computer",
                    "give me access to linux",
                    "show my computer",
                ),
            ),
            (
                VisualVoiceAction.SHOW_TEMPERATURE,
                "temperature",
                (
                    "temperatura",
                    "temperature",
                    "twoja temperatura",
                    "jaka jest twoja temperatura",
                    "jaka masz temperature",
                    "czy jest ci za goraco",
                    "jest ci goraco",
                    "czy sie grzejesz",
                    "czy jestes goracy",
                    "czy masz goraco",
                    "are you hot",
                    "are you overheating",
                    "your temperature",
                    "how hot are you",
                    "how warm are you",
                ),
            ),
            (
                VisualVoiceAction.SHOW_BATTERY,
                "battery",
                (
                    "bateria",
                    "baterii",
                    "stan baterii",
                    "ile masz baterii",
                    "ile baterii",
                    "twoja bateria",
                    "pokaz baterie",
                    "poziom baterii",
                    "czy jestes zmeczony",
                    "czy jestes zmeczona",
                    "jestes zmeczony",
                    "jestes zmeczona",
                    "masz energie",
                    "ile masz energii",
                    "battery",
                    "battery level",
                    "your battery",
                    "how much battery",
                    "how much charge",
                    "charge level",
                    "power level",
                    "are you tired",
                    "are you low on energy",
                    "how tired are you",
                ),
            ),
            (
                VisualVoiceAction.SHOW_FACE_CONTOUR,
                "show_face",
                (
                    "pokaz sie",
                    "pokaz siebie",
                    "ujawnij sie",
                    "pokaz twarz",
                    "pokaz swoja twarz",
                    "pokaz mi twarz",
                    "show yourself",
                    "show yourself nexa",
                    "reveal yourself",
                    "show face",
                    "show your face",
                    "show me your face",
                ),
            ),


            (
                VisualVoiceAction.SHOW_DATE,
                "show_date",
                (
                    "pokaz date",
                    "pokaż datę",
                    "pokaz datę",
                    "pokaż date",
                    "wyswietl date",
                    "wyświetl datę",
                    "show date",
                    "show the date",
                    "display date",
                ),
            ),
            (
                VisualVoiceAction.SHOW_TIME,
                "show_time",
                (
                    "wyswietl czas",
                    "wyświetl czas",
                    "wyswietl godzine",
                    "wyświetl godzinę",
                    "show clock",
                    "display time",
                ),
            ),
            (
                VisualVoiceAction.RETURN_TO_IDLE,
                "return_idle",
                (
                    "spokoj",
                    "wracaj",
                    "wroc do chmury",
                    "normalny ekran",
                    "return to idle",
                    "go idle",
                    "calm down",
                    "normal screen",
                ),
            ),
        ]

        for action, rule_name, phrases in ordered_rules:
            if self._contains_any(normalized, phrases):
                return VisualVoiceCommandMatch(
                    action=action,
                    matched_rule=rule_name,
                    normalized_text=normalized,
                )

        return None

    @staticmethod
    def normalize(text: str) -> str:
        """Normalize Polish/English speech text for robust phrase matching."""
        source = str(text or "").translate(
            str.maketrans(
                {
                    "ł": "l",
                    "Ł": "l",
                }
            )
        )
        normalized = unicodedata.normalize("NFKD", source)
        normalized = "".join(
            char for char in normalized if not unicodedata.combining(char)
        )
        normalized = normalized.lower()
        normalized = re.sub(r"[^a-z0-9%° ]+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    @classmethod
    def _apply_stt_rescue(cls, normalized_text: str) -> str:
        rescued = str(normalized_text or "").strip()
        if not rescued:
            return ""

        exact = cls._EXACT_STT_RESCUE.get(rescued)
        if exact:
            return exact

        for pattern, replacement in cls._STT_PHRASE_REPLACEMENTS:
            rescued = pattern.sub(replacement, rescued)

        tokens = [
            cls._STT_TOKEN_REPLACEMENTS.get(token, token)
            for token in rescued.split()
        ]
        rescued = " ".join(tokens)
        rescued = re.sub(r"\bdesk\s+top\b", "desktop", rescued)
        rescued = re.sub(r"\s+", " ", rescued).strip()
        return rescued

    @classmethod
    def _is_conceptual_desktop_question(cls, normalized_text: str) -> bool:
        normalized = str(normalized_text or "").strip()
        if not normalized:
            return False
        return any(phrase in normalized for phrase in cls._CONCEPTUAL_DESKTOP_QUESTIONS)

    @staticmethod
    def _contains_any(normalized_text: str, phrases: tuple[str, ...]) -> bool:
        """Match deterministic command phrases without broad single-word false positives."""
        normalized = str(normalized_text or "").strip()
        if not normalized:
            return False

        for phrase in phrases:
            candidate = str(phrase or "").strip()
            if not candidate:
                continue

            if " " not in candidate:
                if normalized == candidate:
                    return True
                continue

            pattern = r"(?:^|\s)" + re.escape(candidate) + r"(?:\s|$)"
            if re.search(pattern, normalized):
                return True

        return False
