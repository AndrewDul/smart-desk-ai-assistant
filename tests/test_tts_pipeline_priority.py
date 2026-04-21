from __future__ import annotations

import io
import queue
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from modules.devices.audio.output.tts_pipeline.cache_queue_mixin import TTSPipelineCacheQueueMixin
from modules.devices.audio.output.tts_pipeline.speech_api_mixin import TTSPipelineSpeechApiMixin
from modules.devices.audio.output.tts_pipeline.synthesis_mixin import TTSPipelineSynthesisMixin
from modules.devices.audio.output.tts_pipeline.wav_playback_mixin import TTSPipelineWavPlaybackMixin


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
        self._action_fast_direct_current_synthesis_max_chars = 220
        self.waited_priority = None
        self.waited_timeout_seconds = None
        self.synthesized_paths: list[Path] = []

    def _piper_model_ready(self, lang: str) -> bool:
        return True

    def _wait_for_job(self, job, *, timeout_seconds: float) -> bool:
        self.waited_priority = int(job.priority)
        self.waited_timeout_seconds = float(timeout_seconds)
        return False

    def _synthesize_piper_to_wav(self, text: str, lang: str, wav_path) -> bool:
        del text, lang
        wav_path = Path(wav_path)
        wav_path.write_bytes(b"RIFFtest")
        self.synthesized_paths.append(wav_path)
        return True


class _SpeechApiProbe(TTSPipelineSpeechApiMixin):
    def __init__(self, *, console_echo_enabled: bool = False) -> None:
        self.enabled = True
        self.preferred_engine = "piper"
        self.audio_coordinator = None
        self._speak_lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._console_echo_enabled = bool(console_echo_enabled)

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

    def _speak_with_piper(self, text: str, lang: str, *, prepare_next=None, latency_profile=None) -> bool:
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


class _PlaybackProbe(TTSPipelineWavPlaybackMixin, TTSPipelineSynthesisMixin):
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


class _PreferredPlaybackProbe(TTSPipelineWavPlaybackMixin, TTSPipelineSynthesisMixin):
    def __init__(self, *, preferred_playback_backend: str = "") -> None:
        self.enabled = True
        self.preferred_engine = "piper"
        self._playback_backends = [
            ("pw-play", ["pw-play"]),
            ("aplay", ["aplay", "-q"]),
            ("ffplay", ["ffplay", "-autoexit", "-nodisp"]),
        ]
        self._preferred_playback_backend = str(preferred_playback_backend)
        self._last_good_playback_backend = None
        self._playback_timeout_seconds = 24.0
        self._playback_poll_seconds = 0.005
        self.playback_calls: list[dict[str, object]] = []
        self._output_stream_lock = threading.Lock()
        self._active_output_stream = None
        self._sounddevice_playback_ready = False

    def _run_process_interruptibly(self, args, **kwargs) -> bool:
        self.playback_calls.append({"args": list(args), **dict(kwargs)})
        return True


class _RunnerResolutionProbe(TTSPipelineSynthesisMixin):
    def __init__(self) -> None:
        self.piper_path = ""
        self.python_path = "/fake/python"
        self.project_venv_python_path = ""
        self.runtime_python_path = ""
        self.piper_python_runner_path = "/fake/python"
        self._resolved_piper_binary_runner = None
        self._resolved_piper_binary_runner_checked = False
        self._resolved_piper_python_runner = None
        self._resolved_piper_python_runner_checked = False
        self.python_probe_calls: list[str] = []

    def _python_has_piper_module(self, python_path: str) -> bool:
        self.python_probe_calls.append(str(python_path))
        return str(python_path) == "/fake/python"

