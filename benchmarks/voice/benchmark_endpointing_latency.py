from __future__ import annotations
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from dataclasses import dataclass

from modules.devices.audio.vad.endpointing_policy import (
    EndpointingPolicy,
    EndpointingPolicyConfig,
)
from modules.devices.audio.vad.vad_events import VadDecision, VadEventType


@dataclass(frozen=True, slots=True)
class EndpointingLatencyAcceptanceTargets:
    """Acceptance targets for VAD endpointing latency."""

    max_endpoint_delay_ms: float = 300.0
    max_speech_start_delay_ms: float = 150.0


@dataclass(frozen=True, slots=True)
class EndpointingLatencyBenchmarkResult:
    """Measured VAD endpointing benchmark result."""

    speech_started: bool
    speech_ended: bool
    speech_start_delay_ms: float | None
    endpoint_delay_ms: float | None
    accepted: bool
    rejection_reasons: tuple[str, ...]


def run_endpointing_latency_benchmark(
    *,
    frame_duration_seconds: float = 0.02,
    min_speech_ms: int = 120,
    min_silence_ms: int = 250,
    targets: EndpointingLatencyAcceptanceTargets | None = None,
) -> EndpointingLatencyBenchmarkResult:
    """Run deterministic endpointing benchmark using policy decisions."""

    if frame_duration_seconds <= 0:
        raise ValueError("frame_duration_seconds must be greater than zero")

    resolved_targets = targets or EndpointingLatencyAcceptanceTargets()
    policy = EndpointingPolicy(
        EndpointingPolicyConfig(
            min_speech_ms=min_speech_ms,
            min_silence_ms=min_silence_ms,
        )
    )

    speech_start_event_timestamp: float | None = None
    speech_end_event_timestamp: float | None = None
    last_speech_timestamp: float | None = None

    sequence = 0
    timestamp = 0.0

    speech_frames = int((min_speech_ms / 1000.0) / frame_duration_seconds) + 2
    silence_frames = int((min_silence_ms / 1000.0) / frame_duration_seconds) + 2

    for _ in range(speech_frames):
        decision = _decision(
            sequence=sequence,
            timestamp=timestamp,
            is_speech=True,
            frame_duration_seconds=frame_duration_seconds,
        )
        events = policy.process(decision)
        last_speech_timestamp = timestamp

        for event in events:
            if event.event_type is VadEventType.SPEECH_STARTED:
                speech_start_event_timestamp = event.timestamp_monotonic

        sequence += 1
        timestamp += frame_duration_seconds

    for _ in range(silence_frames):
        decision = _decision(
            sequence=sequence,
            timestamp=timestamp,
            is_speech=False,
            frame_duration_seconds=frame_duration_seconds,
        )
        events = policy.process(decision)

        for event in events:
            if event.event_type is VadEventType.SPEECH_ENDED:
                speech_end_event_timestamp = event.timestamp_monotonic

        if speech_end_event_timestamp is not None:
            break

        sequence += 1
        timestamp += frame_duration_seconds

    speech_start_delay_ms = (
        None
        if speech_start_event_timestamp is None
        else round(speech_start_event_timestamp * 1000.0, 3)
    )
    endpoint_delay_ms = (
        None
        if speech_end_event_timestamp is None or last_speech_timestamp is None
        else round(
            (speech_end_event_timestamp - last_speech_timestamp) * 1000.0,
            3,
        )
    )

    accepted, rejection_reasons = _evaluate_endpointing_gates(
        speech_start_delay_ms=speech_start_delay_ms,
        endpoint_delay_ms=endpoint_delay_ms,
        targets=resolved_targets,
    )

    return EndpointingLatencyBenchmarkResult(
        speech_started=speech_start_event_timestamp is not None,
        speech_ended=speech_end_event_timestamp is not None,
        speech_start_delay_ms=speech_start_delay_ms,
        endpoint_delay_ms=endpoint_delay_ms,
        accepted=accepted,
        rejection_reasons=rejection_reasons,
    )


def _decision(
    *,
    sequence: int,
    timestamp: float,
    is_speech: bool,
    frame_duration_seconds: float,
) -> VadDecision:
    return VadDecision(
        is_speech=is_speech,
        score=0.9 if is_speech else 0.1,
        threshold=0.5,
        timestamp_monotonic=timestamp,
        frame_sequence=sequence,
        frame_duration_seconds=frame_duration_seconds,
    )


def _evaluate_endpointing_gates(
    *,
    speech_start_delay_ms: float | None,
    endpoint_delay_ms: float | None,
    targets: EndpointingLatencyAcceptanceTargets,
) -> tuple[bool, tuple[str, ...]]:
    rejection_reasons: list[str] = []

    if speech_start_delay_ms is None:
        rejection_reasons.append("missing_speech_start_event")
    elif speech_start_delay_ms > targets.max_speech_start_delay_ms:
        rejection_reasons.append(
            f"speech_start_delay_ms_above_target:{speech_start_delay_ms:.3f}"
        )

    if endpoint_delay_ms is None:
        rejection_reasons.append("missing_speech_end_event")
    elif endpoint_delay_ms > targets.max_endpoint_delay_ms:
        rejection_reasons.append(
            f"endpoint_delay_ms_above_target:{endpoint_delay_ms:.3f}"
        )

    return not rejection_reasons, tuple(rejection_reasons)


if __name__ == "__main__":
    result = run_endpointing_latency_benchmark()
    print(
        {
            "accepted": result.accepted,
            "speech_started": result.speech_started,
            "speech_ended": result.speech_ended,
            "speech_start_delay_ms": result.speech_start_delay_ms,
            "endpoint_delay_ms": result.endpoint_delay_ms,
            "rejection_reasons": result.rejection_reasons,
        }
    )