from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from modules.devices.audio.realtime import AudioBus
from modules.devices.audio.realtime.audio_frame import AudioFrame
from modules.devices.audio.vad import (
    EndpointingPolicy,
    EndpointingPolicyConfig,
    SileroVadEngine,
    VadDecision,
    VadEvent,
)
from modules.runtime.voice_engine_v2.realtime_audio_bus_probe import (
    find_realtime_audio_bus,
)


VadScoreProviderFactory = Callable[[], Callable[[AudioFrame], float]]


@dataclass(frozen=True, slots=True)
class VoiceEngineV2VadShadowSnapshot:
    enabled: bool
    observed: bool
    reason: str
    audio_bus_present: bool
    source: str
    frames_processed: int = 0
    decisions_processed: int = 0
    events_emitted: int = 0
    latest_frame_sequence: int | None = None
    latest_event_type: str = ""
    in_speech: bool = False
    speech_started_count: int = 0
    speech_ended_count: int = 0
    min_speech_ms: int = 0
    min_silence_ms: int = 0
    speech_threshold: float = 0.0
    action_executed: bool = False
    full_stt_prevented: bool = False
    runtime_takeover: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def __post_init__(self) -> None:
        if self.action_executed:
            raise ValueError("VAD shadow must never execute actions")
        if self.full_stt_prevented:
            raise ValueError("VAD shadow must never prevent full STT")
        if self.runtime_takeover:
            raise ValueError("VAD shadow must never take over runtime")

        object.__setattr__(self, "events", list(self.events or []))

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "observed": self.observed,
            "reason": self.reason,
            "audio_bus_present": self.audio_bus_present,
            "source": self.source,
            "frames_processed": self.frames_processed,
            "decisions_processed": self.decisions_processed,
            "events_emitted": self.events_emitted,
            "latest_frame_sequence": self.latest_frame_sequence,
            "latest_event_type": self.latest_event_type,
            "in_speech": self.in_speech,
            "speech_started_count": self.speech_started_count,
            "speech_ended_count": self.speech_ended_count,
            "min_speech_ms": self.min_speech_ms,
            "min_silence_ms": self.min_silence_ms,
            "speech_threshold": self.speech_threshold,
            "action_executed": self.action_executed,
            "full_stt_prevented": self.full_stt_prevented,
            "runtime_takeover": self.runtime_takeover,
            "events": list(self.events),
            "error": self.error,
        }


