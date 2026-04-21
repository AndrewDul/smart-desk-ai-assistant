from __future__ import annotations

import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from modules.system.utils import BASE_DIR, CACHE_DIR, append_log

from .cache_queue_mixin import TTSPipelineCacheQueueMixin
from .control_mixin import TTSPipelineControlMixin
from .normalization_mixin import TTSPipelineNormalizationMixin
from .wav_playback_mixin import TTSPipelineWavPlaybackMixin
from .process_mixin import TTSPipelineProcessMixin
from .resolution_mixin import TTSPipelineResolutionMixin
from .speech_api_mixin import TTSPipelineSpeechApiMixin
from .synthesis_mixin import TTSPipelineSynthesisMixin

if TYPE_CHECKING:
    from modules.devices.audio.coordination import AssistantAudioCoordinator

    from .job import _SynthesisJob


class TTSPipeline(
    TTSPipelineControlMixin,
    TTSPipelineProcessMixin,
    TTSPipelineResolutionMixin,
    TTSPipelineNormalizationMixin,
    TTSPipelineWavPlaybackMixin,
    TTSPipelineCacheQueueMixin,
    TTSPipelineSynthesisMixin,
    TTSPipelineSpeechApiMixin,
):
    """
    Low-latency local TTS pipeline for NeXa.

    Design goals:
    - keep speech stable on Raspberry Pi
    - avoid spawning multiple concurrent Piper synth jobs that fight for CPU
    - prefetch likely next chunks in the background
    - keep interruption responsive
    - fall back to eSpeak when Piper is unavailable
    - reduce first-audio latency for short live replies
    """

    _CACHE_VERSION = "tts-v8-direct-current-low-latency"

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
        process_poll_seconds: float = 0.02,
        playback_poll_seconds: float = 0.005,
        preferred_playback_backend: str = "",
    ) -> None:
        self.enabled = bool(enabled)
        self.preferred_engine = (
            str(preferred_engine or "piper").strip().lower() or "piper"
        )
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
        self._output_stream_lock = threading.Lock()
        self._stop_requested = threading.Event()

        self._active_processes: list[subprocess.Popen] = []
        self._active_output_stream = None
        self._last_process_results: dict[str, dict[str, object]] = {}

        self.audio_coordinator: AssistantAudioCoordinator | None = None

        self.runtime_python_path = str(sys.executable or "")
        project_venv_python = self._base_dir / ".venv" / "bin" / "python"
        self.project_venv_python_path = (
            str(project_venv_python)
            if project_venv_python.exists()
            else ""
        )
        self.piper_python_runner_path: str | None = None
        self._resolved_piper_binary_runner: str | None = None
        self._resolved_piper_binary_runner_checked = False
        self._resolved_piper_python_runner: str | None = None
        self._resolved_piper_python_runner_checked = False

        self._playback_backends: list[tuple[str, list[str]]] = (
            self._detect_playback_backends()
        )
        self._preferred_playback_backend = str(preferred_playback_backend or "").strip()
        self._last_good_playback_backend: str | None = None
        self._sounddevice_playback_ready: bool | None = None

        # Timeouts and queue timing tuned for fast short replies on Raspberry Pi.
        self._synthesis_timeout_seconds = 18.0
        self._playback_timeout_seconds = 24.0
        self._process_poll_seconds = max(0.001, float(process_poll_seconds))
        self._playback_poll_seconds = max(0.001, float(playback_poll_seconds))
        self._job_wait_poll_seconds = 0.015
        self._cache_warmup_delay_seconds = 0.45
        self._current_job_wait_seconds = 6.5

        # If the current reply is short enough, synthesize it directly instead
        # of waiting behind the background queue.
        self._direct_current_synthesis_max_chars = 115
        self._action_fast_direct_current_synthesis_max_chars = 220
        # Output hold tuning:
        # - interrupted playback should release input almost immediately
        # - short replies should not keep the mic blocked too long
        self._interrupted_output_hold_seconds = 0.10
        self._short_response_output_hold_seconds = 0.18
        self._short_response_output_hold_max_chars = 48

        # Start preparing the likely next chunk early for short current chunks.
        self._early_next_prefetch_max_chars = 72

        self._job_queue: queue.PriorityQueue[
            tuple[int, int, int, _SynthesisJob | None]
        ] = queue.PriorityQueue()
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
        append_log(
            "TTS latency profile: "
            f"synthesis_timeout={self._synthesis_timeout_seconds:.1f}s, "
            f"playback_timeout={self._playback_timeout_seconds:.1f}s, "
            f"job_wait_poll={self._job_wait_poll_seconds:.3f}s, "
            f"process_poll={self._process_poll_seconds:.3f}s, "
            f"playback_poll={self._playback_poll_seconds:.3f}s, "
            f"preferred_playback_backend={self._preferred_playback_backend or '-'}, "
            f"current_job_wait={self._current_job_wait_seconds:.1f}s, "
            f"direct_current_chars={self._direct_current_synthesis_max_chars}, "
            f"action_fast_direct_current_chars={self._action_fast_direct_current_synthesis_max_chars}, "
            f"early_next_prefetch_chars={self._early_next_prefetch_max_chars}"
        )
        append_log(
            "TTS python paths: "
            f"runtime_python={self.runtime_python_path or '-'}, "
            f"project_venv_python={self.project_venv_python_path or '-'}"
        )

        if self.enabled and self.preferred_engine == "piper":
            self._start_synthesis_worker()
            self._start_cache_warmup()


__all__ = ["TTSPipeline"]