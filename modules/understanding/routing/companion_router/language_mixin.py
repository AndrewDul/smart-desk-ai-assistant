from __future__ import annotations


class CompanionRouterLanguageMixin:
    """
    Resolve the most likely routing language for the current input.
    """

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


__all__ = ["CompanionRouterLanguageMixin"]