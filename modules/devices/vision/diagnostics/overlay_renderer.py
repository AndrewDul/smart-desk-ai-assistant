from __future__ import annotations

from typing import Any

import cv2
import numpy as np


_COLOR_PALETTE = {
    "people": (80, 220, 80),
    "faces": (80, 160, 255),
    "objects": (255, 200, 80),
    "zone": (140, 140, 140),
    "active": (80, 220, 80),
    "inactive": (90, 90, 90),
    "warning": (0, 215, 255),
    "text": (235, 235, 235),
}


def _ensure_bgr_frame(frame: Any) -> np.ndarray:
    image = np.asarray(frame)
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.ndim == 3 and image.shape[2] == 3:
        return image.copy()
    raise ValueError("Diagnostics overlay renderer expects a grayscale or BGR frame.")


def _draw_detection_boxes(image: np.ndarray, diagnostics: dict[str, Any]) -> None:
    detections = diagnostics.get("detections", {})
    for group_name, color in (
        ("people", _COLOR_PALETTE["people"]),
        ("faces", _COLOR_PALETTE["faces"]),
        ("objects", _COLOR_PALETTE["objects"]),
    ):
        for detection in detections.get(group_name, []):
            box = detection.get("bounding_box", {})
            left = int(box.get("left", 0))
            top = int(box.get("top", 0))
            right = int(box.get("right", 0))
            bottom = int(box.get("bottom", 0))
            if right <= left or bottom <= top:
                continue

            cv2.rectangle(image, (left, top), (right, bottom), color, 2)
            label = f"{detection.get('label', group_name[:-1])}:{float(detection.get('confidence', 0.0)):.2f}"
            label_y = top - 8 if top > 18 else top + 18
            cv2.putText(
                image,
                label,
                (left, label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                color,
                1,
                cv2.LINE_AA,
            )


def _draw_zone_layout(image: np.ndarray, diagnostics: dict[str, Any]) -> None:
    frame_height, frame_width = image.shape[:2]
    scene = diagnostics.get("scene", {})
    metadata = scene.get("metadata", {})
    zone_layout = scene.get("zone_layout") or metadata.get("zone_layout") or {}

    for zone_name, region in zone_layout.items():
        try:
            left = int(float(region["x_min"]) * frame_width)
            top = int(float(region["y_min"]) * frame_height)
            right = int(float(region["x_max"]) * frame_width)
            bottom = int(float(region["y_max"]) * frame_height)
        except (KeyError, TypeError, ValueError):
            continue

        if right <= left or bottom <= top:
            continue

        cv2.rectangle(image, (left, top), (right, bottom), _COLOR_PALETTE["zone"], 1)
        cv2.putText(
            image,
            zone_name,
            (left, max(12, top - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            _COLOR_PALETTE["zone"],
            1,
            cv2.LINE_AA,
        )


def _signal_line(signal_name: str, signal: dict[str, Any]) -> str:
    raw_active = "1" if signal.get("raw_active") else "0"
    stable_active = "1" if signal.get("stable_active") else "0"
    raw_confidence = float(signal.get("raw_confidence", 0.0))
    stable_confidence = float(signal.get("stable_confidence", 0.0))
    return f"{signal_name}: raw={raw_active}/{raw_confidence:.2f} stable={stable_active}/{stable_confidence:.2f}"


def _draw_signal_panel(image: np.ndarray, diagnostics: dict[str, Any]) -> None:
    signals = diagnostics.get("signals", {})
    summary = diagnostics.get("summary", {})
    sessions = diagnostics.get("sessions", {})

    lines = [
        f"presence={int(bool(summary.get('user_present', False)))} desk={int(bool(summary.get('desk_active', False)))} study={int(bool(summary.get('studying_likely', False)))}",
        f"people={int(summary.get('people_count', 0))} faces={int(summary.get('face_count', 0))} objects={int(summary.get('object_count', 0))}",
    ]
    lines.extend(
        _signal_line(signal_name, signal)
        for signal_name, signal in signals.items()
    )
    lines.append(
        "presence_session="
        f"{float(sessions.get('presence', {}).get('current_active_seconds', 0.0)):.1f}s "
        f"desk_session={float(sessions.get('desk_activity', {}).get('current_active_seconds', 0.0)):.1f}s"
    )

    panel_height = 24 + (len(lines) * 20)
    panel_width = min(image.shape[1] - 12, 560)
    cv2.rectangle(image, (6, 6), (6 + panel_width, 6 + panel_height), (20, 20, 20), -1)
    cv2.rectangle(image, (6, 6), (6 + panel_width, 6 + panel_height), _COLOR_PALETTE["zone"], 1)

    y = 24
    for line in lines:
        cv2.putText(
            image,
            line,
            (14, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            _COLOR_PALETTE["text"],
            1,
            cv2.LINE_AA,
        )
        y += 20


def render_diagnostics_overlay(frame: Any, diagnostics: dict[str, Any]) -> np.ndarray:
    """
    Render a diagnostics overlay on top of a raw vision frame.

    The renderer is intentionally read-only for diagnostics payloads and returns
    a new BGR image that can be shown in a preview/debug window or saved for
    offline inspection.
    """
    image = _ensure_bgr_frame(frame)
    _draw_zone_layout(image, diagnostics)
    _draw_detection_boxes(image, diagnostics)
    _draw_signal_panel(image, diagnostics)
    return image