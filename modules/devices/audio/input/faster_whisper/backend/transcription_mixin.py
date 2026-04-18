from __future__ import annotations

from typing import Any

import numpy as np


class FasterWhisperTranscriptionMixin:
    def _transcribe_audio_candidate(
        self,
        audio: np.ndarray,
        debug: bool = False,
    ) -> dict[str, Any] | None:
        self._ensure_faster_whisper_runtime()
        if self._fw_model is None or audio.size == 0:
            return None

        primary_audio = self._trim_audio_for_transcription(audio)
        if primary_audio.size < int(self.sample_rate * self.min_speech_seconds):
            primary_audio = audio

        prepared_primary = self._prepare_audio_for_model(primary_audio)
        if prepared_primary is None:
            if debug:
                print("Skipping transcription: clip too short or too weak after trimming.")
            return None

        primary_candidate = self._transcribe_single_audio(
            prepared_primary,
            debug=debug,
            label="primary",
            forced_language=None,
        )

        if self._accept_candidate(primary_candidate):
            candidate = dict(primary_candidate)
            candidate["path"] = "primary"
            return candidate

        rescue_candidate = self._rescue_bilingual_candidate(
            prepared_primary,
            primary_candidate=primary_candidate,
            debug=debug,
        )
        if rescue_candidate is not None:
            candidate = dict(rescue_candidate)
            candidate["path"] = "rescue"
            return candidate

        primary_duration = len(prepared_primary) / float(self.MODEL_SAMPLE_RATE)
        if primary_duration < self.retry_min_seconds:
            return None

        retry_audio = self._extract_voiced_audio_for_retry(audio)
        if retry_audio is None or retry_audio.size == 0:
            return None

        prepared_retry = self._prepare_audio_for_model(retry_audio)
        if prepared_retry is None:
            return None

        retry_candidate = self._transcribe_single_audio(
            prepared_retry,
            debug=debug,
            label="retry",
            forced_language=None,
        )
        if self._accept_candidate(retry_candidate):
            candidate = dict(retry_candidate)
            candidate["path"] = "retry"
            return candidate

        retry_rescue_candidate = self._rescue_bilingual_candidate(
            prepared_retry,
            primary_candidate=retry_candidate,
            debug=debug,
        )
        if retry_rescue_candidate is not None:
            candidate = dict(retry_rescue_candidate)
            candidate["path"] = "retry_rescue"
            return candidate

        return None

    def _transcribe_audio(self, audio: np.ndarray, debug: bool = False) -> str | None:
        candidate = self._transcribe_audio_candidate(audio, debug=debug)
        if candidate is None:
            return None
        return str(candidate.get("text") or "").strip() or None

    def _transcribe_single_audio(
        self,
        audio: np.ndarray,
        *,
        debug: bool = False,
        label: str = "primary",
        forced_language: str | None = None,
    ) -> dict[str, Any]:
        candidate: dict[str, Any] = {
            "text": None,
            "language": forced_language,
            "language_probability": 0.0,
            "elapsed": 0.0,
            "forced_language": forced_language,
            "engine": "faster_whisper",
        }

        try:
            language_arg = forced_language if forced_language else (None if self.language == "auto" else self.language)
            started_at = self._now()
            segments, info = self._fw_model.transcribe(
                audio,
                language=language_arg,
                beam_size=self.beam_size,
                best_of=self.best_of,
                condition_on_previous_text=False,
                vad_filter=False,
                word_timestamps=False,
                temperature=0.0,
            )

            parts: list[str] = []
            for segment in segments:
                text = str(getattr(segment, "text", "")).strip()
                if text:
                    parts.append(text)

            elapsed = self._now() - started_at
            transcript = self._cleanup_transcript(" ".join(parts))
            detected_language = forced_language or getattr(info, "language", None)
            language_probability = getattr(info, "language_probability", None)
            if language_probability is None:
                language_probability = 1.0 if forced_language else 0.0

            candidate.update(
                {
                    "text": transcript,
                    "language": self._normalize_language(detected_language, allow_auto=True),
                    "language_probability": float(language_probability),
                    "elapsed": elapsed,
                }
            )

            if debug and self._debug_print_allowed():
                printable = transcript if transcript else "<empty>"
                mode_label = label if forced_language is None else f"{label}:{forced_language}"
                print(
                    f"FasterWhisper {mode_label} transcript: {printable} | "
                    f"lang={detected_language} prob={language_probability} elapsed={elapsed:.2f}s"
                )

            return candidate
        except Exception as error:
            self.LOGGER.warning("FasterWhisper transcription error (%s): %s", label, error)
            return candidate

    def _rescue_bilingual_candidate(
        self,
        audio: np.ndarray,
        *,
        primary_candidate: dict[str, Any] | None = None,
        debug: bool = False,
    ) -> dict[str, Any] | None:
        candidates: list[dict[str, Any]] = []
        primary_language = str((primary_candidate or {}).get("language") or "").strip().lower()
        if primary_language not in self.SUPPORTED_LANGUAGES:
            primary_language = ""

        for forced_language in self._preferred_rescue_languages(primary_candidate):
            candidate = self._transcribe_single_audio(
                audio,
                debug=debug,
                label="rescue",
                forced_language=forced_language,
            )
            if candidate.get("text"):
                candidates.append(candidate)

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: self._candidate_score(item, primary_language=primary_language or None),
            reverse=True,
        )
        best = candidates[0]
        if self._candidate_score(best, primary_language=primary_language or None) <= 0.0:
            return None
        return best

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
        probability = float(candidate.get("language_probability") or 0.0)

        if not text:
            return False
        if self._contains_unsupported_script(text):
            return False
        if self._looks_like_blank_or_garbage(text):
            return False
        if self._strong_command_match(text):
            return True

        word_count = len(text.split())
        if language not in self.SUPPORTED_LANGUAGES:
            return False
        if probability >= self.language_rescue_probability_threshold:
            return True
        if word_count >= self.min_words_for_low_confidence_accept:
            return True
        return False

    def _candidate_score(
        self,
        candidate: dict[str, Any],
        *,
        primary_language: str | None = None,
    ) -> float:
        text = str(candidate.get("text") or "").strip()
        language = str(candidate.get("language") or "").strip().lower()
        probability = float(candidate.get("language_probability") or 0.0)

        if not text:
            return -10.0

        score = 0.0
        score += min(len(text.split()), 8) * 0.25
        score += min(probability, 1.0)

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
            "what time",
            "time is it",
            "ktora godzina",
            "która godzina",
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
            "przypomnij ",
            "zapamietaj ",
            "zapamiętaj ",
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
            "remember ",
            "remind ",
            "set ",
            "start ",
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
                penalty += 1.4
            if normalized in {"thank you", "thanks", "thank you very much"}:
                penalty += 3.0
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

    def _strong_command_match(self, text: str) -> bool:
        normalized = self._normalize_scoring_text(text)
        if not normalized:
            return False

        for phrases in self.SHORT_COMMAND_PHRASES.values():
            if normalized in phrases:
                return True
        return False