class _PiperSynthesisProbe(TTSPipelineSynthesisMixin):
    def __init__(self, temp_dir: Path, *, success_on_attempt: int = 1) -> None:
        self._resolved_piper_paths = {
            "en": {
                "model": temp_dir / "model.onnx",
                "config": temp_dir / "model.onnx.json",
            }
        }
        self._resolved_piper_paths["en"]["model"].write_text("model")
        self._resolved_piper_paths["en"]["config"].write_text("config")
        self._synthesis_timeout_seconds = 18.0
        self._stop_requested = threading.Event()
        self._piper_failure_diagnostic_retry_enabled = True
        self.run_calls: list[dict[str, object]] = []
        self.success_on_attempt = int(success_on_attempt)

    def _normalize_language(self, language: str | None) -> str:
        return str(language or "en").strip().lower() or "en"

    def _build_piper_command(self, model_path, config_path, wav_path, text: str):
        del model_path, config_path, text
        return ["fake-piper", str(wav_path)]

    def _format_process_command(self, args: list[str]) -> str:
        return " ".join(str(item) for item in args)

    def _run_process_interruptibly(self, args, **kwargs) -> bool:
        attempt = len(self.run_calls) + 1
        wav_path = Path(args[-1])
        self.run_calls.append({"args": list(args), **dict(kwargs)})
        if attempt >= self.success_on_attempt:
            wav_path.write_bytes(b"RIFFtest")
            return True
        return False

    def _get_last_process_result(self, source: str) -> dict[str, object]:
        del source
        return {}

