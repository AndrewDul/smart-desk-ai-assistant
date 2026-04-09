from __future__ import annotations

import re
import unicodedata

import numpy as np


class FasterWhisperWakeMixin:
    def _transcribe_wake_audio(self, audio: np.ndarray, debug: bool = False) -> str | None:
        self._ensure_faster_whisper_runtime()
        if self._fw_model is None or audio.size == 0:
            return None

        prepared_audio = self._prepare_audio_for_wake_model(audio)
        if prepared_audio is None:
            return None

        best_text: str | None = None
        best_score = -999.0

        for forced_language in self.wake_forced_languages:
            candidate = self._transcribe_single_audio(
                prepared_audio,
                debug=debug,
                label="wake-fast",
                forced_language=forced_language,
            )
            text = str(candidate.get("text") or "").strip()
            if not text:
                continue

            score = self._wake_candidate_score(candidate)
            if score > best_score:
                best_score = score
                best_text = text

            if self._looks_like_isolated_wake_text(text):
                return text

        if best_text is None:
            return None
        if not self._contains_wake_alias(best_text):
            return None
        return best_text

    def _wake_candidate_score(self, candidate: dict[str, object]) -> float:
        text = str(candidate.get("text") or "").strip()
        if not text:
            return -999.0

        normalized = self._normalize_wake_text(text)
        probability = float(candidate.get("language_probability") or 0.0)
        score = probability

        if self._looks_like_isolated_wake_text(normalized):
            score += 4.0
        if self._contains_wake_alias(normalized):
            score += 3.0

        token_count = len(normalized.split())
        if token_count <= 2:
            score += 0.7
        elif token_count <= 4:
            score += 0.25
        else:
            score -= 1.0

        if self._looks_like_blank_or_garbage(text):
            score -= 5.0
        if self._contains_unsupported_script(text):
            score -= 5.0

        return score

    @classmethod
    def _contains_wake_alias(cls, text: str) -> bool:
        normalized = cls._normalize_wake_text(text)
        if not normalized:
            return False

        tokens = [token for token in normalized.split() if token]
        for token in tokens[:6]:
            compact = re.sub(r"[^a-z0-9]", "", token)
            if compact in cls.WAKE_ALIASES:
                return True
            if compact.startswith("nex") and len(compact) <= 8:
                return True

        compact_text = re.sub(r"[^a-z0-9]", "", normalized)
        return compact_text.startswith("nex") and len(compact_text) <= 12

    @classmethod
    def _looks_like_isolated_wake_text(cls, text: str) -> bool:
        normalized = cls._normalize_wake_text(text)
        if not normalized:
            return False

        tokens = [token for token in normalized.split() if token]
        if not tokens or len(tokens) > 4:
            return False

        filtered = [token for token in tokens if token not in cls.WAKE_FILLER_WORDS]
        if not filtered:
            return False

        for token in filtered:
            compact = re.sub(r"[^a-z0-9]", "", token)
            if compact in cls.WAKE_ALIASES:
                continue
            if compact.startswith("nex") and len(compact) <= 8:
                continue
            return False

        return True

    @staticmethod
    def _normalize_wake_text(text: str) -> str:
        cleaned = str(text or "").strip().lower()
        cleaned = unicodedata.normalize("NFKD", cleaned)
        cleaned = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
        cleaned = cleaned.replace("ł", "l")
        cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned