from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
import time
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
    speech_frame_count: int = 0
    silence_frame_count: int = 0
    speech_score_count: int = 0
    speech_score_min: float | None = None
    speech_score_max: float | None = None
    speech_score_avg: float | None = None
    speech_score_over_threshold_count: int = 0
    latest_score: float | None = None
    observation_started_monotonic: float | None = None
    observation_completed_monotonic: float | None = None
    observation_duration_ms: float | None = None
    first_frame_timestamp_monotonic: float | None = None
    last_frame_timestamp_monotonic: float | None = None
    last_frame_end_timestamp_monotonic: float | None = None
    last_frame_age_ms: float | None = None
    audio_window_duration_ms: float | None = None
    latest_speech_started_lag_ms: float | None = None
    latest_speech_ended_lag_ms: float | None = None
    latest_speech_end_to_observe_ms: float | None = None
    audio_bus_latest_sequence: int | None = None
    audio_bus_frame_count: int | None = None
    audio_bus_duration_seconds: float | None = None
    subscription_next_sequence_before: int | None = None
    subscription_next_sequence_after: int | None = None
    subscription_backlog_frames: int | None = None
    stale_audio_threshold_ms: float = 1000.0
    stale_audio_observed: bool = False
    cadence_diagnostic_reason: str = ""
    score_profile_sample_count: int = 0
    score_profile_first_scores: list[float] = field(default_factory=list)
    score_profile_middle_scores: list[float] = field(default_factory=list)
    score_profile_last_scores: list[float] = field(default_factory=list)
    score_profile_peak_score: float | None = None
    score_profile_peak_index: int | None = None
    score_profile_peak_sequence: int | None = None
    score_profile_peak_position_ratio: float | None = None
    score_profile_peak_bucket: str = ""
    score_profile_peak_frame_source: str = ""
    score_profile_peak_frame_age_ms: float | None = None
    frame_source_counts: dict[str, int] = field(default_factory=dict)
    pcm_profile_frame_count: int = 0
    pcm_profile_sample_width_bytes: int | None = None
    pcm_profile_total_byte_count: int = 0
    pcm_profile_total_sample_count: int = 0
    pcm_profile_rms: float | None = None
    pcm_profile_mean_abs: float | None = None
    pcm_profile_peak_abs: float | None = None
    pcm_profile_zero_ratio: float | None = None
    pcm_profile_near_zero_ratio: float | None = None
    pcm_profile_clipping_ratio: float | None = None
    pcm_profile_signal_level: str = ""
    pcm_profile_first_frame_rms: float | None = None
    pcm_profile_first_frame_peak_abs: float | None = None
    pcm_profile_middle_frame_rms: float | None = None
    pcm_profile_middle_frame_peak_abs: float | None = None
    pcm_profile_last_frame_rms: float | None = None
    pcm_profile_last_frame_peak_abs: float | None = None
    pcm_profile_peak_frame_index: int | None = None
    pcm_profile_peak_frame_sequence: int | None = None
    pcm_profile_peak_frame_source: str = ""
    pcm_profile_peak_frame_rms: float | None = None
    pcm_profile_peak_frame_peak_abs: float | None = None
    pcm_profile_peak_frame_zero_ratio: float | None = None
    pcm_profile_peak_frame_age_ms: float | None = None
    event_emission_reason: str = ""
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
            "speech_frame_count": self.speech_frame_count,
            "silence_frame_count": self.silence_frame_count,
            "speech_score_count": self.speech_score_count,
            "speech_score_min": self.speech_score_min,
            "speech_score_max": self.speech_score_max,
            "speech_score_avg": self.speech_score_avg,
            "speech_score_over_threshold_count": self.speech_score_over_threshold_count,
            "latest_score": self.latest_score,
            "observation_started_monotonic": self.observation_started_monotonic,
            "observation_completed_monotonic": self.observation_completed_monotonic,
            "observation_duration_ms": self.observation_duration_ms,
            "first_frame_timestamp_monotonic": self.first_frame_timestamp_monotonic,
            "last_frame_timestamp_monotonic": self.last_frame_timestamp_monotonic,
            "last_frame_end_timestamp_monotonic": self.last_frame_end_timestamp_monotonic,
            "last_frame_age_ms": self.last_frame_age_ms,
            "audio_window_duration_ms": self.audio_window_duration_ms,
            "latest_speech_started_lag_ms": self.latest_speech_started_lag_ms,
            "latest_speech_ended_lag_ms": self.latest_speech_ended_lag_ms,
            "latest_speech_end_to_observe_ms": self.latest_speech_end_to_observe_ms,
            "audio_bus_latest_sequence": self.audio_bus_latest_sequence,
            "audio_bus_frame_count": self.audio_bus_frame_count,
            "audio_bus_duration_seconds": self.audio_bus_duration_seconds,
            "subscription_next_sequence_before": self.subscription_next_sequence_before,
            "subscription_next_sequence_after": self.subscription_next_sequence_after,
            "subscription_backlog_frames": self.subscription_backlog_frames,
            "stale_audio_threshold_ms": self.stale_audio_threshold_ms,
            "stale_audio_observed": self.stale_audio_observed,
            "cadence_diagnostic_reason": self.cadence_diagnostic_reason,
            "score_profile_sample_count": self.score_profile_sample_count,
            "score_profile_first_scores": list(self.score_profile_first_scores),
            "score_profile_middle_scores": list(self.score_profile_middle_scores),
            "score_profile_last_scores": list(self.score_profile_last_scores),
            "score_profile_peak_score": self.score_profile_peak_score,
            "score_profile_peak_index": self.score_profile_peak_index,
            "score_profile_peak_sequence": self.score_profile_peak_sequence,
            "score_profile_peak_position_ratio": self.score_profile_peak_position_ratio,
            "score_profile_peak_bucket": self.score_profile_peak_bucket,
            "score_profile_peak_frame_source": self.score_profile_peak_frame_source,
            "score_profile_peak_frame_age_ms": self.score_profile_peak_frame_age_ms,
            "frame_source_counts": dict(self.frame_source_counts),
            "pcm_profile_frame_count": self.pcm_profile_frame_count,
            "pcm_profile_sample_width_bytes": self.pcm_profile_sample_width_bytes,
            "pcm_profile_total_byte_count": self.pcm_profile_total_byte_count,
            "pcm_profile_total_sample_count": self.pcm_profile_total_sample_count,
            "pcm_profile_rms": self.pcm_profile_rms,
            "pcm_profile_mean_abs": self.pcm_profile_mean_abs,
            "pcm_profile_peak_abs": self.pcm_profile_peak_abs,
            "pcm_profile_zero_ratio": self.pcm_profile_zero_ratio,
            "pcm_profile_near_zero_ratio": self.pcm_profile_near_zero_ratio,
            "pcm_profile_clipping_ratio": self.pcm_profile_clipping_ratio,
            "pcm_profile_signal_level": self.pcm_profile_signal_level,
            "pcm_profile_first_frame_rms": self.pcm_profile_first_frame_rms,
            "pcm_profile_first_frame_peak_abs": self.pcm_profile_first_frame_peak_abs,
            "pcm_profile_middle_frame_rms": self.pcm_profile_middle_frame_rms,
            "pcm_profile_middle_frame_peak_abs": self.pcm_profile_middle_frame_peak_abs,
            "pcm_profile_last_frame_rms": self.pcm_profile_last_frame_rms,
            "pcm_profile_last_frame_peak_abs": self.pcm_profile_last_frame_peak_abs,
            "pcm_profile_peak_frame_index": self.pcm_profile_peak_frame_index,
            "pcm_profile_peak_frame_sequence": self.pcm_profile_peak_frame_sequence,
            "pcm_profile_peak_frame_source": self.pcm_profile_peak_frame_source,
            "pcm_profile_peak_frame_rms": self.pcm_profile_peak_frame_rms,
            "pcm_profile_peak_frame_peak_abs": self.pcm_profile_peak_frame_peak_abs,
            "pcm_profile_peak_frame_zero_ratio": self.pcm_profile_peak_frame_zero_ratio,
            "pcm_profile_peak_frame_age_ms": self.pcm_profile_peak_frame_age_ms,
            "event_emission_reason": self.event_emission_reason,
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
    """Lazy Silero VAD ONNX probability provider for shadow endpointing.

    Silero streaming scoring expects fixed-size audio windows: 512 samples at
    16 kHz or 256 samples at 8 kHz. RealtimeAudioBus frames can be larger than
    one Silero window, so this provider scores every complete window in the
    frame and returns the maximum speech probability for the frame-level
    endpointing policy.
    """

    _WINDOW_SAMPLES_BY_SAMPLE_RATE = {
        8_000: 256,
        16_000: 512,
    }

    def __init__(self) -> None:
        self._model: Any | None = None
        self._torch: Any | None = None

    def __call__(self, frame: AudioFrame) -> float:
        self._ensure_loaded()

        if frame.channels != 1:
            raise ValueError("Silero VAD shadow supports mono PCM only")
        if frame.sample_width_bytes != 2:
            raise ValueError("Silero VAD shadow supports int16 PCM only")

        window_samples = self._window_samples_for(frame.sample_rate)
        audio = np.frombuffer(frame.pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size < window_samples:
            return 0.0

        scores = [
            self._score_window(audio[start : start + window_samples], frame.sample_rate)
            for start in range(0, audio.size - window_samples + 1, window_samples)
        ]
        return max(scores) if scores else 0.0

    def _ensure_loaded(self) -> None:
        if self._model is not None and self._torch is not None:
            return

        import torch
        from silero_vad import load_silero_vad

        self._torch = torch
        if self._model is None:
            self._model = load_silero_vad(onnx=True)

    def _score_window(self, audio: np.ndarray, sample_rate: int) -> float:
        if self._model is None:
            raise RuntimeError("Silero VAD model is not loaded")

        audio_tensor = self._window_to_tensor(audio)
        no_grad = getattr(self._torch, "no_grad", None)

        if callable(no_grad):
            with no_grad():
                raw_probability = self._model(audio_tensor, sample_rate)
        else:
            raw_probability = self._model(audio_tensor, sample_rate)

        score = _coerce_probability(raw_probability)
        if not 0.0 <= score <= 1.0:
            raise ValueError("Silero VAD score must be between 0.0 and 1.0")
        return score

    def _window_to_tensor(self, audio: np.ndarray) -> Any:
        if self._torch is None:
            import torch

            self._torch = torch

        contiguous_audio = np.ascontiguousarray(audio, dtype=np.float32)
        return self._torch.from_numpy(contiguous_audio)

    @classmethod
    def _window_samples_for(cls, sample_rate: int) -> int:
        try:
            return cls._WINDOW_SAMPLES_BY_SAMPLE_RATE[sample_rate]
        except KeyError as error:
            raise ValueError(
                "Silero VAD shadow supports 8 kHz or 16 kHz audio only"
            ) from error


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

    def arm(
        self,
        owner: Any,
        *,
        subscription_name: str = "voice_engine_v2_vad_shadow",
        start_at_latest: bool = True,
    ) -> VoiceEngineV2VadShadowSnapshot:
        observation_started_monotonic = time.monotonic()

        if not self._enabled:
            return self._snapshot(
                observed=False,
                reason="vad_shadow_disabled",
                audio_bus_present=False,
                source="",
                observation_started_monotonic=observation_started_monotonic,
            )

        audio_bus, source = find_realtime_audio_bus(owner)
        if audio_bus is None:
            return self._snapshot(
                observed=False,
                reason="audio_bus_unavailable_for_vad_shadow",
                audio_bus_present=False,
                source="",
                observation_started_monotonic=observation_started_monotonic,
            )

        try:
            self._reset_subscription(
                audio_bus,
                subscription_name=subscription_name,
                start_at_latest=start_at_latest,
            )
            next_sequence = (
                self._subscription.next_sequence
                if self._subscription is not None
                else None
            )
            return self._snapshot(
                observed=True,
                reason="vad_shadow_armed_observe_only",
                audio_bus_present=True,
                source=source,
                in_speech=self._policy.in_speech,
                observation_started_monotonic=observation_started_monotonic,
                audio_bus_latest_sequence=audio_bus.latest_sequence,
                audio_bus_frame_count=audio_bus.frame_count,
                audio_bus_duration_seconds=audio_bus.duration_seconds,
                subscription_next_sequence_before=next_sequence,
                subscription_next_sequence_after=next_sequence,
            )
        except Exception as error:
            return self._snapshot(
                observed=False,
                reason=f"vad_shadow_arm_failed:{type(error).__name__}",
                audio_bus_present=True,
                source=source,
                error=str(error),
                observation_started_monotonic=observation_started_monotonic,
            )

    def observe(self, owner: Any) -> VoiceEngineV2VadShadowSnapshot:
        observation_started_monotonic = time.monotonic()

        if not self._enabled:
            return self._snapshot(
                observed=False,
                reason="vad_shadow_disabled",
                audio_bus_present=False,
                source="",
                observation_started_monotonic=observation_started_monotonic,
            )

        audio_bus, source = find_realtime_audio_bus(owner)
        if audio_bus is None:
            return self._snapshot(
                observed=False,
                reason="audio_bus_unavailable_for_vad_shadow",
                audio_bus_present=False,
                source="",
                observation_started_monotonic=observation_started_monotonic,
            )

        try:
            self._ensure_subscription(audio_bus)
            engine = self._ensure_engine()
            subscription_next_sequence_before = self._subscription.next_sequence
            audio_bus_latest_sequence = audio_bus.latest_sequence
            audio_bus_frame_count = audio_bus.frame_count
            audio_bus_duration_seconds = audio_bus.duration_seconds

            frames = self._subscription.read_available(
                max_frames=self._max_frames_per_observation
            )
            subscription_next_sequence_after = self._subscription.next_sequence

            if not frames:
                return self._snapshot(
                    observed=True,
                    reason="no_new_audio_frames_observe_only",
                    audio_bus_present=True,
                    source=source,
                    in_speech=self._policy.in_speech,
                    observation_started_monotonic=observation_started_monotonic,
                    audio_bus_latest_sequence=audio_bus_latest_sequence,
                    audio_bus_frame_count=audio_bus_frame_count,
                    audio_bus_duration_seconds=audio_bus_duration_seconds,
                    subscription_next_sequence_before=subscription_next_sequence_before,
                    subscription_next_sequence_after=subscription_next_sequence_after,
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
                decisions=decisions,
                events=events,
                frames=frames,
                latest_frame_sequence=frames[-1].sequence,
                in_speech=self._policy.in_speech,
                observation_started_monotonic=observation_started_monotonic,
                audio_bus_latest_sequence=audio_bus_latest_sequence,
                audio_bus_frame_count=audio_bus_frame_count,
                audio_bus_duration_seconds=audio_bus_duration_seconds,
                subscription_next_sequence_before=subscription_next_sequence_before,
                subscription_next_sequence_after=subscription_next_sequence_after,
            )

        except ModuleNotFoundError as error:
            self._engine_error = f"{type(error).__name__}:{error}"
            return self._snapshot(
                observed=False,
                reason="silero_vad_unavailable_observe_only",
                audio_bus_present=True,
                source=source,
                error=self._engine_error,
                observation_started_monotonic=observation_started_monotonic,
            )
        except Exception as error:
            return self._snapshot(
                observed=False,
                reason=f"vad_shadow_failed:{type(error).__name__}",
                audio_bus_present=True,
                source=source,
                error=str(error),
                observation_started_monotonic=observation_started_monotonic,
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

        self._reset_subscription(
            audio_bus,
            subscription_name="voice_engine_v2_vad_shadow",
            start_at_latest=False,
        )

    def _reset_subscription(
        self,
        audio_bus: AudioBus,
        *,
        subscription_name: str,
        start_at_latest: bool,
    ) -> None:
        self._audio_bus_id = id(audio_bus)
        self._subscription = audio_bus.create_subscription(
            subscription_name,
            start_at_latest=start_at_latest,
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
        return SileroOnnxVadScoreProvider()

    def _snapshot(
        self,
        *,
        observed: bool,
        reason: str,
        audio_bus_present: bool,
        source: str,
        frames_processed: int = 0,
        decisions_processed: int = 0,
        decisions: list[VadDecision] | None = None,
        events: list[VadEvent] | None = None,
        frames: list[AudioFrame] | None = None,
        latest_frame_sequence: int | None = None,
        in_speech: bool = False,
        error: str = "",
        observation_started_monotonic: float | None = None,
        audio_bus_latest_sequence: int | None = None,
        audio_bus_frame_count: int | None = None,
        audio_bus_duration_seconds: float | None = None,
        subscription_next_sequence_before: int | None = None,
        subscription_next_sequence_after: int | None = None,
    ) -> VoiceEngineV2VadShadowSnapshot:
        safe_decisions = list(decisions or [])
        safe_events = list(events or [])
        safe_frames = list(frames or [])
        observation_completed_monotonic = time.monotonic()
        serialized_events = [_event_to_json_dict(event) for event in safe_events]
        timing_diagnostics = _timing_diagnostics(
            frames=safe_frames,
            events=safe_events,
            observation_started_monotonic=observation_started_monotonic,
            observation_completed_monotonic=observation_completed_monotonic,
        )
        cadence_diagnostics = _cadence_diagnostics(
            frames=safe_frames,
            audio_bus_latest_sequence=audio_bus_latest_sequence,
            audio_bus_frame_count=audio_bus_frame_count,
            audio_bus_duration_seconds=audio_bus_duration_seconds,
            subscription_next_sequence_before=subscription_next_sequence_before,
            subscription_next_sequence_after=subscription_next_sequence_after,
            last_frame_age_ms=timing_diagnostics["last_frame_age_ms"],
            latest_speech_end_to_observe_ms=timing_diagnostics[
                "latest_speech_end_to_observe_ms"
            ],
        )
        score_profile_diagnostics = _score_profile_diagnostics(
            decisions=safe_decisions,
            frames=safe_frames,
            observation_completed_monotonic=observation_completed_monotonic,
        )
        pcm_profile_diagnostics = _pcm_profile_diagnostics(
            frames=safe_frames,
            observation_completed_monotonic=observation_completed_monotonic,
        )
        diagnostics = _decision_diagnostics(
            decisions=safe_decisions,
            events=safe_events,
            in_speech=in_speech,
            min_speech_ms=self._endpointing_policy_config.min_speech_ms,
            min_silence_ms=self._endpointing_policy_config.min_silence_ms,
            threshold=self._speech_threshold,
            reason=reason,
        )

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
            speech_frame_count=int(diagnostics["speech_frame_count"]),
            silence_frame_count=int(diagnostics["silence_frame_count"]),
            speech_score_count=int(diagnostics["speech_score_count"]),
            speech_score_min=diagnostics["speech_score_min"],
            speech_score_max=diagnostics["speech_score_max"],
            speech_score_avg=diagnostics["speech_score_avg"],
            speech_score_over_threshold_count=int(
                diagnostics["speech_score_over_threshold_count"]
            ),
            latest_score=diagnostics["latest_score"],
            observation_started_monotonic=timing_diagnostics[
                "observation_started_monotonic"
            ],
            observation_completed_monotonic=timing_diagnostics[
                "observation_completed_monotonic"
            ],
            observation_duration_ms=timing_diagnostics["observation_duration_ms"],
            first_frame_timestamp_monotonic=timing_diagnostics[
                "first_frame_timestamp_monotonic"
            ],
            last_frame_timestamp_monotonic=timing_diagnostics[
                "last_frame_timestamp_monotonic"
            ],
            last_frame_end_timestamp_monotonic=timing_diagnostics[
                "last_frame_end_timestamp_monotonic"
            ],
            last_frame_age_ms=timing_diagnostics["last_frame_age_ms"],
            audio_window_duration_ms=timing_diagnostics["audio_window_duration_ms"],
            latest_speech_started_lag_ms=timing_diagnostics[
                "latest_speech_started_lag_ms"
            ],
            latest_speech_ended_lag_ms=timing_diagnostics[
                "latest_speech_ended_lag_ms"
            ],
            latest_speech_end_to_observe_ms=timing_diagnostics[
                "latest_speech_end_to_observe_ms"
            ],
            audio_bus_latest_sequence=cadence_diagnostics["audio_bus_latest_sequence"],
            audio_bus_frame_count=cadence_diagnostics["audio_bus_frame_count"],
            audio_bus_duration_seconds=cadence_diagnostics[
                "audio_bus_duration_seconds"
            ],
            subscription_next_sequence_before=cadence_diagnostics[
                "subscription_next_sequence_before"
            ],
            subscription_next_sequence_after=cadence_diagnostics[
                "subscription_next_sequence_after"
            ],
            subscription_backlog_frames=cadence_diagnostics[
                "subscription_backlog_frames"
            ],
            stale_audio_threshold_ms=cadence_diagnostics["stale_audio_threshold_ms"],
            stale_audio_observed=cadence_diagnostics["stale_audio_observed"],
            cadence_diagnostic_reason=str(
                cadence_diagnostics["cadence_diagnostic_reason"]
            ),
            score_profile_sample_count=score_profile_diagnostics[
                "score_profile_sample_count"
            ],
            score_profile_first_scores=list(
                score_profile_diagnostics["score_profile_first_scores"]
            ),
            score_profile_middle_scores=list(
                score_profile_diagnostics["score_profile_middle_scores"]
            ),
            score_profile_last_scores=list(
                score_profile_diagnostics["score_profile_last_scores"]
            ),
            score_profile_peak_score=score_profile_diagnostics[
                "score_profile_peak_score"
            ],
            score_profile_peak_index=score_profile_diagnostics[
                "score_profile_peak_index"
            ],
            score_profile_peak_sequence=score_profile_diagnostics[
                "score_profile_peak_sequence"
            ],
            score_profile_peak_position_ratio=score_profile_diagnostics[
                "score_profile_peak_position_ratio"
            ],
            score_profile_peak_bucket=str(
                score_profile_diagnostics["score_profile_peak_bucket"]
            ),
            score_profile_peak_frame_source=str(
                score_profile_diagnostics["score_profile_peak_frame_source"]
            ),
            score_profile_peak_frame_age_ms=score_profile_diagnostics[
                "score_profile_peak_frame_age_ms"
            ],
            frame_source_counts=dict(
                score_profile_diagnostics["frame_source_counts"]
            ),
            pcm_profile_frame_count=pcm_profile_diagnostics[
                "pcm_profile_frame_count"
            ],
            pcm_profile_sample_width_bytes=pcm_profile_diagnostics[
                "pcm_profile_sample_width_bytes"
            ],
            pcm_profile_total_byte_count=pcm_profile_diagnostics[
                "pcm_profile_total_byte_count"
            ],
            pcm_profile_total_sample_count=pcm_profile_diagnostics[
                "pcm_profile_total_sample_count"
            ],
            pcm_profile_rms=pcm_profile_diagnostics["pcm_profile_rms"],
            pcm_profile_mean_abs=pcm_profile_diagnostics["pcm_profile_mean_abs"],
            pcm_profile_peak_abs=pcm_profile_diagnostics["pcm_profile_peak_abs"],
            pcm_profile_zero_ratio=pcm_profile_diagnostics[
                "pcm_profile_zero_ratio"
            ],
            pcm_profile_near_zero_ratio=pcm_profile_diagnostics[
                "pcm_profile_near_zero_ratio"
            ],
            pcm_profile_clipping_ratio=pcm_profile_diagnostics[
                "pcm_profile_clipping_ratio"
            ],
            pcm_profile_signal_level=str(
                pcm_profile_diagnostics["pcm_profile_signal_level"]
            ),
            pcm_profile_first_frame_rms=pcm_profile_diagnostics[
                "pcm_profile_first_frame_rms"
            ],
            pcm_profile_first_frame_peak_abs=pcm_profile_diagnostics[
                "pcm_profile_first_frame_peak_abs"
            ],
            pcm_profile_middle_frame_rms=pcm_profile_diagnostics[
                "pcm_profile_middle_frame_rms"
            ],
            pcm_profile_middle_frame_peak_abs=pcm_profile_diagnostics[
                "pcm_profile_middle_frame_peak_abs"
            ],
            pcm_profile_last_frame_rms=pcm_profile_diagnostics[
                "pcm_profile_last_frame_rms"
            ],
            pcm_profile_last_frame_peak_abs=pcm_profile_diagnostics[
                "pcm_profile_last_frame_peak_abs"
            ],
            pcm_profile_peak_frame_index=pcm_profile_diagnostics[
                "pcm_profile_peak_frame_index"
            ],
            pcm_profile_peak_frame_sequence=pcm_profile_diagnostics[
                "pcm_profile_peak_frame_sequence"
            ],
            pcm_profile_peak_frame_source=str(
                pcm_profile_diagnostics["pcm_profile_peak_frame_source"]
            ),
            pcm_profile_peak_frame_rms=pcm_profile_diagnostics[
                "pcm_profile_peak_frame_rms"
            ],
            pcm_profile_peak_frame_peak_abs=pcm_profile_diagnostics[
                "pcm_profile_peak_frame_peak_abs"
            ],
            pcm_profile_peak_frame_zero_ratio=pcm_profile_diagnostics[
                "pcm_profile_peak_frame_zero_ratio"
            ],
            pcm_profile_peak_frame_age_ms=pcm_profile_diagnostics[
                "pcm_profile_peak_frame_age_ms"
            ],
            event_emission_reason=str(diagnostics["event_emission_reason"]),
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


def _timing_diagnostics(
    *,
    frames: list[AudioFrame],
    events: list[VadEvent],
    observation_started_monotonic: float | None,
    observation_completed_monotonic: float,
) -> dict[str, float | None]:
    latest_speech_started = _latest_event(events, "speech_started")
    latest_speech_ended = _latest_event(events, "speech_ended")

    first_frame_timestamp: float | None = None
    last_frame_timestamp: float | None = None
    last_frame_end_timestamp: float | None = None
    last_frame_age_ms: float | None = None
    audio_window_duration_ms: float | None = None

    if frames:
        first_frame = frames[0]
        last_frame = frames[-1]
        first_frame_timestamp = first_frame.timestamp_monotonic
        last_frame_timestamp = last_frame.timestamp_monotonic
        last_frame_end_timestamp = (
            last_frame.timestamp_monotonic + last_frame.duration_seconds
        )
        last_frame_age_ms = _elapsed_ms(
            start=last_frame_end_timestamp,
            end=observation_completed_monotonic,
        )
        audio_window_duration_ms = _elapsed_ms(
            start=first_frame.timestamp_monotonic,
            end=last_frame_end_timestamp,
        )

    latest_speech_started_lag_ms = (
        None
        if latest_speech_started is None
        else _elapsed_ms(
            start=latest_speech_started.timestamp_monotonic,
            end=observation_completed_monotonic,
        )
    )
    latest_speech_ended_lag_ms = (
        None
        if latest_speech_ended is None
        else _elapsed_ms(
            start=latest_speech_ended.timestamp_monotonic,
            end=observation_completed_monotonic,
        )
    )
    latest_speech_end_to_observe_ms = (
        None
        if latest_speech_ended is None
        or latest_speech_ended.speech_end_timestamp is None
        else _elapsed_ms(
            start=latest_speech_ended.speech_end_timestamp,
            end=observation_completed_monotonic,
        )
    )

    return {
        "observation_started_monotonic": observation_started_monotonic,
        "observation_completed_monotonic": observation_completed_monotonic,
        "observation_duration_ms": (
            None
            if observation_started_monotonic is None
            else _elapsed_ms(
                start=observation_started_monotonic,
                end=observation_completed_monotonic,
            )
        ),
        "first_frame_timestamp_monotonic": first_frame_timestamp,
        "last_frame_timestamp_monotonic": last_frame_timestamp,
        "last_frame_end_timestamp_monotonic": last_frame_end_timestamp,
        "last_frame_age_ms": last_frame_age_ms,
        "audio_window_duration_ms": audio_window_duration_ms,
        "latest_speech_started_lag_ms": latest_speech_started_lag_ms,
        "latest_speech_ended_lag_ms": latest_speech_ended_lag_ms,
        "latest_speech_end_to_observe_ms": latest_speech_end_to_observe_ms,
    }


def _latest_event(events: list[VadEvent], event_type: str) -> VadEvent | None:
    for event in reversed(events):
        if str(event.event_type.value) == event_type:
            return event
    return None


def _elapsed_ms(*, start: float, end: float) -> float:
    return max(0.0, (end - start) * 1000.0)


def _cadence_diagnostics(
    *,
    frames: list[AudioFrame],
    audio_bus_latest_sequence: int | None,
    audio_bus_frame_count: int | None,
    audio_bus_duration_seconds: float | None,
    subscription_next_sequence_before: int | None,
    subscription_next_sequence_after: int | None,
    last_frame_age_ms: float | None,
    latest_speech_end_to_observe_ms: float | None,
) -> dict[str, int | float | bool | str | None]:
    stale_audio_threshold_ms = 1000.0
    stale_audio_observed = _is_stale_audio(
        last_frame_age_ms=last_frame_age_ms,
        latest_speech_end_to_observe_ms=latest_speech_end_to_observe_ms,
        threshold_ms=stale_audio_threshold_ms,
    )

    subscription_backlog_frames: int | None = None
    if (
        audio_bus_latest_sequence is not None
        and subscription_next_sequence_before is not None
    ):
        subscription_backlog_frames = max(
            0,
            int(audio_bus_latest_sequence) - int(subscription_next_sequence_before) + 1,
        )

    cadence_diagnostic_reason = _cadence_diagnostic_reason(
        frames_processed=len(frames),
        stale_audio_observed=stale_audio_observed,
        subscription_backlog_frames=subscription_backlog_frames,
        audio_bus_latest_sequence=audio_bus_latest_sequence,
        subscription_next_sequence_before=subscription_next_sequence_before,
    )

    return {
        "audio_bus_latest_sequence": audio_bus_latest_sequence,
        "audio_bus_frame_count": audio_bus_frame_count,
        "audio_bus_duration_seconds": audio_bus_duration_seconds,
        "subscription_next_sequence_before": subscription_next_sequence_before,
        "subscription_next_sequence_after": subscription_next_sequence_after,
        "subscription_backlog_frames": subscription_backlog_frames,
        "stale_audio_threshold_ms": stale_audio_threshold_ms,
        "stale_audio_observed": stale_audio_observed,
        "cadence_diagnostic_reason": cadence_diagnostic_reason,
    }


def _is_stale_audio(
    *,
    last_frame_age_ms: float | None,
    latest_speech_end_to_observe_ms: float | None,
    threshold_ms: float,
) -> bool:
    observed_lags = [
        value
        for value in [last_frame_age_ms, latest_speech_end_to_observe_ms]
        if value is not None
    ]
    return any(value > threshold_ms for value in observed_lags)


def _cadence_diagnostic_reason(
    *,
    frames_processed: int,
    stale_audio_observed: bool,
    subscription_backlog_frames: int | None,
    audio_bus_latest_sequence: int | None,
    subscription_next_sequence_before: int | None,
) -> str:
    if frames_processed <= 0:
        return "no_new_audio_frames_at_observe_time"

    if stale_audio_observed:
        return "stale_audio_backlog_observed"

    if subscription_backlog_frames is not None and subscription_backlog_frames > 0:
        return "fresh_audio_backlog_observed"

    if audio_bus_latest_sequence is not None and subscription_next_sequence_before is not None:
        return "subscription_cursor_at_latest"

    return "cadence_diagnostics_unavailable"


def _score_profile_diagnostics(
    *,
    decisions: list[VadDecision],
    frames: list[AudioFrame],
    observation_completed_monotonic: float,
) -> dict[str, object]:
    if not decisions:
        return {
            "score_profile_sample_count": 0,
            "score_profile_first_scores": [],
            "score_profile_middle_scores": [],
            "score_profile_last_scores": [],
            "score_profile_peak_score": None,
            "score_profile_peak_index": None,
            "score_profile_peak_sequence": None,
            "score_profile_peak_position_ratio": None,
            "score_profile_peak_bucket": "",
            "score_profile_peak_frame_source": "",
            "score_profile_peak_frame_age_ms": None,
            "frame_source_counts": _frame_source_counts(frames),
        }

    scores = [float(decision.score) for decision in decisions]
    peak_index = max(range(len(scores)), key=scores.__getitem__)
    peak_decision = decisions[peak_index]
    peak_frame = frames[peak_index] if peak_index < len(frames) else None

    return {
        "score_profile_sample_count": len(scores),
        "score_profile_first_scores": _score_samples(scores, start=0),
        "score_profile_middle_scores": _middle_score_samples(scores),
        "score_profile_last_scores": _score_samples(
            scores,
            start=max(0, len(scores) - 5),
        ),
        "score_profile_peak_score": scores[peak_index],
        "score_profile_peak_index": peak_index,
        "score_profile_peak_sequence": peak_decision.frame_sequence,
        "score_profile_peak_position_ratio": _score_position_ratio(
            peak_index=peak_index,
            score_count=len(scores),
        ),
        "score_profile_peak_bucket": _score_position_bucket(
            peak_index=peak_index,
            score_count=len(scores),
        ),
        "score_profile_peak_frame_source": (
            "" if peak_frame is None else str(peak_frame.source)
        ),
        "score_profile_peak_frame_age_ms": (
            None
            if peak_frame is None
            else _elapsed_ms(
                start=peak_frame.timestamp_monotonic + peak_frame.duration_seconds,
                end=observation_completed_monotonic,
            )
        ),
        "frame_source_counts": _frame_source_counts(frames),
    }


def _score_samples(scores: list[float], *, start: int, sample_count: int = 5) -> list[float]:
    return [
        round(float(score), 6)
        for score in scores[start : min(len(scores), start + sample_count)]
    ]


def _middle_score_samples(scores: list[float], *, sample_count: int = 5) -> list[float]:
    if not scores:
        return []
    start = max(0, (len(scores) // 2) - (sample_count // 2))
    return _score_samples(scores, start=start, sample_count=sample_count)


def _score_position_ratio(*, peak_index: int, score_count: int) -> float:
    if score_count <= 1:
        return 0.0
    return round(float(peak_index) / float(score_count - 1), 6)


def _score_position_bucket(*, peak_index: int, score_count: int) -> str:
    if score_count <= 0:
        return ""
    ratio = _score_position_ratio(peak_index=peak_index, score_count=score_count)
    if ratio < 0.34:
        return "first_third"
    if ratio < 0.67:
        return "middle_third"
    return "last_third"


def _frame_source_counts(frames: list[AudioFrame]) -> dict[str, int]:
    return dict(Counter(str(frame.source) for frame in frames))

def _pcm_profile_diagnostics(
    *,
    frames: list[AudioFrame],
    observation_completed_monotonic: float,
) -> dict[str, object]:
    if not frames:
        return _empty_pcm_profile_diagnostics()

    frame_metrics = [
        _pcm_frame_metrics(
            index=index,
            frame=frame,
            observation_completed_monotonic=observation_completed_monotonic,
        )
        for index, frame in enumerate(frames)
    ]
    valid_metrics = [
        metric for metric in frame_metrics if int(metric["sample_count"]) > 0
    ]

    if not valid_metrics:
        return _empty_pcm_profile_diagnostics(
            frame_count=len(frames),
            sample_width_bytes=frames[0].sample_width_bytes if frames else None,
            total_byte_count=sum(len(frame.pcm) for frame in frames),
        )

    total_byte_count = sum(int(metric["byte_count"]) for metric in valid_metrics)
    total_sample_count = sum(int(metric["sample_count"]) for metric in valid_metrics)
    weighted_square_sum = sum(
        float(metric["square_sum"]) for metric in valid_metrics
    )
    weighted_abs_sum = sum(float(metric["abs_sum"]) for metric in valid_metrics)
    zero_count = sum(int(metric["zero_count"]) for metric in valid_metrics)
    near_zero_count = sum(int(metric["near_zero_count"]) for metric in valid_metrics)
    clipping_count = sum(int(metric["clipping_count"]) for metric in valid_metrics)
    peak_abs = max(float(metric["peak_abs"]) for metric in valid_metrics)

    peak_metric = max(valid_metrics, key=lambda metric: float(metric["peak_abs"]))
    middle_metric = valid_metrics[len(valid_metrics) // 2]
    first_metric = valid_metrics[0]
    last_metric = valid_metrics[-1]

    rms = float(np.sqrt(weighted_square_sum / total_sample_count))
    mean_abs = weighted_abs_sum / total_sample_count
    zero_ratio = zero_count / total_sample_count
    near_zero_ratio = near_zero_count / total_sample_count
    clipping_ratio = clipping_count / total_sample_count

    return {
        "pcm_profile_frame_count": len(frames),
        "pcm_profile_sample_width_bytes": frames[0].sample_width_bytes,
        "pcm_profile_total_byte_count": total_byte_count,
        "pcm_profile_total_sample_count": total_sample_count,
        "pcm_profile_rms": _round_float(rms),
        "pcm_profile_mean_abs": _round_float(mean_abs),
        "pcm_profile_peak_abs": _round_float(peak_abs),
        "pcm_profile_zero_ratio": _round_float(zero_ratio),
        "pcm_profile_near_zero_ratio": _round_float(near_zero_ratio),
        "pcm_profile_clipping_ratio": _round_float(clipping_ratio),
        "pcm_profile_signal_level": _pcm_signal_level(rms=rms, peak_abs=peak_abs),
        "pcm_profile_first_frame_rms": first_metric["rms"],
        "pcm_profile_first_frame_peak_abs": first_metric["peak_abs"],
        "pcm_profile_middle_frame_rms": middle_metric["rms"],
        "pcm_profile_middle_frame_peak_abs": middle_metric["peak_abs"],
        "pcm_profile_last_frame_rms": last_metric["rms"],
        "pcm_profile_last_frame_peak_abs": last_metric["peak_abs"],
        "pcm_profile_peak_frame_index": peak_metric["index"],
        "pcm_profile_peak_frame_sequence": peak_metric["sequence"],
        "pcm_profile_peak_frame_source": peak_metric["source"],
        "pcm_profile_peak_frame_rms": peak_metric["rms"],
        "pcm_profile_peak_frame_peak_abs": peak_metric["peak_abs"],
        "pcm_profile_peak_frame_zero_ratio": peak_metric["zero_ratio"],
        "pcm_profile_peak_frame_age_ms": peak_metric["age_ms"],
    }


def _empty_pcm_profile_diagnostics(
    *,
    frame_count: int = 0,
    sample_width_bytes: int | None = None,
    total_byte_count: int = 0,
) -> dict[str, object]:
    return {
        "pcm_profile_frame_count": frame_count,
        "pcm_profile_sample_width_bytes": sample_width_bytes,
        "pcm_profile_total_byte_count": total_byte_count,
        "pcm_profile_total_sample_count": 0,
        "pcm_profile_rms": None,
        "pcm_profile_mean_abs": None,
        "pcm_profile_peak_abs": None,
        "pcm_profile_zero_ratio": None,
        "pcm_profile_near_zero_ratio": None,
        "pcm_profile_clipping_ratio": None,
        "pcm_profile_signal_level": "unavailable",
        "pcm_profile_first_frame_rms": None,
        "pcm_profile_first_frame_peak_abs": None,
        "pcm_profile_middle_frame_rms": None,
        "pcm_profile_middle_frame_peak_abs": None,
        "pcm_profile_last_frame_rms": None,
        "pcm_profile_last_frame_peak_abs": None,
        "pcm_profile_peak_frame_index": None,
        "pcm_profile_peak_frame_sequence": None,
        "pcm_profile_peak_frame_source": "",
        "pcm_profile_peak_frame_rms": None,
        "pcm_profile_peak_frame_peak_abs": None,
        "pcm_profile_peak_frame_zero_ratio": None,
        "pcm_profile_peak_frame_age_ms": None,
    }


def _pcm_frame_metrics(
    *,
    index: int,
    frame: AudioFrame,
    observation_completed_monotonic: float,
) -> dict[str, object]:
    if frame.sample_width_bytes != 2 or not frame.pcm:
        return {
            "index": index,
            "sequence": frame.sequence,
            "source": str(frame.source),
            "byte_count": len(frame.pcm),
            "sample_count": 0,
            "square_sum": 0.0,
            "abs_sum": 0.0,
            "zero_count": 0,
            "near_zero_count": 0,
            "clipping_count": 0,
            "rms": None,
            "mean_abs": None,
            "peak_abs": None,
            "zero_ratio": None,
            "age_ms": _elapsed_ms(
                start=frame.timestamp_monotonic + frame.duration_seconds,
                end=observation_completed_monotonic,
            ),
        }

    samples = np.frombuffer(frame.pcm, dtype=np.int16).astype(np.float32) / 32768.0
    if samples.size == 0:
        return {
            "index": index,
            "sequence": frame.sequence,
            "source": str(frame.source),
            "byte_count": len(frame.pcm),
            "sample_count": 0,
            "square_sum": 0.0,
            "abs_sum": 0.0,
            "zero_count": 0,
            "near_zero_count": 0,
            "clipping_count": 0,
            "rms": None,
            "mean_abs": None,
            "peak_abs": None,
            "zero_ratio": None,
            "age_ms": _elapsed_ms(
                start=frame.timestamp_monotonic + frame.duration_seconds,
                end=observation_completed_monotonic,
            ),
        }

    abs_samples = np.abs(samples)
    square_sum = float(np.sum(samples * samples))
    abs_sum = float(np.sum(abs_samples))
    zero_count = int(np.count_nonzero(samples == 0.0))
    near_zero_count = int(np.count_nonzero(abs_samples <= 0.001))
    clipping_count = int(np.count_nonzero(abs_samples >= 0.999))
    rms = float(np.sqrt(square_sum / float(samples.size)))
    mean_abs = abs_sum / float(samples.size)
    peak_abs = float(np.max(abs_samples))
    zero_ratio = zero_count / float(samples.size)

    return {
        "index": index,
        "sequence": frame.sequence,
        "source": str(frame.source),
        "byte_count": len(frame.pcm),
        "sample_count": int(samples.size),
        "square_sum": square_sum,
        "abs_sum": abs_sum,
        "zero_count": zero_count,
        "near_zero_count": near_zero_count,
        "clipping_count": clipping_count,
        "rms": _round_float(rms),
        "mean_abs": _round_float(mean_abs),
        "peak_abs": _round_float(peak_abs),
        "zero_ratio": _round_float(zero_ratio),
        "age_ms": _elapsed_ms(
            start=frame.timestamp_monotonic + frame.duration_seconds,
            end=observation_completed_monotonic,
        ),
    }


def _pcm_signal_level(*, rms: float, peak_abs: float) -> str:
    if peak_abs < 0.002 or rms < 0.001:
        return "near_silent"
    if peak_abs < 0.01 or rms < 0.004:
        return "very_low"
    if peak_abs < 0.04 or rms < 0.015:
        return "low"
    if peak_abs < 0.15 or rms < 0.06:
        return "medium"
    return "high"


def _round_float(value: float) -> float:
    return round(float(value), 6)



def _decision_diagnostics(
    *,
    decisions: list[VadDecision],
    events: list[VadEvent],
    in_speech: bool,
    min_speech_ms: int,
    min_silence_ms: int,
    threshold: float,
    reason: str,
) -> dict[str, Any]:
    if not decisions:
        return {
            "speech_frame_count": 0,
            "silence_frame_count": 0,
            "speech_score_count": 0,
            "speech_score_min": None,
            "speech_score_max": None,
            "speech_score_avg": None,
            "speech_score_over_threshold_count": 0,
            "latest_score": None,
            "event_emission_reason": _event_emission_reason(
                decisions=[],
                events=events,
                in_speech=in_speech,
                min_speech_ms=min_speech_ms,
                min_silence_ms=min_silence_ms,
                threshold=threshold,
                reason=reason,
            ),
        }

    scores = [float(decision.score) for decision in decisions]
    speech_frame_count = sum(1 for decision in decisions if decision.is_speech)
    silence_frame_count = len(decisions) - speech_frame_count
    over_threshold_count = sum(1 for score in scores if score >= threshold)

    return {
        "speech_frame_count": speech_frame_count,
        "silence_frame_count": silence_frame_count,
        "speech_score_count": len(scores),
        "speech_score_min": min(scores),
        "speech_score_max": max(scores),
        "speech_score_avg": sum(scores) / len(scores),
        "speech_score_over_threshold_count": over_threshold_count,
        "latest_score": scores[-1],
        "event_emission_reason": _event_emission_reason(
            decisions=decisions,
            events=events,
            in_speech=in_speech,
            min_speech_ms=min_speech_ms,
            min_silence_ms=min_silence_ms,
            threshold=threshold,
            reason=reason,
        ),
    }


def _event_emission_reason(
    *,
    decisions: list[VadDecision],
    events: list[VadEvent],
    in_speech: bool,
    min_speech_ms: int,
    min_silence_ms: int,
    threshold: float,
    reason: str,
) -> str:
    if events:
        return "events_emitted"

    if reason != "vad_shadow_observed_audio":
        return reason

    if not decisions:
        return "no_decisions"

    speech_frames = [decision for decision in decisions if decision.is_speech]
    silence_frames = [decision for decision in decisions if not decision.is_speech]

    if not speech_frames and silence_frames:
        max_score = max(float(decision.score) for decision in decisions)
        return f"all_scores_below_threshold:max={max_score:.3f}:threshold={threshold:.3f}"

    if speech_frames and not in_speech:
        speech_duration = sum(
            decision.frame_duration_seconds for decision in speech_frames
        )
        min_speech_seconds = min_speech_ms / 1000.0
        if speech_duration < min_speech_seconds:
            return (
                "speech_candidate_shorter_than_min_speech:"
                f"duration={speech_duration:.3f}:required={min_speech_seconds:.3f}"
            )
        return "speech_frames_seen_but_policy_not_in_speech"

    if in_speech and not silence_frames:
        return "in_speech_waiting_for_silence"

    if in_speech and silence_frames:
        silence_duration = sum(
            decision.frame_duration_seconds for decision in silence_frames
        )
        min_silence_seconds = min_silence_ms / 1000.0
        if silence_duration < min_silence_seconds:
            return (
                "silence_candidate_shorter_than_min_silence:"
                f"duration={silence_duration:.3f}:required={min_silence_seconds:.3f}"
            )
        return "silence_frames_seen_but_no_speech_end_event"

    return "no_events_emitted"

def _coerce_probability(raw_probability: Any) -> float:
    if hasattr(raw_probability, "item"):
        score = float(raw_probability.item())
    else:
        array = np.asarray(raw_probability, dtype=np.float32)
        if array.size != 1:
            raise ValueError("Silero VAD model must return one probability value")
        score = float(array.reshape(-1)[0])

    if not np.isfinite(score):
        raise ValueError("Silero VAD score must be finite")
    return score

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