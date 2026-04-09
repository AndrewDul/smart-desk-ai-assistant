from __future__ import annotations

import re


class WhisperCppTextFiltersMixin:
    @staticmethod
    def _cleanup_transcript(text: str | None) -> str | None:
        if text is None:
            return None

        cleaned = str(text).strip()
        if not cleaned:
            return None

        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = cleaned.replace("[BLANK_AUDIO]", "").replace("[NOISE]", "").strip()
        if not cleaned:
            return None

        lowered_words = cleaned.lower().split()
        if len(lowered_words) >= 12:
            for chunk_size in range(4, min(12, len(lowered_words) // 2) + 1):
                phrase = lowered_words[:chunk_size]
                repeats = 1
                index = chunk_size
                while index + chunk_size <= len(lowered_words):
                    if lowered_words[index:index + chunk_size] == phrase:
                        repeats += 1
                        index += chunk_size
                    else:
                        break
                if repeats >= 3:
                    return None

        if WhisperCppTextFiltersMixin._looks_like_repetition_hallucination(cleaned):
            return None

        return cleaned

    @staticmethod
    def _looks_like_repetition_hallucination(text: str) -> bool:
        cleaned = str(text or "").strip().lower()
        if not cleaned:
            return False

        words = cleaned.split()
        if len(words) < 12:
            return False

        for chunk_size in range(2, min(8, len(words) // 3) + 1):
            repeats = 1
            phrase = words[:chunk_size]
            index = chunk_size
            while index + chunk_size <= len(words):
                if words[index:index + chunk_size] == phrase:
                    repeats += 1
                    index += chunk_size
                else:
                    break
            if repeats >= 3:
                return True

        unique_ratio = len(set(words)) / max(len(words), 1)
        return len(words) >= 18 and unique_ratio < 0.38

    @staticmethod
    def _normalize_scoring_text(text: str) -> str:
        cleaned = str(text or "").strip().lower()
        cleaned = re.sub(r"[^\w\s]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _contains_unsupported_script(text: str) -> bool:
        if not text:
            return False
        for char in text:
            code = ord(char)
            if 0x4E00 <= code <= 0x9FFF:
                return True
            if 0x3400 <= code <= 0x4DBF:
                return True
            if 0x3040 <= code <= 0x30FF:
                return True
            if 0xAC00 <= code <= 0xD7AF:
                return True
        return False

    @staticmethod
    def _looks_like_blank_or_garbage(text: str) -> bool:
        cleaned = str(text or "").strip().lower()
        if not cleaned:
            return True
        return cleaned in {
            "[blank_audio]",
            "[noise]",
            "blank audio",
            "noise",
            "music",
            "foreign",
            "speaking in foreign language",
        }