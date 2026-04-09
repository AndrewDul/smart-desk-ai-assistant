from __future__ import annotations

import time

from modules.system.utils import append_log


class TTSPipelineSynthesisMixin:
    """
    Helpers for Piper synthesis, WAV playback, and eSpeak fallback.
    """

    def _build_piper_command(self, model_path, config_path, wav_path) -> list[str] | None:
        if self.piper_path:
            return [
                self.piper_path,
                "-m",
                str(model_path),
                "-c",
                str(config_path),
                "-f",
                str(wav_path),
            ]

        if self.python_path:
            return [
                self.python_path,
                "-m",
                "piper",
                "-m",
                str(model_path),
                "-c",
                str(config_path),
                "-f",
                str(wav_path),
            ]

        return None

    def _synthesize_piper_to_wav(self, text: str, lang: str, wav_path) -> bool:
        normalized_lang = self._normalize_language(lang)
        model_info = self._resolved_piper_paths.get(normalized_lang)

        if not model_info:
            append_log(f"No Piper model config for language '{normalized_lang}'.")
            return False

        model_path = model_info["model"]
        config_path = model_info["config"]
        if not model_path.exists() or not config_path.exists():
            append_log(f"Piper model missing for language '{normalized_lang}'.")
            return False

        command = self._build_piper_command(model_path, config_path, wav_path)
        if not command:
            append_log("Piper command is not available.")
            return False

        wav_path.parent.mkdir(parents=True, exist_ok=True)

        started_at = time.monotonic()
        ok = self._run_process_interruptibly(
            command,
            input_text=text,
            timeout_seconds=self._synthesis_timeout_seconds,
            source=f"piper_synthesis_{normalized_lang}",
        )
        if not ok:
            append_log(f"Piper synthesis failed for language '{normalized_lang}'.")
            return False

        if not wav_path.exists():
            append_log(
                "Piper synthesis finished but WAV was not created for language "
                f"'{normalized_lang}'."
            )
            return False

        append_log(
            f"Piper synthesis finished: lang={normalized_lang}, chars={len(text)}, "
            f"elapsed={time.monotonic() - started_at:.3f}s"
        )
        return True

    def _play_wav(self, wav_path) -> bool:
        if not wav_path.exists():
            return False

        playback_started_at = time.monotonic()

        backends = list(self._playback_backends)
        if self._last_good_playback_backend:
            backends.sort(
                key=lambda item: 0 if item[0] == self._last_good_playback_backend else 1
            )

        for backend_name, base_command in backends:
            command = list(base_command) + [str(wav_path)]
            ok = self._run_process_interruptibly(
                command,
                timeout_seconds=self._playback_timeout_seconds,
                source=f"{backend_name}_playback",
            )
            if ok:
                self._last_good_playback_backend = backend_name
                append_log(
                    f"TTS playback finished with {backend_name} in "
                    f"{time.monotonic() - playback_started_at:.3f}s"
                )
                return True

        append_log("All playback backends failed for current WAV.")
        return False

    def _speak_with_piper(
        self,
        text: str,
        lang: str,
        *,
        prepare_next: tuple[str, str] | None = None,
    ) -> bool:
        if not self.enabled:
            return False
        if not self._piper_model_ready(lang):
            return False

        started_at = time.monotonic()
        cache_path = self._cached_wav_path(text, lang)
        cache_hit = cache_path.exists()

        normalized_next = self._normalize_prefetch_request(prepare_next)
        if normalized_next is not None and len(text) <= self._early_next_prefetch_max_chars:
            self._start_prefetch(normalized_next[0], normalized_next[1])

        if not cache_hit:
            current_job = self._enqueue_synthesis(
                text,
                lang,
                priority=self._PRIORITY_CURRENT,
            )
            ready = self._wait_for_job(
                current_job,
                timeout_seconds=self._current_job_wait_seconds,
            )
            if not ready:
                append_log(
                    f"TTS current synthesis did not finish in time: lang={lang}, chars={len(text)}"
                )
                return False

        if normalized_next is not None and len(text) > self._early_next_prefetch_max_chars:
            self._start_prefetch(normalized_next[0], normalized_next[1])

        played = self._play_wav(cache_path)
        if played:
            append_log(
                f"TTS total finished: lang={lang}, chars={len(text)}, "
                f"cache_hit={cache_hit}, elapsed={time.monotonic() - started_at:.3f}s"
            )
            return True

        if cache_path.exists():
            try:
                cache_path.unlink()
            except OSError:
                pass

        current_job = self._enqueue_synthesis(
            text,
            lang,
            priority=self._PRIORITY_CURRENT,
        )
        ready = self._wait_for_job(
            current_job,
            timeout_seconds=self._current_job_wait_seconds,
        )
        if not ready:
            return False

        played = self._play_wav(cache_path)
        if played:
            append_log(
                "TTS total finished after playback retry: "
                f"lang={lang}, chars={len(text)}, elapsed={time.monotonic() - started_at:.3f}s"
            )
            return True

        append_log(f"No working WAV playback command available for language '{lang}'.")
        return False

    def _speak_with_espeak(self, text: str, lang: str) -> bool:
        if not self.espeak_path:
            append_log("eSpeak is not available.")
            return False

        voice = self.voices.get(lang)
        if not voice:
            append_log(f"No eSpeak voice configured for language '{lang}'.")
            return False

        started_at = time.monotonic()
        ok = self._run_process_interruptibly(
            [
                self.espeak_path,
                "-v",
                voice,
                "-s",
                str(self.speed),
                "-p",
                str(self.pitch),
                "--stdin",
            ],
            input_text=text,
            timeout_seconds=self._synthesis_timeout_seconds,
            source=f"espeak_tts_{lang}",
        )
        if ok:
            append_log(
                f"eSpeak total finished: lang={lang}, chars={len(text)}, "
                f"elapsed={time.monotonic() - started_at:.3f}s"
            )
        return ok


__all__ = ["TTSPipelineSynthesisMixin"]