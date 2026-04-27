from modules.devices.audio.realtime.audio_bus import AudioBus


def _pcm(sample_count: int = 1600) -> bytes:
    return b"\x00\x00" * sample_count


def test_audio_bus_assigns_monotonic_sequences() -> None:
    bus = AudioBus(
        max_duration_seconds=1.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )

    first = bus.publish_pcm(_pcm(), timestamp_monotonic=1.0, source="test")
    second = bus.publish_pcm(_pcm(), timestamp_monotonic=2.0, source="test")

    assert first.sequence == 0
    assert second.sequence == 1
    assert bus.latest_sequence == 1
    assert bus.frame_count == 2


def test_audio_bus_subscription_reads_only_new_frames() -> None:
    bus = AudioBus(
        max_duration_seconds=1.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )

    bus.publish_pcm(_pcm(), timestamp_monotonic=1.0, source="test")
    subscription = bus.create_subscription("vad", start_at_latest=True)

    bus.publish_pcm(_pcm(), timestamp_monotonic=2.0, source="test")
    bus.publish_pcm(_pcm(), timestamp_monotonic=3.0, source="test")

    frames = subscription.read_available()

    assert [frame.sequence for frame in frames] == [1, 2]
    assert subscription.read_available() == []


def test_audio_bus_subscription_can_start_from_oldest_buffered_frame() -> None:
    bus = AudioBus(
        max_duration_seconds=1.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )

    bus.publish_pcm(_pcm(), timestamp_monotonic=1.0, source="test")
    bus.publish_pcm(_pcm(), timestamp_monotonic=2.0, source="test")

    subscription = bus.create_subscription("command-asr", start_at_latest=False)

    frames = subscription.read_available()

    assert [frame.sequence for frame in frames] == [0, 1]


def test_audio_bus_read_pcm_concatenates_available_frames() -> None:
    bus = AudioBus(
        max_duration_seconds=1.0,
        sample_rate=16_000,
        channels=1,
        sample_width_bytes=2,
    )
    subscription = bus.create_subscription("reader", start_at_latest=True)

    first_pcm = b"\x01\x00" * 1600
    second_pcm = b"\x02\x00" * 1600

    bus.publish_pcm(first_pcm, timestamp_monotonic=1.0, source="test")
    bus.publish_pcm(second_pcm, timestamp_monotonic=2.0, source="test")

    assert subscription.read_pcm() == first_pcm + second_pcm