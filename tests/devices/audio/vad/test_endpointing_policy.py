from modules.devices.audio.vad.endpointing_policy import (
    EndpointingPolicy,
    EndpointingPolicyConfig,
)
from modules.devices.audio.vad.vad_events import VadDecision, VadEventType


def _decision(
    *,
    sequence: int,
    timestamp: float,
    is_speech: bool,
    duration: float = 0.1,
    score: float | None = None,
) -> VadDecision:
    resolved_score = score
    if resolved_score is None:
        resolved_score = 0.8 if is_speech else 0.1

    return VadDecision(
        is_speech=is_speech,
        score=resolved_score,
        threshold=0.5,
        timestamp_monotonic=timestamp,
        frame_sequence=sequence,
        frame_duration_seconds=duration,
    )


def test_endpointing_policy_emits_speech_started_after_min_speech() -> None:
    policy = EndpointingPolicy(
        EndpointingPolicyConfig(
            min_speech_ms=120,
            min_silence_ms=250,
        )
    )

    assert policy.process(
        _decision(sequence=0, timestamp=0.0, is_speech=True, duration=0.06)
    ) == []

    events = policy.process(
        _decision(sequence=1, timestamp=0.06, is_speech=True, duration=0.06)
    )

    assert len(events) == 1
    assert events[0].event_type == VadEventType.SPEECH_STARTED
    assert events[0].speech_start_timestamp == 0.0
    assert events[0].speech_duration_seconds == 0.12
    assert policy.in_speech is True


def test_endpointing_policy_resets_candidate_on_short_noise() -> None:
    policy = EndpointingPolicy(
        EndpointingPolicyConfig(
            min_speech_ms=120,
            min_silence_ms=250,
        )
    )

    assert policy.process(
        _decision(sequence=0, timestamp=0.0, is_speech=True, duration=0.06)
    ) == []
    assert policy.process(
        _decision(sequence=1, timestamp=0.06, is_speech=False, duration=0.06)
    ) == []
    assert policy.in_speech is False

    assert policy.process(
        _decision(sequence=2, timestamp=0.12, is_speech=True, duration=0.06)
    ) == []

    events = policy.process(
        _decision(sequence=3, timestamp=0.18, is_speech=True, duration=0.06)
    )

    assert len(events) == 1
    assert events[0].event_type == VadEventType.SPEECH_STARTED
    assert events[0].speech_start_timestamp == 0.12


def test_endpointing_policy_emits_speech_ended_after_min_silence() -> None:
    policy = EndpointingPolicy(
        EndpointingPolicyConfig(
            min_speech_ms=100,
            min_silence_ms=200,
        )
    )

    start_events = policy.process(
        _decision(sequence=0, timestamp=0.0, is_speech=True, duration=0.1)
    )

    assert len(start_events) == 1
    assert start_events[0].event_type == VadEventType.SPEECH_STARTED

    assert policy.process(
        _decision(sequence=1, timestamp=0.1, is_speech=True, duration=0.1)
    ) == []
    assert policy.process(
        _decision(sequence=2, timestamp=0.2, is_speech=False, duration=0.1)
    ) == []

    end_events = policy.process(
        _decision(sequence=3, timestamp=0.3, is_speech=False, duration=0.1)
    )

    assert len(end_events) == 1
    assert end_events[0].event_type == VadEventType.SPEECH_ENDED
    assert end_events[0].speech_start_timestamp == 0.0
    assert end_events[0].speech_end_timestamp == 0.1
    assert end_events[0].silence_duration_seconds == 0.2
    assert policy.in_speech is False


def test_endpointing_policy_can_emit_continued_events_when_enabled() -> None:
    policy = EndpointingPolicy(
        EndpointingPolicyConfig(
            min_speech_ms=100,
            min_silence_ms=200,
            emit_continued_events=True,
        )
    )

    assert policy.process(
        _decision(sequence=0, timestamp=0.0, is_speech=True, duration=0.1)
    )[0].event_type == VadEventType.SPEECH_STARTED

    events = policy.process(
        _decision(sequence=1, timestamp=0.1, is_speech=True, duration=0.1)
    )

    assert len(events) == 1
    assert events[0].event_type == VadEventType.SPEECH_CONTINUED