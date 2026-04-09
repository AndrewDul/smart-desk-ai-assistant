from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.runtime.contracts import InputSource


@dataclass(slots=True)
class PreparedCommand:
    raw_text: str
    routing_text: str
    normalized_routing_text: str
    detected_language: str
    normalizer_language_hint: str
    command_language: str
    parser_result: Any | None
    semantic_override_applied: bool
    semantic_override_mode: str | None
    semantic_override_source_text: str | None
    normalizer_corrections: tuple[str, ...] = ()
    source: InputSource = InputSource.VOICE
    ignore: bool = False
    cancel_requested: bool = False
    wake_phrase_detected: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def normalized_text(self) -> str:
        return self.normalized_routing_text

    @property
    def language(self) -> str:
        return self.command_language

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "routing_text": self.routing_text,
            "normalized_text": self.normalized_routing_text,
            "normalized_routing_text": self.normalized_routing_text,
            "detected_language": self.detected_language,
            "normalizer_language_hint": self.normalizer_language_hint,
            "command_language": self.command_language,
            "language": self.command_language,
            "parser_result": self.parser_result,
            "semantic_override_applied": self.semantic_override_applied,
            "semantic_override_mode": self.semantic_override_mode,
            "semantic_override_source_text": self.semantic_override_source_text,
            "normalizer_corrections": self.normalizer_corrections,
            "source": self.source,
            "ignore": self.ignore,
            "cancel_requested": self.cancel_requested,
            "wake_phrase_detected": self.wake_phrase_detected,
            "notes": list(self.notes),
        }


__all__ = ["PreparedCommand"]