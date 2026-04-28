from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

from modules.devices.audio.realtime import AudioBus
from modules.devices.audio.realtime.audio_frame import AudioFrame
from modules.devices.audio.vad import EndpointingPolicyConfig
from modules.runtime.voice_engine_v2.vad_shadow import VoiceEngineV2VadShadowObserver
from modules.runtime.voice_engine_v2.vad_timing_bridge import (
    VoiceEngineV2VadTimingBridgeAdapter,
    VoiceEngineV2VadTimingBridgeTelemetryWriter,
)


def _speech_pcm(sample_count: int = 1600) -> bytes:
    return (b"\x10\x20" * sample_count)


def _silence_pcm(sample_count: int = 1600) -> bytes:
    return (b"\x00\x00" * sample_count)


def _score_provider(frame: AudioFrame) -> float:
    return 0.0 if frame.pcm == _silence_pcm(len(frame.pcm) // 2) else 0.9


def _safe_settings(
    *,
    bridge_enabled: bool = True,
    command_asr_shadow_bridge_enabled: bool = False,
) -> dict[str, object]:
    return {
        "voice_engine": {
            "enabled": False,
            "mode": "legacy",
            "command_first_enabled": False,
            "fallback_to_legacy_enabled": True,
            "runtime_candidates_enabled": False,
            "pre_stt_shadow_enabled": True,
            "faster_whisper_audio_bus_tap_enabled": True,
            "vad_shadow_enabled": True,
            "vad_timing_bridge_enabled": bridge_enabled,
            "command_asr_shadow_bridge_enabled": (
                command_asr_shadow_bridge_enabled
            ),
            "vad_timing_bridge_log_path": (
                "var/data/voice_engine_v2_vad_timing_bridge.jsonl"
            ),
        }
    }


def _observer() -> VoiceEngineV2VadShadowObserver:
    return VoiceEngineV2VadShadowObserver(
        enabled=True,
        endpointing_policy_config=EndpointingPolicyConfig(
            min_speech_ms=120,
            min_silence_ms=180,
        ),
        max_frames_per_observation=32,
        score_provider_factory=lambda: _score_provider,
    )


def test_vad_timing_bridge_reads_frames_published_after_arm(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    audio_bus = AudioBus(
        max_duration_seconds=6.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )

    audio_bus.publish_pcm(_speech_pcm(), source="old_backlog")
    audio_bus.publish_pcm(_silence_pcm(), source="old_backlog")

    adapter = VoiceEngineV2VadTimingBridgeAdapter(
        settings=_safe_settings(),
        vad_observer=_observer(),
        telemetry_writer=VoiceEngineV2VadTimingBridgeTelemetryWriter(
            log_path,
            enabled=True,
        ),
    )
    owner = SimpleNamespace(realtime_audio_bus=audio_bus)

    armed = adapter.arm(
        owner=owner,
        turn_id="turn-bridge",
        phase="command",
        capture_mode="wake_command",
        capture_handoff={"strategy": "unit_test"},
    )

    for _index in range(3):
        audio_bus.publish_pcm(_speech_pcm(), source="current_capture")
    for _index in range(4):
        audio_bus.publish_pcm(_silence_pcm(), source="current_capture")

    record = adapter.observe_after_capture(
        owner=owner,
        turn_id="turn-bridge",
        phase="command",
        capture_mode="wake_command",
        transcript_present=True,
        transcript_metadata={"backend_label": "test"},
    )

    assert armed is True
    assert record.observed is True
    assert record.reason == "vad_timing_bridge_observed_audio"
    assert record.action_executed is False
    assert record.full_stt_prevented is False
    assert record.runtime_takeover is False
    assert record.telemetry_written is True

    assert log_path.exists()
    payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    vad_shadow = payload["vad_shadow"]

    assert payload["hook"] == "post_capture"
    assert payload["legacy_runtime_primary"] is True
    assert payload["action_executed"] is False
    assert payload["full_stt_prevented"] is False
    assert payload["runtime_takeover"] is False

    assert vad_shadow["frames_processed"] == 7
    assert vad_shadow["speech_started_count"] >= 1
    assert vad_shadow["speech_ended_count"] >= 1
    assert vad_shadow["subscription_backlog_frames"] == 7


def test_vad_timing_bridge_is_disabled_by_default(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    adapter = VoiceEngineV2VadTimingBridgeAdapter(
        settings=_safe_settings(bridge_enabled=False),
        vad_observer=_observer(),
        telemetry_writer=VoiceEngineV2VadTimingBridgeTelemetryWriter(
            log_path,
            enabled=True,
        ),
    )

    owner = SimpleNamespace(realtime_audio_bus=None)

    armed = adapter.arm(
        owner=owner,
        turn_id="turn-disabled",
        phase="command",
        capture_mode="command",
    )
    record = adapter.observe_after_capture(
        owner=owner,
        turn_id="turn-disabled",
        phase="command",
        capture_mode="command",
        transcript_present=False,
    )

    assert armed is False
    assert record.observed is False
    assert record.reason == "vad_timing_bridge_disabled"
    assert record.telemetry_written is False
    assert not log_path.exists()


def test_vad_timing_bridge_refuses_unsafe_runtime_state(tmp_path: Path) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    settings = _safe_settings()
    settings["voice_engine"]["command_first_enabled"] = True

    adapter = VoiceEngineV2VadTimingBridgeAdapter(
        settings=settings,
        vad_observer=_observer(),
        telemetry_writer=VoiceEngineV2VadTimingBridgeTelemetryWriter(
            log_path,
            enabled=True,
        ),
    )

    owner = SimpleNamespace(realtime_audio_bus=None)

    armed = adapter.arm(
        owner=owner,
        turn_id="turn-unsafe",
        phase="command",
        capture_mode="command",
    )
    record = adapter.observe_after_capture(
        owner=owner,
        turn_id="turn-unsafe",
        phase="command",
        capture_mode="command",
        transcript_present=False,
    )

    assert armed is False
    assert record.observed is False
    assert record.reason == (
        "vad_timing_bridge_not_safe:command_first_enabled_must_remain_false"
    )
    assert record.telemetry_written is True

    payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert payload["action_executed"] is False
    assert payload["full_stt_prevented"] is False
    assert payload["runtime_takeover"] is False



def test_vad_timing_bridge_observes_capture_window_before_transcription(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    audio_bus = AudioBus(
        max_duration_seconds=6.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )

    adapter = VoiceEngineV2VadTimingBridgeAdapter(
        settings=_safe_settings(),
        vad_observer=_observer(),
        telemetry_writer=VoiceEngineV2VadTimingBridgeTelemetryWriter(
            log_path,
            enabled=True,
        ),
    )
    owner = SimpleNamespace(_realtime_audio_bus_shadow_tap=audio_bus)

    armed = adapter.arm(
        owner=owner,
        turn_id="turn-pre-transcription",
        phase="command",
        capture_mode="wake_command",
        capture_handoff={"strategy": "unit_test"},
    )

    for _index in range(3):
        audio_bus.publish_pcm(
            _speech_pcm(),
            source="faster_whisper_capture_window_shadow_tap",
        )
    for _index in range(4):
        audio_bus.publish_pcm(
            _silence_pcm(),
            source="faster_whisper_capture_window_shadow_tap",
        )

    record = adapter.observe_after_capture_window_publish(
        owner=owner,
        capture_window_metadata={
            "source": "faster_whisper_capture_window_shadow_tap",
            "publish_stage": "before_transcription",
        },
    )

    assert armed is True
    assert record.observed is True
    assert record.reason == "vad_timing_bridge_pre_transcription_observed_audio"
    assert record.hook == "capture_window_pre_transcription"
    assert record.transcript_present is False
    assert record.action_executed is False
    assert record.full_stt_prevented is False
    assert record.runtime_takeover is False
    assert record.telemetry_written is True

    payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    vad_shadow = payload["vad_shadow"]

    assert payload["hook"] == "capture_window_pre_transcription"
    assert payload["transcript_present"] is False
    assert payload["metadata"]["capture_window_shadow_tap"]["publish_stage"] == (
        "before_transcription"
    )
    assert vad_shadow["frames_processed"] == 7
    assert vad_shadow["speech_started_count"] >= 1
    assert vad_shadow["speech_ended_count"] >= 1
    assert vad_shadow["frame_source_counts"] == {
        "faster_whisper_capture_window_shadow_tap": 7
    }



def test_vad_timing_bridge_writes_pre_transcription_endpointing_candidate(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    audio_bus = AudioBus(
        max_duration_seconds=6.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )

    adapter = VoiceEngineV2VadTimingBridgeAdapter(
        settings=_safe_settings(),
        vad_observer=_observer(),
        telemetry_writer=VoiceEngineV2VadTimingBridgeTelemetryWriter(
            log_path,
            enabled=True,
        ),
    )
    owner = SimpleNamespace(_realtime_audio_bus_shadow_tap=audio_bus)

    armed = adapter.arm(
        owner=owner,
        turn_id="turn-endpointing-candidate",
        phase="command",
        capture_mode="wake_command",
        capture_handoff={"strategy": "unit_test"},
    )

    for _index in range(3):
        audio_bus.publish_pcm(
            _speech_pcm(),
            source="faster_whisper_capture_window_shadow_tap",
        )
    for _index in range(4):
        audio_bus.publish_pcm(
            _silence_pcm(),
            source="faster_whisper_capture_window_shadow_tap",
        )

    capture_finished_at_monotonic = time.monotonic()

    record = adapter.observe_after_capture_window_publish(
        owner=owner,
        capture_window_metadata={
            "source": "faster_whisper_capture_window_shadow_tap",
            "publish_stage": "before_transcription",
            "sample_rate": 16_000,
            "channels": 1,
            "audio_sample_count": 32_000,
            "audio_duration_seconds": 2.0,
            "published_frame_count": 32,
            "published_byte_count": 64_000,
            "capture_finished_at_monotonic": capture_finished_at_monotonic,
            "publish_started_at_monotonic": capture_finished_at_monotonic + 0.01,
            "capture_finished_to_publish_start_ms": 10.0,
        },
    )

    assert armed is True
    assert record.observed is True
    assert record.hook == "capture_window_pre_transcription"
    assert record.transcript_present is False
    assert record.action_executed is False
    assert record.full_stt_prevented is False
    assert record.runtime_takeover is False

    candidate = record.metadata["endpointing_candidate"]

    assert candidate["candidate_present"] is True
    assert candidate["endpoint_detected"] is True
    assert candidate["reason"] == "endpoint_detected"
    assert candidate["source"] == "faster_whisper_capture_window_shadow_tap"
    assert candidate["publish_stage"] == "before_transcription"
    assert candidate["frames_processed"] == 7
    assert candidate["speech_started"] is True
    assert candidate["speech_ended"] is True
    assert candidate["action_executed"] is False
    assert candidate["full_stt_prevented"] is False
    assert candidate["runtime_takeover"] is False

    payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    logged_candidate = payload["metadata"]["endpointing_candidate"]

    assert logged_candidate["endpoint_detected"] is True
    assert logged_candidate["reason"] == "endpoint_detected"
    assert logged_candidate["source"] == "faster_whisper_capture_window_shadow_tap"
    assert logged_candidate["publish_stage"] == "before_transcription"


def test_vad_timing_bridge_does_not_attach_command_asr_shadow_by_default(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    audio_bus = AudioBus(
        max_duration_seconds=6.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )

    adapter = VoiceEngineV2VadTimingBridgeAdapter(
        settings=_safe_settings(command_asr_shadow_bridge_enabled=False),
        vad_observer=_observer(),
        telemetry_writer=VoiceEngineV2VadTimingBridgeTelemetryWriter(
            log_path,
            enabled=True,
        ),
    )
    owner = SimpleNamespace(_realtime_audio_bus_shadow_tap=audio_bus)

    armed = adapter.arm(
        owner=owner,
        turn_id="turn-command-asr-shadow-default-off",
        phase="command",
        capture_mode="wake_command",
        capture_handoff={"strategy": "unit_test"},
    )

    for _index in range(3):
        audio_bus.publish_pcm(
            _speech_pcm(),
            source="faster_whisper_capture_window_shadow_tap",
        )
    for _index in range(4):
        audio_bus.publish_pcm(
            _silence_pcm(),
            source="faster_whisper_capture_window_shadow_tap",
        )

    capture_finished_at_monotonic = time.monotonic()

    record = adapter.observe_after_capture_window_publish(
        owner=owner,
        capture_window_metadata={
            "source": "faster_whisper_capture_window_shadow_tap",
            "publish_stage": "before_transcription",
            "sample_rate": 16_000,
            "channels": 1,
            "audio_sample_count": 32_000,
            "audio_duration_seconds": 2.0,
            "published_frame_count": 32,
            "published_byte_count": 64_000,
            "capture_finished_at_monotonic": capture_finished_at_monotonic,
            "publish_started_at_monotonic": capture_finished_at_monotonic + 0.01,
            "capture_finished_to_publish_start_ms": 10.0,
        },
    )

    assert armed is True
    assert record.observed is True
    assert "command_asr_shadow_bridge" not in record.metadata
    assert "command_asr_candidate" not in record.metadata

    payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

    assert "command_asr_shadow_bridge" not in payload["metadata"]
    assert "command_asr_candidate" not in payload["metadata"]


def test_vad_timing_bridge_attaches_disabled_command_asr_shadow_when_enabled(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    audio_bus = AudioBus(
        max_duration_seconds=6.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )

    adapter = VoiceEngineV2VadTimingBridgeAdapter(
        settings=_safe_settings(command_asr_shadow_bridge_enabled=True),
        vad_observer=_observer(),
        telemetry_writer=VoiceEngineV2VadTimingBridgeTelemetryWriter(
            log_path,
            enabled=True,
        ),
    )
    owner = SimpleNamespace(_realtime_audio_bus_shadow_tap=audio_bus)

    armed = adapter.arm(
        owner=owner,
        turn_id="turn-command-asr-shadow-enabled",
        phase="command",
        capture_mode="wake_command",
        capture_handoff={"strategy": "unit_test"},
    )

    for _index in range(3):
        audio_bus.publish_pcm(
            _speech_pcm(),
            source="faster_whisper_capture_window_shadow_tap",
        )
    for _index in range(4):
        audio_bus.publish_pcm(
            _silence_pcm(),
            source="faster_whisper_capture_window_shadow_tap",
        )

    capture_finished_at_monotonic = time.monotonic()

    record = adapter.observe_after_capture_window_publish(
        owner=owner,
        capture_window_metadata={
            "source": "faster_whisper_capture_window_shadow_tap",
            "publish_stage": "before_transcription",
            "sample_rate": 16_000,
            "channels": 1,
            "audio_sample_count": 32_000,
            "audio_duration_seconds": 2.0,
            "published_frame_count": 32,
            "published_byte_count": 64_000,
            "capture_finished_at_monotonic": capture_finished_at_monotonic,
            "publish_started_at_monotonic": capture_finished_at_monotonic + 0.01,
            "capture_finished_to_publish_start_ms": 10.0,
        },
    )

    assert armed is True
    assert record.observed is True
    assert record.action_executed is False
    assert record.full_stt_prevented is False
    assert record.runtime_takeover is False

    bridge = record.metadata["command_asr_shadow_bridge"]
    candidate = record.metadata["command_asr_candidate"]

    assert bridge["enabled"] is True
    assert bridge["observed"] is True
    assert bridge["reason"] == "command_asr_shadow_bridge_observed"
    assert bridge["candidate_attached"] is True
    assert bridge["command_asr_candidate_present"] is False
    assert bridge["command_asr_reason"] == "command_asr_disabled"
    assert bridge["asr_reason"] == "command_asr_disabled"
    assert bridge["recognizer_name"] == "disabled_command_asr"
    assert bridge["recognizer_enabled"] is False
    assert bridge["recognition_attempted"] is False
    assert bridge["recognized"] is False
    assert bridge["raw_pcm_included"] is False
    assert bridge["action_executed"] is False
    assert bridge["full_stt_prevented"] is False
    assert bridge["runtime_takeover"] is False

    assert candidate["candidate_present"] is False
    assert candidate["reason"] == "command_asr_disabled"
    assert candidate["recognizer_name"] == "disabled_command_asr"
    assert candidate["recognizer_enabled"] is False
    assert candidate["recognition_attempted"] is False
    assert candidate["recognized"] is False
    assert candidate["raw_pcm_included"] is False
    assert candidate["action_executed"] is False
    assert candidate["full_stt_prevented"] is False
    assert candidate["runtime_takeover"] is False

    payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    logged_bridge = payload["metadata"]["command_asr_shadow_bridge"]
    logged_candidate = payload["metadata"]["command_asr_candidate"]

    assert logged_bridge["enabled"] is True
    assert logged_bridge["candidate_attached"] is True
    assert logged_bridge["recognizer_enabled"] is False
    assert logged_bridge["recognition_attempted"] is False
    assert logged_bridge["recognized"] is False
    assert logged_candidate["raw_pcm_included"] is False