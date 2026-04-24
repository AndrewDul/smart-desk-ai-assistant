from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class VisualVoiceAction(StrEnum):
    """Deterministic visual actions recognized from voice text."""

    SHOW_TEMPERATURE = "SHOW_TEMPERATURE"
    SHOW_BATTERY = "SHOW_BATTERY"
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
    """Maps Polish/English voice text to deterministic Visual Shell actions."""

    def match(self, text: str) -> VisualVoiceCommandMatch | None:
        normalized = self.normalize(text)
        if not normalized:
            return None

        ordered_rules: list[tuple[VisualVoiceAction, str, tuple[str, ...]]] = [
            (
                VisualVoiceAction.SHOW_TEMPERATURE,
                "temperature",
                (
                    "temperatura",
                    "temperature",
                    "temp",
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
                VisualVoiceAction.HIDE_DESKTOP,
                "hide_desktop",
                (
                    "schowaj pulpit",
                    "ukryj pulpit",
                    "zamknij pulpit",
                    "nie chce pulpitu",
                    "nie potrzebuje pulpitu",
                    "juz nie potrzebuje pulpitu",
                    "wroc do siebie",
                    "wroc na ekran nexa",
                    "wroc do nexa",
                    "schowaj desktop",
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
                    "gdzie moj pulpit",
                    "przejdz do pulpitu",
                    "wlacz pulpit",
                    "desktop",
                    "show desktop",
                    "give me desktop",
                    "where is my desktop",
                    "open desktop",
                    "switch to desktop",
                ),
            ),
            (
                VisualVoiceAction.LOOK_AT_USER,
                "look_at_user",
                (
                    "spojrz na mnie",
                    "patrz na mnie",
                    "popatrz na mnie",
                    "spogladaj na mnie",
                    "look at me",
                    "watch me",
                    "look here",
                    "look straight at me",
                ),
            ),
            (
                VisualVoiceAction.SHOW_FACE_CONTOUR,
                "show_face",
                (
                    "pokaz twarz",
                    "pokaz swoja twarz",
                    "pokaz mi twarz",
                    "show face",
                    "show your face",
                    "show me your face",
                ),
            ),
            (
                VisualVoiceAction.SHOW_EYES,
                "show_eyes",
                (
                    "pokaz oczy",
                    "pokaz swoje oczy",
                    "show eyes",
                    "show your eyes",
                ),
            ),
            (
                VisualVoiceAction.SHOW_SELF,
                "show_self",
                (
                    "pokaz sie",
                    "pokaz siebie",
                    "ujawnij sie",
                    "show yourself",
                    "show yourself nexa",
                    "reveal yourself",
                ),
            ),
            (
                VisualVoiceAction.START_SCANNING,
                "scanning",
                (
                    "sprawdz pokoj",
                    "sprawdz pomieszczenie",
                    "sprawdz biurko",
                    "sprawdz teren",
                    "rozejrzyj sie",
                    "co widzisz",
                    "zobacz co jest",
                    "poszukaj",
                    "szukaj",
                    "znajdz",
                    "sprawdz gdzie",
                    "look around",
                    "check room",
                    "check the room",
                    "check desk",
                    "check the desk",
                    "what do you see",
                    "look for",
                    "search for",
                    "find",
                    "scan room",
                    "scan the room",
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
        normalized = unicodedata.normalize("NFKD", text or "")
        normalized = "".join(
            char for char in normalized if not unicodedata.combining(char)
        )
        normalized = normalized.lower()
        normalized = re.sub(r"[^a-z0-9%° ]+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    @staticmethod
    def _contains_any(normalized_text: str, phrases: tuple[str, ...]) -> bool:
        return any(phrase in normalized_text for phrase in phrases)