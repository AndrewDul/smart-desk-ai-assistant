from __future__ import annotations


class CompanionRouterLanguageMixin:
    """
    Resolve the most likely routing language for the current input.
    """

    @staticmethod
    def _resolve_language(normalized_text: str, preferred_language: str | None) -> str:
        polish_score = 0
        english_score = 0

        polish_markers = {
            "co",
            "czym",
            "sa",
            "są",
            "czarne",
            "dziury",
            "dziurach",
            "jestem",
            "czuje",
            "pomoz",
            "pomoc",
            "opowiedz",
            "powiedz",
            "wyjasnij",
            "wyjaśnij",
            "wytlumacz",
            "wytłumacz",
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
            "tell",
            "about",
            "explain",
            "black",
            "holes",
            "are",
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

        if any(
            phrase in normalized_text
            for phrase in (
                "tell me about",
                "explain",
                "what are",
                "black holes",
            )
        ):
            english_score += 3

        if any(
            phrase in normalized_text
            for phrase in (
                "co to sa",
                "co to są",
                "czym sa",
                "czym są",
                "czarne dziury",
                "powiedz mi",
                "opowiedz mi",
            )
        ):
            polish_score += 3

        if english_score >= polish_score + 2:
            return "en"
        if polish_score >= english_score + 2:
            return "pl"

        preferred = str(preferred_language or "").strip().lower()
        if preferred in {"pl", "en"}:
            return preferred

        if polish_score > english_score:
            return "pl"
        return "en"


__all__ = ["CompanionRouterLanguageMixin"]
