from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from modules.runtime.voice_engine_v2.shadow_mode import (
        VoiceEngineV2ShadowResult,
    )


@dataclass(frozen=True, slots=True)
class VoiceEngineV2ShadowTelemetryRecord:
    """Serializable JSONL record for Voice Engine v2 shadow-mode observations."""

    recorded_at_monotonic: float
    turn_id: str
    transcript: str
    legacy_route: str
    legacy_intent_key: str | None
    enabled: bool
    reason: str
    legacy_runtime_primary: bool
    matched_legacy_intent: bool | None
    voice_engine_route: str | None
    voice_engine_intent_key: str | None
    voice_engine_language: str
    fallback_reason: str
    action_executed: bool
    command_recognition_ms: float | None
    intent_resolution_ms: float | None
    speech_end_to_finish_ms: float | None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_result(
        cls,
        result: VoiceEngineV2ShadowResult,
        *,
        recorded_at_monotonic: float | None = None,
    ) -> VoiceEngineV2ShadowTelemetryRecord:
        metrics = None
        if result.turn_result is not None:
            metrics = result.turn_result.metrics

        return cls(
            recorded_at_monotonic=(
                time.monotonic()
                if recorded_at_monotonic is None
                else recorded_at_monotonic
            ),
            turn_id=result.request.turn_id,
            transcript=result.request.transcript,
            legacy_route=result.request.legacy_route,
            legacy_intent_key=result.request.legacy_intent_key,
            enabled=result.enabled,
            reason=result.reason,
            legacy_runtime_primary=result.legacy_runtime_primary,
            matched_legacy_intent=result.matched_legacy_intent,
            voice_engine_route=(
                None
                if result.voice_engine_route is None
                else result.voice_engine_route.value
            ),
            voice_engine_intent_key=result.voice_engine_intent_key,
            voice_engine_language=result.voice_engine_language.value,
            fallback_reason=result.fallback_reason,
            action_executed=result.action_executed,
            command_recognition_ms=(
                None if metrics is None else metrics.command_recognition_ms
            ),
            intent_resolution_ms=(
                None if metrics is None else metrics.intent_resolution_ms
            ),
            speech_end_to_finish_ms=(
                None if metrics is None else metrics.speech_end_to_finish_ms
            ),
            metadata=dict(result.metadata),
        )

    def to_json_line(self) -> str:
        return json.dumps(
            asdict(self),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


class VoiceEngineV2ShadowTelemetryWriter:
    """Append-only JSONL writer for shadow-mode runtime observations."""

    def __init__(self, path: str | Path, *, enabled: bool = True) -> None:
        self._path = Path(path)
        self._enabled = enabled

    @property
    def path(self) -> Path:
        return self._path

    @property
    def enabled(self) -> bool:
        return self._enabled

    def write_result(self, result: VoiceEngineV2ShadowResult) -> Path | None:
        if not self._enabled:
            return None

        record = VoiceEngineV2ShadowTelemetryRecord.from_result(result)
        self._path.parent.mkdir(parents=True, exist_ok=True)

        with self._path.open("a", encoding="utf-8") as file:
            file.write(record.to_json_line())
            file.write("\n")

        return self._path