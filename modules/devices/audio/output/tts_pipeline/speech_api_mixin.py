from __future__ import annotations

import inspect
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

    def latest_speak_report(self) -> dict[str, object]:
        return dict(getattr(self, "_last_speak_report", {}) or {})

    def _store_speak_report(self, **values: object) -> None:
        self._last_speak_report = dict(values)

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

        if self._should_log_tts_hot_path_success():
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
        latency_profile: str | None = None,
        on_first_audio=None,
    ) -> bool:
        started_at = time.monotonic()
        self._store_speak_report(
            text=str(text or ""),
            language=str(language or ""),
            started_at_monotonic=started_at,
            first_audio_started_at_monotonic=0.0,
            first_audio_latency_ms=0.0,
            engine="none",
            success=False,
            interrupted=False,
        )

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

        if self._should_echo_spoken_text_to_console():
            print(f"Assistant> {cleaned_text}")
        if self._should_log_spoken_text_content():
            self._log_spoken_text(cleaned_text, lang)

        if not self.enabled:
            append_log("TTS speak skipped: pipeline disabled.")
            return False

        coordinator_token: str | None = None
        used_engine = "none"
        success = False
        interrupted = False
        presence_first_audio_started_at = 0.0

        try:
            with self._speak_lock:
                self.clear_stop_request()
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
                    piper_kwargs = {
                        "prepare_next": normalized_prepare_next,
                        "latency_profile": latency_profile,
                    }
                    if callable(on_first_audio):
                        try:
                            signature = inspect.signature(self._speak_with_piper)
                            supports_first_audio = "on_first_audio" in signature.parameters
                            supports_var_kwargs = any(
                                parameter.kind is inspect.Parameter.VAR_KEYWORD
                                for parameter in signature.parameters.values()
                            )
                            if supports_first_audio or supports_var_kwargs:
                                piper_kwargs["on_first_audio"] = on_first_audio
                        except (TypeError, ValueError):
                            piper_kwargs["on_first_audio"] = on_first_audio
                    used_piper = self._speak_with_piper(tts_text, lang, **piper_kwargs)
                    if used_piper:
                        used_engine = "piper"
                        success = True
                        return True

                    if self._stop_requested.is_set():
                        append_log("TTS speak interrupted after Piper attempt.")
                        interrupted = True
                        return False

                if not self._should_allow_espeak_fallback():
                    append_log(
                        "TTS eSpeak fallback blocked by config: "
                        f"preferred_engine={self.preferred_engine}, lang={lang}"
                    )
                    self._log_voice_output_failure(lang)
                    return False

                if callable(on_first_audio):
                    try:
                        on_first_audio()
                    except Exception:
                        pass
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
            playback_report_method = getattr(self, "_consume_playback_report", None)
            playback_report = (
                playback_report_method()
                if callable(playback_report_method)
                else {}
            )

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

            first_audio_started_at = 0.0
            first_audio_latency_ms = 0.0
            try:
                first_audio_started_at = max(
                    0.0,
                    float(playback_report.get("first_audio_started_at_monotonic", 0.0) or 0.0),
                )
            except (TypeError, ValueError):
                first_audio_started_at = 0.0
            try:
                first_audio_latency_ms = max(
                    0.0,
                    float(playback_report.get("first_audio_latency_ms", 0.0) or 0.0),
                )
            except (TypeError, ValueError):
                first_audio_latency_ms = 0.0
            if first_audio_latency_ms <= 0.0 and first_audio_started_at > 0.0:
                first_audio_latency_ms = max(
                    0.0,
                    (first_audio_started_at - started_at) * 1000.0,
                )

            self._store_speak_report(
                text=cleaned_text,
                language=lang,
                started_at_monotonic=started_at,
                first_audio_started_at_monotonic=first_audio_started_at,
                first_audio_latency_ms=first_audio_latency_ms,
                engine=str(playback_report.get("engine", used_engine) or used_engine),
                success=success,
                interrupted=interrupted,
                playback_backend=str(playback_report.get("playback_backend", "") or ""),
                playback_command=str(playback_report.get("playback_command", "") or ""),
                playback_exit_code=playback_report.get("playback_exit_code"),
                playback_stderr=str(playback_report.get("playback_stderr", "") or ""),
                playback_stdout=str(playback_report.get("playback_stdout", "") or ""),
                playback_process_started=bool(playback_report.get("playback_process_started", False)),
                playback_timed_out=bool(playback_report.get("playback_timed_out", False)),
                playback_interrupted=bool(playback_report.get("playback_interrupted", interrupted)),
                audio_file=str(playback_report.get("audio_file", "") or ""),
                audio_file_exists=bool(playback_report.get("audio_file_exists", False)),
                audio_file_size_bytes=int(playback_report.get("audio_file_size_bytes", 0) or 0),
                prepare_next=has_prepare_next,
                output_hold_seconds=output_hold_seconds,
                latency_profile=latency_profile,
                on_first_audio=callable(on_first_audio),
                elapsed_ms=max(0.0, (time.monotonic() - started_at) * 1000.0),
            )

            if self._should_log_tts_hot_path_success():
                append_log(
                    "TTS speak finished: "
                    f"lang={lang}, "
                    f"chars={len(tts_text)}, "
                    f"engine={used_engine}, "
                    f"success={success}, "
                    f"interrupted={interrupted}, "
                    f"prepare_next={has_prepare_next}, "
                    f"output_hold_override={output_hold_seconds}, "
                    f"latency_profile={latency_profile or '-'}, "
                    f"first_audio_ms={first_audio_latency_ms:.1f}, "
                    f"elapsed={time.monotonic() - started_at:.3f}s"
                )

    def speak_presence(
        self,
        text: str,
        language: str | None = None,
    ) -> tuple[bool, str]:
        """
        Best-effort low-priority speech for presence heartbeat phrases.

        This must never wait behind real speech. If the TTS lock is busy, the
        heartbeat is skipped and the manager can try again later.
        """
        started_at = time.monotonic()
        cleaned_text = self._normalize_text_for_log(text)
        if not cleaned_text:
            return False, "empty"
        if not self.enabled:
            return False, "tts_disabled"

        lang = self._resolve_language(language)
        tts_text = self._normalize_text_for_tts(cleaned_text, lang)
        if not tts_text:
            return False, "empty_tts_text"

        if self.preferred_engine != "piper" or not self._piper_model_ready(lang):
            return False, "piper_unavailable"

        cache_path = self._cached_wav_path(tts_text, lang)
        if not cache_path.exists():
            append_log(
                "[presence-heartbeat] skipped reason=cache_miss "
                f"lang={lang} text={cleaned_text!r}"
            )
            self._start_prefetch(tts_text, lang)
            return False, "cache_miss"

        lock = getattr(self, "_presence_playback_lock", None)
        if lock is None:
            lock = self._presence_playback_lock = __import__("threading").Lock()

        acquired = lock.acquire(blocking=False)
        if not acquired:
            append_log("[presence-heartbeat] skipped reason=presence_playback_busy")
            return False, "presence_playback_busy"

        presence_stop = getattr(self, "_presence_stop_requested", None)
        if presence_stop is None:
            presence_stop = self._presence_stop_requested = __import__("threading").Event()
        else:
            try:
                presence_stop.clear()
            except Exception:
                pass

        coordinator_token: str | None = None
        used_engine = "none"
        success = False
        interrupted = False
        presence_first_audio_started_at = 0.0

        try:
            if self._stop_requested.is_set():
                interrupted = True
                return False, "stop_requested"

            if self.audio_coordinator is not None:
                coordinator_token = self.audio_coordinator.begin_assistant_output(
                    source="tts_presence",
                    text_preview=cleaned_text,
                )

            played, first_audio_started_at = self._play_wav(
                cache_path,
                stop_event=presence_stop,
                presence_playback=True,
            )
            presence_first_audio_started_at = first_audio_started_at
            used_engine = "piper_cached_presence"
            if played:
                success = True
                append_log(
                    "[presence-heartbeat] spoken "
                    f"lang={lang} text={cleaned_text!r}"
                )
                return True, "spoken"

            interrupted = interrupted or self._stop_requested.is_set()
            return False, "playback_failed"
        finally:
            interrupted = interrupted or self._stop_requested.is_set()

            if self.audio_coordinator is not None:
                self.audio_coordinator.end_assistant_output(
                    coordinator_token,
                    hold_seconds=0.0 if interrupted else 0.05,
                )

            first_audio_latency_ms = (
                max(0.0, (presence_first_audio_started_at - started_at) * 1000.0)
                if presence_first_audio_started_at > 0.0
                else 0.0
            )

            self._store_speak_report(
                text=cleaned_text,
                language=lang,
                started_at_monotonic=started_at,
                first_audio_started_at_monotonic=presence_first_audio_started_at,
                first_audio_latency_ms=first_audio_latency_ms,
                engine=used_engine,
                success=success,
                interrupted=interrupted,
                prepare_next=False,
                output_hold_seconds=0.0,
                latency_profile="presence",
                elapsed_ms=max(0.0, (time.monotonic() - started_at) * 1000.0),
            )
            lock.release()

    def _should_allow_espeak_fallback(self) -> bool:
        preferred_engine = str(
            getattr(self, "preferred_engine", "piper") or "piper"
        ).strip().lower()
        if preferred_engine in {"espeak", "espeak-ng"}:
            return True
        return bool(getattr(self, "_allow_espeak_fallback", False))

    def _should_echo_spoken_text_to_console(self) -> bool:
        return bool(getattr(self, "_console_echo_enabled", False))

    def _should_log_spoken_text_content(self) -> bool:
        return bool(getattr(self, "_spoken_text_log_enabled", False))

    def _should_log_tts_hot_path_success(self) -> bool:
        return bool(getattr(self, "_tts_hot_path_success_log_enabled", False))

    @staticmethod
    def _log_spoken_text(cleaned_text: str, lang: str) -> None:
        append_log(f"Assistant said [{lang}]: {cleaned_text}")

    @staticmethod
    def _log_voice_output_failure(lang: str) -> None:
        append_log(f"Voice output failed for language '{lang}' on all available engines.")


__all__ = ["TTSPipelineSpeechApiMixin"]