class TTSPipelinePriorityTests(unittest.TestCase):
    def test_current_path_promotes_matching_pending_prefetch_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            probe = _PriorityProbe(Path(temp_dir))
            existing_job = probe._enqueue_synthesis("Timer started.", "en", priority=probe._PRIORITY_NEXT)

            ready, source, ready_path = probe._ensure_current_wav_ready(
                text="Timer started.",
                lang="en",
                cache_path=probe._cached_wav_path("Timer started.", "en"),
                cache_hit=False,
            )

            self.assertFalse(ready)
            self.assertEqual(source, "pending_job_promoted")
            self.assertEqual(ready_path, probe._cached_wav_path("Timer started.", "en"))
            self.assertEqual(existing_job.priority, probe._PRIORITY_CURRENT)
            self.assertEqual(probe.waited_priority, probe._PRIORITY_CURRENT)

    def test_action_fast_bypasses_low_priority_pending_job_with_direct_current_temp_wav(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            probe = _PriorityProbe(Path(temp_dir))
            text = "Timer started successfully."
            existing_job = probe._enqueue_synthesis(text, "en", priority=probe._PRIORITY_NEXT)

            ready, source, ready_path = probe._ensure_current_wav_ready(
                text=text,
                lang="en",
                cache_path=probe._cached_wav_path(text, "en"),
                cache_hit=False,
                latency_profile="action_fast",
            )

            self.assertTrue(ready)
            self.assertEqual(source, "direct_current_bypass_pending")
            self.assertEqual(existing_job.priority, probe._PRIORITY_NEXT)
            self.assertIsNone(probe.waited_priority)
            self.assertTrue(ready_path.exists())
            self.assertTrue(str(ready_path.name).endswith(".direct-current.wav"))
            self.assertEqual(probe.synthesized_paths[-1], ready_path)

    def test_speak_does_not_require_audio_coordinator(self) -> None:
        probe = _SpeechApiProbe()

        spoken = probe.speak("Hello there.", language="en")

        self.assertTrue(spoken)
        report = probe.latest_speak_report()
        self.assertTrue(report["success"])
        self.assertEqual(report["engine"], "piper")
        self.assertFalse(report["interrupted"])


    def test_speak_does_not_echo_to_console_by_default(self) -> None:
        probe = _SpeechApiProbe()
        captured = io.StringIO()

        with redirect_stdout(captured):
            spoken = probe.speak("Hello there.", language="en")

        self.assertTrue(spoken)
        self.assertEqual(captured.getvalue(), "")

    def test_speak_can_echo_to_console_when_explicitly_enabled(self) -> None:
        probe = _SpeechApiProbe(console_echo_enabled=True)
        captured = io.StringIO()

        with redirect_stdout(captured):
            spoken = probe.speak("Hello there.", language="en")

        self.assertTrue(spoken)
        self.assertIn("Assistant> Hello there.", captured.getvalue())


    def test_playback_uses_fast_poll_and_skips_output_capture(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            probe = _PlaybackProbe()
            wav_path = Path(temp_dir) / "reply.wav"
            wav_path.write_bytes(b"RIFFtest")

            ok, started_at = probe._play_wav(wav_path)

            self.assertTrue(ok)
            self.assertGreater(started_at, 0.0)
            self.assertEqual(len(probe.playback_calls), 1)
            self.assertEqual(probe.playback_calls[0]["poll_sleep_seconds"], 0.005)
            self.assertFalse(probe.playback_calls[0]["capture_output"])
            self.assertEqual(probe._last_good_playback_backend, "aplay")

    def test_playback_prefers_configured_backend_before_first_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            probe = _PreferredPlaybackProbe(preferred_playback_backend="aplay")
            wav_path = Path(temp_dir) / "reply.wav"
            wav_path.write_bytes(b"RIFFtest")

            ok, started_at = probe._play_wav(wav_path)

            self.assertTrue(ok)
            self.assertGreater(started_at, 0.0)
            self.assertEqual(len(probe.playback_calls), 1)
            self.assertEqual(probe.playback_calls[0]["args"][:2], ["aplay", "-q"])
            self.assertEqual(probe._last_good_playback_backend, "aplay")

    def test_playback_uses_sounddevice_before_subprocess_backends(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            probe = _PlaybackProbe()
            probe._sounddevice_playback_ready = True
            probe._play_wav_with_sounddevice = lambda wav_path: (True, 123.0)
            wav_path = Path(temp_dir) / "reply.wav"
            wav_path.write_bytes(b"RIFFtest")

            ok, started_at = probe._play_wav(wav_path)

            self.assertTrue(ok)
            self.assertEqual(started_at, 123.0)
            self.assertEqual(probe.playback_calls, [])

    def test_action_fast_profile_expands_direct_current_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            probe = _PriorityProbe(Path(temp_dir))
            text = "x" * 160

            self.assertFalse(
                probe._should_direct_synthesize_current(
                    text=text,
                    lang="en",
                    latency_profile=None,
                )
            )
            self.assertTrue(
                probe._should_direct_synthesize_current(
                    text=text,
                    lang="en",
                    latency_profile="action_fast",
                )
            )


    def test_resolved_piper_python_runner_is_cached_after_first_lookup(self) -> None:
        probe = _RunnerResolutionProbe()

        first = probe._resolve_piper_python_runner()
        second = probe._resolve_piper_python_runner()

        self.assertEqual(first, "/fake/python")
        self.assertEqual(second, "/fake/python")
        self.assertEqual(probe.python_probe_calls, ["/fake/python"])


    def test_piper_synthesis_fast_path_skips_output_capture_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            probe = _PiperSynthesisProbe(Path(temp_dir), success_on_attempt=1)
            wav_path = Path(temp_dir) / "reply.wav"

            ok = probe._synthesize_piper_to_wav("Hello", "en", wav_path)

            self.assertTrue(ok)
            self.assertEqual(len(probe.run_calls), 1)
            self.assertFalse(probe.run_calls[0]["capture_output"])

    def test_piper_synthesis_retries_with_output_capture_for_diagnostics_after_fast_path_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            probe = _PiperSynthesisProbe(Path(temp_dir), success_on_attempt=2)
            wav_path = Path(temp_dir) / "reply.wav"

            ok = probe._synthesize_piper_to_wav("Hello", "en", wav_path)

            self.assertTrue(ok)
            self.assertEqual(len(probe.run_calls), 2)
            self.assertFalse(probe.run_calls[0]["capture_output"])
            self.assertTrue(probe.run_calls[1]["capture_output"])


if __name__ == "__main__":
    unittest.main()