from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class FaceCaptureResult:
    ok: bool
    path: str = ""
    width: int = 0
    height: int = 0
    backend: str = ""
    reason: str = ""
    face_detected: bool = False
    face_count: int = 0
    face_confidence: float = 0.0


def capture_face_reference_from_vision(
    *,
    vision_backend: Any,
    target_path: str | Path,
    timeout_seconds: float = 1.5,
    poll_interval_seconds: float = 0.05,
    max_long_edge_px: int = 960,
    jpeg_quality: int = 88,
    require_face: bool = True,
    min_face_confidence: float = 0.20,
) -> FaceCaptureResult:
    """Save a single face-reference frame from the existing vision backend.

    This helper intentionally reuses the runtime vision backend instead of
    opening Picamera2 directly. That avoids a second camera owner and keeps the
    memory feature compatible with the existing CameraService lifecycle.
    """

    if vision_backend is None:
        return FaceCaptureResult(ok=False, reason="vision_backend_unavailable")

    destination = Path(target_path).expanduser()
    if not str(destination).strip():
        return FaceCaptureResult(ok=False, reason="target_path_missing")

    face_gate = _check_face_presence(
        vision_backend=vision_backend,
        require_face=bool(require_face),
        min_face_confidence=max(0.0, float(min_face_confidence)),
        timeout_seconds=max(0.1, float(timeout_seconds)),
        poll_interval_seconds=max(0.01, float(poll_interval_seconds)),
    )
    if not bool(face_gate["ok"]):
        return FaceCaptureResult(
            ok=False,
            reason=str(face_gate["reason"]),
            face_detected=False,
            face_count=int(face_gate["face_count"]),
            face_confidence=float(face_gate["face_confidence"]),
        )

    packet = _wait_for_latest_frame(
        vision_backend=vision_backend,
        timeout_seconds=max(0.1, float(timeout_seconds)),
        poll_interval_seconds=max(0.01, float(poll_interval_seconds)),
    )
    if packet is None:
        return FaceCaptureResult(ok=False, reason="frame_unavailable")

    pixels = getattr(packet, "pixels", None)
    if pixels is None:
        return FaceCaptureResult(ok=False, reason="frame_pixels_missing")

    try:
        width, height = _save_pixels_as_jpeg(
            pixels=pixels,
            packet=packet,
            destination=destination,
            max_long_edge_px=max_long_edge_px,
            jpeg_quality=jpeg_quality,
        )
    except Exception as exc:  # pragma: no cover - defensive runtime fallback
        return FaceCaptureResult(ok=False, reason=f"save_failed:{exc.__class__.__name__}")

    return FaceCaptureResult(
        ok=True,
        path=str(destination),
        width=width,
        height=height,
        backend=str(getattr(packet, "backend_label", "") or "unknown"),
        face_detected=bool(face_gate["face_detected"]),
        face_count=int(face_gate["face_count"]),
        face_confidence=float(face_gate["face_confidence"]),
    )


