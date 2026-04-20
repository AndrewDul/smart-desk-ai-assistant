from __future__ import annotations

import time

from modules.system.utils import append_log


class TTSPipelineSpeechApiMixin:
    """
    Public speech API for prefetching and speaking text.

    Goals:
    - keep the external API simple
    - normalize text once before entering synthesis
    - normalize prepare_next early so Piper gets ready-to-use data
    - emit useful latency logs for real-world tuning
    - reduce dead time after short or interrupted playback
    """

    def prepare_speech(self, text: str, language: str | None = None) -> None:
        cleaned_text = self._normalize_text_for_log(text)
        if not cleaned_text:
            return

        if not self.enabled:
            return

        lang = self._resolve_language(language)
        tts_text = self._normalize_text_for_tts(cleaned_text, lang)
        if not tts_text:
            return

        append_log(
            f"TTS prepare_speech queued: lang={lang}, chars={len(tts_text)}"
        )
        self._start_prefetch(tts_text, lang)

    def speak(
        self,
        text: str,
        language: str | None = None,
        prepare_next: tuple[str, str] | None = None,
        output_hold_seconds: float | None = None,
    ) -> bool:
        started_at = time.monotonic()

        cleaned_text = self._normalize_text_for_log(text)
        if not cleaned_text:
            append_log("TTS speak skipped: empty cleaned text.")
            return False

        lang = self._resolve_language(language)
        tts_text = self._normalize_text_for_tts(cleaned_text, lang)
        if not tts_text:
            append_log(f"TTS speak skipped: empty normalized TTS text for lang={lang}.")
            return False

        normalized_prepare_next = self._normalize_prefetch_request(prepare_next)
        has_prepare_next = normalized_prepare_next is not None

        print(f"Assistant> {cleaned_text}")
        self._log_spoken_text(cleaned_text, lang)

        if not self.enabled:
            append_log("TTS speak skipped: pipeline disabled.")
            return False

        self.clear_stop_request()

        coordinator_token: str | None = None
        used_engine = "none"
        success = False
        interrupted = False

        try:
            with self._speak_lock:
                if self._stop_requested.is_set():
                    append_log("TTS speak aborted before synthesis due to stop request.")
                    interrupted = True
                    return False

                if self.audio_coordinator is not None:
                    coordinator_token = self.audio_coordinator.begin_assistant_output(
                        source="tts",
                        text_preview=cleaned_text,
                    )

                if self.preferred_engine == "piper":
                    used_piper = self._speak_with_piper(
                        tts_text,
                        lang,
                        prepare_next=normalized_prepare_next,
                    )
                    if used_piper:
                        used_engine = "piper"
                        success = True
                        return True

                    if self._stop_requested.is_set():
                        append_log("TTS speak interrupted after Piper attempt.")
                        interrupted = True
                        return False

                used_espeak = self._speak_with_espeak(tts_text, lang)
                if used_espeak:
                    used_engine = "espeak"
                    success = True
                    return True

                if self._stop_requested.is_set():
                    append_log("TTS speak interrupted after fallback attempt.")
                    interrupted = True
                    return False

                self._log_voice_output_failure(lang)
                return False
        finally:
            interrupted = interrupted or self._stop_requested.is_set()

            if self.audio_coordinator is not None:
                hold_seconds = self._resolve_output_hold_seconds(
                    interrupted=interrupted,
                    success=success,
                    spoken_text=tts_text,
                    output_hold_override=output_hold_seconds,
                )
                self.audio_coordinator.end_assistant_output(
                    coordinator_token,
                    hold_seconds=hold_seconds,
                )

            append_log(
                "TTS speak finished: "
                f"lang={lang}, "
                f"chars={len(tts_text)}, "
                f"engine={used_engine}, "
                f"success={success}, "
                f"interrupted={interrupted}, "
                f"prepare_next={has_prepare_next}, "
                f"output_hold_override={output_hold_seconds}, "
                f"elapsed={time.monotonic() - started_at:.3f}s"
            )

    @staticmethod
    def _log_spoken_text(cleaned_text: str, lang: str) -> None:
        append_log(f"Assistant said [{lang}]: {cleaned_text}")

    @staticmethod
    def _log_voice_output_failure(lang: str) -> None:
        append_log(f"Voice output failed for language '{lang}' on all available engines.")


__all__ = ["TTSPipelineSpeechApiMixin"]