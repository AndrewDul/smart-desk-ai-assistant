from __future__ import annotations

from types import SimpleNamespace

from modules.devices.audio.realtime import AudioBus
from modules.runtime.voice_engine_v2.realtime_audio_bus_probe import (
    find_realtime_audio_bus,
    probe_realtime_audio_bus,
)


def test_realtime_audio_bus_probe_reports_missing_bus() -> None:
    owner = SimpleNamespace()

    snapshot = probe_realtime_audio_bus(owner)

    assert snapshot.audio_bus_present is False
    assert snapshot.source == ""
    assert snapshot.probe_error == ""


def test_realtime_audio_bus_probe_reads_assistant_direct_bus() -> None:
    bus = AudioBus(
        max_duration_seconds=1.0,
        sample_rate=16000,
        channels=1,
        sample_width_bytes=2,
    )
    bus.publish_pcm(b"\x00\x00" * 160)
    owner = SimpleNamespace(realtime_audio_bus=bus)

    snapshot = probe_realtime_audio_bus(owner)

    assert snapshot.audio_bus_present is True
    assert snapshot.source == "assistant.realtime_audio_bus"
    assert snapshot.sample_rate == 16000
    assert snapshot.channels == 1
    assert snapshot.sample_width_bytes == 2
    assert snapshot.frame_count == 1
    assert snapshot.latest_sequence == 0
    assert snapshot.snapshot_byte_count == 320
    assert snapshot.probe_error == ""


def test_realtime_audio_bus_probe_reads_audio_runtime_bus() -> None:
    bus = AudioBus(
        max_duration_seconds=1.0,
        sample_rate=16000,
        channels=1,
        sample_width_bytes=2,
    )
    owner = SimpleNamespace(
        audio_runtime=SimpleNamespace(realtime_audio_bus=bus),
    )

    found_bus, source = find_realtime_audio_bus(owner)

    assert found_bus is bus
    assert source == "assistant.audio_runtime.realtime_audio_bus"


def test_realtime_audio_bus_probe_reads_runtime_metadata_bus() -> None:
    bus = AudioBus(
        max_duration_seconds=1.0,
        sample_rate=16000,
        channels=1,
        sample_width_bytes=2,
    )
    owner = SimpleNamespace(
        runtime=SimpleNamespace(metadata={"realtime_audio_bus": bus}),
    )

    found_bus, source = find_realtime_audio_bus(owner)

    assert found_bus is bus
    assert source == "runtime.metadata.realtime_audio_bus"


def test_realtime_audio_bus_probe_is_fail_open_when_bus_property_fails() -> None:
    class BrokenBus:
        @property
        def sample_rate(self):
            raise RuntimeError("broken bus")

    owner = SimpleNamespace(realtime_audio_bus=BrokenBus())

    snapshot = probe_realtime_audio_bus(owner)

    assert snapshot.audio_bus_present is True
    assert snapshot.source == "assistant.realtime_audio_bus"
    assert snapshot.probe_error == "RuntimeError"