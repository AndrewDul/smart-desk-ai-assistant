from __future__ import annotations

import time
from types import SimpleNamespace

import numpy as np

from modules.devices.audio.realtime import AudioBus
from modules.devices.audio.realtime.audio_frame import AudioFrame
from modules.devices.audio.vad import EndpointingPolicyConfig
from modules.runtime.voice_engine_v2.vad_shadow import (
    VoiceEngineV2VadShadowObserver,
    build_voice_engine_v2_vad_shadow_observer,
)


def _speech_pcm(sample_count: int = 1600) -> bytes:
    return np.full(sample_count, 1200, dtype=np.int16).tobytes(order="C")


def _silence_pcm(sample_count: int = 1600) -> bytes:
    return np.zeros(sample_count, dtype=np.int16).tobytes(order="C")


def _owner_with_bus(audio_bus: AudioBus) -> SimpleNamespace:
    return SimpleNamespace(runtime=SimpleNamespace(metadata={"realtime_audio_bus": audio_bus}))


def _fake_score_provider(frame: AudioFrame) -> float:
    audio = np.frombuffer(frame.pcm, dtype=np.int16)
    if audio.size == 0:
        return 0.0
    return 1.0 if int(np.max(np.abs(audio))) > 0 else 0.0


def test_vad_shadow_is_disabled_by_default() -> None:
    observer = build_voice_engine_v2_vad_shadow_observer({"voice_engine": {}})

    snapshot = observer.observe(SimpleNamespace())

    assert snapshot.enabled is False
    assert snapshot.observed is False
    assert snapshot.reason == "vad_shadow_disabled"
    assert snapshot.action_executed is False
    assert snapshot.full_stt_prevented is False
    assert snapshot.runtime_takeover is False


def test_vad_shadow_reports_missing_audio_bus() -> None:
    observer = VoiceEngineV2VadShadowObserver(
        enabled=True,
        score_provider_factory=lambda: _fake_score_provider,
    )

    snapshot = observer.observe(SimpleNamespace())

    assert snapshot.enabled is True
    assert snapshot.observed is False
    assert snapshot.reason == "audio_bus_unavailable_for_vad_shadow"
    assert snapshot.audio_bus_present is False
    assert snapshot.action_executed is False
    assert snapshot.full_stt_prevented is False
    assert snapshot.runtime_takeover is False


def test_vad_shadow_reports_no_new_audio_frames() -> None:
    audio_bus = AudioBus(
        max_duration_seconds=3.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )
    observer = VoiceEngineV2VadShadowObserver(
        enabled=True,
        score_provider_factory=lambda: _fake_score_provider,
    )

    snapshot = observer.observe(_owner_with_bus(audio_bus))

    assert snapshot.enabled is True
    assert snapshot.observed is True
    assert snapshot.reason == "no_new_audio_frames_observe_only"
    assert snapshot.audio_bus_present is True
    assert snapshot.frames_processed == 0


def test_vad_shadow_emits_speech_start_and_end_events() -> None:
    audio_bus = AudioBus(
        max_duration_seconds=3.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )
    observer = VoiceEngineV2VadShadowObserver(
        enabled=True,
        endpointing_policy_config=EndpointingPolicyConfig(
            min_speech_ms=120,
            min_silence_ms=180,
        ),
        max_frames_per_observation=16,
        score_provider_factory=lambda: _fake_score_provider,
    )

    base_time = time.monotonic()

    for index in range(3):
        audio_bus.publish_pcm(
            _speech_pcm(),
            timestamp_monotonic=base_time + (index * 0.10),
            source="test",
        )

    for index in range(3, 7):
        audio_bus.publish_pcm(
            _silence_pcm(),
            timestamp_monotonic=base_time + (index * 0.10),
            source="test",
        )

    snapshot = observer.observe(_owner_with_bus(audio_bus))

    assert snapshot.enabled is True
    assert snapshot.observed is True
    assert snapshot.reason == "vad_shadow_observed_audio"
    assert snapshot.audio_bus_present is True
    assert snapshot.frames_processed == 7
    assert snapshot.decisions_processed == 7
    assert snapshot.events_emitted >= 2
    assert snapshot.speech_started_count == 1
    assert snapshot.speech_ended_count == 1
    assert snapshot.latest_event_type == "speech_ended"
    assert snapshot.in_speech is False
    assert snapshot.speech_frame_count == 3
    assert snapshot.silence_frame_count == 4
    assert snapshot.speech_score_count == 7
    assert snapshot.speech_score_min == 0.0
    assert snapshot.speech_score_max == 1.0
    assert snapshot.speech_score_avg == 3 / 7
    assert snapshot.speech_score_over_threshold_count == 3
    assert snapshot.latest_score == 0.0
    assert snapshot.event_emission_reason == "events_emitted"

    event_types = [event["event_type"] for event in snapshot.events]
    assert "speech_started" in event_types
    assert "speech_ended" in event_types


def test_vad_shadow_reads_only_new_frames_after_first_observation() -> None:
    audio_bus = AudioBus(
        max_duration_seconds=3.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )
    observer = VoiceEngineV2VadShadowObserver(
        enabled=True,
        endpointing_policy_config=EndpointingPolicyConfig(
            min_speech_ms=120,
            min_silence_ms=180,
        ),
        max_frames_per_observation=16,
        score_provider_factory=lambda: _fake_score_provider,
    )

    audio_bus.publish_pcm(_speech_pcm(), timestamp_monotonic=time.monotonic())
    first_snapshot = observer.observe(_owner_with_bus(audio_bus))

    audio_bus.publish_pcm(_speech_pcm(), timestamp_monotonic=time.monotonic())
    second_snapshot = observer.observe(_owner_with_bus(audio_bus))

    assert first_snapshot.frames_processed == 1
    assert second_snapshot.frames_processed == 1
    assert second_snapshot.latest_frame_sequence == 1


