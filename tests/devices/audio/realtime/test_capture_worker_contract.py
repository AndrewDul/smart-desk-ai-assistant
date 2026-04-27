from collections import deque

from modules.devices.audio.realtime.audio_bus import AudioBus
from modules.devices.audio.realtime.audio_device_config import AudioDeviceConfig
from modules.devices.audio.realtime.capture_worker import AudioCaptureWorker


def test_capture_worker_run_once_publishes_pcm_to_audio_bus() -> None:
    chunks: deque[bytes | None] = deque([b"\x00\x00" * 1600])

    bus = AudioBus(
        max_duration_seconds=1.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )
    config = AudioDeviceConfig(
        sample_rate=16_000,
        channels=1,
        blocksize=1600,
        sample_width_bytes=2,
        source_name="test-microphone",
    )
    worker = AudioCaptureWorker(
        audio_bus=bus,
        config=config,
        pcm_reader=chunks.popleft,
    )

    frame = worker.run_once()

    assert frame is not None
    assert frame.sequence == 0
    assert frame.source == "test-microphone"
    assert worker.published_frames == 1
    assert bus.frame_count == 1


def test_capture_worker_ignores_empty_reads() -> None:
    chunks: deque[bytes | None] = deque([b"", None])

    bus = AudioBus(
        max_duration_seconds=1.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )
    config = AudioDeviceConfig(source_name="test-microphone")
    worker = AudioCaptureWorker(
        audio_bus=bus,
        config=config,
        pcm_reader=chunks.popleft,
    )

    assert worker.run_once() is None
    assert worker.run_once() is None
    assert worker.published_frames == 0
    assert bus.frame_count == 0


def test_audio_device_config_from_settings_reads_voice_input_defaults() -> None:
    config = AudioDeviceConfig.from_settings(
        {
            "voice_input": {
                "sample_rate": 16_000,
                "blocksize": 1024,
                "device_index": 2,
                "device_name_contains": "reSpeaker",
            }
        }
    )

    assert config.sample_rate == 16_000
    assert config.blocksize == 1024
    assert config.device_index == 2
    assert config.device_name_contains == "reSpeaker"
    assert config.source_name == "reSpeaker"