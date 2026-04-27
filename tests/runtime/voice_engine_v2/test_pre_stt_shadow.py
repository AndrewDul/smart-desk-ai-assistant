from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from modules.runtime.main_loop.active_window import (
    _observe_voice_engine_v2_pre_stt_shadow,
)
from modules.runtime.voice_engine_v2 import build_voice_engine_v2_runtime


def _bundle(
    *,
    log_path: Path,
    pre_stt_shadow_enabled: bool,
    enabled: bool = False,
    mode: str = "legacy",
    command_first_enabled: bool = False,
    fallback_to_legacy_enabled: bool = True,
):
    return build_voice_engine_v2_runtime(
        {
            "voice_engine": {
                "enabled": enabled,
                "version": "v2",
                "mode": mode,
                "command_first_enabled": command_first_enabled,
                "fallback_to_legacy_enabled": fallback_to_legacy_enabled,
                "pre_stt_shadow_enabled": pre_stt_shadow_enabled,
                "pre_stt_shadow_log_path": str(log_path),
            }
        }
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_pre_stt_shadow_adapter_does_not_write_when_disabled(tmp_path: Path) -> None:
    log_path = tmp_path / "pre_stt_shadow.jsonl"
    bundle = _bundle(
        log_path=log_path,
        pre_stt_shadow_enabled=False,
    )

    result = bundle.pre_stt_shadow_adapter.observe_pre_stt(
        turn_id="turn-disabled",
        phase="command",
        capture_mode="command",
        input_owner="voice_input",
    )

    assert result.enabled is False
    assert result.observed is False
    assert result.reason == "pre_stt_shadow_disabled"
    assert result.action_executed is False
    assert result.full_stt_prevented is False
    assert result.telemetry_written is False
    assert not log_path.exists()


def test_pre_stt_shadow_adapter_writes_observe_only_record_when_enabled(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "pre_stt_shadow.jsonl"
    bundle = _bundle(
        log_path=log_path,
        pre_stt_shadow_enabled=True,
    )

    result = bundle.pre_stt_shadow_adapter.observe_pre_stt(
        turn_id="turn-enabled",
        phase="command",
        capture_mode="command",
        input_owner="voice_input",
        audio_bus_available=False,
        audio_bus_probe={
            "audio_bus_present": False,
            "source": "",
        },
        metadata={"source": "unit_test"},
    )

    assert result.enabled is True
    assert result.observed is True
    assert result.reason == "audio_bus_unavailable_observe_only"
    assert result.legacy_runtime_primary is True
    assert result.action_executed is False
    assert result.full_stt_prevented is False
    assert result.telemetry_written is True

    records = _read_jsonl(log_path)

    assert len(records) == 1
    assert records[0]["turn_id"] == "turn-enabled"
    assert records[0]["phase"] == "command"
    assert records[0]["capture_mode"] == "command"
    assert records[0]["legacy_runtime_primary"] is True
    assert records[0]["action_executed"] is False
    assert records[0]["full_stt_prevented"] is False
    assert records[0]["reason"] == "audio_bus_unavailable_observe_only"
    assert records[0]["metadata"]["source"] == "unit_test"
    assert records[0]["audio_bus_probe"]["audio_bus_present"] is False
    assert records[0]["metadata"]["audio_bus_probe"]["audio_bus_present"] is False

def test_pre_stt_shadow_adapter_refuses_unsafe_full_v2_state(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "pre_stt_shadow.jsonl"
    bundle = _bundle(
        log_path=log_path,
        pre_stt_shadow_enabled=True,
        enabled=True,
        mode="v2",
        command_first_enabled=True,
    )

    result = bundle.pre_stt_shadow_adapter.observe_pre_stt(
        turn_id="turn-unsafe",
        phase="command",
        capture_mode="command",
        input_owner="voice_input",
    )

    assert result.enabled is True
    assert result.observed is False
    assert result.reason == "pre_stt_shadow_not_safe"
    assert result.action_executed is False
    assert result.full_stt_prevented is False
    assert result.telemetry_written is True

    records = _read_jsonl(log_path)
    assert records[0]["reason"] == "pre_stt_shadow_not_safe"


def test_pre_stt_shadow_hook_is_fail_open_without_adapter() -> None:
    assistant = SimpleNamespace(
        runtime=SimpleNamespace(metadata={}),
        voice_session=SimpleNamespace(
            state="listening",
            input_owner=lambda: "voice_input",
        ),
    )

    observed = _observe_voice_engine_v2_pre_stt_shadow(
        assistant,
        phase="command",
        capture_mode="command",
        capture_handoff={"strategy": "unit_test"},
    )

    assert observed is False


def test_pre_stt_shadow_hook_calls_adapter_without_preventing_stt(tmp_path: Path) -> None:
    log_path = tmp_path / "pre_stt_shadow.jsonl"
    bundle = _bundle(
        log_path=log_path,
        pre_stt_shadow_enabled=True,
    )
    assistant = SimpleNamespace(
        voice_engine_v2_pre_stt_shadow_adapter=bundle.pre_stt_shadow_adapter,
        runtime=SimpleNamespace(metadata={}),
        voice_session=SimpleNamespace(
            state="listening",
            input_owner=lambda: "voice_input",
        ),
        turn_benchmark_service=SimpleNamespace(current_turn_id="turn-hook"),
        realtime_audio_bus=None,
    )

    observed = _observe_voice_engine_v2_pre_stt_shadow(
        assistant,
        phase="command",
        capture_mode="command",
        capture_handoff={"strategy": "unit_test"},
    )

    assert observed is True
    assert hasattr(assistant, "_last_voice_engine_v2_pre_stt_shadow")
    assert assistant._last_voice_engine_v2_pre_stt_shadow.full_stt_prevented is False
    assert log_path.exists()

    records = _read_jsonl(log_path)
    assert records[0]["turn_id"] == "turn-hook"
    assert records[0]["metadata"]["capture_handoff"]["strategy"] == "unit_test"
    assert records[0]["audio_bus_probe"]["audio_bus_present"] is False
    assert records[0]["metadata"]["audio_bus_probe"]["audio_bus_present"] is False



def test_pre_stt_shadow_hook_records_realtime_audio_bus_probe(tmp_path: Path) -> None:
    from modules.devices.audio.realtime import AudioBus

    log_path = tmp_path / "pre_stt_shadow.jsonl"
    bundle = _bundle(
        log_path=log_path,
        pre_stt_shadow_enabled=True,
    )

    bus = AudioBus(
        max_duration_seconds=1.0,
        sample_rate=16000,
        channels=1,
        sample_width_bytes=2,
    )
    bus.publish_pcm(b"\x00\x00" * 80)

    assistant = SimpleNamespace(
        voice_engine_v2_pre_stt_shadow_adapter=bundle.pre_stt_shadow_adapter,
        runtime=SimpleNamespace(metadata={}),
        voice_session=SimpleNamespace(
            state="listening",
            input_owner=lambda: "voice_input",
        ),
        turn_benchmark_service=SimpleNamespace(current_turn_id="turn-hook-bus"),
        realtime_audio_bus=bus,
    )

    observed = _observe_voice_engine_v2_pre_stt_shadow(
        assistant,
        phase="command",
        capture_mode="command",
        capture_handoff={"strategy": "unit_test"},
    )

    assert observed is True

    records = _read_jsonl(log_path)
    assert records[0]["audio_bus_available"] is True
    assert records[0]["reason"] == "audio_bus_available_observe_only"
    assert records[0]["audio_bus_probe"]["audio_bus_present"] is True
    assert records[0]["audio_bus_probe"]["sample_rate"] == 16000
    assert records[0]["audio_bus_probe"]["channels"] == 1
    assert records[0]["audio_bus_probe"]["frame_count"] == 1
    assert records[0]["audio_bus_probe"]["snapshot_byte_count"] == 160
    assert records[0]["metadata"]["audio_bus_probe"]["audio_bus_present"] is True