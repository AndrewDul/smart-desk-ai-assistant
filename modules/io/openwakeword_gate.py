from __future__ import annotations

import queue
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np
import sounddevice as sd

from modules.system.utils import BASE_DIR, append_log


class OpenWakeWordGate:
    MODEL_SAMPLE_RATE = 16000

    def __init__(
        self,
        *,
        model_path: str,
        device_index: Optional[int] = None,
        device_name_contains: Optional[str] = None,
        threshold: float = 0.16,
        trigger_level: int = 1,
        block_ms: int = 80,
        vad_threshold: float = 0.0,
        enable_speex_noise_suppression: bool = False,
        debug: bool = False,
    ) -> None:
        self.model_path = self._resolve_project_path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"Wake model was not found: {self.model_path}")

        self.model_name = self.model_path.stem.lower()

        self.threshold = float(threshold)
        self.trigger_level = max(int(trigger_level), 1)
        self.block_ms = max(int(block_ms), 80)
        self.vad_threshold = float(vad_threshold)
        self.enable_speex_noise_suppression = bool(enable_speex_noise_suppression)
        self.debug = bool(debug)

        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self.device = self._resolve_input_device(device_index, device_name_contains)

        input_info = sd.query_devices(self.device, "input")
        self.device_name = str(input_info["name"])
        self.dtype = "int16"
        self.channels = 1
        self.input_sample_rate = self._resolve_supported_input_sample_rate(
            int(round(float(input_info.get("default_samplerate", self.MODEL_SAMPLE_RATE))))
        )

        self.model_frame_samples = int(self.MODEL_SAMPLE_RATE * (self.block_ms / 1000.0))
        self.input_blocksize = max(1, int(self.input_sample_rate * (self.block_ms / 1000.0)))
        self._resampled_buffer = np.array([], dtype=np.int16)

        from openwakeword.model import Model

        self.model = self._build_model(
            Model,
            vad_threshold=self.vad_threshold,
            enable_speex_noise_suppression=self.enable_speex_noise_suppression,
        )

        append_log(
            "OpenWakeWord gate initialized: "
            f"model='{self.model_path}', device='{self.device_name}', "
            f"input_rate={self.input_sample_rate}, threshold={self.threshold}, "
            f"trigger_level={self.trigger_level}, block_ms={self.block_ms}"
        )

    @staticmethod
    def _resolve_project_path(raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if candidate.is_absolute():
            return candidate
        return BASE_DIR / candidate

    def _resolve_input_device(
        self,
        device_index: Optional[int],
        device_name_contains: Optional[str],
    ) -> int | str | None:
        if device_name_contains:
            wanted = device_name_contains.lower()
            for index, device in enumerate(sd.query_devices()):
                if device.get("max_input_channels", 0) < 1:
                    continue
                if wanted in str(device["name"]).lower():
                    return index
            raise ValueError(f"Input device containing '{device_name_contains}' was not found.")
        return device_index

    def _resolve_supported_input_sample_rate(self, preferred_rate: int) -> int:
        candidates = [preferred_rate, self.MODEL_SAMPLE_RATE, 32000, 44100, 48000]
        seen: set[int] = set()

        for rate in candidates:
            if not rate or rate in seen:
                continue
            seen.add(rate)
            try:
                sd.check_input_settings(
                    device=self.device,
                    channels=self.channels,
                    dtype=self.dtype,
                    samplerate=rate,
                )
                return rate
            except Exception:
                continue

        raise RuntimeError(
            f"No supported sample rate found for openWakeWord gate on device '{self.device_name}'."
        )

    def _build_model(
        self,
        model_class,
        *,
        vad_threshold: float,
        enable_speex_noise_suppression: bool,
    ):
        modern_kwargs: dict[str, Any] = {
            "wakeword_models": [str(self.model_path)],
            "inference_framework": "onnx",
        }

        if vad_threshold > 0.0:
            modern_kwargs["vad_threshold"] = vad_threshold

        if enable_speex_noise_suppression:
            modern_kwargs["enable_speex_noise_suppression"] = True

        try:
            model = model_class(**modern_kwargs)
            append_log("OpenWakeWord gate using modern model API.")
            return model
        except TypeError as error:
            append_log(f"OpenWakeWord modern API unavailable, trying legacy API. Error: {error}")

        legacy_kwargs: dict[str, Any] = {
            "wakeword_model_paths": [str(self.model_path)],
        }

        if vad_threshold > 0.0:
            legacy_kwargs["vad_threshold"] = vad_threshold

        try:
            model = model_class(**legacy_kwargs)
            append_log("OpenWakeWord gate using legacy 0.4.x model API.")
            return model
        except TypeError:
            legacy_kwargs.pop("vad_threshold", None)
            model = model_class(**legacy_kwargs)
            append_log("OpenWakeWord gate using minimal legacy 0.4.x model API.")
            return model

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            append_log(f"OpenWakeWord audio callback status: {status}")

        try:
            if indata.ndim == 2:
                mono = indata[:, 0].copy()
            else:
                mono = indata.copy()

            if mono.dtype != np.int16:
                mono = mono.astype(np.int16, copy=False)

            self.audio_queue.put_nowait(mono)
        except Exception as error:
            append_log(f"OpenWakeWord audio callback error: {error}")

    def _clear_audio_queue(self) -> None:
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

    def _extract_numeric(self, value: Any) -> float | None:
        if value is None:
            return None

        if isinstance(value, (int, float, np.integer, np.floating)):
            return float(value)

        if isinstance(value, np.ndarray):
            if value.size == 0:
                return None
            flattened = value.reshape(-1)
            return float(flattened[-1])

        if isinstance(value, (list, tuple)):
            if not value:
                return None
            for item in reversed(value):
                numeric = self._extract_numeric(item)
                if numeric is not None:
                    return numeric
            return None

        if isinstance(value, dict):
            if "score" in value:
                numeric = self._extract_numeric(value["score"])
                if numeric is not None:
                    return numeric

            preferred_keys = []
            for key in value.keys():
                key_str = str(key).lower()
                if key_str == self.model_name:
                    preferred_keys.append(key)
                elif self.model_name in key_str:
                    preferred_keys.append(key)

            for key in preferred_keys:
                numeric = self._extract_numeric(value[key])
                if numeric is not None:
                    return numeric

            for nested in value.values():
                numeric = self._extract_numeric(nested)
                if numeric is not None:
                    return numeric

            return None

        return None

    def _extract_score(self, prediction: Any) -> float:
        numeric = self._extract_numeric(prediction)
        if numeric is None:
            if self.debug:
                print(f"OpenWakeWord raw prediction (unparsed): {prediction!r}")
            return 0.0
        return float(numeric)

    @staticmethod
    def _resample_to_16k(audio_int16: np.ndarray, src_rate: int) -> np.ndarray:
        if audio_int16.size == 0:
            return np.array([], dtype=np.int16)

        if src_rate == OpenWakeWordGate.MODEL_SAMPLE_RATE:
            return audio_int16.astype(np.int16, copy=False)

        audio_f32 = audio_int16.astype(np.float32) / 32768.0
        duration = len(audio_f32) / float(src_rate)
        if duration <= 0:
            return np.array([], dtype=np.int16)

        src_positions = np.linspace(0.0, duration, num=len(audio_f32), endpoint=False, dtype=np.float64)
        dst_length = max(1, int(round(duration * OpenWakeWordGate.MODEL_SAMPLE_RATE)))
        dst_positions = np.linspace(0.0, duration, num=dst_length, endpoint=False, dtype=np.float64)
        resampled = np.interp(dst_positions, src_positions, audio_f32)
        resampled = np.clip(resampled * 32768.0, -32768, 32767).astype(np.int16)
        return resampled

    def listen_for_wake_phrase(self, timeout: float = 2.0, debug: bool = False) -> str | None:
        self._clear_audio_queue()
        self._resampled_buffer = np.array([], dtype=np.int16)

        started_at = time.monotonic()
        consecutive_hits = 0
        best_score = 0.0

        with sd.InputStream(
            samplerate=self.input_sample_rate,
            blocksize=self.input_blocksize,
            device=self.device,
            channels=self.channels,
            dtype=self.dtype,
            callback=self._audio_callback,
        ):
            while time.monotonic() - started_at <= float(timeout):
                try:
                    chunk = self.audio_queue.get(timeout=0.12)
                except queue.Empty:
                    continue

                pcm16 = np.asarray(chunk).astype(np.int16, copy=False)
                pcm16 = self._resample_to_16k(pcm16, self.input_sample_rate)
                if pcm16.size == 0:
                    continue

                self._resampled_buffer = np.concatenate((self._resampled_buffer, pcm16))

                while len(self._resampled_buffer) >= self.model_frame_samples:
                    frame = self._resampled_buffer[: self.model_frame_samples]
                    self._resampled_buffer = self._resampled_buffer[self.model_frame_samples :]

                    prediction = self.model.predict(frame)
                    score = self._extract_score(prediction)
                    best_score = max(best_score, score)

                    if score >= self.threshold:
                        consecutive_hits += 1
                    else:
                        consecutive_hits = 0

                    if debug or self.debug:
                        print(f"OpenWakeWord score={score:.3f} hits={consecutive_hits}")

                    if consecutive_hits >= self.trigger_level:
                        append_log(
                            f"OpenWakeWord wake accepted: score={score:.3f}, best_score={best_score:.3f}"
                        )
                        return "nexa"

        if debug or self.debug:
            print(f"OpenWakeWord best score={best_score:.3f}")

        return None

    def close(self) -> None:
        self._clear_audio_queue()
        self._resampled_buffer = np.array([], dtype=np.int16)