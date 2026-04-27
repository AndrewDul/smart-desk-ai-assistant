from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from modules.core.voice_engine import VoiceEngineSettings


@dataclass(frozen=True, slots=True)
class VoiceEngineV2PreSttShadowRequest:
    """Observation request captured before legacy full STT starts."""

    turn_id: str
    phase: str
    capture_mode: str
    input_owner: str
    source: str = "active_window"
    audio_bus_available: bool = False
    audio_bus_probe: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.turn_id.strip():
            raise ValueError("turn_id must not be empty")
        if not self.phase.strip():
            raise ValueError("phase must not be empty")
        if not self.capture_mode.strip():
            raise ValueError("capture_mode must not be empty")
        if not self.input_owner.strip():
            raise ValueError("input_owner must not be empty")
        if not self.source.strip():
            raise ValueError("source must not be empty")

        object.__setattr__(self, "metadata", dict(self.metadata or {}))
        object.__setattr__(self, "audio_bus_probe", dict(self.audio_bus_probe or {}))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))


@dataclass(frozen=True, slots=True)
class VoiceEngineV2PreSttShadowResult:
    """Result of the pre-STT shadow observation."""

    enabled: bool
    observed: bool
    reason: str
    legacy_runtime_primary: bool
    action_executed: bool
    full_stt_prevented: bool
    request: VoiceEngineV2PreSttShadowRequest
    timestamp_utc: str
    timestamp_monotonic: float
    metadata: dict[str, Any] = field(default_factory=dict)
    telemetry_written: bool = False

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("reason must not be empty")
        if not self.timestamp_utc.strip():
            raise ValueError("timestamp_utc must not be empty")
        if self.action_executed:
            raise ValueError("pre-STT shadow result must never execute actions")
        if self.full_stt_prevented:
            raise ValueError("Stage 21A must never prevent legacy full STT")

        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def with_telemetry_written(
        self,
        telemetry_written: bool,
    ) -> VoiceEngineV2PreSttShadowResult:
        return VoiceEngineV2PreSttShadowResult(
            enabled=self.enabled,
            observed=self.observed,
            reason=self.reason,
            legacy_runtime_primary=self.legacy_runtime_primary,
            action_executed=self.action_executed,
            full_stt_prevented=self.full_stt_prevented,
            request=self.request,
            timestamp_utc=self.timestamp_utc,
            timestamp_monotonic=self.timestamp_monotonic,
            metadata=self.metadata,
            telemetry_written=telemetry_written,
        )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "timestamp_monotonic": self.timestamp_monotonic,
            "enabled": self.enabled,
            "observed": self.observed,
            "reason": self.reason,
            "legacy_runtime_primary": self.legacy_runtime_primary,
            "action_executed": self.action_executed,
            "full_stt_prevented": self.full_stt_prevented,
            "turn_id": self.request.turn_id,
            "phase": self.request.phase,
            "capture_mode": self.request.capture_mode,
            "input_owner": self.request.input_owner,
            "source": self.request.source,
            "audio_bus_available": self.request.audio_bus_available,
            "audio_bus_probe": dict(self.request.audio_bus_probe),
            "metadata": dict(self.metadata),
        }


class VoiceEngineV2PreSttShadowTelemetryWriter:
    """Fail-open JSONL writer for pre-STT shadow observations."""

    def __init__(self, path: str | Path, *, enabled: bool) -> None:
        self._path = Path(path)
        self._enabled = bool(enabled)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def enabled(self) -> bool:
        return self._enabled

    def write(self, result: VoiceEngineV2PreSttShadowResult) -> bool:
        if not self._enabled:
            return False

        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(result.to_json_dict(), ensure_ascii=False))
            file.write("\n")

        return True

    def write_safely(self, result: VoiceEngineV2PreSttShadowResult) -> bool:
        try:
            return self.write(result)
        except Exception:
            return False


