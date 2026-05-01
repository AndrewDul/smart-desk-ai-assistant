from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

import numpy as np

from modules.devices.audio.command_asr import CommandLanguage
from modules.runtime.voice_engine_v2.command_audio_segment import (
    EXPECTED_PUBLISH_STAGE,
    EXPECTED_SOURCE,
    PCM_ENCODING,
    VoiceEngineV2CommandAudioSegment,
)
from modules.runtime.voice_engine_v2.vosk_command_asr_adapter import (
    VoskCommandAsrAdapter,
    VoskCommandAsrAdapterSettings,
)


@dataclass(frozen=True, slots=True)
class VoiceEngineV2VoskPreWhisperCandidateDecision:
    """Safe Vosk-before-Whisper command candidate decision."""

    attempted: bool
    accepted: bool
    reason: str
    transcript: str = ""
    normalized_text: str = ""
    language: str = ""
    confidence: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("reason must not be empty")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "candidate_stage": "vosk_pre_whisper_candidate",
            "candidate_version": "v1",
            "attempted": self.attempted,
            "accepted": self.accepted,
            "reason": self.reason,
            "transcript": self.transcript,
            "normalized_text": self.normalized_text,
            "language": self.language,
            "confidence": self.confidence,
            "raw_pcm_included": False,
            "action_executed": False,
            "runtime_takeover": False,
            "metadata": dict(self.metadata),
        }


