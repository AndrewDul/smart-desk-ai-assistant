from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RealtimeAudioBusProbeSnapshot:
    """Safe observe-only snapshot of a realtime audio bus candidate."""

    audio_bus_present: bool
    sample_rate: int | None = None
    channels: int | None = None
    sample_width_bytes: int | None = None
    frame_count: int | None = None
    duration_seconds: float | None = None
    latest_sequence: int | None = None
    snapshot_byte_count: int | None = None
    source: str = ""
    probe_error: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "audio_bus_present": self.audio_bus_present,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "sample_width_bytes": self.sample_width_bytes,
            "frame_count": self.frame_count,
            "duration_seconds": self.duration_seconds,
            "latest_sequence": self.latest_sequence,
            "snapshot_byte_count": self.snapshot_byte_count,
            "source": self.source,
            "probe_error": self.probe_error,
        }


def find_realtime_audio_bus(owner: Any) -> tuple[Any | None, str]:
    """Find a realtime audio bus candidate without creating or owning one."""

    direct_bus = getattr(owner, "realtime_audio_bus", None)
    if direct_bus is not None:
        return direct_bus, "assistant.realtime_audio_bus"

    audio_runtime = getattr(owner, "audio_runtime", None)
    runtime_bus = getattr(audio_runtime, "realtime_audio_bus", None)
    if runtime_bus is not None:
        return runtime_bus, "assistant.audio_runtime.realtime_audio_bus"

    faster_whisper_shadow_bus = getattr(
        owner,
        "_realtime_audio_bus_shadow_tap",
        None,
    )
    if faster_whisper_shadow_bus is not None:
        return (
            faster_whisper_shadow_bus,
            "faster_whisper._realtime_audio_bus_shadow_tap",
        )

    runtime = getattr(owner, "runtime", None)
    metadata = getattr(runtime, "metadata", {}) if runtime is not None else {}
    if isinstance(metadata, dict):
        metadata_bus = metadata.get("realtime_audio_bus")
        if metadata_bus is not None:
            return metadata_bus, "runtime.metadata.realtime_audio_bus"

        voice_engine_metadata = metadata.get("voice_engine_v2_metadata")
        if isinstance(voice_engine_metadata, dict):
            nested_bus = voice_engine_metadata.get("realtime_audio_bus")
            if nested_bus is not None:
                return nested_bus, "runtime.metadata.voice_engine_v2_metadata.realtime_audio_bus"

    return None, ""


def probe_realtime_audio_bus(owner: Any) -> RealtimeAudioBusProbeSnapshot:
    """Return a fail-open snapshot of the realtime audio bus candidate.

    The probe never starts capture, never subscribes as a consumer and never
    mutates the bus. It only reads public diagnostic properties.
    """

    audio_bus, source = find_realtime_audio_bus(owner)
    if audio_bus is None:
        return RealtimeAudioBusProbeSnapshot(
            audio_bus_present=False,
            source="",
        )

    try:
        snapshot_byte_count = _safe_snapshot_byte_count(audio_bus)

        return RealtimeAudioBusProbeSnapshot(
            audio_bus_present=True,
            sample_rate=_safe_int(getattr(audio_bus, "sample_rate", None)),
            channels=_safe_int(getattr(audio_bus, "channels", None)),
            sample_width_bytes=_safe_int(
                getattr(audio_bus, "sample_width_bytes", None)
            ),
            frame_count=_safe_int(getattr(audio_bus, "frame_count", None)),
            duration_seconds=_safe_float(
                getattr(audio_bus, "duration_seconds", None)
            ),
            latest_sequence=_safe_int(getattr(audio_bus, "latest_sequence", None)),
            snapshot_byte_count=snapshot_byte_count,
            source=source,
        )
    except Exception as error:
        return RealtimeAudioBusProbeSnapshot(
            audio_bus_present=True,
            source=source,
            probe_error=type(error).__name__,
        )


def _safe_snapshot_byte_count(audio_bus: Any) -> int | None:
    snapshot_pcm = getattr(audio_bus, "snapshot_pcm", None)
    if not callable(snapshot_pcm):
        return None

    try:
        pcm = snapshot_pcm(max_duration_seconds=0.25)
    except TypeError:
        pcm = snapshot_pcm()
    except Exception:
        return None

    if not isinstance(pcm, bytes):
        return None

    return len(pcm)


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None