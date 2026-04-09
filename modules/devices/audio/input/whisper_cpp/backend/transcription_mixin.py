from __future__ import annotations

import re
from typing import Any

import numpy as np


class WhisperCppTranscriptionMixin:
    def _transcribe_audio(self, audio: np.ndarray, debug: bool = False) -> str | None:
        if audio.size == 0:
            return None

        trimmed_audio = self._trim_audio_for_transcription(audio)
        if trimmed_audio.size == 0:
            trimmed_audio = audio

        auto_candidate = self._transcribe_candidate(
            trimmed_audio,
            forced_language=None,
            label="auto",
            debug=debug,
        )
        if self._accept_candidate(auto_candidate):
            return str(auto_candidate.get("text") or "").strip() or None

        rescue_candidates: list[dict[str, Any]] = []
        for forced_language in self._preferred_rescue_languages(auto_candidate):
            candidate = self._transcribe_candidate(
                trimmed_audio,
                forced_language=forced_language,
                label=f"rescue_{forced_language}",
                debug=debug,
            )
            if candidate.get("text"):
                rescue_candidates.append(candidate)

        if rescue_candidates:
            rescue_candidates.sort(
                key=lambda item: self._candidate_score(
                    item,
                    primary_language=str(auto_candidate.get("language") or "") or None,
                ),
                reverse=True,
            )
            best = rescue_candidates[0]
            if self._candidate_score(
                best,
                primary_language=str(auto_candidate.get("language") or "") or None,
            ) > 0.0:
                return str(best.get("text") or "").strip() or None

        return None

    def _transcribe_candidate(
        self,
        audio: np.ndarray,
        *,
        forced_language: str | None,
        label: str,
        debug: bool = False,
    ) -> dict[str, Any]:
        candidate: dict[str, Any] = {
            "text": None,
            "language": forced_language or "auto",
            "language_probability": 0.0,
            "elapsed": 0.0,
            "forced_language": forced_language,
            "engine": "whisper_cpp",
        }

        try:
            wav_path = self._write_temp_wav(audio)
            started_at = self._now()
            transcript = self._run_whisper_cpp(
                wav_path,
                forced_language=forced_language,
                label=label,
                debug=debug,
            )
            elapsed = self._now() - started_at
            cleaned = self._cleanup_transcript(transcript)
            guessed_language = forced_language or self._detect_language_from_text(cleaned or "") or "auto"

            candidate.update(
                {
                    "text": cleaned,
                    "language": self._normalize_language(guessed_language, allow_auto=True),
                    "elapsed": elapsed,
                }
            )

            if debug and self._debug_print_allowed():
                printable = cleaned if cleaned else "<empty>"
                mode_label = label if forced_language is None else f"{label}:{forced_language}"
                print(
                    f"Whisper.cpp {mode_label} transcript: {printable} | "
                    f"lang={candidate['language']} elapsed={elapsed:.2f}s"
                )

            return candidate
        except Exception as error:
            self.LOGGER.warning("Whisper.cpp transcription error (%s): %s", label, error)
            return candidate

    def _preferred_rescue_languages(
        self,
        primary_candidate: dict[str, Any] | None,
    ) -> tuple[str, ...]:
        text = str((primary_candidate or {}).get("text") or "").strip()
        hinted_language = self._guess_hint_language(text)
        if hinted_language == "pl":
            return ("pl", "en")
        if hinted_language == "en":
            return ("en", "pl")

        primary_language = str((primary_candidate or {}).get("language") or "").strip().lower()
        if primary_language == "pl":
            return ("pl", "en")
        if primary_language == "en":
            return ("en", "pl")
        return ("pl", "en")

    def _accept_candidate(self, candidate: dict[str, Any]) -> bool:
        text = str(candidate.get("text") or "").strip()
        language = str(candidate.get("language") or "").strip().lower()

        if not text:
            return False
        if self._contains_unsupported_script(text):
            return False
        if self._looks_like_blank_or_garbage(text):
            return False
        if self._strong_command_match(text):
            return True

        word_count = len(text.split())

        if language in self.SUPPORTED_LANGUAGES and word_count >= 2:
            return True
        return word_count >= 4

    def _candidate_score(
        self,
        candidate: dict[str, Any],
        *,
        primary_language: str | None = None,
    ) -> float:
        text = str(candidate.get("text") or "").strip()
        language = str(candidate.get("language") or "").strip().lower()

        if not text:
            return -10.0

        score = 0.0
        score += min(len(text.split()), 8) * 0.25

        if language in self.SUPPORTED_LANGUAGES:
            score += 0.5
        elif language == "auto":
            score -= 0.2
        else:
            score -= 2.0

        if self._contains_unsupported_script(text):
            score -= 5.0
        if self._looks_like_blank_or_garbage(text):
            score -= 3.0

        score += self._language_affinity_score(text, language)
        score += self._question_shape_bonus(text, language)
        score += self._command_phrase_bonus(text, language)
        score += self._primary_language_bonus(language, primary_language)
        score -= self._false_positive_penalty(text, language)

        if self._strong_command_match(text):
            score += 1.5

        return score

    def _command_phrase_bonus(self, text: str, language: str) -> float:
        normalized = self._normalize_scoring_text(text)
        if not normalized:
            return 0.0

        shared_commands = {
            "yes",
            "no",
            "tak",
            "nie",
            "cancel",
            "anuluj",
            "timer",
            "focus",
            "break",
            "exit",
            "shutdown",
            "set timer",
        }

        bonus = 0.0
        if normalized in shared_commands:
            bonus += 1.9
        if language == "en" and normalized in self.SHORT_COMMAND_PHRASES["en"]:
            bonus += 2.1
        if language == "pl" and normalized in self.SHORT_COMMAND_PHRASES["pl"]:
            bonus += 2.1
        return bonus

    def _primary_language_bonus(self, language: str, primary_language: str | None) -> float:
        if not primary_language or primary_language not in self.SUPPORTED_LANGUAGES:
            return 0.0
        if language == primary_language:
            return 0.95
        if language in self.SUPPORTED_LANGUAGES:
            return -0.15
        return 0.0

    def _language_affinity_score(self, text: str, language: str) -> float:
        normalized = self._normalize_scoring_text(text)
        if not normalized:
            return 0.0

        words = set(normalized.split())
        polish_hits = len(words & self.POLISH_HINT_WORDS)
        english_hits = len(words & self.ENGLISH_HINT_WORDS)

        if language == "pl":
            return polish_hits * 0.32 - english_hits * 0.12
        if language == "en":
            return english_hits * 0.28 - polish_hits * 0.10
        return 0.0

    def _question_shape_bonus(self, text: str, language: str) -> float:
        normalized = self._normalize_scoring_text(text)
        if not normalized:
            return 0.0

        polish_starts = (
            "ktora ",
            "która ",
            "jaka ",
            "kim ",
            "jak ",
            "czy ",
            "pokaz ",
            "pokaż ",
            "wyswietl ",
            "wyświetl ",
            "wytlumacz ",
            "wytłumacz ",
            "wyjasnij ",
            "wyjaśnij ",
        )
        english_starts = (
            "what ",
            "who ",
            "how ",
            "show ",
            "tell ",
            "explain ",
            "turn ",
            "close ",
        )

        if language == "pl" and normalized.startswith(polish_starts):
            return 0.55
        if language == "en" and normalized.startswith(english_starts):
            return 0.45
        return 0.0

    def _false_positive_penalty(self, text: str, language: str) -> float:
        normalized = self._normalize_scoring_text(text)
        if not normalized:
            return 0.0

        penalty = 0.0
        if language == "en":
            for phrase in self.SUSPICIOUS_ENGLISH_FALSE_POSITIVES:
                if phrase in normalized:
                    penalty += 2.2
            if normalized.startswith("thank ") and len(normalized.split()) <= 4:
                penalty += 1.2
        if language == "pl" and normalized in {"tak", "nie"}:
            penalty += 0.4
        return penalty

    def _guess_hint_language(self, text: str) -> str | None:
        normalized = self._normalize_scoring_text(text)
        if not normalized:
            return None

        words = set(normalized.split())
        polish_hits = len(words & self.POLISH_HINT_WORDS)
        english_hits = len(words & self.ENGLISH_HINT_WORDS)

        if polish_hits > english_hits:
            return "pl"
        if english_hits > polish_hits:
            return "en"
        return None

    def _detect_language_from_text(self, text: str) -> str | None:
        if not text:
            return None
        if re.search(r"[ąćęłńóśźż]", text.lower()):
            return "pl"
        return self._guess_hint_language(text)

    def _strong_command_match(self, text: str) -> bool:
        normalized = self._normalize_scoring_text(text)
        if not normalized:
            return False

        for phrases in self.SHORT_COMMAND_PHRASES.values():
            if normalized in phrases:
                return True
        return False