def test_vad_shadow_is_fail_open_when_score_provider_fails() -> None:
    def failing_score_provider(frame: AudioFrame) -> float:
        raise RuntimeError("score failed")

    audio_bus = AudioBus(
        max_duration_seconds=3.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )
    audio_bus.publish_pcm(_speech_pcm(), timestamp_monotonic=time.monotonic())

    observer = VoiceEngineV2VadShadowObserver(
        enabled=True,
        score_provider_factory=lambda: failing_score_provider,
    )

    snapshot = observer.observe(_owner_with_bus(audio_bus))

    assert snapshot.enabled is True
    assert snapshot.observed is False
    assert snapshot.reason == "vad_shadow_failed:RuntimeError"
    assert snapshot.action_executed is False
    assert snapshot.full_stt_prevented is False
    assert snapshot.runtime_takeover is False
    assert "score failed" in snapshot.error


def test_vad_shadow_builder_reads_safe_config() -> None:
    observer = build_voice_engine_v2_vad_shadow_observer(
        {
            "voice_engine": {
                "vad_shadow_enabled": True,
                "vad_shadow_max_frames_per_observation": 24,
                "vad_shadow_speech_threshold": 0.7,
                "vad_shadow_min_speech_ms": 160,
                "vad_shadow_min_silence_ms": 320,
            }
        }
    )

    assert observer.enabled is True

    snapshot = observer.observe(SimpleNamespace())

    assert snapshot.enabled is True
    assert snapshot.min_speech_ms == 160
    assert snapshot.min_silence_ms == 320
    assert snapshot.speech_threshold == 0.7




def test_vad_shadow_reports_all_scores_below_threshold_reason() -> None:
    audio_bus = AudioBus(
        max_duration_seconds=3.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )
    observer = VoiceEngineV2VadShadowObserver(
        enabled=True,
        endpointing_policy_config=EndpointingPolicyConfig(
            min_speech_ms=120,
            min_silence_ms=180,
        ),
        max_frames_per_observation=16,
        score_provider_factory=lambda: (lambda frame: 0.2),
    )

    audio_bus.publish_pcm(_speech_pcm(), timestamp_monotonic=time.monotonic())

    snapshot = observer.observe(_owner_with_bus(audio_bus))

    assert snapshot.reason == "vad_shadow_observed_audio"
    assert snapshot.events_emitted == 0
    assert snapshot.speech_score_count == 1
    assert snapshot.speech_score_min == 0.2
    assert snapshot.speech_score_max == 0.2
    assert snapshot.speech_score_avg == 0.2
    assert snapshot.speech_score_over_threshold_count == 0
    assert snapshot.speech_frame_count == 0
    assert snapshot.silence_frame_count == 1
    assert snapshot.event_emission_reason.startswith("all_scores_below_threshold")


def test_vad_shadow_reports_short_speech_candidate_reason() -> None:
    audio_bus = AudioBus(
        max_duration_seconds=3.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )
    observer = VoiceEngineV2VadShadowObserver(
        enabled=True,
        endpointing_policy_config=EndpointingPolicyConfig(
            min_speech_ms=300,
            min_silence_ms=180,
        ),
        max_frames_per_observation=16,
        score_provider_factory=lambda: (lambda frame: 1.0),
    )

    audio_bus.publish_pcm(
        _speech_pcm(sample_count=1600),
        timestamp_monotonic=time.monotonic(),
    )

    snapshot = observer.observe(_owner_with_bus(audio_bus))

    assert snapshot.reason == "vad_shadow_observed_audio"
    assert snapshot.events_emitted == 0
    assert snapshot.speech_frame_count == 1
    assert snapshot.silence_frame_count == 0
    assert snapshot.speech_score_over_threshold_count == 1
    assert snapshot.event_emission_reason.startswith(
        "speech_candidate_shorter_than_min_speech"
    )


def test_vad_shadow_reports_waiting_for_silence_reason() -> None:
    audio_bus = AudioBus(
        max_duration_seconds=3.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )
    observer = VoiceEngineV2VadShadowObserver(
        enabled=True,
        endpointing_policy_config=EndpointingPolicyConfig(
            min_speech_ms=120,
            min_silence_ms=180,
        ),
        max_frames_per_observation=16,
        score_provider_factory=lambda: (lambda frame: 1.0),
    )

    now = time.monotonic()
    for index in range(2):
        audio_bus.publish_pcm(
            _speech_pcm(sample_count=1600),
            timestamp_monotonic=now + (index * 0.10),
        )

    snapshot = observer.observe(_owner_with_bus(audio_bus))

    assert snapshot.events_emitted == 1
    assert snapshot.latest_event_type == "speech_started"
    assert snapshot.in_speech is True

    audio_bus.publish_pcm(
        _speech_pcm(sample_count=1600),
        timestamp_monotonic=now + 0.30,
    )
    second_snapshot = observer.observe(_owner_with_bus(audio_bus))

    assert second_snapshot.events_emitted == 0
    assert second_snapshot.in_speech is True
    assert second_snapshot.event_emission_reason == "in_speech_waiting_for_silence"