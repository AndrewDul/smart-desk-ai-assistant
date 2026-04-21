from __future__ import annotations

import queue
import tempfile
import threading
import unittest
from pathlib import Path

from modules.devices.audio.output.tts_pipeline.cache_queue_mixin import TTSPipelineCacheQueueMixin
from modules.devices.audio.output.tts_pipeline.speech_api_mixin import TTSPipelineSpeechApiMixin
from modules.devices.audio.output.tts_pipeline.synthesis_mixin import TTSPipelineSynthesisMixin


class _PriorityProbe(TTSPipelineCacheQueueMixin, TTSPipelineSynthesisMixin):
    _CACHE_VERSION = "tts-priority-test"
    _PRIORITY_CURRENT = 0
    _PRIORITY_NEXT = 10

    def __init__(self, cache_dir: Path) -> None:
        self.enabled = True
        self.preferred_engine = "piper"
        self._tts_cache_dir = cache_dir
        self._tts_cache_dir.mkdir(parents=True, exist_ok=True)
        self._prefetch_lock = threading.Lock()
        self._pending_jobs = {}
        self._job_queue = queue.PriorityQueue()
        self._job_sequence = 0
        self._stop_requested = threading.Event()
        self._current_job_wait_seconds = 0.01
        self._direct_current_synthesis_max_chars = 115

    def _piper_model_ready(self, lang: str) -> bool:
        return True

    def _wait_for_job(self, job, *, timeout_seconds: float) -> bool:
        self.waited_priority = int(job.priority)
        self.waited_timeout_seconds = float(timeout_seconds)
        return False


class _SpeechApiProbe(TTSPipelineSpeechApiMixin):
    def __init__(self) -> None:
        self.enabled = True
        self.preferred_engine = "piper"
        self.audio_coordinator = None
        self._speak_lock = threading.Lock()
        self._stop_requested = threading.Event()

    def _normalize_text_for_log(self, text: str) -> str:
        return str(text or "").strip()

    def _resolve_language(self, language: str | None) -> str:
        return str(language or "en").strip() or "en"

    def _normalize_text_for_tts(self, text: str, lang: str) -> str:
        return str(text or "").strip()

    def _normalize_prefetch_request(self, prepare_next):
        return None

    def clear_stop_request(self) -> None:
        self._stop_requested.clear()

    def _speak_with_piper(self, text: str, lang: str, *, prepare_next=None) -> bool:
        self._playback_report = {
            "engine": "piper",
            "success": True,
            "first_audio_started_at_monotonic": 0.0,
            "first_audio_latency_ms": 0.0,
        }
        return True

    def _speak_with_espeak(self, text: str, lang: str) -> bool:
        return False

    def _consume_playback_report(self) -> dict[str, object]:
        report = dict(getattr(self, "_playback_report", {}) or {})
        self._playback_report = {}
        return report

class _PlaybackProbe(TTSPipelineSynthesisMixin):
    def __init__(self) -> None:
        self.enabled = True
        self.preferred_engine = "piper"
        self._playback_backends = [("aplay", ["aplay", "-q"])]
        self._last_good_playback_backend = None
        self._playback_timeout_seconds = 24.0
        self._playback_poll_seconds = 0.005
        self.playback_calls: list[dict[str, object]] = []

    def _run_process_interruptibly(self, args, **kwargs) -> bool:
        self.playback_calls.append({"args": list(args), **dict(kwargs)})
        return True

class TTSPipelinePriorityTests(unittest.TestCase):
    def test_current_path_promotes_matching_pending_prefetch_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            probe = _PriorityProbe(Path(temp_dir))
            existing_job = probe._enqueue_synthesis("Timer started.", "en", priority=probe._PRIORITY_NEXT)

            ready, source = probe._ensure_current_wav_ready(
                text="Timer started.",
                lang="en",
                cache_path=probe._cached_wav_path("Timer started.", "en"),
                cache_hit=False,
            )

            self.assertFalse(ready)
            self.assertEqual(source, "pending_job_promoted")
            self.assertEqual(existing_job.priority, probe._PRIORITY_CURRENT)
            self.assertEqual(probe.waited_priority, probe._PRIORITY_CURRENT)

    def test_speak_does_not_require_audio_coordinator(self) -> None:
        probe = _SpeechApiProbe()

        spoken = probe.speak("Hello there.", language="en")

        self.assertTrue(spoken)
        report = probe.latest_speak_report()
        self.assertTrue(report["success"])
        self.assertEqual(report["engine"], "piper")
        self.assertFalse(report["interrupted"])

    def test_playback_uses_fast_poll_and_skips_output_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            probe = _PlaybackProbe()
            wav_path = Path(temp_dir) / "reply.wav"
            wav_path.write_bytes(b"RIFFtest")

            ok = probe._play_wav(wav_path)

            self.assertTrue(ok)
            self.assertEqual(len(probe.playback_calls), 1)
            self.assertEqual(probe.playback_calls[0]["poll_sleep_seconds"], 0.005)
            self.assertFalse(probe.playback_calls[0]["capture_output"])
            self.assertEqual(probe._last_good_playback_backend, "aplay")


if __name__ == "__main__":
    unittest.main()