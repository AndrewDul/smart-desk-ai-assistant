from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class DiagnosticsSignal:
    name: str
    raw_active: bool
    stable_active: bool
    raw_confidence: float
    stable_confidence: float
    raw_reasons: tuple[str, ...] = ()
    stable_reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "raw_active": self.raw_active,
            "stable_active": self.stable_active,
            "raw_confidence": self.raw_confidence,
            "stable_confidence": self.stable_confidence,
            "raw_reasons": list(self.raw_reasons),
            "stable_reasons": list(self.stable_reasons),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class DiagnosticsDetection:
    kind: str
    label: str
    confidence: float
    bounding_box: dict[str, int]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "confidence": self.confidence,
            "bounding_box": dict(self.bounding_box),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class DiagnosticsSnapshot:
    frame: dict[str, Any]
    signals: dict[str, DiagnosticsSignal]
    detections: dict[str, tuple[DiagnosticsDetection, ...]]
    scene: dict[str, Any]
    sessions: dict[str, Any]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame": dict(self.frame),
            "signals": {
                name: signal.to_dict()
                for name, signal in self.signals.items()
            },
            "detections": {
                name: [detection.to_dict() for detection in items]
                for name, items in self.detections.items()
            },
            "scene": dict(self.scene),
            "sessions": dict(self.sessions),
            "summary": dict(self.summary),
        }