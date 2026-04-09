from __future__ import annotations


class DialogueFlowUnclear:
    """Helpers for unclear-route handling in dialogue flow."""

    @staticmethod
    def _looks_like_feature_request(normalized_text: str) -> bool:
        phrases = [
            "can you",
            "could you",
            "will you",
            "czy mozesz",
            "czy możesz",
            "mozesz",
            "możesz",
            "potrafisz",
            "zrob",
            "zrób",
            "zrobisz",
            "uruchom",
            "wlacz",
            "włącz",
            "wlaczysz",
            "włączysz",
            "turn on",
            "start",
            "open",
            "show",
        ]
        lowered = str(normalized_text or "").strip().lower()
        return any(phrase in lowered for phrase in phrases)


__all__ = ["DialogueFlowUnclear"]