class SileroOnnxVadScoreProvider:
    """Lazy Silero VAD ONNX score provider for shadow endpointing."""

    def __init__(
        self,
        *,
        speech_threshold: float,
        min_speech_ms: int,
        min_silence_ms: int,
        speech_pad_ms: int = 0,
    ) -> None:
        self._speech_threshold = speech_threshold
        self._min_speech_ms = min_speech_ms
        self._min_silence_ms = min_silence_ms
        self._speech_pad_ms = speech_pad_ms
        self._model: Any | None = None
        self._get_speech_timestamps: Any | None = None

    def __call__(self, frame: AudioFrame) -> float:
        self._ensure_loaded()

        if frame.channels != 1:
            raise ValueError("Silero VAD shadow supports mono PCM only")
        if frame.sample_width_bytes != 2:
            raise ValueError("Silero VAD shadow supports int16 PCM only")
        if frame.sample_rate not in {8_000, 16_000}:
            raise ValueError("Silero VAD shadow supports 8 kHz or 16 kHz audio only")

        audio = np.frombuffer(frame.pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size == 0:
            return 0.0

        timestamps = self._get_speech_timestamps(
            audio,
            self._model,
            sampling_rate=frame.sample_rate,
            threshold=self._speech_threshold,
            min_speech_duration_ms=self._min_speech_ms,
            min_silence_duration_ms=self._min_silence_ms,
            speech_pad_ms=self._speech_pad_ms,
        )
        return 1.0 if timestamps else 0.0

    def _ensure_loaded(self) -> None:
        if self._model is not None and self._get_speech_timestamps is not None:
            return

        from silero_vad import get_speech_timestamps, load_silero_vad

        self._model = load_silero_vad(onnx=True)
        self._get_speech_timestamps = get_speech_timestamps


class VoiceEngineV2VadShadowObserver:
    """Observe-only VAD endpointing over RealtimeAudioBus frames."""

    def __init__(
        self,
        *,
        enabled: bool,
        speech_threshold: float = 0.5,
        endpointing_policy_config: EndpointingPolicyConfig | None = None,
        max_frames_per_observation: int = 96,
        score_provider_factory: VadScoreProviderFactory | None = None,
    ) -> None:
        self._enabled = bool(enabled)
        self._speech_threshold = _bounded_float(
            speech_threshold,
            fallback=0.5,
            minimum=0.0,
            maximum=1.0,
        )
        self._endpointing_policy_config = (
            endpointing_policy_config or EndpointingPolicyConfig()
        )
        self._max_frames_per_observation = max(int(max_frames_per_observation), 1)
        self._score_provider_factory = (
            score_provider_factory or self._build_default_score_provider
        )

        self._audio_bus_id: int | None = None
        self._subscription: Any | None = None
        self._policy = EndpointingPolicy(self._endpointing_policy_config)
        self._engine: SileroVadEngine | None = None
        self._engine_error: str = ""

    @property
    def enabled(self) -> bool:
        return self._enabled

    def observe(self, owner: Any) -> VoiceEngineV2VadShadowSnapshot:
        if not self._enabled:
            return self._snapshot(
                observed=False,
                reason="vad_shadow_disabled",
                audio_bus_present=False,
                source="",
            )

        audio_bus, source = find_realtime_audio_bus(owner)
        if audio_bus is None:
            return self._snapshot(
                observed=False,
                reason="audio_bus_unavailable_for_vad_shadow",
                audio_bus_present=False,
                source="",
            )

        try:
            self._ensure_subscription(audio_bus)
            engine = self._ensure_engine()
            frames = self._subscription.read_available(
                max_frames=self._max_frames_per_observation
            )
            if not frames:
                return self._snapshot(
                    observed=True,
                    reason="no_new_audio_frames_observe_only",
                    audio_bus_present=True,
                    source=source,
                    in_speech=self._policy.in_speech,
                )

            decisions: list[VadDecision] = []
            events: list[VadEvent] = []
            for frame in frames:
                decision = engine.score_frame(frame)
                decisions.append(decision)
                events.extend(self._policy.process(decision))

            return self._snapshot(
                observed=True,
                reason="vad_shadow_observed_audio",
                audio_bus_present=True,
                source=source,
                frames_processed=len(frames),
                decisions_processed=len(decisions),
                events=events,
                latest_frame_sequence=frames[-1].sequence,
                in_speech=self._policy.in_speech,
            )

        except ModuleNotFoundError as error:
            self._engine_error = f"{type(error).__name__}:{error}"
            return self._snapshot(
                observed=False,
                reason="silero_vad_unavailable_observe_only",
                audio_bus_present=True,
                source=source,
                error=self._engine_error,
            )
        except Exception as error:
            return self._snapshot(
                observed=False,
                reason=f"vad_shadow_failed:{type(error).__name__}",
                audio_bus_present=True,
                source=source,
                error=str(error),
            )

    def reset(self) -> None:
        self._audio_bus_id = None
        self._subscription = None
        self._policy.reset()
        if self._engine is not None:
            self._engine.reset()

    def _ensure_subscription(self, audio_bus: AudioBus) -> None:
        audio_bus_id = id(audio_bus)
        if self._subscription is not None and self._audio_bus_id == audio_bus_id:
            return

        self._audio_bus_id = audio_bus_id
        self._subscription = audio_bus.create_subscription(
            "voice_engine_v2_vad_shadow",
            start_at_latest=False,
        )
        self._policy.reset()
        if self._engine is not None:
            self._engine.reset()

    def _ensure_engine(self) -> SileroVadEngine:
        if self._engine is not None:
            return self._engine

        score_provider = self._score_provider_factory()
        self._engine = SileroVadEngine(
            score_provider=score_provider,
            speech_threshold=self._speech_threshold,
        )
        return self._engine

    def _build_default_score_provider(self) -> Callable[[AudioFrame], float]:
        return SileroOnnxVadScoreProvider(
            speech_threshold=self._speech_threshold,
            min_speech_ms=self._endpointing_policy_config.min_speech_ms,
            min_silence_ms=self._endpointing_policy_config.min_silence_ms,
        )

    def _snapshot(
        self,
        *,
        observed: bool,
        reason: str,
        audio_bus_present: bool,
        source: str,
        frames_processed: int = 0,
        decisions_processed: int = 0,
        events: list[VadEvent] | None = None,
        latest_frame_sequence: int | None = None,
        in_speech: bool = False,
        error: str = "",
    ) -> VoiceEngineV2VadShadowSnapshot:
        safe_events = list(events or [])
        serialized_events = [_event_to_json_dict(event) for event in safe_events]

        speech_started_count = sum(
            1 for event in safe_events if str(event.event_type.value) == "speech_started"
        )
        speech_ended_count = sum(
            1 for event in safe_events if str(event.event_type.value) == "speech_ended"
        )

        latest_event_type = ""
        if safe_events:
            latest_event_type = str(safe_events[-1].event_type.value)

        return VoiceEngineV2VadShadowSnapshot(
            enabled=self._enabled,
            observed=observed,
            reason=reason,
            audio_bus_present=audio_bus_present,
            source=source,
            frames_processed=frames_processed,
            decisions_processed=decisions_processed,
            events_emitted=len(safe_events),
            latest_frame_sequence=latest_frame_sequence,
            latest_event_type=latest_event_type,
            in_speech=in_speech,
            speech_started_count=speech_started_count,
            speech_ended_count=speech_ended_count,
            min_speech_ms=self._endpointing_policy_config.min_speech_ms,
            min_silence_ms=self._endpointing_policy_config.min_silence_ms,
            speech_threshold=self._speech_threshold,
            events=serialized_events,
            error=error,
        )


def build_voice_engine_v2_vad_shadow_observer(
    settings: Mapping[str, Any],
) -> VoiceEngineV2VadShadowObserver:
    voice_engine_cfg = _voice_engine_config(settings)

    min_speech_ms = _positive_int(
        voice_engine_cfg.get("vad_shadow_min_speech_ms"),
        fallback=120,
    )
    min_silence_ms = _positive_int(
        voice_engine_cfg.get("vad_shadow_min_silence_ms"),
        fallback=250,
    )

    return VoiceEngineV2VadShadowObserver(
        enabled=bool(voice_engine_cfg.get("vad_shadow_enabled", False)),
        speech_threshold=_bounded_float(
            voice_engine_cfg.get("vad_shadow_speech_threshold"),
            fallback=0.5,
            minimum=0.0,
            maximum=1.0,
        ),
        endpointing_policy_config=EndpointingPolicyConfig(
            min_speech_ms=min_speech_ms,
            min_silence_ms=min_silence_ms,
            emit_continued_events=False,
        ),
        max_frames_per_observation=_positive_int(
            voice_engine_cfg.get("vad_shadow_max_frames_per_observation"),
            fallback=96,
        ),
    )


def _event_to_json_dict(event: VadEvent) -> dict[str, Any]:
    return {
        "event_type": str(event.event_type.value),
        "timestamp_monotonic": event.timestamp_monotonic,
        "frame_sequence": event.frame_sequence,
        "speech_start_timestamp": event.speech_start_timestamp,
        "speech_end_timestamp": event.speech_end_timestamp,
        "speech_duration_seconds": event.speech_duration_seconds,
        "silence_duration_seconds": event.silence_duration_seconds,
        "score": event.score,
    }


def _voice_engine_config(settings: Mapping[str, Any]) -> Mapping[str, Any]:
    voice_engine_cfg = settings.get("voice_engine", {})
    if isinstance(voice_engine_cfg, Mapping):
        return voice_engine_cfg
    return {}


def _positive_int(raw_value: Any, *, fallback: int) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


def _bounded_float(
    raw_value: Any,
    *,
    fallback: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return fallback
    if value < minimum or value > maximum:
        return fallback
    return value


__all__ = [
    "SileroOnnxVadScoreProvider",
    "VoiceEngineV2VadShadowObserver",
    "VoiceEngineV2VadShadowSnapshot",
    "build_voice_engine_v2_vad_shadow_observer",
]