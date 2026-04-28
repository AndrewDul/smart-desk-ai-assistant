from __future__ import annotations

from modules.runtime.voice_engine_v2.faster_whisper_audio_bus_tap import (
    configure_faster_whisper_audio_bus_shadow_tap,
)


class FakeFasterWhisperVoiceInput:
    def __init__(self) -> None:
        self.sample_rate = 16_000
        self.channels = 1
        self.attached_bus = None
        self.attached_enabled = False
        self.capture_window_observer = None
        self.capture_window_observer_enabled = False

    def set_realtime_audio_bus_shadow_tap(self, audio_bus, *, enabled: bool) -> None:
        self.attached_bus = audio_bus
        self.attached_enabled = enabled

    def set_realtime_audio_bus_capture_window_observer(
        self,
        observer,
        *,
        enabled: bool,
    ) -> None:
        self.capture_window_observer = observer if enabled else None
        self.capture_window_observer_enabled = bool(enabled and observer is not None)


class UnsupportedVoiceInput:
    sample_rate = 16_000
    channels = 1


def test_faster_whisper_audio_bus_tap_is_disabled_by_default() -> None:
    voice_input = FakeFasterWhisperVoiceInput()

    audio_bus, status = configure_faster_whisper_audio_bus_shadow_tap(
        voice_input=voice_input,
        settings={"voice_engine": {}},
    )

    assert audio_bus is None
    assert status.enabled is False
    assert status.attached is False
    assert status.reason == "disabled"
    assert voice_input.attached_bus is None
    assert voice_input.attached_enabled is False
    assert voice_input.capture_window_observer is None
    assert voice_input.capture_window_observer_enabled is False


def test_faster_whisper_audio_bus_tap_attaches_runtime_owned_bus() -> None:
    voice_input = FakeFasterWhisperVoiceInput()

    audio_bus, status = configure_faster_whisper_audio_bus_shadow_tap(
        voice_input=voice_input,
        settings={
            "voice_engine": {
                "faster_whisper_audio_bus_tap_enabled": True,
                "faster_whisper_audio_bus_tap_max_duration_seconds": 2.5,
            }
        },
    )

    assert audio_bus is not None
    assert voice_input.attached_bus is audio_bus
    assert voice_input.attached_enabled is True

    assert status.enabled is True
    assert status.attached is True
    assert status.reason == "attached"
    assert status.sample_rate == 16_000
    assert status.channels == 1
    assert status.sample_width_bytes == 2
    assert status.max_duration_seconds == 2.5

    metadata = status.to_metadata()
    assert metadata["enabled"] is True
    assert metadata["attached"] is True
    assert metadata["reason"] == "attached"
    assert metadata["capture_window_observer_attached"] is False


def test_faster_whisper_audio_bus_tap_refuses_unsupported_voice_input() -> None:
    audio_bus, status = configure_faster_whisper_audio_bus_shadow_tap(
        voice_input=UnsupportedVoiceInput(),
        settings={
            "voice_engine": {
                "faster_whisper_audio_bus_tap_enabled": True,
            }
        },
    )

    assert audio_bus is None
    assert status.enabled is True
    assert status.attached is False
    assert status.reason == "unsupported_voice_input"


def test_faster_whisper_audio_bus_tap_uses_safe_config_fallbacks() -> None:
    voice_input = FakeFasterWhisperVoiceInput()
    voice_input.sample_rate = None
    voice_input.channels = None

    audio_bus, status = configure_faster_whisper_audio_bus_shadow_tap(
        voice_input=voice_input,
        settings={
            "voice_engine": {
                "faster_whisper_audio_bus_tap_enabled": True,
                "faster_whisper_audio_bus_tap_sample_rate": "bad",
                "faster_whisper_audio_bus_tap_channels": 0,
                "faster_whisper_audio_bus_tap_sample_width_bytes": -1,
                "faster_whisper_audio_bus_tap_max_duration_seconds": 0,
            }
        },
    )

    assert audio_bus is not None
    assert status.attached is True
    assert status.sample_rate == 16_000
    assert status.channels == 1
    assert status.sample_width_bytes == 2
    assert status.max_duration_seconds == 3.0




def test_faster_whisper_audio_bus_tap_attaches_capture_window_observer() -> None:
    voice_input = FakeFasterWhisperVoiceInput()

    def observer(**_kwargs):
        return None

    audio_bus, status = configure_faster_whisper_audio_bus_shadow_tap(
        voice_input=voice_input,
        settings={
            "voice_engine": {
                "faster_whisper_audio_bus_tap_enabled": True,
            }
        },
        capture_window_observer=observer,
    )

    assert audio_bus is not None
    assert voice_input.attached_bus is audio_bus
    assert voice_input.attached_enabled is True
    assert voice_input.capture_window_observer is observer
    assert voice_input.capture_window_observer_enabled is True
    assert status.capture_window_observer_attached is True

    metadata = status.to_metadata()
    assert metadata["capture_window_observer_attached"] is True