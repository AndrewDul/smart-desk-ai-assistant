from __future__ import annotations

import hashlib
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from modules.system.utils import BASE_DIR, CACHE_DIR, append_log

if TYPE_CHECKING:
    from modules.devices.audio.coordination import AssistantAudioCoordinator


class _SynthesisJob:
    """One cached Piper synthesis request."""

    __slots__ = (
        "key",
        "text",
        "lang",
        "cache_path",
        "event",
        "success",
        "error",
        "priority",
        "version",
    )

    def __init__(
        self,
        *,
        key: tuple[str, str],
        text: str,
        lang: str,
        cache_path: Path,
        priority: int,
    ) -> None:
        self.key = key
        self.text = text
        self.lang = lang
        self.cache_path = cache_path
        self.event = threading.Event()
        self.success = False
        self.error = ""
        self.priority = int(priority)
        self.version = 0


class TTSPipeline:
    """
    Low-latency local TTS pipeline for NeXa.

    Design goals:
    - keep speech stable on Raspberry Pi
    - avoid spawning multiple concurrent Piper synth jobs that fight for CPU
    - prefetch likely next chunks in the background
    - keep interruption responsive
    - fall back to eSpeak when Piper is unavailable
    """

    _CACHE_VERSION = "tts-v7-priority-synthesis-queue"

    _PRIORITY_CURRENT = 0
    _PRIORITY_NEXT = 10
    _PRIORITY_WARMUP = 20

    def __init__(
        self,
        enabled: bool = True,
        preferred_engine: str = "piper",
        default_language: str = "en",
        speed: int = 155,
        pitch: int = 58,
        voices: dict[str, str] | None = None,
        piper_models: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.preferred_engine = str(preferred_engine or "piper").strip().lower() or "piper"
        self.default_language = self._normalize_language(default_language)
        self.speed = int(speed)
        self.pitch = int(pitch)

        self.voices = voices or {
            "pl": "pl+f3",
            "en": "en+f3",
        }
        self.piper_models = piper_models or {
            "pl": {
                "model": "voices/piper/pl_PL-gosia-medium.onnx",
                "config": "voices/piper/pl_PL-gosia-medium.onnx.json",
            },
            "en": {
                "model": "voices/piper/en_GB-jenny_dioco-medium.onnx",
                "config": "voices/piper/en_GB-jenny_dioco-medium.onnx.json",
            },
        }

        self.python_path = shutil.which("python3") or shutil.which("python") or sys.executable
        self.piper_path = shutil.which("piper")
        self.espeak_path = shutil.which("espeak-ng") or shutil.which("espeak")

        self._base_dir = BASE_DIR
        self._tts_cache_dir = CACHE_DIR / "tts"
        self._tts_cache_dir.mkdir(parents=True, exist_ok=True)

        self._speak_lock = threading.Lock()
        self._process_lock = threading.Lock()
        self._prefetch_lock = threading.Lock()
        self._stop_requested = threading.Event()

        self._active_processes: list[subprocess.Popen] = []
        self.audio_coordinator: AssistantAudioCoordinator | None = None

        self._playback_backends: list[tuple[str, list[str]]] = self._detect_playback_backends()
        self._last_good_playback_backend: str | None = None

        self._synthesis_timeout_seconds = 28.0
        self._playback_timeout_seconds = 32.0
        self._job_wait_poll_seconds = 0.03
        self._cache_warmup_delay_seconds = 0.8
        self._current_job_wait_seconds = 20.0
        self._early_next_prefetch_max_chars = 64

        self._job_queue: queue.PriorityQueue[tuple[int, int, int, _SynthesisJob | None]] = queue.PriorityQueue()
        self._job_sequence = 0
        self._pending_jobs: dict[tuple[str, str], _SynthesisJob] = {}
        self._synthesis_worker_started = False
        self._synthesis_worker: threading.Thread | None = None
        self._cache_warmup_thread: threading.Thread | None = None

        self._resolved_piper_paths = self._resolve_piper_paths()
        self._piper_ready_cache: dict[str, bool] = {
            lang: self._paths_ready(model_info)
            for lang, model_info in self._resolved_piper_paths.items()
        }

        self._common_cache_phrases: dict[str, list[str]] = {
            "pl": [
                "Dobrze.",
                "Oczywiście.",
                "Jasne.",
                "Jestem tutaj.",
                "Już mówię.",
                "Powiedz tak albo nie.",
                "Nie usłyszałam wyraźnie. Powiedz proszę jeszcze raz.",
                "Jak mogę pomóc?",
                "Nie mogę tego teraz zrobić.",
                "Przypomnienie.",
                "Nazywam się NeXa.",
            ],
            "en": [
                "Okay.",
                "Of course.",
                "Sure.",
                "I am here.",
                "I can help.",
                "Please say yes or no.",
                "I did not catch that clearly. Please say it again.",
                "How can I help?",
                "I cannot do that right now.",
                "Reminder.",
                "My name is NeXa.",
            ],
        }

        append_log(
            "Voice playback backends detected: "
            f"{', '.join(name for name, _ in self._playback_backends) if self._playback_backends else 'none'}"
        )
        append_log(
            "TTS engines detected: "
            f"piper_binary={'yes' if self.piper_path else 'no'}, "
            f"python_runner={'yes' if self.python_path else 'no'}, "
            f"espeak={'yes' if self.espeak_path else 'no'}"
        )

        if self.enabled and self.preferred_engine == "piper":
            self._start_synthesis_worker()
            self._start_cache_warmup()

    # ------------------------------------------------------------------
    # Public control
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = str(language or "").strip().lower()
        if normalized in {"pl", "en"}:
            return normalized
        return "en"

    def _resolve_language(self, language: str | None) -> str:
        normalized = self._normalize_language(language)
        return normalized if normalized in {"pl", "en"} else self.default_language

    def set_audio_coordinator(
        self,
        audio_coordinator: AssistantAudioCoordinator | None,
    ) -> None:
        self.audio_coordinator = audio_coordinator

    def clear_stop_request(self) -> None:
        self._stop_requested.clear()

    def stop_playback(self) -> None:
        self._stop_requested.set()

        with self._process_lock:
            processes = list(self._active_processes)

        for process in processes:
            self._terminate_process(process, reason="stop_request")

    # ------------------------------------------------------------------
    # Process helpers
    # ------------------------------------------------------------------

    def _register_process(self, process: subprocess.Popen) -> None:
        with self._process_lock:
            self._active_processes.append(process)

    def _unregister_process(self, process: subprocess.Popen) -> None:
        with self._process_lock:
            self._active_processes = [item for item in self._active_processes if item is not process]

    @staticmethod
    def _terminate_process(process: subprocess.Popen, *, reason: str) -> None:
        try:
            if process.poll() is not None:
                return

            process.terminate()
            try:
                process.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=0.25)
        except Exception as error:
            append_log(f"TTS process termination warning ({reason}): {error}")

    def _run_process_interruptibly(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        timeout_seconds: float,
        source: str,
    ) -> bool:
        started_at = time.monotonic()
        process: subprocess.Popen | None = None

        try:
            process = subprocess.Popen(
                args,
                stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            self._register_process(process)

            if input_text is not None and process.stdin is not None:
                try:
                    process.stdin.write(input_text)
                    process.stdin.close()
                except BrokenPipeError:
                    pass
                except Exception as error:
                    append_log(f"{source} stdin warning: {error}")

            while True:
                if self._stop_requested.is_set():
                    self._terminate_process(process, reason=source)
                    return False

                return_code = process.poll()
                if return_code is not None:
                    return return_code == 0

                if (time.monotonic() - started_at) >= timeout_seconds:
                    append_log(f"{source} process timed out after {timeout_seconds:.2f}s.")
                    self._terminate_process(process, reason=f"{source}_timeout")
                    return False

                time.sleep(0.02)
        except Exception as error:
            append_log(f"{source} process error: {error}")
            return False
        finally:
            if process is not None:
                self._unregister_process(process)

    # ------------------------------------------------------------------
    # Path / tool resolution
    # ------------------------------------------------------------------

    def _resolve_project_path(self, raw_path: str) -> Path:
        candidate = Path(str(raw_path or "").strip())
        if candidate.is_absolute():
            return candidate
        return self._base_dir / candidate

    @staticmethod
    def _paths_ready(model_info: dict[str, Path]) -> bool:
        return model_info["model"].exists() and model_info["config"].exists()

    def _resolve_piper_paths(self) -> dict[str, dict[str, Path]]:
        resolved: dict[str, dict[str, Path]] = {}
        for lang, model_info in self.piper_models.items():
            if not isinstance(model_info, dict):
                continue
            model_raw = str(model_info.get("model", "")).strip()
            config_raw = str(model_info.get("config", "")).strip()
            resolved[self._normalize_language(lang)] = {
                "model": self._resolve_project_path(model_raw) if model_raw else self._base_dir / "__missing_model__",
                "config": self._resolve_project_path(config_raw) if config_raw else self._base_dir / "__missing_config__",
            }
        return resolved

    def _detect_playback_backends(self) -> list[tuple[str, list[str]]]:
        detected: list[tuple[str, list[str]]] = []

        pw_play = shutil.which("pw-play")
        if pw_play:
            detected.append(("pw-play", [pw_play]))

        paplay = shutil.which("paplay")
        if paplay:
            detected.append(("paplay", [paplay]))

        aplay = shutil.which("aplay")
        if aplay:
            detected.append(("aplay", [aplay]))

        ffplay = shutil.which("ffplay")
        if ffplay:
            detected.append(("ffplay", [ffplay, "-autoexit", "-nodisp"]))

        return detected

    def _piper_model_ready(self, lang: str) -> bool:
        normalized = self._normalize_language(lang)
        cached = self._piper_ready_cache.get(normalized)
        if cached is not None:
            return cached

        model_info = self._resolved_piper_paths.get(normalized)
        ready = bool(model_info and self._paths_ready(model_info))
        self._piper_ready_cache[normalized] = ready
        return ready

    # ------------------------------------------------------------------
    # Text normalization
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Cache / synthesis queue
    # ------------------------------------------------------------------

    @classmethod
    def _cache_key(cls, text: str, lang: str) -> str:
        digest = hashlib.sha256(f"{cls._CACHE_VERSION}|{lang}|{text}".encode("utf-8")).hexdigest()
        return digest[:24]

    def _cached_wav_path(self, text: str, lang: str) -> Path:
        return self._tts_cache_dir / f"{lang}_{self._cache_key(text, lang)}.wav"

    def _prefetch_key(self, text: str, lang: str) -> tuple[str, str]:
        return lang, self._cache_key(text, lang)

    def _start_synthesis_worker(self) -> None:
        if self._synthesis_worker_started:
            return

        self._synthesis_worker = threading.Thread(
            target=self._synthesis_worker_loop,
            name="tts-synthesis-worker",
            daemon=True,
        )
        self._synthesis_worker.start()
        self._synthesis_worker_started = True

    def _enqueue_synthesis(self, text: str, lang: str, *, priority: int) -> _SynthesisJob:
        key = self._prefetch_key(text, lang)
        cache_path = self._cached_wav_path(text, lang)

        if cache_path.exists():
            job = _SynthesisJob(
                key=key,
                text=text,
                lang=lang,
                cache_path=cache_path,
                priority=priority,
            )
            job.success = True
            job.event.set()
            return job

        with self._prefetch_lock:
            existing = self._pending_jobs.get(key)
            if existing is not None and not existing.event.is_set():
                if priority < existing.priority:
                    existing.priority = priority
                    existing.version += 1
                    self._job_queue.put((existing.priority, self._job_sequence, existing.version, existing))
                    self._job_sequence += 1
                return existing

            job = _SynthesisJob(
                key=key,
                text=text,
                lang=lang,
                cache_path=cache_path,
                priority=priority,
            )
            self._pending_jobs[key] = job
            self._job_queue.put((job.priority, self._job_sequence, job.version, job))
            self._job_sequence += 1
            return job

    def _wait_for_job(self, job: _SynthesisJob, *, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + max(0.1, float(timeout_seconds))
        while time.monotonic() < deadline:
            if self._stop_requested.is_set():
                return False
            if job.event.wait(self._job_wait_poll_seconds):
                return bool(job.success and job.cache_path.exists())
        return bool(job.success and job.cache_path.exists())

    def _synthesis_worker_loop(self) -> None:
        while True:
            try:
                priority, _, version, job = self._job_queue.get()
            except Exception:
                continue

            if job is None:
                return

            if job.event.is_set():
                continue

            if priority != job.priority or version != job.version:
                continue

            if job.cache_path.exists():
                job.success = True
                job.event.set()
                with self._prefetch_lock:
                    if self._pending_jobs.get(job.key) is job:
                        self._pending_jobs.pop(job.key, None)
                continue

            success = self._synthesize_piper_to_wav(job.text, job.lang, job.cache_path)
            job.success = success
            if not success:
                job.error = f"Piper synthesis failed for lang={job.lang}"
                try:
                    if job.cache_path.exists():
                        job.cache_path.unlink()
                except OSError:
                    pass

            job.event.set()

            with self._prefetch_lock:
                if self._pending_jobs.get(job.key) is job:
                    self._pending_jobs.pop(job.key, None)

    def _normalize_prefetch_request(
        self,
        prepare_next: tuple[str, str] | None,
    ) -> tuple[str, str] | None:
        if not prepare_next:
            return None

        next_text, next_language = prepare_next
        normalized_language = self._resolve_language(next_language)
        normalized_text = self._normalize_text_for_tts(
            self._normalize_text_for_log(next_text),
            normalized_language,
        )
        if not normalized_text:
            return None

        return normalized_text, normalized_language

    def _start_prefetch(self, text: str, lang: str) -> None:
        if not self.enabled:
            return
        if self.preferred_engine != "piper":
            return
        if not text:
            return
        if not self._piper_model_ready(lang):
            return

        self._enqueue_synthesis(text, lang, priority=self._PRIORITY_NEXT)

    def _warm_common_cache(self) -> None:
        try:
            time.sleep(self._cache_warmup_delay_seconds)
            for lang, phrases in self._common_cache_phrases.items():
                for phrase in phrases:
                    tts_text = self._normalize_text_for_tts(phrase, lang)
                    if not tts_text:
                        continue
                    self._enqueue_synthesis(tts_text, lang, priority=self._PRIORITY_WARMUP)
        except Exception as error:
            append_log(f"TTS cache warmup skipped: {error}")

    def _start_cache_warmup(self) -> None:
        if not self.enabled or self.preferred_engine != "piper":
            return

        self._cache_warmup_thread = threading.Thread(
            target=self._warm_common_cache,
            name="tts-cache-warmup",
            daemon=True,
        )
        self._cache_warmup_thread.start()

    # ------------------------------------------------------------------
    # Playback / synthesis
    # ------------------------------------------------------------------

    def _build_piper_command(self, model_path: Path, config_path: Path, wav_path: Path) -> list[str] | None:
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

    def _synthesize_piper_to_wav(self, text: str, lang: str, wav_path: Path) -> bool:
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

    def _play_wav(self, wav_path: Path) -> bool:
        if not wav_path.exists():
            return False

        playback_started_at = time.monotonic()

        backends = list(self._playback_backends)
        if self._last_good_playback_backend:
            backends.sort(key=lambda item: 0 if item[0] == self._last_good_playback_backend else 1)

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
            current_job = self._enqueue_synthesis(text, lang, priority=self._PRIORITY_CURRENT)
            ready = self._wait_for_job(current_job, timeout_seconds=self._current_job_wait_seconds)
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

        current_job = self._enqueue_synthesis(text, lang, priority=self._PRIORITY_CURRENT)
        ready = self._wait_for_job(current_job, timeout_seconds=self._current_job_wait_seconds)
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

    # ------------------------------------------------------------------
    # Public speech API
    # ------------------------------------------------------------------

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
        append_log(f"Assistant said [{lang}]: {cleaned_text}")

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

                append_log(f"Voice output failed for language '{lang}' on all available engines.")
                return False
        finally:
            if self.audio_coordinator is not None:
                self.audio_coordinator.end_assistant_output(coordinator_token)


__all__ = ["TTSPipeline"]