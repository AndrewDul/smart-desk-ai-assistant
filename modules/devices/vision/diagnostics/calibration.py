from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from modules.devices.vision.diagnostics.models import DiagnosticsSnapshot


def _as_dict(snapshot: DiagnosticsSnapshot | Mapping[str, Any]) -> dict[str, Any]:
    if hasattr(snapshot, "to_dict"):
        return snapshot.to_dict()
    return dict(snapshot or {})


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value or {})


def _safe_list(value: Any) -> list[Any]:
    return list(value or [])


def _extract_inference_mode(metadata: Mapping[str, Any] | None) -> str:
    payload = dict(metadata or {})
    return str(payload.get("inference_mode", "") or "-")


@dataclass(frozen=True, slots=True)
class CalibrationSignalSample:
    name: str
    stable_active: bool
    stable_confidence: float
    stable_inference_mode: str
    stable_reasons: tuple[str, ...] = ()
    raw_active: bool = False
    raw_confidence: float = 0.0
    raw_inference_mode: str = "-"
    raw_reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "stable_active": self.stable_active,
            "stable_confidence": self.stable_confidence,
            "stable_inference_mode": self.stable_inference_mode,
            "stable_reasons": list(self.stable_reasons),
            "raw_active": self.raw_active,
            "raw_confidence": self.raw_confidence,
            "raw_inference_mode": self.raw_inference_mode,
            "raw_reasons": list(self.raw_reasons),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class CalibrationSample:
    capture_tag: str
    captured_at: float
    backend: str
    frame_size: dict[str, int]
    counts: dict[str, int]
    object_labels: tuple[str, ...]
    scene: dict[str, Any]
    summary: dict[str, Any]
    signals: dict[str, CalibrationSignalSample]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_tag": self.capture_tag,
            "captured_at": self.captured_at,
            "backend": self.backend,
            "frame_size": dict(self.frame_size),
            "counts": dict(self.counts),
            "object_labels": list(self.object_labels),
            "scene": dict(self.scene),
            "summary": dict(self.summary),
            "signals": {
                name: signal.to_dict()
                for name, signal in self.signals.items()
            },
            "metadata": dict(self.metadata),
        }


def build_calibration_sample(
    *,
    capture_tag: str,
    diagnostics: DiagnosticsSnapshot | Mapping[str, Any],
) -> CalibrationSample:
    payload = _as_dict(diagnostics)
    frame = _safe_dict(payload.get("frame"))
    detections = _safe_dict(payload.get("detections"))
    scene = _safe_dict(payload.get("scene"))
    summary = _safe_dict(payload.get("summary"))
    signals_payload = _safe_dict(payload.get("signals"))

    object_labels = tuple(
        sorted(
            {
                str(item.get("label", "")).strip().lower()
                for item in _safe_list(detections.get("objects"))
                if str(item.get("label", "")).strip()
            }
        )
    )

    counts = {
        "people": len(_safe_list(detections.get("people"))),
        "faces": len(_safe_list(detections.get("faces"))),
        "objects": len(_safe_list(detections.get("objects"))),
    }

    signals: dict[str, CalibrationSignalSample] = {}
    for name, signal_payload in signals_payload.items():
        signal = _safe_dict(signal_payload)
        metadata = _safe_dict(signal.get("metadata"))
        raw_metadata = _safe_dict(metadata.get("raw_metadata"))

        signals[str(name)] = CalibrationSignalSample(
            name=str(name),
            stable_active=bool(signal.get("stable_active", False)),
            stable_confidence=float(signal.get("stable_confidence", 0.0) or 0.0),
            stable_inference_mode=_extract_inference_mode(metadata),
            stable_reasons=tuple(str(item) for item in _safe_list(signal.get("stable_reasons"))),
            raw_active=bool(signal.get("raw_active", False)),
            raw_confidence=float(signal.get("raw_confidence", 0.0) or 0.0),
            raw_inference_mode=_extract_inference_mode(raw_metadata),
            raw_reasons=tuple(str(item) for item in _safe_list(signal.get("raw_reasons"))),
            metadata=metadata,
        )

    return CalibrationSample(
        capture_tag=str(capture_tag or "").strip() or "untagged",
        captured_at=float(frame.get("captured_at", 0.0) or 0.0),
        backend=str(frame.get("backend", "") or ""),
        frame_size={
            "width": int(frame.get("width", 0) or 0),
            "height": int(frame.get("height", 0) or 0),
        },
        counts=counts,
        object_labels=object_labels,
        scene=scene,
        summary=summary,
        signals=signals,
        metadata={
            "scene_labels": list(scene.get("labels", []) or []),
        },
    )