from __future__ import annotations

import queue
import time
from collections import deque
from typing import Any, Callable

import numpy as np
import sounddevice as sd


class FasterWhisperCaptureMixin:
    def set_realtime_audio_bus_shadow_tap(
        self,
        audio_bus: Any | None,
        *,
        enabled: bool,
    ) -> None:
        self._realtime_audio_bus_shadow_tap = audio_bus if enabled else None
        self._realtime_audio_bus_shadow_tap_enabled = bool(enabled and audio_bus is not None)
        self._realtime_audio_bus_shadow_tap_publish_errors = 0
        self._realtime_audio_bus_shadow_tap_recent_records = deque(maxlen=32)
        self._realtime_audio_bus_capture_window_shadow_tap_recent_records = deque(
            maxlen=8
        )
        self._realtime_audio_bus_capture_window_observer: (
            Callable[..., Any] | None
        ) = None
        self._realtime_audio_bus_capture_window_observer_enabled = False

    def set_realtime_audio_bus_capture_window_observer(
        self,
        observer: Callable[..., Any] | None,
        *,
        enabled: bool,
    ) -> None:
        self._realtime_audio_bus_capture_window_observer = (
            observer if enabled and callable(observer) else None
        )
        self._realtime_audio_bus_capture_window_observer_enabled = bool(
            enabled and callable(observer)
        )

    def realtime_audio_bus_shadow_tap_diagnostics_snapshot(self) -> dict[str, Any]:
        recent_records = list(
            getattr(self, "_realtime_audio_bus_shadow_tap_recent_records", [])
            or []
        )
        return {
            "enabled": bool(
                getattr(self, "_realtime_audio_bus_shadow_tap_enabled", False)
            ),
            "attached": getattr(self, "_realtime_audio_bus_shadow_tap", None)
            is not None,
            "publish_errors": int(
                getattr(self, "_realtime_audio_bus_shadow_tap_publish_errors", 0)
                or 0
            ),
            "recent_record_count": len(recent_records),
            "recent_records": recent_records[-5:],
            "last_record": recent_records[-1] if recent_records else {},
        }

    def _append_realtime_audio_bus_shadow_tap_diagnostic(
        self,
        record: dict[str, Any],
    ) -> None:
        records = getattr(
            self,
            "_realtime_audio_bus_shadow_tap_recent_records",
            None,
        )
        if records is None:
            records = deque(maxlen=32)
            self._realtime_audio_bus_shadow_tap_recent_records = records
        records.append(dict(record))

    def _realtime_audio_bus_shadow_tap_audio_profile(
        self,
        audio: Any,
        *,
        label: str,
    ) -> dict[str, Any]:
        profile = self._audio_array_profile(audio)
        profile["label"] = str(label or "audio")
        return profile

    @staticmethod
    def _audio_array_profile(audio: Any) -> dict[str, Any]:
        try:
            array = np.asarray(audio)
        except Exception as error:
            return {
                "available": False,
                "reason": f"array_unavailable:{type(error).__name__}",
            }

        profile: dict[str, Any] = {
            "available": True,
            "dtype": str(array.dtype),
            "shape": list(array.shape),
            "sample_count": int(array.size),
        }

        if array.size <= 0:
            profile.update(
                {
                    "reason": "empty",
                    "raw_min": None,
                    "raw_max": None,
                    "raw_peak_abs": None,
                    "normalized_rms": None,
                    "normalized_mean_abs": None,
                    "normalized_peak_abs": None,
                    "normalized_near_zero_ratio": None,
                }
            )
            return profile

        flat = array.reshape(-1)

        if not np.issubdtype(flat.dtype, np.number):
            profile.update(
                {
                    "available": False,
                    "reason": "non_numeric",
                    "raw_min": None,
                    "raw_max": None,
                    "raw_peak_abs": None,
                    "normalized_rms": None,
                    "normalized_mean_abs": None,
                    "normalized_peak_abs": None,
                    "normalized_near_zero_ratio": None,
                }
            )
            return profile

        raw_min = float(np.min(flat))
        raw_max = float(np.max(flat))
        raw_peak_abs = float(np.max(np.abs(flat)))

        if np.issubdtype(flat.dtype, np.integer):
            if flat.dtype == np.int16:
                scale = 32768.0
            else:
                info = np.iinfo(flat.dtype)
                scale = float(max(abs(int(info.min)), abs(int(info.max)), 1))
            normalized = flat.astype(np.float32, copy=False) / scale
        else:
            normalized = flat.astype(np.float32, copy=False)

        finite_mask = np.isfinite(normalized)
        if not np.any(finite_mask):
            profile.update(
                {
                    "available": False,
                    "reason": "non_finite",
                    "raw_min": round(raw_min, 6),
                    "raw_max": round(raw_max, 6),
                    "raw_peak_abs": round(raw_peak_abs, 6),
                    "normalized_rms": None,
                    "normalized_mean_abs": None,
                    "normalized_peak_abs": None,
                    "normalized_near_zero_ratio": None,
                }
            )
            return profile

        normalized = normalized[finite_mask]
        abs_normalized = np.abs(normalized)
        near_zero_threshold = 1.0 / 32768.0

        profile.update(
            {
                "reason": "ok",
                "raw_min": round(raw_min, 6),
                "raw_max": round(raw_max, 6),
                "raw_peak_abs": round(raw_peak_abs, 6),
                "normalized_rms": round(
                    float(np.sqrt(np.mean(np.square(normalized), dtype=np.float64))),
                    6,
                ),
                "normalized_mean_abs": round(float(np.mean(abs_normalized)), 6),
                "normalized_peak_abs": round(float(np.max(abs_normalized)), 6),
                "normalized_near_zero_ratio": round(
                    float(np.mean(abs_normalized <= near_zero_threshold)),
                    6,
                ),
            }
        )
        return profile

    @staticmethod
    def _audio_callback_time_info_snapshot(time_info: Any) -> dict[str, float | None]:
        fields = (
            "inputBufferAdcTime",
            "currentTime",
            "outputBufferDacTime",
        )
        snapshot: dict[str, float | None] = {}
        for field in fields:
            value = getattr(time_info, field, None)
            if value is None and isinstance(time_info, dict):
                value = time_info.get(field)
            try:
                snapshot[field] = None if value is None else float(value)
            except (TypeError, ValueError):
                snapshot[field] = None
        return snapshot

    @staticmethod
    def _conversion_warning(
        *,
        raw_profile: dict[str, Any],
        converted_profile: dict[str, Any],
    ) -> str:
        raw_dtype = str(raw_profile.get("dtype") or "")
        raw_peak = float(raw_profile.get("normalized_peak_abs") or 0.0)
        converted_raw_peak = float(converted_profile.get("raw_peak_abs") or 0.0)
        converted_peak = float(converted_profile.get("normalized_peak_abs") or 0.0)

        if (
            raw_dtype.startswith("float")
            and raw_peak >= 0.01
            and converted_raw_peak <= 1.0
        ):
            return "float_audio_cast_to_int16_without_scaling"

        if raw_peak >= 0.05 and converted_peak <= 0.005:
            return "converted_pcm_much_weaker_than_raw_audio"

        return ""

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        callback_started_at = time.monotonic()

        if status:
            self.LOGGER.warning("FasterWhisper audio callback status: %s", status)
        try:
            if indata.ndim == 2:
                raw_mono = indata[:, 0].copy()
            else:
                raw_mono = indata.copy()

            mono = raw_mono
            if mono.dtype != np.int16:
                mono = mono.astype(np.int16, copy=False)

            self._publish_realtime_audio_bus_shadow_tap(
                raw_mono=raw_mono,
                converted_mono=mono,
                frames=frames,
                time_info=time_info,
                callback_status=status,
                callback_started_at=callback_started_at,
            )

            try:
                self.audio_queue.put_nowait(mono)
            except queue.Full:
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self.audio_queue.put_nowait(mono)
                except queue.Full:
                    pass
        except Exception as error:
            self.LOGGER.warning("FasterWhisper audio callback error: %s", error)

    def _publish_realtime_audio_bus_shadow_tap(
        self,
        mono: np.ndarray | None = None,
        *,
        raw_mono: Any | None = None,
        converted_mono: np.ndarray | None = None,
        frames: int | None = None,
        time_info: Any | None = None,
        callback_status: Any | None = None,
        callback_started_at: float | None = None,
    ) -> None:
        if not bool(getattr(self, "_realtime_audio_bus_shadow_tap_enabled", False)):
            return

        audio_bus = getattr(self, "_realtime_audio_bus_shadow_tap", None)
        converted = converted_mono if converted_mono is not None else mono
        if converted is None:
            return

        timestamp_monotonic = (
            float(callback_started_at)
            if callback_started_at is not None
            else time.monotonic()
        )

        raw_profile = self._audio_array_profile(
            raw_mono if raw_mono is not None else converted
        )
        converted_profile = self._audio_array_profile(converted)

        publish_status = "not_published"
        publish_error = ""
        published_byte_count = 0

        publish_pcm = getattr(audio_bus, "publish_pcm", None)
        if audio_bus is None:
            publish_status = "audio_bus_unavailable"
        elif not callable(publish_pcm):
            publish_status = "publish_pcm_unavailable"
        else:
            try:
                pcm = np.asarray(converted).tobytes(order="C")
                publish_pcm(
                    pcm,
                    timestamp_monotonic=timestamp_monotonic,
                    source="faster_whisper_callback_shadow_tap",
                )
                publish_status = "published"
                published_byte_count = len(pcm)
            except Exception as error:
                publish_status = f"publish_failed:{type(error).__name__}"
                publish_error = str(error)
                error_count = int(
                    getattr(self, "_realtime_audio_bus_shadow_tap_publish_errors", 0)
                )
                self._realtime_audio_bus_shadow_tap_publish_errors = error_count + 1
                if error_count < 3:
                    self.LOGGER.warning(
                        "FasterWhisper realtime audio bus shadow tap publish failed: %s",
                        error,
                    )

        try:
            frames_argument = None if frames is None else int(frames)
        except (TypeError, ValueError):
            frames_argument = None

        diagnostic_record = {
            "timestamp_monotonic": timestamp_monotonic,
            "source": "faster_whisper_callback_shadow_tap",
            "publish_status": publish_status,
            "publish_error": publish_error,
            "frames_argument": frames_argument,
            "published_byte_count": published_byte_count,
            "callback_status": str(callback_status or ""),
            "callback_time_info": self._audio_callback_time_info_snapshot(time_info),
            "raw_profile": raw_profile,
            "converted_profile": converted_profile,
            "conversion_warning": self._conversion_warning(
                raw_profile=raw_profile,
                converted_profile=converted_profile,
            ),
        }
        self._append_realtime_audio_bus_shadow_tap_diagnostic(diagnostic_record)

    def publish_realtime_audio_bus_capture_window_shadow_tap(
        self,
        audio: Any,
        *,
        capture_finished_at_monotonic: float | None = None,
        transcription_finished_at_monotonic: float | None = None,
    ) -> dict[str, Any]:
        """Replay the captured FasterWhisper audio window into AudioBus.

        This is diagnostic-only. It does not start a microphone stream, does not
        affect FasterWhisper transcription, and does not execute actions.
        """

        source = "faster_whisper_capture_window_shadow_tap"

        if not bool(getattr(self, "_realtime_audio_bus_shadow_tap_enabled", False)):
            return {
                "enabled": False,
                "attached": False,
                "published": False,
                "reason": "shadow_tap_disabled",
                "source": source,
            }

        audio_bus = getattr(self, "_realtime_audio_bus_shadow_tap", None)
        publish_pcm = getattr(audio_bus, "publish_pcm", None)
        if audio_bus is None or not callable(publish_pcm):
            return {
                "enabled": True,
                "attached": False,
                "published": False,
                "reason": "audio_bus_unavailable",
                "source": source,
            }

        input_profile = self._audio_array_profile(audio)
        int16_audio, conversion_reason = self._capture_window_audio_to_int16(audio)
        int16_profile = self._audio_array_profile(int16_audio)

        if int16_audio is None or int16_audio.size <= 0:
            record = {
                "enabled": True,
                "attached": True,
                "published": False,
                "reason": "empty_capture_window",
                "source": source,
                "capture_finished_at_monotonic": capture_finished_at_monotonic,
                "transcription_finished_at_monotonic": (
                    transcription_finished_at_monotonic
                ),
                "input_profile": input_profile,
                "int16_profile": int16_profile,
                "conversion_reason": conversion_reason,
            }
            self._append_realtime_audio_bus_capture_window_shadow_tap_diagnostic(
                record
            )
            self._notify_realtime_audio_bus_capture_window_observer(record)
            return record

        sample_rate = self._positive_int_for_audio_profile(
            getattr(self, "sample_rate", None),
            fallback=16000,
        )
        blocksize = self._positive_int_for_audio_profile(
            getattr(self, "blocksize", None),
            fallback=1024,
        )
        chunk_sample_count = max(1, blocksize)

        sample_count = int(int16_audio.size)
        duration_seconds = sample_count / float(sample_rate)
        publish_started_at = time.monotonic()
        publish_stage = (
            "before_transcription"
            if transcription_finished_at_monotonic is None
            else "after_transcription"
        )
        replay_window_started_at = publish_started_at - duration_seconds

        capture_finished_to_publish_start_ms = None
        if capture_finished_at_monotonic is not None:
            capture_finished_to_publish_start_ms = round(
                max(
                    0.0,
                    (
                        publish_started_at
                        - float(capture_finished_at_monotonic)
                    )
                    * 1000.0,
                ),
                3,
            )

        transcription_finished_to_publish_start_ms = None
        if transcription_finished_at_monotonic is not None:
            transcription_finished_to_publish_start_ms = round(
                max(
                    0.0,
                    (
                        publish_started_at
                        - float(transcription_finished_at_monotonic)
                    )
                    * 1000.0,
                ),
                3,
            )

        published_frame_count = 0
        published_byte_count = 0
        publish_errors: list[str] = []

        for start in range(0, sample_count, chunk_sample_count):
            chunk = int16_audio[start : start + chunk_sample_count]
            if chunk.size <= 0:
                continue

            timestamp_monotonic = replay_window_started_at + (
                float(start) / float(sample_rate)
            )
            try:
                pcm = chunk.tobytes(order="C")
                publish_pcm(
                    pcm,
                    timestamp_monotonic=timestamp_monotonic,
                    source=source,
                )
                published_frame_count += 1
                published_byte_count += len(pcm)
            except Exception as error:
                publish_errors.append(f"{type(error).__name__}: {error}")
                error_count = int(
                    getattr(self, "_realtime_audio_bus_shadow_tap_publish_errors", 0)
                )
                self._realtime_audio_bus_shadow_tap_publish_errors = error_count + 1
                if error_count < 3:
                    self.LOGGER.warning(
                        "FasterWhisper capture-window shadow tap publish failed: %s",
                        error,
                    )

        publish_completed_at = time.monotonic()
        published = published_frame_count > 0 and not publish_errors
        record = {
            "enabled": True,
            "attached": True,
            "published": published,
            "reason": "published" if published else "publish_failed",
            "source": source,
            "timestamp_mode": "diagnostic_replay_window_ending_at_publish_start",
            "publish_stage": publish_stage,
            "capture_finished_to_publish_start_ms": (
                capture_finished_to_publish_start_ms
            ),
            "transcription_finished_to_publish_start_ms": (
                transcription_finished_to_publish_start_ms
            ),
            "sample_rate": sample_rate,
            "chunk_sample_count": chunk_sample_count,
            "audio_sample_count": sample_count,
            "audio_duration_seconds": round(duration_seconds, 6),
            "published_frame_count": published_frame_count,
            "published_byte_count": published_byte_count,
            "publish_error_count": len(publish_errors),
            "publish_errors": publish_errors[:3],
            "capture_finished_at_monotonic": capture_finished_at_monotonic,
            "transcription_finished_at_monotonic": transcription_finished_at_monotonic,
            "publish_started_at_monotonic": publish_started_at,
            "publish_completed_at_monotonic": publish_completed_at,
            "input_profile": input_profile,
            "int16_profile": int16_profile,
            "conversion_reason": conversion_reason,
        }
        self._append_realtime_audio_bus_capture_window_shadow_tap_diagnostic(record)
        self._notify_realtime_audio_bus_capture_window_observer(record)
        return record

    def _notify_realtime_audio_bus_capture_window_observer(
        self,
        record: dict[str, Any],
    ) -> None:
        if not bool(
            getattr(
                self,
                "_realtime_audio_bus_capture_window_observer_enabled",
                False,
            )
        ):
            return

        observer = getattr(
            self,
            "_realtime_audio_bus_capture_window_observer",
            None,
        )
        if not callable(observer):
            return

        try:
            observer(
                owner=self,
                capture_window_metadata=dict(record or {}),
            )
        except Exception as error:
            self.LOGGER.warning(
                "FasterWhisper capture-window observer failed safely: %s",
                error,
            )

    def _append_realtime_audio_bus_capture_window_shadow_tap_diagnostic(
        self,
        record: dict[str, Any],
    ) -> None:
        records = getattr(
            self,
            "_realtime_audio_bus_capture_window_shadow_tap_recent_records",
            None,
        )
        if records is None:
            records = deque(maxlen=8)
            self._realtime_audio_bus_capture_window_shadow_tap_recent_records = (
                records
            )
        records.append(dict(record))

    @staticmethod
    def _capture_window_audio_to_int16(
        audio: Any,
    ) -> tuple[np.ndarray | None, str]:
        try:
            array = np.asarray(audio)
        except Exception as error:
            return None, f"array_unavailable:{type(error).__name__}"

        if array.size <= 0:
            return None, "empty"

        if array.ndim > 1:
            array = array.reshape(-1)

        if np.issubdtype(array.dtype, np.integer):
            if array.dtype == np.int16:
                return array.astype(np.int16, copy=True), "already_int16"

            info = np.iinfo(array.dtype)
            scale = float(max(abs(int(info.min)), abs(int(info.max)), 1))
            normalized = array.astype(np.float32, copy=False) / scale
            converted = np.clip(normalized, -1.0, 1.0)
            return (
                np.round(converted * 32767.0).astype(np.int16),
                f"integer_scaled_from_{array.dtype}_to_int16",
            )

        if not np.issubdtype(array.dtype, np.floating):
            return None, f"unsupported_dtype:{array.dtype}"

        normalized = array.astype(np.float32, copy=False)
        normalized = np.nan_to_num(
            normalized,
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        )
        normalized = np.clip(normalized, -1.0, 1.0)
        return (
            np.round(normalized * 32767.0).astype(np.int16),
            f"float_scaled_from_{array.dtype}_to_int16",
        )

    @staticmethod
    def _positive_int_for_audio_profile(raw_value: Any, *, fallback: int) -> int:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return int(fallback)
        return value if value > 0 else int(fallback)

    def _ensure_stream_open(self) -> None:
        if self._stream is not None:
            return
        stream = sd.InputStream(
            samplerate=self.sample_rate,
            blocksize=self.blocksize,
            device=self.device,
            channels=self.channels,
            dtype=self.dtype,
            callback=self._audio_callback,
        )
        stream.start()
        self._stream = stream
        self._last_stream_open_monotonic = self._now()
        self.LOGGER.info(
            "FasterWhisper input stream started: device='%s', sample_rate=%s, blocksize=%s",
            self.device_name,
            self.sample_rate,
            self.blocksize,
        )

    def _close_stream(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        try:
            stream.stop()
        except Exception as error:
            self.LOGGER.debug("FasterWhisper input stream stop warning: %s", error)
        try:
            stream.close()
        except Exception as error:
            self.LOGGER.debug("FasterWhisper input stream close warning: %s", error)

    def _clear_audio_queue(self) -> None:
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

    def _record_until_silence(
        self,
        timeout: float = 8.0,
        debug: bool = False,
        *,
        end_silence_seconds: float | None = None,
        min_speech_seconds: float | None = None,
        pre_roll_seconds: float | None = None,
        flush_queue: bool = True,
    ) -> np.ndarray | None:
        if self._input_blocked_by_assistant_output() or self._recently_unblocked():
            if debug:
                print("Capture skipped because audio shield is active or just released.")
            if flush_queue:
                self._clear_audio_queue()
            return None

        self._ensure_runtime_ready()
        self._ensure_stream_open()

        if flush_queue:
            self._clear_audio_queue()

        if self._stream_recently_opened():
            time.sleep(self.stream_start_settle_seconds)

        effective_end_silence = (
            self.end_silence_seconds
            if end_silence_seconds is None
            else max(float(end_silence_seconds), 0.08)
        )
        effective_min_speech = (
            self.min_speech_seconds
            if min_speech_seconds is None
            else max(float(min_speech_seconds), 0.05)
        )
        effective_pre_roll = (
            self.pre_roll_seconds
            if pre_roll_seconds is None
            else max(float(pre_roll_seconds), 0.05)
        )

        requested_timeout = max(float(timeout), 0.25)
        hard_timeout = min(requested_timeout, self.max_record_seconds)
        hard_timeout = max(hard_timeout, effective_min_speech + effective_end_silence + 0.20)
        start_time = self._now()

        pre_roll_max_chunks = max(
            1,
            int(round(effective_pre_roll * self.sample_rate / self.blocksize)),
        )
        pre_roll = deque(maxlen=pre_roll_max_chunks)

        recorded_chunks: list[np.ndarray] = []
        speech_started = False
        speech_started_at: float | None = None
        last_speech_at: float | None = None
        last_voiced_observation: float | None = None
        low_energy_after_start = 0

        while self._now() - start_time <= hard_timeout:
            if self._input_blocked_by_assistant_output():
                if debug:
                    print("Capture aborted because assistant output shield became active.")
                if flush_queue:
                    self._clear_audio_queue()
                return None

            try:
                chunk = self.audio_queue.get(timeout=0.08)
            except queue.Empty:
                if speech_started and last_speech_at is not None:
                    if (self._now() - last_speech_at) >= effective_end_silence:
                        break
                continue
            except Exception as error:
                self.LOGGER.warning("FasterWhisper queue read error: %s", error)
                self._close_stream()
                return None

            chunk_f32 = self._int16_chunk_to_float32(chunk)
            if chunk_f32.size == 0:
                continue

            pre_roll.append(chunk_f32)
            chunk_has_speech = self._window_contains_speech(chunk_f32)
            if chunk_has_speech:
                last_voiced_observation = self._now()

            if not speech_started:
                onset_window = self._concat_audio(list(pre_roll))
                onset_has_speech = self._window_contains_speech(onset_window)
                if onset_has_speech or chunk_has_speech:
                    speech_started = True
                    speech_started_at = self._now()
                    last_speech_at = speech_started_at
                    recorded_chunks.extend(list(pre_roll))
                    low_energy_after_start = 0
                    if debug:
                        print("Speech onset detected by Faster-Whisper frontend.")
                    continue
            else:
                recorded_chunks.append(chunk_f32)

                trailing_chunks = recorded_chunks[-max(1, pre_roll_max_chunks * 2):]
                trailing_window = self._concat_audio(trailing_chunks)
                trailing_has_speech = self._window_contains_speech(trailing_window)

                if chunk_has_speech or trailing_has_speech:
                    last_speech_at = self._now()
                    low_energy_after_start = 0
                else:
                    low_energy_after_start += 1

                enough_speech = False
                if speech_started_at is not None:
                    enough_speech = (self._now() - speech_started_at) >= effective_min_speech

                if enough_speech and last_speech_at is not None:
                    if (self._now() - last_speech_at) >= effective_end_silence:
                        break

                if (
                    enough_speech
                    and last_voiced_observation is not None
                    and (self._now() - last_voiced_observation)
                    >= max(self.no_speech_decay_seconds, effective_end_silence)
                    and low_energy_after_start >= 2
                ):
                    break

        if not speech_started or not recorded_chunks:
            if debug:
                print(f"No speech onset detected before command timeout ({hard_timeout:.2f}s).")
            return None

        audio = self._concat_audio(recorded_chunks)
        duration = len(audio) / float(self.sample_rate)
        if duration < effective_min_speech:
            if debug:
                print("Recorded utterance too short, dropping.")
            return None

        trimmed_audio = self._trim_audio_for_transcription(audio)
        trimmed_duration = len(trimmed_audio) / float(self.sample_rate) if trimmed_audio.size else 0.0

        if debug:
            print(f"Recorded audio duration: {duration:.2f}s | trimmed duration: {trimmed_duration:.2f}s")

        if trimmed_audio.size >= int(self.sample_rate * effective_min_speech):
            return trimmed_audio
        return audio

    def _window_contains_speech(self, audio: np.ndarray) -> bool:
        if audio.size == 0:
            return False
        if self.vad_enabled and self._silero_window_contains_speech(audio):
            return True
        return self._energy_window_contains_speech(audio)

    def _silero_window_contains_speech(self, audio: np.ndarray) -> bool:
        if self._silero_model is None or self._silero_get_speech_timestamps is None:
            return False
        resampled = self._resample_audio(audio, self.sample_rate, self.MODEL_SAMPLE_RATE)
        if resampled.size == 0:
            return False
        try:
            timestamps = self._silero_get_speech_timestamps(
                resampled,
                self._silero_model,
                sampling_rate=self.MODEL_SAMPLE_RATE,
                threshold=self.vad_threshold,
                min_speech_duration_ms=self.vad_min_speech_ms,
                min_silence_duration_ms=self.vad_min_silence_ms,
                speech_pad_ms=self.vad_speech_pad_ms,
            )
            return bool(timestamps)
        except Exception as error:
            self.LOGGER.warning("Silero VAD inference warning: %s", error)
            return False

    def _energy_window_contains_speech(self, audio: np.ndarray) -> bool:
        rms = float(np.sqrt(np.mean(np.square(audio), dtype=np.float64)))
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        return rms >= self.energy_speech_threshold or peak >= max(
            self.energy_speech_threshold * 4.2,
            0.025,
        )