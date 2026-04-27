from __future__ import annotations

import time
from collections.abc import Callable
from threading import Event, RLock, Thread

from modules.devices.audio.realtime.audio_bus import AudioBus
from modules.devices.audio.realtime.audio_device_config import AudioDeviceConfig
from modules.devices.audio.realtime.audio_frame import AudioFrame

PcmReader = Callable[[], bytes | None]


class AudioCaptureWorker:
    """Background PCM capture worker that publishes frames to AudioBus.

    The worker is intentionally source-injected. This keeps Stage 1 safe:
    no sounddevice/PyAudio ownership changes, no runtime microphone changes,
    and no risk to the current wake/STT path.
    """

    def __init__(
        self,
        *,
        audio_bus: AudioBus,
        config: AudioDeviceConfig,
        pcm_reader: PcmReader,
        empty_read_sleep_seconds: float = 0.005,
        thread_name: str = "nexa-realtime-audio-capture",
    ) -> None:
        if empty_read_sleep_seconds < 0:
            raise ValueError("empty_read_sleep_seconds must not be negative")
        if not thread_name.strip():
            raise ValueError("thread_name must not be empty")

        self._audio_bus = audio_bus
        self._config = config
        self._pcm_reader = pcm_reader
        self._empty_read_sleep_seconds = empty_read_sleep_seconds
        self._thread_name = thread_name
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._lock = RLock()
        self._published_frames = 0

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    @property
    def published_frames(self) -> int:
        with self._lock:
            return self._published_frames

    def start(self) -> None:
        with self._lock:
            if self.is_running:
                return

            self._stop_event.clear()
            self._thread = Thread(
                target=self._run,
                name=self._thread_name,
                daemon=True,
            )
            self._thread.start()

    def stop(self, *, timeout_seconds: float = 1.0) -> None:
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must not be negative")

        with self._lock:
            thread = self._thread
            self._stop_event.set()

        if thread is not None:
            thread.join(timeout=timeout_seconds)

        with self._lock:
            if self._thread is thread and not thread.is_alive():
                self._thread = None

    def run_once(self) -> AudioFrame | None:
        pcm = self._pcm_reader()
        if pcm is None:
            return None

        if not pcm:
            return None

        frame = self._audio_bus.publish_pcm(
            pcm,
            timestamp_monotonic=time.monotonic(),
            source=self._config.source_name,
        )

        with self._lock:
            self._published_frames += 1

        return frame

    def _run(self) -> None:
        while not self._stop_event.is_set():
            frame = self.run_once()
            if frame is None and self._empty_read_sleep_seconds:
                time.sleep(self._empty_read_sleep_seconds)