from __future__ import annotations

import re


class TTSPipelineNormalizationMixin:
    """
    Helpers for log-safe and TTS-safe text normalization.
    """

    @staticmethod
    def _normalize_text_for_log(text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "").strip())

    def _apply_brand_pronunciation(self, text: str, lang: str) -> str:
        cleaned = str(text or "")
        cleaned = re.sub(r"\bNeXa\b", "Neksa", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bNexa\b", "Neksa", cleaned, flags=re.IGNORECASE)

        if lang == "en":
            cleaned = re.sub(
                r"\bmy name is neksa\b",
                "My name is Neksa",
                cleaned,
                flags=re.IGNORECASE,
            )
        else:
            cleaned = re.sub(
                r"\bnazywam sie neksa\b",
                "Nazywam się Neksa",
                cleaned,
                flags=re.IGNORECASE,
            )

        return cleaned

    def _normalize_text_for_tts(self, text: str, lang: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""

        cleaned = self._apply_brand_pronunciation(cleaned, lang)
        cleaned = cleaned.replace("OLED", "O led")
        cleaned = cleaned.replace("->", " ")
        cleaned = cleaned.replace("_", " ")
        cleaned = cleaned.replace("/", " ")
        cleaned = cleaned.replace("\\", " ")
        cleaned = cleaned.replace(": ", ". ")
        cleaned = cleaned.replace("; ", ". ")

        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"[.]{2,}", ".", cleaned)
        cleaned = re.sub(r"[!]{2,}", "!", cleaned)
        cleaned = re.sub(r"[?]{2,}", "?", cleaned)
        cleaned = re.sub(r"([,.!?])([A-Za-zÀ-ÿ0-9])", r"\1 \2", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if lang == "en":
            replacements = {
                r"\bi m\b": "I'm",
                r"\bi ll\b": "I'll",
                r"\bdont\b": "don't",
                r"\bcant\b": "can't",
                r"\bwont\b": "won't",
                r"\bwhats\b": "what's",
            }
            lowered = cleaned.lower()
            for pattern, replacement in replacements.items():
                lowered = re.sub(pattern, replacement.lower(), lowered)
            cleaned = lowered.strip()
            if cleaned:
                cleaned = cleaned[:1].upper() + cleaned[1:]

        if cleaned and cleaned[-1] not in ".!?":
            cleaned += "."

        return cleaned


__all__ = ["TTSPipelineNormalizationMixin"]