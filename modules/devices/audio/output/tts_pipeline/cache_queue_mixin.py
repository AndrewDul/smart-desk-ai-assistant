from __future__ import annotations

import hashlib
import threading
import time

from modules.system.utils import append_log

from .job import _SynthesisJob


class TTSPipelineCacheQueueMixin:
    """
    Helpers for cache keys, synthesis queue handling, and cache warmup.

    Queue policy:
    - deduplicate identical requests
    - allow priority promotion for the same pending job
    - clean up stale finished/failed jobs
    - keep current speech responsive while still supporting background prefetch
    """

    @classmethod
    def _cache_key(cls, text: str, lang: str) -> str:
        digest = hashlib.sha256(
            f"{cls._CACHE_VERSION}|{lang}|{text}".encode("utf-8")
        ).hexdigest()
        return digest[:24]

    def _cached_wav_path(self, text: str, lang: str):
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
        append_log("TTS synthesis worker started.")

    def _enqueue_synthesis(self, text: str, lang: str, *, priority: int) -> _SynthesisJob:
        key = self._prefetch_key(text, lang)
        cache_path = self._cached_wav_path(text, lang)
        normalized_priority = int(priority)

        if cache_path.exists():
            job = _SynthesisJob(
                key=key,
                text=text,
                lang=lang,
                cache_path=cache_path,
                priority=normalized_priority,
            )
            job.success = True
            job.event.set()
            return job

        with self._prefetch_lock:
            existing = self._pending_jobs.get(key)

            if existing is not None:
                if existing.event.is_set():
                    if existing.success and existing.cache_path.exists():
                        return existing
                    self._pending_jobs.pop(key, None)
                    existing = None

            if existing is not None:
                if normalized_priority < existing.priority:
                    existing.priority = normalized_priority
                    existing.version += 1
                    self._job_queue.put(
                        (
                            existing.priority,
                            self._job_sequence,
                            existing.version,
                            existing,
                        )
                    )
                    self._job_sequence += 1
                    append_log(
                        "TTS job priority promoted: "
                        f"lang={lang}, chars={len(text)}, priority={normalized_priority}"
                    )
                return existing

            job = _SynthesisJob(
                key=key,
                text=text,
                lang=lang,
                cache_path=cache_path,
                priority=normalized_priority,
            )
            self._pending_jobs[key] = job
            self._job_queue.put((job.priority, self._job_sequence, job.version, job))
            self._job_sequence += 1
            return job

    def _wait_for_job(self, job: _SynthesisJob, *, timeout_seconds: float) -> bool:
        if job.event.is_set():
            return bool(job.success and job.cache_path.exists())

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

            if self._stop_requested.is_set():
                continue

            if job.event.is_set():
                self._finalize_job_cleanup(job)
                continue

            if priority != job.priority or version != job.version:
                continue

            if job.cache_path.exists():
                job.success = True
                job.event.set()
                self._finalize_job_cleanup(job)
                continue

            started_at = time.monotonic()
            success = self._synthesize_piper_to_wav(job.text, job.lang, job.cache_path)
            job.success = bool(success)

            if not success:
                job.error = f"Piper synthesis failed for lang={job.lang}"
                try:
                    if job.cache_path.exists():
                        job.cache_path.unlink()
                except OSError:
                    pass
            else:
                append_log(
                    "TTS queued synthesis finished: "
                    f"lang={job.lang}, chars={len(job.text)}, "
                    f"elapsed={time.monotonic() - started_at:.3f}s, "
                    f"priority={job.priority}"
                )

            job.event.set()
            self._finalize_job_cleanup(job)

    def _finalize_job_cleanup(self, job: _SynthesisJob) -> None:
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

        cache_path = self._cached_wav_path(text, lang)
        if cache_path.exists():
            return

        pending = self._get_pending_job(text=text, lang=lang)
        if pending is not None and not pending.event.is_set():
            return

        self._enqueue_synthesis(text, lang, priority=self._PRIORITY_NEXT)

    def _warm_common_cache(self) -> None:
        try:
            time.sleep(self._cache_warmup_delay_seconds)

            for lang, phrases in self._common_cache_phrases.items():
                if self._stop_requested.is_set():
                    return

                if not self._piper_model_ready(lang):
                    continue

                for phrase in phrases:
                    if self._stop_requested.is_set():
                        return

                    tts_text = self._normalize_text_for_tts(phrase, lang)
                    if not tts_text:
                        continue

                    cache_path = self._cached_wav_path(tts_text, lang)
                    if cache_path.exists():
                        continue

                    self._enqueue_synthesis(
                        tts_text,
                        lang,
                        priority=self._PRIORITY_WARMUP,
                    )

            append_log("TTS cache warmup queued.")
        except Exception as error:
            append_log(f"TTS cache warmup skipped: {error}")

    def _start_cache_warmup(self) -> None:
        if not self.enabled or self.preferred_engine != "piper":
            return

        if self._cache_warmup_thread is not None and self._cache_warmup_thread.is_alive():
            return

        self._cache_warmup_thread = threading.Thread(
            target=self._warm_common_cache,
            name="tts-cache-warmup",
            daemon=True,
        )
        self._cache_warmup_thread.start()


__all__ = ["TTSPipelineCacheQueueMixin"]