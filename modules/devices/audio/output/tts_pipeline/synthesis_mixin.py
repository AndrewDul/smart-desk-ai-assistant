from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from modules.system.utils import append_log


class TTSPipelineSynthesisMixin:
    """
    Helpers for Piper synthesis, WAV playback, and eSpeak fallback.

    Main latency improvement:
    - short current utterances can be synthesized directly instead of waiting
      behind the background queue
    - if the same text is already being synthesized, reuse that pending job
    """
    def _store_playback_report(self, **values) -> None:
        self._latest_playback_report = dict(values)

    def _consume_playback_report(self) -> dict[str, object]:
        report = dict(getattr(self, "_latest_playback_report", {}) or {})
        self._latest_playback_report = {}
        return report

    def _resolve_piper_binary_runner(self) -> str | None:
        candidate = str(getattr(self, "piper_path", "") or "").strip()
        if not candidate:
            return None

        path = Path(candidate)
        if path.exists() and path.is_file():
            return candidate

        resolved = shutil.which(candidate)
        if resolved:
            return resolved

        return None

    def _python_has_piper_module(self, python_path: str) -> bool:
        candidate = str(python_path or "").strip()
        if not candidate:
            return False

        try:
            if not Path(candidate).exists():
                return False
        except Exception:
            return False

        try:
            completed = subprocess.run(
                [
                    candidate,
                    "-c",
                    "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('piper') else 1)",
                ],
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
            return completed.returncode == 0
        except Exception:
            return False

    def _resolve_piper_python_runner(self) -> str | None:
        cached = str(getattr(self, "piper_python_runner_path", "") or "").strip()
        if cached and self._python_has_piper_module(cached):
            return cached

        candidates: list[str] = []

        explicit_python = str(getattr(self, "python_path", "") or "").strip()
        if explicit_python:
            candidates.append(explicit_python)

        project_venv_python = str(getattr(self, "project_venv_python_path", "") or "").strip()
        if project_venv_python:
            candidates.append(project_venv_python)

        runtime_python = str(getattr(self, "runtime_python_path", "") or "").strip()
        if runtime_python:
            candidates.append(runtime_python)

        python3_path = shutil.which("python3") or ""
        if python3_path:
            candidates.append(python3_path)

        python_path = shutil.which("python") or ""
        if python_path:
            candidates.append(python_path)

        seen: set[str] = set()
        for candidate in candidates:
            normalized = str(candidate or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)

            if self._python_has_piper_module(normalized):
                self.piper_python_runner_path = normalized
                append_log(f"Piper python runner resolved: {normalized}")
                return normalized

        self.piper_python_runner_path = None
        return None

    def _build_piper_command(
        self,
        model_path,
        config_path,
        wav_path,
        text: str,
    ) -> list[str] | None:
        normalized_text = str(text or "").strip()
        if not normalized_text:
            return None

        binary_runner = self._resolve_piper_binary_runner()
        if binary_runner:
            return [
                binary_runner,
                "-m",
                str(model_path),
                "-c",
                str(config_path),
                "-f",
                str(wav_path),
                "--",
                normalized_text,
            ]

        python_runner = self._resolve_piper_python_runner()
        if python_runner:
            return [
                python_runner,
                "-m",
                "piper",
                "-m",
                str(model_path),
                "-c",
                str(config_path),
                "-f",
                str(wav_path),
                "--",
                normalized_text,
            ]

        return None

    def _log_last_tts_process_failure(self, source: str, lang: str) -> None:
        result = self._get_last_process_result(source)
        if not result:
            append_log(f"No subprocess diagnostics available for {source} ({lang}).")
            return

        command_display = str(result.get("command_display", "") or "").strip()
        return_code = result.get("return_code")
        elapsed_seconds = float(result.get("elapsed_seconds", 0.0) or 0.0)
        error_text = str(result.get("error_text", "") or "").strip()
        stderr_text = str(result.get("stderr_text", "") or "").strip()
        stdout_text = str(result.get("stdout_text", "") or "").strip()

        append_log(
            f"TTS subprocess diagnostics: source={source}, lang={lang}, "
            f"exit_code={return_code}, elapsed={elapsed_seconds:.3f}s, "
            f"command={command_display or '-'}"
        )
        if error_text:
            append_log(f"TTS subprocess exception: {error_text}")
        if stderr_text:
            append_log(f"TTS subprocess stderr: {stderr_text}")
        elif stdout_text:
            append_log(f"TTS subprocess stdout: {stdout_text}")

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

        command = self._build_piper_command(model_path, config_path, wav_path, text)
        if not command:
            append_log(
                "Piper command is not available. "
                "No usable Piper binary and no Python interpreter with module 'piper' were found. "
                f"explicit_python={getattr(self, 'python_path', '') or '-'} | "
                f"runtime_python={getattr(self, 'runtime_python_path', '') or '-'} | "
                f"project_venv_python={getattr(self, 'project_venv_python_path', '') or '-'} | "
                f"piper_path={getattr(self, 'piper_path', '') or '-'}"
            )
            return False

        append_log(
            "Piper synthesis command prepared: "
            f"lang={normalized_lang}, command={self._format_process_command(command)}"
        )

        wav_path.parent.mkdir(parents=True, exist_ok=True)

        started_at = time.monotonic()
        source = f"piper_synthesis_{normalized_lang}"
        ok = self._run_process_interruptibly(
            command,
            timeout_seconds=self._synthesis_timeout_seconds,
            source=source,
        )
        if not ok:
            append_log(f"Piper synthesis failed for language '{normalized_lang}'.")
            self._log_last_tts_process_failure(source, normalized_lang)
            return False

        if not wav_path.exists():
            append_log(
                "Piper synthesis finished but WAV was not created for language "
                f"'{normalized_lang}'."
            )
            self._log_last_tts_process_failure(source, normalized_lang)
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
        preferred_backend = str(getattr(self, "_preferred_playback_backend", "") or "").strip()
        preferred_order: list[str] = []
        if self._last_good_playback_backend:
            preferred_order.append(self._last_good_playback_backend)
        if preferred_backend and preferred_backend not in preferred_order:
            preferred_order.append(preferred_backend)

        if preferred_order:
            priority_map = {name: index for index, name in enumerate(preferred_order)}
            backends.sort(
                key=lambda item: (
                    priority_map.get(item[0], len(priority_map)),
                    item[0],
                )
            )

        for backend_name, base_command in backends:
            command = list(base_command) + [str(wav_path)]
            ok = self._run_process_interruptibly(
                command,
                timeout_seconds=self._playback_timeout_seconds,
                source=f"{backend_name}_playback",
                poll_sleep_seconds=getattr(self, "_playback_poll_seconds", 0.005),
                capture_output=False,
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
        latency_profile: str | None = None,
    ) -> bool:
        if not self.enabled:
            return False
        if not self._piper_model_ready(lang):
            return False

        started_at = time.monotonic()
        normalized_lang = self._normalize_language(lang)
        cache_path = self._cached_wav_path(text, normalized_lang)
        cache_hit = cache_path.exists()

        normalized_next = self._normalize_prefetch_request(prepare_next)
        if normalized_next is not None and len(text) <= self._early_next_prefetch_max_chars:
            self._start_prefetch(normalized_next[0], normalized_next[1])

        wav_ready_started_at = time.monotonic()
        ready, ready_source, ready_wav_path = self._ensure_current_wav_ready(
            text=text,
            lang=normalized_lang,
            cache_path=cache_path,
            cache_hit=cache_hit,
            latency_profile=latency_profile,
        )
        wav_ready_ms = (time.monotonic() - wav_ready_started_at) * 1000.0

        if not ready:
            append_log(
                f"TTS current synthesis did not finish in time: lang={normalized_lang}, "
                f"chars={len(text)}, wav_ready_ms={wav_ready_ms:.1f}, source={ready_source}, "
                f"latency_profile={latency_profile or '-'}"
            )
            return False

        if normalized_next is not None and len(text) > self._early_next_prefetch_max_chars:
            self._start_prefetch(normalized_next[0], normalized_next[1])

        played, first_audio_started_at = self._play_wav(ready_wav_path)
        if first_audio_started_at <= 0.0:
            first_audio_started_at = time.monotonic() if played else 0.0
        first_audio_ms = (first_audio_started_at - started_at) * 1000.0 if played else 0.0
        self._store_playback_report(
            engine="piper",
            success=played,
            first_audio_started_at_monotonic=first_audio_started_at if played else 0.0,
            first_audio_latency_ms=first_audio_ms if played else 0.0,
            wav_ready_ms=wav_ready_ms,
            wav_ready_source=ready_source,
            cache_hit=cache_hit,
        )

        if played:
            append_log(
                f"TTS total finished: lang={normalized_lang}, chars={len(text)}, "
                f"cache_hit={cache_hit}, wav_ready_source={ready_source}, "
                f"wav_ready_ms={wav_ready_ms:.1f}, first_audio_path_ms={first_audio_ms:.1f}, "
                f"latency_profile={latency_profile or '-'}, "
                f"elapsed={time.monotonic() - started_at:.3f}s"
            )
            return True

        if ready_source == "direct_current_bypass_pending" and ready_wav_path.exists():
            try:
                ready_wav_path.unlink()
            except OSError:
                pass

        if cache_path.exists():
            try:
                cache_path.unlink()
            except OSError:
                pass

        retry_ready_started_at = time.monotonic()
        current_job = self._enqueue_synthesis(
            text,
            normalized_lang,
            priority=self._PRIORITY_CURRENT,
        )
        ready = self._wait_for_job(
            current_job,
            timeout_seconds=self._current_job_wait_seconds,
        )
        retry_ready_ms = (time.monotonic() - retry_ready_started_at) * 1000.0
        if not ready:
            append_log(
                f"TTS retry synthesis did not finish in time: lang={normalized_lang}, "
                f"chars={len(text)}, retry_ready_ms={retry_ready_ms:.1f}"
            )
            return False

        played, retry_first_audio_started_at = self._play_wav(cache_path)
        if retry_first_audio_started_at <= 0.0:
            retry_first_audio_started_at = time.monotonic() if played else 0.0
        retry_first_audio_ms = (retry_first_audio_started_at - started_at) * 1000.0 if played else 0.0
        self._store_playback_report(
            engine="piper",
            success=played,
            first_audio_started_at_monotonic=retry_first_audio_started_at if played else 0.0,
            first_audio_latency_ms=retry_first_audio_ms if played else 0.0,
            wav_ready_ms=retry_ready_ms,
            wav_ready_source="retry_ready",
            cache_hit=False,
        )
        if played:
            append_log(
                "TTS total finished after playback retry: "
                f"lang={normalized_lang}, chars={len(text)}, retry_ready_ms={retry_ready_ms:.1f}, "
                f"elapsed={time.monotonic() - started_at:.3f}s"
            )
            return True

        append_log(f"No working WAV playback command available for language '{normalized_lang}'.")
        return False

    def _ensure_current_wav_ready(
        self,
        *,
        text: str,
        lang: str,
        cache_path: Path,
        cache_hit: bool,
        latency_profile: str | None = None,
    ) -> tuple[bool, str, Path]:
        if cache_hit and cache_path.exists():
            return True, "cache_hit", cache_path

        pending_job = self._get_pending_job(text=text, lang=lang)
        if self._should_bypass_pending_job_for_direct_current(
            pending_job=pending_job,
            text=text,
            lang=lang,
            latency_profile=latency_profile,
        ):
            direct_path = self._bypass_pending_direct_current_wav_path(cache_path)
            ok = self._synthesize_piper_to_wav(text, lang, direct_path)
            if ok and direct_path.exists():
                return True, "direct_current_bypass_pending", direct_path
            if direct_path.exists():
                try:
                    direct_path.unlink()
                except OSError:
                    pass

        existing_job, promoted = self._promote_pending_job(
            text=text,
            lang=lang,
            priority=self._PRIORITY_CURRENT,
        )
        if existing_job is not None:
            ready = self._wait_for_job(
                existing_job,
                timeout_seconds=self._current_job_wait_seconds,
            )
            return ready, "pending_job_promoted" if promoted else "pending_job", cache_path

        if self._should_direct_synthesize_current(
            text=text,
            lang=lang,
            latency_profile=latency_profile,
        ):
            ok = self._synthesize_piper_to_wav(text, lang, cache_path)
            return ok, "direct_current", cache_path

        current_job = self._enqueue_synthesis(
            text,
            lang,
            priority=self._PRIORITY_CURRENT,
        )
        ready = self._wait_for_job(
            current_job,
            timeout_seconds=self._current_job_wait_seconds,
        )
        return ready, "queued_current", cache_path

    @staticmethod
    def _bypass_pending_direct_current_wav_path(cache_path: Path) -> Path:
        return cache_path.with_name(f"{cache_path.stem}.direct-current{cache_path.suffix}")

    def _should_bypass_pending_job_for_direct_current(
        self,
        *,
        pending_job,
        text: str,
        lang: str,
        latency_profile: str | None = None,
    ) -> bool:
        normalized_profile = str(latency_profile or "").strip().lower()
        if normalized_profile != "action_fast":
            return False
        if pending_job is None:
            return False
        if getattr(pending_job, "event", None) is not None and pending_job.event.is_set():
            return False

        pending_priority = int(getattr(pending_job, "priority", self._PRIORITY_CURRENT))
        if pending_priority <= self._PRIORITY_CURRENT:
            return False

        return self._should_direct_synthesize_current(
            text=text,
            lang=lang,
            latency_profile=latency_profile,
        )



    def _get_pending_job(self, *, text: str, lang: str):
        key = self._prefetch_key(text, lang)
        with self._prefetch_lock:
            job = self._pending_jobs.get(key)
            if job is None:
                return None
            if job.event.is_set() and not job.cache_path.exists():
                return None
            return job

    def _direct_current_limit_for_profile(self, *, latency_profile: str | None = None) -> int:
        base_limit = int(getattr(self, "_direct_current_synthesis_max_chars", 120))
        normalized_profile = str(latency_profile or "").strip().lower()
        if normalized_profile == "action_fast":
            profile_limit = int(
                getattr(self, "_action_fast_direct_current_synthesis_max_chars", base_limit)
            )
            return max(base_limit, profile_limit)
        return base_limit

    def _should_direct_synthesize_current(
        self,
        *,
        text: str,
        lang: str,
        latency_profile: str | None = None,
    ) -> bool:
        if not self.enabled:
            return False
        if self.preferred_engine != "piper":
            return False
        if not self._piper_model_ready(lang):
            return False
        if self._stop_requested.is_set():
            return False

        max_chars = self._direct_current_limit_for_profile(latency_profile=latency_profile)
        if len(text) > max_chars:
            return False

        return True

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
        self._store_playback_report(
            engine="espeak",
            success=ok,
            first_audio_started_at_monotonic=started_at if ok else 0.0,
            first_audio_latency_ms=0.0,
            wav_ready_ms=0.0,
            wav_ready_source="espeak_stdin",
            cache_hit=False,
        )
        if ok:
            append_log(
                f"eSpeak total finished: lang={lang}, chars={len(text)}, "
                f"elapsed={time.monotonic() - started_at:.3f}s"
            )
        return ok


__all__ = ["TTSPipelineSynthesisMixin"]