class VoiceEngineV2PreSttShadowAdapter:
    """Observe the pre-FasterWhisper hook without taking over runtime.

    Stage 21A is deliberately observation-only. It proves that the main loop can
    call a Voice Engine v2 hook before full STT starts, but it does not consume
    microphone ownership, does not run a live command recognizer, does not
    execute actions and never prevents legacy FasterWhisper capture.
    """

    def __init__(
        self,
        *,
        settings: VoiceEngineSettings,
        telemetry_writer: VoiceEngineV2PreSttShadowTelemetryWriter | None = None,
    ) -> None:
        self._settings = settings
        self._telemetry_writer = telemetry_writer

    @property
    def settings(self) -> VoiceEngineSettings:
        return self._settings

    @property
    def telemetry_path(self) -> str:
        if self._telemetry_writer is None:
            return ""
        return str(self._telemetry_writer.path)

    def observe_pre_stt(
        self,
        *,
        turn_id: str,
        phase: str,
        capture_mode: str,
        input_owner: str,
        source: str = "active_window",
        audio_bus_available: bool = False,
        audio_bus_probe: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VoiceEngineV2PreSttShadowResult:
        request = VoiceEngineV2PreSttShadowRequest(
            turn_id=turn_id,
            phase=phase,
            capture_mode=capture_mode,
            input_owner=input_owner,
            source=source,
            audio_bus_available=bool(audio_bus_available),
            audio_bus_probe=dict(audio_bus_probe or {}),
            metadata=dict(metadata or {}),
        )

        if not self._settings.pre_stt_shadow_enabled:
            return self._result(
                request=request,
                enabled=False,
                observed=False,
                reason="pre_stt_shadow_disabled",
                metadata={"pre_stt_shadow_enabled": False},
                write_telemetry=False,
            )

        if not self._settings.pre_stt_shadow_can_run:
            return self._result(
                request=request,
                enabled=True,
                observed=False,
                reason="pre_stt_shadow_not_safe",
                metadata={
                    "pre_stt_shadow_enabled": self._settings.pre_stt_shadow_enabled,
                    "enabled": self._settings.enabled,
                    "mode": self._settings.mode,
                    "command_first_enabled": self._settings.command_first_enabled,
                    "fallback_to_legacy_enabled": self._settings.fallback_to_legacy_enabled,
                },
                write_telemetry=True,
            )

        reason = (
            "audio_bus_available_observe_only"
            if request.audio_bus_available
            else "audio_bus_unavailable_observe_only"
        )

        return self._result(
            request=request,
            enabled=True,
            observed=True,
            reason=reason,
            metadata={
                **dict(request.metadata),
                "pre_stt_shadow_can_run": True,
                "realtime_audio_bus_enabled": self._settings.realtime_audio_bus_enabled,
                "vad_endpointing_enabled": self._settings.vad_endpointing_enabled,
                "command_first_enabled": self._settings.command_first_enabled,
                "stage": "21A",
                "runtime_takeover": False,
                "audio_bus_probe": dict(request.audio_bus_probe),
            },
            write_telemetry=True,
        )

    def _result(
        self,
        *,
        request: VoiceEngineV2PreSttShadowRequest,
        enabled: bool,
        observed: bool,
        reason: str,
        metadata: dict[str, Any],
        write_telemetry: bool,
    ) -> VoiceEngineV2PreSttShadowResult:
        result = VoiceEngineV2PreSttShadowResult(
            enabled=enabled,
            observed=observed,
            reason=reason,
            legacy_runtime_primary=True,
            action_executed=False,
            full_stt_prevented=False,
            request=request,
            timestamp_utc=datetime.now(UTC).isoformat(),
            timestamp_monotonic=time.monotonic(),
            metadata=metadata,
        )

        if not write_telemetry or self._telemetry_writer is None:
            return result

        return result.with_telemetry_written(
            self._telemetry_writer.write_safely(result)
        )