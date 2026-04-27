from __future__ import annotations

from collections import deque
from threading import RLock

from modules.devices.audio.realtime.audio_frame import AudioFrame


class AudioRingBuffer:
    """Thread-safe audio frame ring buffer with duration-based retention."""

    def __init__(
        self,
        *,
        max_duration_seconds: float,
        sample_rate: int,
        channels: int,
        sample_width_bytes: int = 2,
    ) -> None:
        if max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be greater than zero")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be greater than zero")
        if channels <= 0:
            raise ValueError("channels must be greater than zero")
        if sample_width_bytes <= 0:
            raise ValueError("sample_width_bytes must be greater than zero")

        self._max_sample_count = int(max_duration_seconds * sample_rate)
        self._sample_rate = sample_rate
        self._channels = channels
        self._sample_width_bytes = sample_width_bytes
        self._frames: deque[AudioFrame] = deque()
        self._sample_count = 0
        self._byte_count = 0
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
    def frame_count(self) -> int:
        with self._lock:
            return len(self._frames)

    @property
    def byte_count(self) -> int:
        with self._lock:
            return self._byte_count

    @property
    def sample_count(self) -> int:
        with self._lock:
            return self._sample_count

    @property
    def duration_seconds(self) -> float:
        with self._lock:
            return self._sample_count / float(self._sample_rate)

    @property
    def oldest_sequence(self) -> int | None:
        with self._lock:
            if not self._frames:
                return None
            return self._frames[0].sequence

    @property
    def latest_sequence(self) -> int | None:
        with self._lock:
            if not self._frames:
                return None
            return self._frames[-1].sequence

    def append(self, frame: AudioFrame) -> None:
        self._validate_frame_format(frame)

        with self._lock:
            self._frames.append(frame)
            self._sample_count += frame.sample_count
            self._byte_count += frame.byte_count
            self._trim_locked()

    def clear(self) -> None:
        with self._lock:
            self._frames.clear()
            self._sample_count = 0
            self._byte_count = 0

    def snapshot_frames(self) -> list[AudioFrame]:
        with self._lock:
            return list(self._frames)

    def frames_since(self, sequence: int) -> list[AudioFrame]:
        if sequence < 0:
            raise ValueError("sequence must not be negative")

        with self._lock:
            return [frame for frame in self._frames if frame.sequence >= sequence]

    def snapshot_pcm(self, *, max_duration_seconds: float | None = None) -> bytes:
        with self._lock:
            frames = self._select_frames_for_snapshot_locked(max_duration_seconds)
            return b"".join(frame.pcm for frame in frames)

    def _validate_frame_format(self, frame: AudioFrame) -> None:
        if frame.sample_rate != self._sample_rate:
            raise ValueError("frame sample_rate does not match ring buffer")
        if frame.channels != self._channels:
            raise ValueError("frame channels does not match ring buffer")
        if frame.sample_width_bytes != self._sample_width_bytes:
            raise ValueError("frame sample_width_bytes does not match ring buffer")

    def _trim_locked(self) -> None:
        while (
            len(self._frames) > 1
            and self._sample_count > self._max_sample_count
        ):
            removed = self._frames.popleft()
            self._sample_count -= removed.sample_count
            self._byte_count -= removed.byte_count

    def _select_frames_for_snapshot_locked(
        self,
        max_duration_seconds: float | None,
    ) -> list[AudioFrame]:
        if max_duration_seconds is None:
            return list(self._frames)

        if max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be greater than zero")

        max_samples = int(max_duration_seconds * self._sample_rate)
        selected_reversed: list[AudioFrame] = []
        selected_samples = 0

        for frame in reversed(self._frames):
            next_sample_count = selected_samples + frame.sample_count
            if selected_reversed and next_sample_count > max_samples:
                break
            selected_reversed.append(frame)
            selected_samples = next_sample_count

        return list(reversed(selected_reversed))