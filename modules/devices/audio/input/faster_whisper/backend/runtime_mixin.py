from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from modules.devices.audio.coordination import AssistantAudioCoordinator


class FasterWhisperRuntimeMixin:
    @classmethod
    def _normalize_language(cls, language: str | None, *, allow_auto: bool = False) -> str:
        normalized = str(language or "").strip().lower()
        if allow_auto and normalized in {"", "auto"}:
            return "auto"
        if normalized in cls.SUPPORTED_LANGUAGES:
            return normalized
        return "auto" if allow_auto else "en"

    def set_audio_coordinator(self, audio_coordinator: AssistantAudioCoordinator | None) -> None:
        self.audio_coordinator = audio_coordinator

    def _input_blocked_by_assistant_output(self) -> bool:
        if self.audio_coordinator is None:
            return False
        try:
            blocked = bool(self.audio_coordinator.input_blocked())
        except Exception:
            return False
        if blocked:
            self._last_input_blocked_monotonic = self._now()
        return blocked

    def _recently_unblocked(self) -> bool:
        if self._last_input_blocked_monotonic <= 0.0:
            return False
        return (self._now() - self._last_input_blocked_monotonic) < self.input_unblock_settle_seconds

    def _stream_recently_opened(self) -> bool:
        if self._last_stream_open_monotonic <= 0.0:
            return False
        return (self._now() - self._last_stream_open_monotonic) < self.stream_start_settle_seconds

    def _ensure_faster_whisper_runtime(self) -> None:
        if self._fw_dependency_error:
            raise RuntimeError(self._fw_dependency_error)
        if self._fw_model is not None:
            return

        try:
            from faster_whisper import WhisperModel
        except Exception as error:
            self._fw_dependency_error = (
                "Missing faster-whisper dependency. Install it before using the Faster-Whisper backend."
            )
            raise RuntimeError(self._fw_dependency_error) from error

        self._fw_model = WhisperModel(
            self.model_size_or_path,
            device="cpu",
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
            num_workers=1,
        )

        self.LOGGER.info(
            "Faster-Whisper model loaded: model_ref='%s', compute_type='%s', threads=%s",
            self.model_size_or_path,
            self.compute_type,
            self.cpu_threads,
        )

    def _ensure_silero_runtime(self) -> None:
        if not self.vad_enabled:
            return
        if self._silero_model is not None and self._silero_get_speech_timestamps is not None:
            return
        try:
            from silero_vad import get_speech_timestamps, load_silero_vad
        except Exception as error:
            if not self._silero_unavailable_logged:
                self.LOGGER.warning(
                    "Silero VAD unavailable. Falling back to energy-based speech detection. Reason: %s",
                    error,
                )
                self._silero_unavailable_logged = True
            return

        self._silero_model = load_silero_vad(onnx=True)
        self._silero_get_speech_timestamps = get_speech_timestamps
        self.LOGGER.info("Silero VAD loaded successfully for FasterWhisperInputBackend.")

    def _ensure_runtime_ready(self) -> None:
        self._ensure_silero_runtime()
        self._ensure_faster_whisper_runtime()

