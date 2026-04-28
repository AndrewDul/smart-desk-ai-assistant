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
    return b"\x10\x20" * sample_count


def _silence_pcm(sample_count: int = 1600) -> bytes:
    return b"\x00\x00" * sample_count


def _score_provider(frame: AudioFrame) -> float:
    return 0.0 if frame.pcm == _silence_pcm(len(frame.pcm) // 2) else 0.9


def _safe_settings(
    *,
    command_asr_shadow_bridge_enabled: bool,
    vosk_live_shadow_contract_enabled: bool,
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
            "vad_timing_bridge_enabled": True,
            "command_asr_shadow_bridge_enabled": (
                command_asr_shadow_bridge_enabled
            ),
            "vosk_live_shadow_contract_enabled": (
                vosk_live_shadow_contract_enabled
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


def _record_for_settings(
    *,
    tmp_path: Path,
    command_asr_shadow_bridge_enabled: bool,
    vosk_live_shadow_contract_enabled: bool,
):
    log_path = tmp_path / "vad_timing_bridge.jsonl"
    audio_bus = AudioBus(
        max_duration_seconds=6.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )

    adapter = VoiceEngineV2VadTimingBridgeAdapter(
        settings=_safe_settings(
            command_asr_shadow_bridge_enabled=command_asr_shadow_bridge_enabled,
            vosk_live_shadow_contract_enabled=vosk_live_shadow_contract_enabled,
        ),
        vad_observer=_observer(),
        telemetry_writer=VoiceEngineV2VadTimingBridgeTelemetryWriter(
            log_path,
            enabled=True,
        ),
    )
    owner = SimpleNamespace(_realtime_audio_bus_shadow_tap=audio_bus)

    armed = adapter.arm(
        owner=owner,
        turn_id="turn-vosk-live-shadow-contract",
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

    payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    return armed, record, payload


def test_vad_timing_bridge_does_not_attach_vosk_live_shadow_by_default(
    tmp_path: Path,
) -> None:
    armed, record, payload = _record_for_settings(
        tmp_path=tmp_path,
        command_asr_shadow_bridge_enabled=True,
        vosk_live_shadow_contract_enabled=False,
    )

    assert armed is True
    assert record.observed is True
    assert "command_asr_shadow_bridge" in record.metadata
    assert "command_asr_candidate" in record.metadata
    assert "vosk_live_shadow" not in record.metadata
    assert "vosk_live_shadow" not in payload["metadata"]


def test_vad_timing_bridge_requires_command_asr_shadow_for_vosk_live_shadow(
    tmp_path: Path,
) -> None:
    armed, record, payload = _record_for_settings(
        tmp_path=tmp_path,
        command_asr_shadow_bridge_enabled=False,
        vosk_live_shadow_contract_enabled=True,
    )

    assert armed is True
    assert record.observed is True
    assert "command_asr_shadow_bridge" not in record.metadata
    assert "command_asr_candidate" not in record.metadata
    assert "vosk_live_shadow" not in record.metadata
    assert "vosk_live_shadow" not in payload["metadata"]


def test_vad_timing_bridge_attaches_enabled_vosk_live_shadow_contract(
    tmp_path: Path,
) -> None:
    armed, record, payload = _record_for_settings(
        tmp_path=tmp_path,
        command_asr_shadow_bridge_enabled=True,
        vosk_live_shadow_contract_enabled=True,
    )

    assert armed is True
    assert record.observed is True
    assert record.action_executed is False
    assert record.full_stt_prevented is False
    assert record.runtime_takeover is False

    assert "command_asr_shadow_bridge" in record.metadata
    assert "command_asr_candidate" in record.metadata
    assert "vosk_live_shadow" in record.metadata

    contract = record.metadata["vosk_live_shadow"]

    assert contract["contract_stage"] == "vosk_live_shadow_contract"
    assert contract["contract_version"] == "vosk_live_shadow_contract_v1"
    assert contract["enabled"] is True
    assert contract["observed"] is False
    assert contract["reason"] == "vosk_live_shadow_result_missing"
    assert contract["metadata_key"] == "vosk_live_shadow"
    assert contract["input_source"] == "existing_command_audio_segment"
    assert contract["recognizer_name"] == "vosk_command_asr_shadow"
    assert contract["recognizer_enabled"] is False
    assert contract["recognition_attempted"] is False
    assert contract["recognized"] is False
    assert contract["transcript"] == ""
    assert contract["normalized_text"] == ""
    assert contract["command_matched"] is False
    assert contract["runtime_integration"] is False
    assert contract["command_execution_enabled"] is False
    assert contract["faster_whisper_bypass_enabled"] is False
    assert contract["microphone_stream_started"] is False
    assert contract["independent_microphone_stream_started"] is False
    assert contract["live_command_recognition_enabled"] is False
    assert contract["raw_pcm_included"] is False
    assert contract["action_executed"] is False
    assert contract["full_stt_prevented"] is False
    assert contract["runtime_takeover"] is False

    logged_contract = payload["metadata"]["vosk_live_shadow"]
    assert logged_contract == contract