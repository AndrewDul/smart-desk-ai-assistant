from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from modules.features.memory_v2.face_capture import _save_pixels_as_jpeg, _wait_for_latest_frame


@dataclass(frozen=True, slots=True)
class ObjectCaptureResult:
    ok: bool
    path: str = ""
    width: int = 0
    height: int = 0
    backend: str = ""
    reason: str = ""


def capture_object_reference_from_vision(
    *,
    vision_backend: Any,
    target_path: str | Path,
    timeout_seconds: float = 1.5,
    poll_interval_seconds: float = 0.05,
    max_long_edge_px: int = 960,
    jpeg_quality: int = 88,
) -> ObjectCaptureResult:
    """Save a single object-reference frame from the existing vision backend.

    Object memory intentionally reuses the runtime vision backend instead of
    opening Picamera2 directly. That keeps camera ownership centralized and
    avoids device-busy failures during guided memory enrollment.
    """

    if vision_backend is None:
        return ObjectCaptureResult(ok=False, reason="vision_backend_unavailable")

    destination = Path(target_path).expanduser()
    if not str(destination).strip():
        return ObjectCaptureResult(ok=False, reason="target_path_missing")

    packet = _wait_for_latest_frame(
        vision_backend=vision_backend,
        timeout_seconds=max(0.1, float(timeout_seconds)),
        poll_interval_seconds=max(0.01, float(poll_interval_seconds)),
    )
    if packet is None:
        return ObjectCaptureResult(ok=False, reason="frame_unavailable")

    pixels = getattr(packet, "pixels", None)
    if pixels is None:
        return ObjectCaptureResult(ok=False, reason="frame_pixels_missing")

    try:
        width, height = _save_pixels_as_jpeg(
            pixels=pixels,
            packet=packet,
            destination=destination,
            max_long_edge_px=max_long_edge_px,
            jpeg_quality=jpeg_quality,
        )
    except Exception as exc:  # pragma: no cover - defensive runtime fallback
        return ObjectCaptureResult(ok=False, reason=f"save_failed:{exc.__class__.__name__}")

    return ObjectCaptureResult(
        ok=True,
        path=str(destination),
        width=width,
        height=height,
        backend=str(getattr(packet, "backend_label", "") or "unknown"),
    )


__all__ = ["ObjectCaptureResult", "capture_object_reference_from_vision"]
