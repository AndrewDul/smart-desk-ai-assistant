from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from modules.devices.audio.realtime import AudioBus


@dataclass(frozen=True, slots=True)
class FasterWhisperAudioBusTapStatus:
    enabled: bool
    attached: bool
    reason: str
    source: str
    sample_rate: int | None = None
    channels: int | None = None
    sample_width_bytes: int | None = None
    max_duration_seconds: float | None = None

    def to_metadata(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "attached": self.attached,
            "reason": self.reason,
            "source": self.source,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "sample_width_bytes": self.sample_width_bytes,
            "max_duration_seconds": self.max_duration_seconds,
        }


def configure_faster_whisper_audio_bus_shadow_tap(
    *,
    voice_input: Any,
    settings: Mapping[str, Any],
) -> tuple[AudioBus | None, FasterWhisperAudioBusTapStatus]:
    voice_engine_cfg = _voice_engine_config(settings)

    enabled = bool(voice_engine_cfg.get("faster_whisper_audio_bus_tap_enabled", False))
    source_name = str(
        voice_engine_cfg.get(
            "faster_whisper_audio_bus_tap_source",
            "faster_whisper_callback_shadow_tap",
        )
        or "faster_whisper_callback_shadow_tap"
    ).strip()

    if not enabled:
        _detach_if_supported(voice_input)
        return (
            None,
            FasterWhisperAudioBusTapStatus(
                enabled=False,
                attached=False,
                reason="disabled",
                source=source_name,
            ),
        )

    setter = getattr(voice_input, "set_realtime_audio_bus_shadow_tap", None)
    if not callable(setter):
        return (
            None,
            FasterWhisperAudioBusTapStatus(
                enabled=True,
                attached=False,
                reason="unsupported_voice_input",
                source=source_name,
            ),
        )

    sample_rate = _positive_int(
        getattr(voice_input, "sample_rate", None),
        fallback=_positive_int(
            voice_engine_cfg.get("faster_whisper_audio_bus_tap_sample_rate"),
            fallback=16_000,
        ),
    )
    channels = _positive_int(
        getattr(voice_input, "channels", None),
        fallback=_positive_int(
            voice_engine_cfg.get("faster_whisper_audio_bus_tap_channels"),
            fallback=1,
        ),
    )
    sample_width_bytes = _positive_int(
        voice_engine_cfg.get("faster_whisper_audio_bus_tap_sample_width_bytes"),
        fallback=2,
    )
    max_duration_seconds = _positive_float(
        voice_engine_cfg.get("faster_whisper_audio_bus_tap_max_duration_seconds"),
        fallback=3.0,
    )

    try:
        audio_bus = AudioBus(
            max_duration_seconds=max_duration_seconds,
            sample_rate=sample_rate,
            channels=channels,
            sample_width_bytes=sample_width_bytes,
            source_name=source_name,
        )
        setter(audio_bus, enabled=True)
    except Exception as error:
        return (
            None,
            FasterWhisperAudioBusTapStatus(
                enabled=True,
                attached=False,
                reason=f"attach_failed:{type(error).__name__}",
                source=source_name,
                sample_rate=sample_rate,
                channels=channels,
                sample_width_bytes=sample_width_bytes,
                max_duration_seconds=max_duration_seconds,
            ),
        )

    return (
        audio_bus,
        FasterWhisperAudioBusTapStatus(
            enabled=True,
            attached=True,
            reason="attached",
            source=source_name,
            sample_rate=sample_rate,
            channels=channels,
            sample_width_bytes=sample_width_bytes,
            max_duration_seconds=max_duration_seconds,
        ),
    )


def _detach_if_supported(voice_input: Any) -> None:
    setter = getattr(voice_input, "set_realtime_audio_bus_shadow_tap", None)
    if callable(setter):
        try:
            setter(None, enabled=False)
        except Exception:
            return


def _voice_engine_config(settings: Mapping[str, Any]) -> Mapping[str, Any]:
    voice_engine_cfg = settings.get("voice_engine", {})
    if isinstance(voice_engine_cfg, Mapping):
        return voice_engine_cfg
    return {}


def _positive_int(raw_value: Any, *, fallback: int) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


def _positive_float(raw_value: Any, *, fallback: float) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


__all__ = [
    "FasterWhisperAudioBusTapStatus",
    "configure_faster_whisper_audio_bus_shadow_tap",
]