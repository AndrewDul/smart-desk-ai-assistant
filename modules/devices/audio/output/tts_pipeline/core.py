from __future__ import annotations

import queue
import shutil
import subprocess
import sys
import threading
from typing import TYPE_CHECKING

from modules.system.utils import BASE_DIR, CACHE_DIR, append_log

from .cache_queue_mixin import TTSPipelineCacheQueueMixin
from .control_mixin import TTSPipelineControlMixin
from .normalization_mixin import TTSPipelineNormalizationMixin
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
        self._stop_requested = threading.Event()

        self._active_processes: list[subprocess.Popen] = []
        self.audio_coordinator: AssistantAudioCoordinator | None = None

        self._playback_backends: list[tuple[str, list[str]]] = (
            self._detect_playback_backends()
        )
        self._last_good_playback_backend: str | None = None

        self._synthesis_timeout_seconds = 28.0
        self._playback_timeout_seconds = 32.0
        self._job_wait_poll_seconds = 0.03
        self._cache_warmup_delay_seconds = 0.8
        self._current_job_wait_seconds = 20.0
        self._early_next_prefetch_max_chars = 64

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

        if self.enabled and self.preferred_engine == "piper":
            self._start_synthesis_worker()
            self._start_cache_warmup()


__all__ = ["TTSPipeline"]