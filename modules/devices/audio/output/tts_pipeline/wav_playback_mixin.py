from __future__ import annotations

import contextlib
import threading
import time
import wave
from pathlib import Path

import numpy as np

from modules.system.utils import append_log


class TTSPipelineWavPlaybackMixin:
    """
    Low-latency WAV playback helpers.

    Primary goal:
    - avoid per-reply playback subprocess launch when sounddevice output is available
    - keep interruption responsive for short built-in replies
    - preserve subprocess fallback when direct playback is unavailable
    """

    def _ensure_output_stream_state(self) -> None:
        if not hasattr(self, "_output_stream_lock") or self._output_stream_lock is None:
            self._output_stream_lock = threading.Lock()
        if not hasattr(self, "_active_output_stream"):
            self._active_output_stream = None

    def _stop_requested_is_set(self) -> bool:
        stop_requested = getattr(self, "_stop_requested", None)
        if stop_requested is None:
            return False
        try:
            return bool(stop_requested.is_set())
        except Exception:
            return False

    def _sounddevice_playback_available(self) -> bool:
        cached = getattr(self, "_sounddevice_playback_ready", None)
        if isinstance(cached, bool):
            return cached

        try:
            import sounddevice as sd

            sd.query_devices(None, "output")
            ready = True
        except Exception:
            ready = False

        self._sounddevice_playback_ready = ready
        return ready

    def _stop_active_output_stream(self) -> None:
        self._ensure_output_stream_state()

        stream = None
        with self._output_stream_lock:
            stream = self._active_output_stream
            self._active_output_stream = None

        if stream is None:
            return

        try:
            stream.abort(ignore_errors=True)
        except Exception:
            pass

        try:
            stream.close(ignore_errors=True)
        except Exception:
            pass

    @staticmethod
    def _wav_numpy_dtype(sample_width: int):
        if sample_width == 1:
            return np.uint8
        if sample_width == 2:
            return np.int16
        if sample_width == 4:
            return np.int32
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")

    def _play_wav_with_sounddevice(self, wav_path: Path) -> tuple[bool, float]:
        import sounddevice as sd

        if not wav_path.exists():
            return False, 0.0

        self._ensure_output_stream_state()

        stream = None
        started_output_at = 0.0

        try:
            with wave.open(str(wav_path), "rb") as wav_file:
                channels = int(wav_file.getnchannels())
                sample_rate = int(wav_file.getframerate())
                sample_width = int(wav_file.getsampwidth())
                frame_count = int(wav_file.getnframes())
                raw_frames = wav_file.readframes(frame_count)

            if frame_count <= 0 or not raw_frames:
                append_log(f"Sounddevice playback skipped empty WAV: {wav_path}")
                return False, 0.0

            dtype = self._wav_numpy_dtype(sample_width)
            audio = np.frombuffer(raw_frames, dtype=dtype)
            if channels > 1:
                audio = audio.reshape(-1, channels)
            else:
                audio = audio.reshape(-1, 1)

            finished = False
            total_frames = int(audio.shape[0])
            frame_index = 0

            def _callback(outdata, frames, time_info, status):
                del time_info

                nonlocal started_output_at
                nonlocal finished
                nonlocal frame_index

                if status:
                    append_log(f"Sounddevice playback status: {status}")

                if self._stop_requested_is_set():
                    outdata.fill(0)
                    finished = True
                    raise sd.CallbackStop()

                if started_output_at <= 0.0:
                    started_output_at = time.monotonic()

                end_index = min(frame_index + frames, total_frames)
                chunk = audio[frame_index:end_index]
                chunk_frames = len(chunk)

                if chunk_frames > 0:
                    outdata[:chunk_frames] = chunk

                if chunk_frames < frames:
                    outdata[chunk_frames:].fill(0)
                    finished = True
                    raise sd.CallbackStop()

                frame_index = end_index
                if frame_index >= total_frames:
                    finished = True
                    raise sd.CallbackStop()

            stream = sd.OutputStream(
                samplerate=sample_rate,
                channels=channels,
                dtype=audio.dtype,
                blocksize=0,
                callback=_callback,
                finished_callback=None,
            )

            with self._output_stream_lock:
                self._active_output_stream = stream

            stream.start()
            if started_output_at <= 0.0:
                started_output_at = time.monotonic()

            while stream.active and not self._stop_requested_is_set():
                time.sleep(0.005)

            if self._stop_requested_is_set() and stream.active:
                try:
                    stream.abort(ignore_errors=True)
                except Exception:
                    pass

            success = bool(
                started_output_at > 0.0 and (finished or not self._stop_requested_is_set())
            )
            return success, started_output_at

        except Exception as error:
            append_log(f"Sounddevice playback failed: {error}")
            self._sounddevice_playback_ready = False
            return False, 0.0
        finally:
            self._ensure_output_stream_state()

            with self._output_stream_lock:
                if self._active_output_stream is stream:
                    self._active_output_stream = None

            if stream is not None:
                with contextlib.suppress(Exception):
                    stream.close(ignore_errors=True)

    def _play_wav(self, wav_path) -> tuple[bool, float]:
        if not wav_path.exists():
            return False, 0.0

        playback_started_at = time.monotonic()

        if self._sounddevice_playback_available():
            ok, first_audio_started_at = self._play_wav_with_sounddevice(Path(wav_path))
            if ok:
                append_log(
                    "TTS playback finished with sounddevice in "
                    f"{time.monotonic() - playback_started_at:.3f}s"
                )
                return True, first_audio_started_at

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
            launched_at = time.monotonic()
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
                return True, launched_at

        append_log("All playback backends failed for current WAV.")
        return False, 0.0


__all__ = ["TTSPipelineWavPlaybackMixin"]