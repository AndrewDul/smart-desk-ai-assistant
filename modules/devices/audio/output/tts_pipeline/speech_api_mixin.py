from __future__ import annotations


class TTSPipelineSpeechApiMixin:
    """
    Public speech API for prefetching and speaking text.
    """

    def prepare_speech(self, text: str, language: str | None = None) -> None:
        cleaned_text = self._normalize_text_for_log(text)
        if not cleaned_text:
            return

        lang = self._resolve_language(language)
        tts_text = self._normalize_text_for_tts(cleaned_text, lang)
        if not tts_text:
            return

        self._start_prefetch(tts_text, lang)

    def speak(
        self,
        text: str,
        language: str | None = None,
        prepare_next: tuple[str, str] | None = None,
    ) -> bool:
        cleaned_text = self._normalize_text_for_log(text)
        if not cleaned_text:
            return False

        lang = self._resolve_language(language)
        tts_text = self._normalize_text_for_tts(cleaned_text, lang)
        if not tts_text:
            return False

        print(f"Assistant> {cleaned_text}")
        self._log_spoken_text(cleaned_text, lang)

        if not self.enabled:
            return False

        self.clear_stop_request()

        coordinator_token: str | None = None
        if self.audio_coordinator is not None:
            coordinator_token = self.audio_coordinator.begin_assistant_output(
                source="tts",
                text_preview=cleaned_text,
            )

        try:
            with self._speak_lock:
                if self._stop_requested.is_set():
                    return False

                if self.preferred_engine == "piper":
                    used_piper = self._speak_with_piper(
                        tts_text,
                        lang,
                        prepare_next=prepare_next,
                    )
                    if used_piper:
                        return True
                    if self._stop_requested.is_set():
                        return False

                used_espeak = self._speak_with_espeak(tts_text, lang)
                if used_espeak:
                    return True

                if self._stop_requested.is_set():
                    return False

                self._log_voice_output_failure(lang)
                return False
        finally:
            if self.audio_coordinator is not None:
                self.audio_coordinator.end_assistant_output(coordinator_token)

    @staticmethod
    def _log_spoken_text(cleaned_text: str, lang: str) -> None:
        from modules.system.utils import append_log

        append_log(f"Assistant said [{lang}]: {cleaned_text}")

    @staticmethod
    def _log_voice_output_failure(lang: str) -> None:
        from modules.system.utils import append_log

        append_log(f"Voice output failed for language '{lang}' on all available engines.")


__all__ = ["TTSPipelineSpeechApiMixin"]