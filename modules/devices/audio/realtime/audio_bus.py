from __future__ import annotations

import time
from threading import RLock

from modules.devices.audio.realtime.audio_frame import AudioFrame
from modules.devices.audio.realtime.ring_buffer import AudioRingBuffer


class AudioBusSubscription:
    """Independent read cursor for realtime audio consumers."""

    def __init__(self, *, audio_bus: AudioBus, name: str, next_sequence: int) -> None:
        if not name.strip():
            raise ValueError("subscription name must not be empty")
        if next_sequence < 0:
            raise ValueError("next_sequence must not be negative")

        self._audio_bus = audio_bus
        self._name = name
        self._next_sequence = next_sequence
        self._lock = RLock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def next_sequence(self) -> int:
        with self._lock:
            return self._next_sequence

    def read_available(self, *, max_frames: int | None = None) -> list[AudioFrame]:
        if max_frames is not None and max_frames <= 0:
            raise ValueError("max_frames must be greater than zero")

        with self._lock:
            frames = self._audio_bus.frames_since(self._next_sequence)
            if max_frames is not None:
                frames = frames[:max_frames]

            if frames:
                self._next_sequence = frames[-1].sequence + 1

            return frames

    def read_pcm(self, *, max_frames: int | None = None) -> bytes:
        frames = self.read_available(max_frames=max_frames)
        return b"".join(frame.pcm for frame in frames)


class AudioBus:
    """Thread-safe realtime PCM audio bus for Voice Engine v2."""

    def __init__(
        self,
        *,
        max_duration_seconds: float,
        sample_rate: int,
        channels: int,
        sample_width_bytes: int = 2,
        source_name: str = "realtime_audio_bus",
    ) -> None:
        self._ring_buffer = AudioRingBuffer(
            max_duration_seconds=max_duration_seconds,
            sample_rate=sample_rate,
            channels=channels,
            sample_width_bytes=sample_width_bytes,
        )
        self._sample_rate = sample_rate
        self._channels = channels
        self._sample_width_bytes = sample_width_bytes
        self._source_name = source_name
        self._next_sequence = 0
        self._lock = RLock()

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    @property
    def channels(self) -> int:
        return self._channels

    @property
    def sample_width_bytes(self) -> int:
        return self._sample_width_bytes

    @property
    def latest_sequence(self) -> int | None:
        return self._ring_buffer.latest_sequence

    @property
    def duration_seconds(self) -> float:
        return self._ring_buffer.duration_seconds

    @property
    def frame_count(self) -> int:
        return self._ring_buffer.frame_count

    def publish(self, frame: AudioFrame) -> AudioFrame:
        self._validate_frame_format(frame)

        with self._lock:
            sequenced_frame = frame.with_sequence(self._next_sequence)
            self._next_sequence += 1
            self._ring_buffer.append(sequenced_frame)
            return sequenced_frame

    def publish_pcm(
        self,
        pcm: bytes,
        *,
        timestamp_monotonic: float | None = None,
        source: str | None = None,
    ) -> AudioFrame:
        frame = AudioFrame(
            pcm=pcm,
            sample_rate=self._sample_rate,
            channels=self._channels,
            sample_width_bytes=self._sample_width_bytes,
            timestamp_monotonic=(
                time.monotonic()
                if timestamp_monotonic is None
                else timestamp_monotonic
            ),
            sequence=0,
            source=source or self._source_name,
        )
        return self.publish(frame)

    def create_subscription(
        self,
        name: str,
        *,
        start_at_latest: bool = True,
    ) -> AudioBusSubscription:
        with self._lock:
            if start_at_latest:
                latest = self._ring_buffer.latest_sequence
                next_sequence = 0 if latest is None else latest + 1
            else:
                oldest = self._ring_buffer.oldest_sequence
                next_sequence = 0 if oldest is None else oldest

            return AudioBusSubscription(
                audio_bus=self,
                name=name,
                next_sequence=next_sequence,
            )

    def frames_since(self, sequence: int) -> list[AudioFrame]:
        return self._ring_buffer.frames_since(sequence)

    def snapshot_frames(self) -> list[AudioFrame]:
        return self._ring_buffer.snapshot_frames()

    def snapshot_pcm(self, *, max_duration_seconds: float | None = None) -> bytes:
        return self._ring_buffer.snapshot_pcm(
            max_duration_seconds=max_duration_seconds
        )

    def clear(self) -> None:
        with self._lock:
            self._ring_buffer.clear()

    def _validate_frame_format(self, frame: AudioFrame) -> None:
        if frame.sample_rate != self._sample_rate:
            raise ValueError("frame sample_rate does not match audio bus")
        if frame.channels != self._channels:
            raise ValueError("frame channels does not match audio bus")
        if frame.sample_width_bytes != self._sample_width_bytes:
            raise ValueError("frame sample_width_bytes does not match audio bus")