class VoiceEngineV2VoskPreWhisperCandidateAdapter:
    """Try Vosk command recognition before FasterWhisper transcription.

    The adapter is fail-open. It never executes actions directly, never starts a
    microphone stream and never writes raw PCM to telemetry. When it cannot
    accept a safe allowlisted command, the caller must continue the normal
    FasterWhisper path.
    """

    def __init__(
        self,
        *,
        settings: Mapping[str, Any],
        runtime_candidate_adapter: Any | None = None,
        command_asr_adapter: Any | None = None,
    ) -> None:
        self._settings = settings
        self._runtime_candidate_adapter = runtime_candidate_adapter
        self._command_asr_adapter = command_asr_adapter

    def try_process_capture_window(
        self,
        *,
        audio: Any,
        turn_id: str,
        sample_rate: int,
        started_monotonic: float,
        speech_end_monotonic: float | None,
        capture_window_shadow_tap: Mapping[str, Any] | None = None,
        request_metadata: Mapping[str, Any] | None = None,
    ) -> VoiceEngineV2VoskPreWhisperCandidateDecision:
        voice_engine = self._voice_engine_config()
        safe, safety_reason = self._safe_to_run(voice_engine)
        if not safe:
            return self._not_attempted(f"not_safe:{safety_reason}")

        runtime_adapter = self._runtime_candidate_adapter
        process_vosk_shadow_result = getattr(
            runtime_adapter,
            "process_vosk_shadow_result",
            None,
        )
        if not callable(process_vosk_shadow_result):
            return self._not_attempted("runtime_candidate_adapter_unavailable")

        pcm, audio_sample_count, audio_duration_ms = self._audio_to_pcm_s16le(
            audio,
            sample_rate=sample_rate,
        )
        if not pcm:
            return self._not_attempted("pcm_unavailable")

        segment = VoiceEngineV2CommandAudioSegment(
            segment_present=True,
            reason="pre_whisper_capture_window_ready",
            turn_id=str(turn_id or self._fallback_turn_id()),
            hook="capture_window_pre_transcription",
            source=EXPECTED_SOURCE,
            publish_stage=EXPECTED_PUBLISH_STAGE,
            pcm_encoding=PCM_ENCODING,
            raw_pcm_included=False,
            sample_rate=int(sample_rate),
            channels=1,
            sample_width_bytes=2,
            audio_sample_count=audio_sample_count,
            audio_duration_ms=audio_duration_ms,
            published_frame_count=self._positive_int(
                (capture_window_shadow_tap or {}).get("published_frame_count")
            ),
            published_byte_count=len(pcm),
            endpoint_detected=True,
            readiness_ready=True,
            readiness_reason="pre_whisper_capture_window_ready",
            frames_processed=self._positive_int(
                (capture_window_shadow_tap or {}).get("published_frame_count"),
                fallback=1,
            ),
            speech_score_max=None,
            capture_finished_to_publish_start_ms=self._optional_float(
                (capture_window_shadow_tap or {}).get(
                    "capture_finished_to_publish_start_ms"
                )
            ),
            capture_finished_to_vad_observed_ms=None,
            capture_window_publish_to_vad_observed_ms=None,
            candidate_reason="pre_whisper_capture_window_ready",
            metadata_keys=tuple(sorted((capture_window_shadow_tap or {}).keys())),
            action_executed=False,
            full_stt_prevented=False,
            runtime_takeover=False,
        )

        command_asr = self._command_asr_adapter_for_pcm(
            pcm=pcm,
            sample_rate=sample_rate,
            voice_engine=voice_engine,
        )

        try:
            asr_result = command_asr.recognize(segment=segment)
        except Exception as error:
            return self._not_attempted(
                f"vosk_command_asr_failed:{type(error).__name__}",
                metadata={"error": str(error)},
            )

        result_metadata = self._asr_result_to_metadata(
            asr_result,
            segment=segment,
        )

        try:
            runtime_result = process_vosk_shadow_result(
                turn_id=str(turn_id or self._fallback_turn_id()),
                result_metadata=result_metadata,
                started_monotonic=started_monotonic,
                speech_end_monotonic=speech_end_monotonic,
                metadata={
                    **dict(request_metadata or {}),
                    "source": "vosk_pre_whisper_candidate",
                    "capture_backend": "faster_whisper",
                    "candidate_stage": "vosk_pre_whisper_candidate",
                },
            )
        except Exception as error:
            return self._not_attempted(
                f"runtime_candidate_failed:{type(error).__name__}",
                metadata={
                    "error": str(error),
                    "vosk_shadow_result": result_metadata,
                },
            )

        accepted = bool(getattr(runtime_result, "accepted", False))
        runtime_reason = str(getattr(runtime_result, "reason", "") or "")

        transcript = str(result_metadata.get("transcript", "") or "").strip()
        normalized_text = str(result_metadata.get("normalized_text", "") or "").strip()
        language = str(result_metadata.get("language", "") or "").strip()
        confidence = self._safe_float(result_metadata.get("confidence"), fallback=0.0)

        return VoiceEngineV2VoskPreWhisperCandidateDecision(
            attempted=True,
            accepted=accepted,
            reason="accepted" if accepted else runtime_reason or "rejected",
            transcript=transcript,
            normalized_text=normalized_text,
            language=language,
            confidence=confidence,
            metadata={
                "runtime_candidate_accepted": accepted,
                "runtime_candidate_reason": runtime_reason,
                "vosk_shadow_result": result_metadata,
                "capture_window_shadow_tap": self._safe_capture_window_summary(
                    capture_window_shadow_tap or {}
                ),
            },
        )

    def _command_asr_adapter_for_pcm(
        self,
        *,
        pcm: bytes,
        sample_rate: int,
        voice_engine: Mapping[str, Any],
    ) -> VoskCommandAsrAdapter:
        if self._command_asr_adapter is not None:
            return self._command_asr_adapter

        model_paths = voice_engine.get("vosk_command_model_paths", {})
        if not isinstance(model_paths, Mapping):
            model_paths = {}

        english_model_path = str(
            model_paths.get("en")
            or voice_engine.get(
                "vosk_command_english_model_path",
                "var/models/vosk/vosk-model-small-en-us-0.15",
            )
        )
        polish_model_path = str(
            model_paths.get("pl")
            or voice_engine.get(
                "vosk_command_polish_model_path",
                "var/models/vosk/vosk-model-small-pl-0.22",
            )
        )
        configured_sample_rate = self._positive_int(
            voice_engine.get("vosk_command_sample_rate"),
            fallback=sample_rate,
        )

        try:
            from modules.devices.audio.command_asr import BilingualVoskCommandRecognizer
        except ImportError:
            from modules.devices.audio.command_asr.bilingual_vosk_command_recognizer import (
                BilingualVoskCommandRecognizer,
            )

        recognizer = BilingualVoskCommandRecognizer(
            english_model_path=english_model_path,
            polish_model_path=polish_model_path,
            sample_rate=configured_sample_rate,
        )

        return VoskCommandAsrAdapter(
            settings=VoskCommandAsrAdapterSettings(enabled=True),
            recognizer=recognizer,
            segment_pcm_provider=lambda segment: pcm,
        )

    @staticmethod
    def _audio_to_pcm_s16le(
        audio: Any,
        *,
        sample_rate: int,
    ) -> tuple[bytes, int, float]:
        if audio is None:
            return b"", 0, 0.0

        array = np.asarray(audio)
        if array.size <= 0:
            return b"", 0, 0.0

        if array.ndim > 1:
            array = np.mean(array, axis=1)

        if array.dtype == np.int16:
            int16_audio = np.ascontiguousarray(array.astype(np.int16, copy=False))
        else:
            float_audio = np.asarray(array, dtype=np.float32)
            max_abs = float(np.max(np.abs(float_audio))) if float_audio.size else 0.0
            if max_abs <= 1.5:
                int16_audio = np.clip(float_audio, -1.0, 1.0)
                int16_audio = np.ascontiguousarray((int16_audio * 32767.0).astype(np.int16))
            else:
                int16_audio = np.clip(float_audio, -32768.0, 32767.0)
                int16_audio = np.ascontiguousarray(int16_audio.astype(np.int16))

        sample_count = int(int16_audio.size)
        if sample_count <= 0:
            return b"", 0, 0.0

        duration_ms = (sample_count / float(max(1, int(sample_rate)))) * 1000.0
        return int16_audio.tobytes(order="C"), sample_count, round(duration_ms, 3)

    def _asr_result_to_metadata(
        self,
        asr_result: Any,
        *,
        segment: VoiceEngineV2CommandAudioSegment,
    ) -> dict[str, Any]:
        recognized = bool(getattr(asr_result, "recognized", False))
        recognition_attempted = bool(
            getattr(asr_result, "recognition_attempted", False)
        )

        return {
            "result_stage": "vosk_shadow_asr_result",
            "result_version": "vosk_shadow_asr_result_v1",
            "enabled": True,
            "result_present": True,
            "reason": str(getattr(asr_result, "reason", "") or ""),
            "metadata_key": "vosk_shadow_asr_result",
            "recognizer_name": str(
                getattr(asr_result, "recognizer_name", "vosk_command_asr") or ""
            ),
            "recognizer_enabled": bool(
                getattr(asr_result, "recognizer_enabled", True)
            ),
            "recognition_invocation_performed": recognition_attempted,
            "recognition_attempted": recognition_attempted,
            "recognized": recognized,
            "command_matched": recognized,
            "intent_key": str(getattr(asr_result, "intent_key", "") or ""),
            "matched_phrase": str(getattr(asr_result, "matched_phrase", "") or ""),
            "transcript": str(getattr(asr_result, "transcript", "") or ""),
            "normalized_text": str(
                getattr(asr_result, "normalized_text", "") or ""
            ),
            "language": str(getattr(asr_result, "language", "") or ""),
            "confidence": self._optional_float(
                getattr(asr_result, "confidence", None)
            ),
            "alternatives": list(getattr(asr_result, "alternatives", ()) or ()),
            "turn_id": segment.turn_id,
            "hook": segment.hook,
            "source": segment.source,
            "publish_stage": segment.publish_stage,
            "segment_present": segment.segment_present,
            "segment_reason": segment.reason,
            "segment_audio_duration_ms": segment.audio_duration_ms,
            "segment_audio_sample_count": segment.audio_sample_count,
            "segment_published_byte_count": segment.published_byte_count,
            "segment_sample_rate": segment.sample_rate,
            "segment_pcm_encoding": segment.pcm_encoding,
            "pcm_retrieval_performed": True,
            "raw_pcm_included": False,
            "action_executed": False,
            "full_stt_prevented": False,
            "runtime_takeover": False,
            "runtime_integration": False,
            "command_execution_enabled": False,
            "faster_whisper_bypass_enabled": False,
            "microphone_stream_started": False,
            "independent_microphone_stream_started": False,
            "live_command_recognition_enabled": False,
        }

    def _voice_engine_config(self) -> Mapping[str, Any]:
        raw = self._settings.get("voice_engine", {})
        return raw if isinstance(raw, Mapping) else {}

    @staticmethod
    def _safe_to_run(voice_engine: Mapping[str, Any]) -> tuple[bool, str]:
        if bool(voice_engine.get("enabled", False)):
            return False, "voice_engine_enabled_must_remain_false"
        if str(voice_engine.get("mode", "legacy") or "legacy").strip().lower() != "legacy":
            return False, "voice_engine_mode_must_remain_legacy"
        if bool(voice_engine.get("command_first_enabled", False)):
            return False, "command_first_enabled_must_remain_false"
        if not bool(voice_engine.get("fallback_to_legacy_enabled", True)):
            return False, "fallback_to_legacy_enabled_must_remain_true"
        if not bool(voice_engine.get("runtime_candidates_enabled", False)):
            return False, "runtime_candidates_disabled"
        if not bool(voice_engine.get("vosk_pre_whisper_candidate_enabled", False)):
            return False, "vosk_pre_whisper_candidate_disabled"
        return True, "safe"

    @staticmethod
    def _safe_capture_window_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
        allowed_keys = (
            "enabled",
            "attached",
            "published",
            "reason",
            "source",
            "publish_stage",
            "sample_rate",
            "chunk_sample_count",
            "audio_sample_count",
            "audio_duration_seconds",
            "published_frame_count",
            "published_byte_count",
            "capture_finished_to_publish_start_ms",
            "publish_error_count",
            "publish_errors",
            "conversion_reason",
        )
        return {key: payload.get(key) for key in allowed_keys if key in payload}

    @staticmethod
    def _not_attempted(
        reason: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> VoiceEngineV2VoskPreWhisperCandidateDecision:
        return VoiceEngineV2VoskPreWhisperCandidateDecision(
            attempted=False,
            accepted=False,
            reason=reason,
            metadata=dict(metadata or {}),
        )

    @staticmethod
    def _fallback_turn_id() -> str:
        return f"vosk-pre-whisper-{time.monotonic_ns()}"

    @staticmethod
    def _positive_int(raw_value: Any, *, fallback: int = 0) -> int:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            value = int(fallback)
        return max(0, value)

    @staticmethod
    def _safe_float(raw_value: Any, *, fallback: float = 0.0) -> float:
        value = VoiceEngineV2VoskPreWhisperCandidateAdapter._optional_float(raw_value)
        if value is None:
            return float(fallback)
        return float(value)

    @staticmethod
    def _optional_float(raw_value: Any) -> float | None:
        if raw_value is None:
            return None
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            return None


def build_voice_engine_v2_vosk_pre_whisper_candidate_adapter(
    *,
    settings: Mapping[str, Any],
    runtime_candidate_adapter: Any | None = None,
) -> VoiceEngineV2VoskPreWhisperCandidateAdapter:
    return VoiceEngineV2VoskPreWhisperCandidateAdapter(
        settings=settings,
        runtime_candidate_adapter=runtime_candidate_adapter,
    )


__all__ = [
    "VoiceEngineV2VoskPreWhisperCandidateAdapter",
    "VoiceEngineV2VoskPreWhisperCandidateDecision",
    "build_voice_engine_v2_vosk_pre_whisper_candidate_adapter",
]
