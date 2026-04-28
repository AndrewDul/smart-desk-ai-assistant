from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from modules.devices.audio.command_asr.command_grammar import (
    build_default_command_grammar,
)
from modules.devices.audio.command_asr.command_result import (
    CommandRecognitionResult,
    CommandRecognitionStatus,
)
from modules.devices.audio.command_asr.vosk_command_recognizer import (
    VoskCommandRecognizer,
)
from modules.runtime.voice_engine_v2.command_asr import CommandAsrResult
from modules.runtime.voice_engine_v2.command_audio_segment import (
    VoiceEngineV2CommandAudioSegment,
)


VOSK_COMMAND_ASR_RECOGNIZER_NAME = "vosk_command_asr"
VOSK_COMMAND_ASR_DISABLED_REASON = "vosk_command_asr_disabled"
VOSK_COMMAND_ASR_SEGMENT_NOT_READY_REASON = "vosk_command_asr_segment_not_ready"
VOSK_COMMAND_ASR_PCM_UNAVAILABLE_REASON = "vosk_command_asr_pcm_unavailable"
VOSK_COMMAND_ASR_SEGMENT_TOO_LONG_REASON = "vosk_command_asr_segment_too_long"
VOSK_COMMAND_ASR_PROVIDER_ERROR_REASON = "vosk_command_asr_provider_error"
VOSK_COMMAND_ASR_NOT_RECOGNIZED_REASON_PREFIX = "vosk_command_asr_not_recognized"

SegmentPcmProvider = Callable[[VoiceEngineV2CommandAudioSegment], bytes | None]


@dataclass(frozen=True, slots=True)
class VoskCommandAsrAdapterSettings:
    enabled: bool = False
    max_audio_duration_ms: float = 2_500.0
    recognizer_name: str = VOSK_COMMAND_ASR_RECOGNIZER_NAME

    def __post_init__(self) -> None:
        if self.max_audio_duration_ms <= 0:
            raise ValueError("max_audio_duration_ms must be greater than zero")
        if not self.recognizer_name.strip():
            raise ValueError("recognizer_name must not be empty")


class VoskCommandAsrAdapter:
    """Guarded runtime adapter around the device-level Vosk command recognizer.

    Stage 24S keeps this adapter disabled by default and does not connect it to
    live runtime. Tests may inject a PCM provider to verify the mapping contract
    without starting a microphone stream or loading a real Vosk model.
    """

    def __init__(
        self,
        *,
        settings: VoskCommandAsrAdapterSettings | None = None,
        recognizer: VoskCommandRecognizer | None = None,
        segment_pcm_provider: SegmentPcmProvider | None = None,
    ) -> None:
        self._settings = settings or VoskCommandAsrAdapterSettings()
        self._recognizer = recognizer or VoskCommandRecognizer(
            grammar=build_default_command_grammar()
        )
        self._segment_pcm_provider = segment_pcm_provider

    @property
    def recognizer_name(self) -> str:
        return self._settings.recognizer_name

    @property
    def recognizer_enabled(self) -> bool:
        return self._settings.enabled

    @property
    def settings(self) -> VoskCommandAsrAdapterSettings:
        return self._settings

    def recognize(
        self,
        *,
        segment: VoiceEngineV2CommandAudioSegment,
    ) -> CommandAsrResult:
        if segment.action_executed:
            raise ValueError("Vosk command ASR adapter must never receive action execution")
        if segment.full_stt_prevented:
            raise ValueError("Vosk command ASR adapter must never receive full STT prevention")
        if segment.runtime_takeover:
            raise ValueError("Vosk command ASR adapter must never receive runtime takeover")

        if not self._settings.enabled:
            return self._not_attempted(
                recognizer_enabled=False,
                reason=VOSK_COMMAND_ASR_DISABLED_REASON,
            )

        if not segment.segment_present:
            return self._not_attempted(
                recognizer_enabled=True,
                reason=f"{VOSK_COMMAND_ASR_SEGMENT_NOT_READY_REASON}:{segment.reason}",
            )

        audio_duration_ms = segment.audio_duration_ms or 0.0
        if audio_duration_ms > self._settings.max_audio_duration_ms:
            return self._not_attempted(
                recognizer_enabled=True,
                reason=VOSK_COMMAND_ASR_SEGMENT_TOO_LONG_REASON,
            )

        if self._segment_pcm_provider is None:
            return self._not_attempted(
                recognizer_enabled=True,
                reason=VOSK_COMMAND_ASR_PCM_UNAVAILABLE_REASON,
            )

        pcm = self._segment_pcm_provider(segment)
        if not pcm:
            return self._not_attempted(
                recognizer_enabled=True,
                reason=VOSK_COMMAND_ASR_PCM_UNAVAILABLE_REASON,
            )

        try:
            recognition = self._recognizer.recognize_pcm(pcm)
        except RuntimeError as error:
            return self._not_attempted(
                recognizer_enabled=True,
                reason=f"{VOSK_COMMAND_ASR_PROVIDER_ERROR_REASON}:{error}",
            )

        return _map_recognition_result(
            recognizer_name=self.recognizer_name,
            recognition=recognition,
        )

    def reset(self) -> None:
        self._recognizer.reset()

    def _not_attempted(
        self,
        *,
        recognizer_enabled: bool,
        reason: str,
    ) -> CommandAsrResult:
        return CommandAsrResult(
            recognizer_name=self.recognizer_name,
            recognizer_enabled=recognizer_enabled,
            recognition_attempted=False,
            recognized=False,
            reason=reason,
            transcript="",
            normalized_text="",
            language=None,
            confidence=None,
            alternatives=(),
            action_executed=False,
            full_stt_prevented=False,
            runtime_takeover=False,
        )


def _map_recognition_result(
    *,
    recognizer_name: str,
    recognition: CommandRecognitionResult,
) -> CommandAsrResult:
    recognized = recognition.status is CommandRecognitionStatus.MATCHED
    reason = (
        "vosk_command_asr_recognized"
        if recognized
        else f"{VOSK_COMMAND_ASR_NOT_RECOGNIZED_REASON_PREFIX}:{recognition.status.value}"
    )

    return CommandAsrResult(
        recognizer_name=recognizer_name,
        recognizer_enabled=True,
        recognition_attempted=True,
        recognized=recognized,
        reason=reason,
        transcript=recognition.transcript,
        normalized_text=recognition.normalized_transcript,
        language=recognition.language.value,
        confidence=recognition.confidence,
        alternatives=recognition.alternatives,
        action_executed=False,
        full_stt_prevented=False,
        runtime_takeover=False,
    )


__all__ = [
    "SegmentPcmProvider",
    "VOSK_COMMAND_ASR_DISABLED_REASON",
    "VOSK_COMMAND_ASR_NOT_RECOGNIZED_REASON_PREFIX",
    "VOSK_COMMAND_ASR_PCM_UNAVAILABLE_REASON",
    "VOSK_COMMAND_ASR_PROVIDER_ERROR_REASON",
    "VOSK_COMMAND_ASR_RECOGNIZER_NAME",
    "VOSK_COMMAND_ASR_SEGMENT_NOT_READY_REASON",
    "VOSK_COMMAND_ASR_SEGMENT_TOO_LONG_REASON",
    "VoskCommandAsrAdapter",
    "VoskCommandAsrAdapterSettings",
]