def _check_face_presence(
    *,
    vision_backend: Any,
    require_face: bool,
    min_face_confidence: float,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> dict[str, Any]:
    if not require_face:
        return {"ok": True, "reason": "face_check_disabled", "face_detected": False, "face_count": 0, "face_confidence": 0.0}

    latest_tracking_observation = getattr(vision_backend, "latest_tracking_observation", None)
    latest_observation = getattr(vision_backend, "latest_observation", None)

    observation_method = latest_tracking_observation if callable(latest_tracking_observation) else latest_observation
    if not callable(observation_method):
        # Some test or fallback backends expose only latest_frame(). In that case
        # keep the capture path usable instead of rejecting the frame blindly.
        return {"ok": True, "reason": "face_check_unavailable", "face_detected": False, "face_count": 0, "face_confidence": 0.0}

    deadline = time.monotonic() + timeout_seconds
    best_count = 0
    best_confidence = 0.0
    while True:
        try:
            observation = observation_method(force_refresh=True)
        except TypeError:
            try:
                observation = observation_method()
            except Exception:
                observation = None
        except Exception:
            observation = None

        face_count, face_confidence = _extract_face_summary(observation)
        best_count = max(best_count, face_count)
        best_confidence = max(best_confidence, face_confidence)
        if face_count > 0 and face_confidence >= min_face_confidence:
            return {
                "ok": True,
                "reason": "face_detected",
                "face_detected": True,
                "face_count": face_count,
                "face_confidence": face_confidence,
            }

        if time.monotonic() >= deadline:
            return {
                "ok": False,
                "reason": "face_not_detected",
                "face_detected": False,
                "face_count": best_count,
                "face_confidence": best_confidence,
            }
        time.sleep(poll_interval_seconds)


def _extract_face_summary(observation: Any | None) -> tuple[int, float]:
    if observation is None:
        return 0, 0.0

    metadata = getattr(observation, "metadata", {}) or {}
    if not isinstance(metadata, dict):
        return 0, 0.0

    perception = metadata.get("perception", {}) or {}
    if not isinstance(perception, dict):
        return 0, 0.0

    faces = perception.get("faces") or []
    if not isinstance(faces, (list, tuple)):
        faces = []

    confidences: list[float] = []
    for face in faces:
        if isinstance(face, dict):
            try:
                confidences.append(float(face.get("confidence", 0.0) or 0.0))
            except (TypeError, ValueError):
                confidences.append(0.0)
        else:
            try:
                confidences.append(float(getattr(face, "confidence", 0.0) or 0.0))
            except (TypeError, ValueError):
                confidences.append(0.0)

    face_count = len(faces)
    if face_count <= 0:
        try:
            face_count = int(perception.get("face_count", 0) or 0)
        except (TypeError, ValueError):
            face_count = 0

    return max(0, face_count), max(confidences, default=0.0)


def _wait_for_latest_frame(
    *,
    vision_backend: Any,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> Any | None:
    start_method = getattr(vision_backend, "start", None)
    if callable(start_method):
        try:
            start_method()
        except Exception:
            pass

    latest_frame = getattr(vision_backend, "latest_frame", None)
    if not callable(latest_frame):
        return None

    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            packet = latest_frame()
        except Exception:
            return None
        if packet is not None:
            return packet
        if time.monotonic() >= deadline:
            return None
        time.sleep(poll_interval_seconds)


def _save_pixels_as_jpeg(
    *,
    pixels: Any,
    packet: Any,
    destination: Path,
    max_long_edge_px: int,
    jpeg_quality: int,
) -> tuple[int, int]:
    from PIL import Image  # type: ignore
    import numpy as np  # type: ignore

    arr = np.asarray(pixels)
    if arr.ndim == 2:
        image = Image.fromarray(arr.astype("uint8"), mode="L").convert("RGB")
    elif arr.ndim == 3:
        if arr.shape[2] == 4:
            arr = arr[:, :, :3]
        backend = str(getattr(packet, "backend_label", "") or "").lower()
        if backend in {"opencv", "bgr"}:
            arr = arr[:, :, ::-1]
        image = Image.fromarray(arr.astype("uint8")).convert("RGB")
    else:
        raise ValueError("unsupported_frame_shape")

    width, height = image.size
    long_edge = max(width, height)
    if long_edge > int(max_long_edge_px) > 0:
        scale = float(max_long_edge_px) / float(long_edge)
        image = image.resize(
            (max(2, int(width * scale)), max(2, int(height * scale))),
            Image.BILINEAR,
        )
        width, height = image.size

    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        destination,
        format="JPEG",
        quality=max(40, min(95, int(jpeg_quality))),
        optimize=False,
    )
    return int(width), int(height)


__all__ = ["FaceCaptureResult", "capture_face_reference_from_vision"]
