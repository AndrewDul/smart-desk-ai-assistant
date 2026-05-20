from __future__ import annotations

import contextlib
import subprocess
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
        return self._stop_event_is_set(getattr(self, "_stop_requested", None))

    @staticmethod
    def _stop_event_is_set(stop_event=None) -> bool:
        stop_requested = stop_event
        if stop_requested is None:
            return False
        try:
            return bool(stop_requested.is_set())
        except Exception:
            return False

    def _should_try_sounddevice_playback(self) -> bool:
        return bool(getattr(self, "_direct_sounddevice_playback_enabled", False))

    def _playback_file_status(self, wav_path: Path) -> dict[str, object]:
        path = Path(wav_path)
        exists = path.exists()
        size = 0
        if exists:
            try:
                size = int(path.stat().st_size)
            except OSError:
                size = 0
        return {
            "audio_file": str(path),
            "audio_file_exists": exists,
            "audio_file_size_bytes": size,
        }

    def _store_wav_playback_attempt(self, **values: object) -> None:
        self._last_wav_playback_attempt = dict(values)

    def _latest_wav_playback_attempt(self) -> dict[str, object]:
        return dict(getattr(self, "_last_wav_playback_attempt", {}) or {})

    def _playback_attempt_from_process_result(
        self,
        *,
        backend_name: str,
        wav_path: Path,
        result: dict[str, object],
        first_audio_started_at: float,
    ) -> dict[str, object]:
        return {
            "playback_backend": backend_name,
            "playback_command": str(result.get("command_display", "") or ""),
            "playback_exit_code": result.get("return_code"),
            "playback_stderr": self._truncate_process_output(
                str(result.get("stderr_text", "") or "")
                or str(result.get("error_text", "") or "")
            ),
            "playback_stdout": self._truncate_process_output(
                str(result.get("stdout_text", "") or "")
            ),
            "playback_process_started": bool(result.get("return_code") is not None or result.get("error_text")),
            "playback_timed_out": bool(result.get("timed_out", False)),
            "playback_interrupted": bool(result.get("interrupted", False)),
            "first_audio_started_at_monotonic": float(first_audio_started_at or 0.0),
            **self._playback_file_status(wav_path),
        }

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

    def _ensure_presence_output_stream_state(self) -> None:
        if not hasattr(self, "_presence_output_stream_lock") or self._presence_output_stream_lock is None:
            self._presence_output_stream_lock = threading.Lock()
        if not hasattr(self, "_active_presence_output_stream"):
            self._active_presence_output_stream = None

    def _stop_active_presence_output_stream(self) -> None:
        self._ensure_presence_output_stream_state()

        stream = None
        with self._presence_output_stream_lock:
            stream = self._active_presence_output_stream
            self._active_presence_output_stream = None

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

    @staticmethod
    def _notify_first_audio(callback, started_at: float) -> None:
        if not callable(callback):
            return
        try:
            callback()
        except TypeError:
            try:
                callback(started_at)
            except Exception:
                pass
        except Exception:
            pass

    def _play_wav_with_sounddevice(
        self,
        wav_path: Path,
        *,
        on_first_audio=None,
        stop_event=None,
        presence_playback: bool = False,
    ) -> tuple[bool, float]:
        import sounddevice as sd

        if not wav_path.exists():
            self._store_wav_playback_attempt(
                playback_backend="sounddevice",
                playback_command="sounddevice.OutputStream",
                playback_exit_code=None,
                playback_stderr="wav file missing",
                playback_process_started=False,
                **self._playback_file_status(wav_path),
            )
            return False, 0.0

        if presence_playback:
            self._ensure_presence_output_stream_state()
        else:
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

                if self._stop_event_is_set(stop_event):
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

            if presence_playback:
                with self._presence_output_stream_lock:
                    self._active_presence_output_stream = stream
            else:
                with self._output_stream_lock:
                    self._active_output_stream = stream

            stream.start()
            if started_output_at <= 0.0:
                started_output_at = time.monotonic()
            self._notify_first_audio(on_first_audio, started_output_at)

            while stream.active and not self._stop_event_is_set(stop_event):
                time.sleep(0.005)

            if self._stop_event_is_set(stop_event) and stream.active:
                try:
                    stream.abort(ignore_errors=True)
                except Exception:
                    pass

            success = bool(
                started_output_at > 0.0 and (finished or not self._stop_event_is_set(stop_event))
            )
            self._store_wav_playback_attempt(
                playback_backend="sounddevice",
                playback_command="sounddevice.OutputStream",
                playback_exit_code=0 if success else 1,
                playback_stderr="",
                playback_process_started=started_output_at > 0.0,
                first_audio_started_at_monotonic=started_output_at if success else 0.0,
                **self._playback_file_status(wav_path),
            )
            return success, started_output_at

        except Exception as error:
            append_log(f"Sounddevice playback failed: {error}")
            self._sounddevice_playback_ready = False
            self._store_wav_playback_attempt(
                playback_backend="sounddevice",
                playback_command="sounddevice.OutputStream",
                playback_exit_code=None,
                playback_stderr=str(error),
                playback_process_started=started_output_at > 0.0,
                first_audio_started_at_monotonic=0.0,
                **self._playback_file_status(wav_path),
            )
            return False, 0.0
        finally:
            if presence_playback:
                self._ensure_presence_output_stream_state()
                with self._presence_output_stream_lock:
                    if self._active_presence_output_stream is stream:
                        self._active_presence_output_stream = None
            else:
                self._ensure_output_stream_state()
                with self._output_stream_lock:
                    if self._active_output_stream is stream:
                        self._active_output_stream = None

            if stream is not None:
                with contextlib.suppress(Exception):
                    stream.close(ignore_errors=True)

    def _run_playback_process_with_stop_event(
        self,
        command: list[str],
        *,
        timeout_seconds: float,
        source: str,
        poll_sleep_seconds: float,
        stop_event,
        on_process_started=None,
    ) -> bool:
        started_at = time.monotonic()
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if callable(on_process_started):
            try:
                on_process_started()
            except Exception:
                pass
        with self._process_lock:
            if not hasattr(self, "_active_presence_processes"):
                self._active_presence_processes = []
            self._active_presence_processes.append(process)
        try:
            while True:
                if self._stop_event_is_set(stop_event):
                    self._terminate_process(process, reason=source)
                    return False

                return_code = process.poll()
                if return_code is not None:
                    return return_code == 0

                if (time.monotonic() - started_at) >= timeout_seconds:
                    append_log(f"{source} process timed out after {timeout_seconds:.2f}s.")
                    self._terminate_process(process, reason=f"{source}_timeout")
                    return False

                time.sleep(max(0.001, float(poll_sleep_seconds)))
        finally:
            with self._process_lock:
                self._active_presence_processes = [
                    item
                    for item in getattr(self, "_active_presence_processes", [])
                    if item is not process
                ]

    def _play_wav(
        self,
        wav_path,
        *,
        on_first_audio=None,
        stop_event=None,
        presence_playback: bool = False,
    ) -> tuple[bool, float]:
        if not wav_path.exists():
            self._store_wav_playback_attempt(
                playback_backend="none",
                playback_command="",
                playback_exit_code=None,
                playback_stderr="wav file missing",
                playback_process_started=False,
                **self._playback_file_status(Path(wav_path)),
            )
            return False, 0.0

        self._store_wav_playback_attempt(
            playback_backend="none",
            playback_command="",
            playback_exit_code=None,
            playback_stderr="not attempted yet",
            playback_process_started=False,
            **self._playback_file_status(Path(wav_path)),
        )

        playback_started_at = time.monotonic()

        if self._should_try_sounddevice_playback() and self._sounddevice_playback_available():
            ok, first_audio_started_at = self._play_wav_with_sounddevice(
                Path(wav_path),
                on_first_audio=on_first_audio,
                stop_event=stop_event,
                presence_playback=presence_playback,
            )
            if ok:
                if bool(getattr(self, "_tts_hot_path_success_log_enabled", False)):
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
            first_audio_started_at = 0.0

            def _mark_first_audio() -> None:
                nonlocal first_audio_started_at
                if first_audio_started_at <= 0.0:
                    first_audio_started_at = time.monotonic()
                self._notify_first_audio(on_first_audio, first_audio_started_at)

            if stop_event is None:
                ok = self._run_process_interruptibly(
                    command,
                    timeout_seconds=self._playback_timeout_seconds,
                    source=f"{backend_name}_playback",
                    poll_sleep_seconds=getattr(self, "_playback_poll_seconds", 0.005),
                    capture_output=True,
                    on_process_started=_mark_first_audio if callable(on_first_audio) else None,
                )
            else:
                ok = self._run_playback_process_with_stop_event(
                    command,
                    timeout_seconds=self._playback_timeout_seconds,
                    source=f"{backend_name}_playback",
                    poll_sleep_seconds=getattr(self, "_playback_poll_seconds", 0.005),
                    stop_event=stop_event,
                    on_process_started=_mark_first_audio if callable(on_first_audio) else None,
                )
            process_result = self._get_last_process_result(f"{backend_name}_playback")
            if process_result:
                self._store_wav_playback_attempt(
                    **self._playback_attempt_from_process_result(
                        backend_name=backend_name,
                        wav_path=Path(wav_path),
                        result=process_result,
                        first_audio_started_at=first_audio_started_at,
                    )
                )
            if ok:
                self._last_good_playback_backend = backend_name
                if bool(getattr(self, "_tts_hot_path_success_log_enabled", False)):
                    append_log(
                        f"TTS playback finished with {backend_name} in "
                        f"{time.monotonic() - playback_started_at:.3f}s"
                    )
                if first_audio_started_at <= 0.0:
                    first_audio_started_at = time.monotonic()
                    attempt = self._latest_wav_playback_attempt()
                    attempt["first_audio_started_at_monotonic"] = first_audio_started_at
                    attempt["playback_process_started"] = True
                    self._store_wav_playback_attempt(**attempt)
                return True, first_audio_started_at

        append_log("All playback backends failed for current WAV.")
        return False, 0.0


__all__ = ["TTSPipelineWavPlaybackMixin"]
