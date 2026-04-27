from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True)
class VoiceEngineV2RuntimeCandidateTelemetryRecord:
    """JSONL telemetry record for one runtime-candidate attempt."""

    timestamp_utc: str
    turn_id: str
    transcript: str
    accepted: bool
    reason: str
    legacy_runtime_primary: bool
    voice_engine_route: str
    voice_engine_intent: str
    voice_engine_action: str
    language: str
    fallback_reason: str
    route_kind: str
    primary_intent: str
    llm_prevented: bool
    metrics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp_utc.strip():
            raise ValueError("timestamp_utc must not be empty")
        if not self.turn_id.strip():
            raise ValueError("turn_id must not be empty")
        if not self.reason.strip():
            raise ValueError("reason must not be empty")

        object.__setattr__(self, "metrics", dict(self.metrics))
        object.__setattr__(self, "metadata", dict(self.metadata))

    @classmethod
    def create(
        cls,
        *,
        turn_id: str,
        transcript: str,
        accepted: bool,
        reason: str,
        legacy_runtime_primary: bool,
        voice_engine_route: str = "",
        voice_engine_intent: str = "",
        voice_engine_action: str = "",
        language: str = "",
        fallback_reason: str = "",
        route_kind: str = "",
        primary_intent: str = "",
        llm_prevented: bool = False,
        metrics: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VoiceEngineV2RuntimeCandidateTelemetryRecord:
        return cls(
            timestamp_utc=datetime.now(UTC).isoformat(),
            turn_id=turn_id,
            transcript=transcript,
            accepted=accepted,
            reason=reason,
            legacy_runtime_primary=legacy_runtime_primary,
            voice_engine_route=voice_engine_route,
            voice_engine_intent=voice_engine_intent,
            voice_engine_action=voice_engine_action,
            language=language,
            fallback_reason=fallback_reason,
            route_kind=route_kind,
            primary_intent=primary_intent,
            llm_prevented=llm_prevented,
            metrics=metrics or {},
            metadata=metadata or {},
        )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "timestamp_utc": self.timestamp_utc,
            "turn_id": self.turn_id,
            "transcript": self.transcript,
            "accepted": self.accepted,
            "reason": self.reason,
            "legacy_runtime_primary": self.legacy_runtime_primary,
            "voice_engine_route": self.voice_engine_route,
            "voice_engine_intent": self.voice_engine_intent,
            "voice_engine_action": self.voice_engine_action,
            "language": self.language,
            "fallback_reason": self.fallback_reason,
            "route_kind": self.route_kind,
            "primary_intent": self.primary_intent,
            "llm_prevented": self.llm_prevented,
            "metrics": dict(self.metrics),
            "metadata": dict(self.metadata),
        }


class VoiceEngineV2RuntimeCandidateTelemetryWriter:
    """Fail-open JSONL writer for runtime-candidate telemetry."""

    def __init__(self, path: str | Path, *, enabled: bool) -> None:
        self._path = Path(path)
        self._enabled = bool(enabled)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def enabled(self) -> bool:
        return self._enabled

    def write(
        self,
        record: VoiceEngineV2RuntimeCandidateTelemetryRecord,
    ) -> bool:
        if not self._enabled:
            return False

        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record.to_json_dict(), ensure_ascii=False))
            file.write("\n")

        return True

    def write_safely(
        self,
        record: VoiceEngineV2RuntimeCandidateTelemetryRecord,
    ) -> bool:
        try:
            return self.write(record)
        except Exception:
            return False


def immutable_metadata(metadata: dict[str, Any] | None) -> MappingProxyType:
    return MappingProxyType(dict(metadata or {}))