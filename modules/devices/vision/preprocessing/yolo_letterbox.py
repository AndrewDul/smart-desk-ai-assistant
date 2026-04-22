# modules/devices/vision/preprocessing/yolo_letterbox.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.devices.vision.capture import FramePacket

from .pixel_formats import frame_to_bgr


@dataclass(frozen=True, slots=True)
class LetterboxTransform:
    """
    Geometric transform applied during letterboxing.

    Used downstream to map YOLO output boxes (in letterboxed image coords,
    normalized to [0,1]) back to the original camera frame in pixel coords.
    """

    target_width: int
    target_height: int
    original_width: int
    original_height: int
    scale: float
    pad_left: int
    pad_top: int
    scaled_width: int
    scaled_height: int


def preprocess_frame_for_yolo(
    packet: FramePacket,
    *,
    target_size: int = 640,
    pad_value: int = 114,
) -> tuple[Any, LetterboxTransform]:
    """
    Letterbox a camera frame for YOLOv11m_h10 (640x640 UINT8 RGB input).

    Pipeline:
    1. BGR frame from capture  (via frame_to_bgr for backend normalization)
    2. Aspect-preserving resize to fit inside target_size x target_size
    3. Pad with 114 (YOLO standard) to fill remaining space
    4. BGR -> RGB channel reorder (HEF input expects RGB)
    5. Return uint8 array of shape (target_size, target_size, 3) in NHWC layout

    Returns (tensor, transform). The transform is required to map inference
    output boxes back to original frame pixel coordinates.

    Note on HEF input: yolov11m_h10.hef declares NHWC(640x640x3) UINT8 with
    NO normalization at the edge — we pass raw pixel values, not [0,1] floats.
    """
    import cv2
    import numpy as np

    if target_size <= 0:
        raise ValueError("target_size must be positive.")

    bgr = frame_to_bgr(packet)
    original_height, original_width = bgr.shape[:2]
    if original_height <= 0 or original_width <= 0:
        raise ValueError("Frame has zero-sized dimensions.")

    scale = min(target_size / original_width, target_size / original_height)
    scaled_width = max(1, int(round(original_width * scale)))
    scaled_height = max(1, int(round(original_height * scale)))

    # Aspect-preserving resize.
    if (scaled_width, scaled_height) != (original_width, original_height):
        resized = cv2.resize(
            bgr,
            (scaled_width, scaled_height),
            interpolation=cv2.INTER_LINEAR,
        )
    else:
        resized = bgr

    # Center padding.
    pad_left = (target_size - scaled_width) // 2
    pad_top = (target_size - scaled_height) // 2
    pad_right = target_size - scaled_width - pad_left
    pad_bottom = target_size - scaled_height - pad_top

    padded = cv2.copyMakeBorder(
        resized,
        pad_top,
        pad_bottom,
        pad_left,
        pad_right,
        borderType=cv2.BORDER_CONSTANT,
        value=(pad_value, pad_value, pad_value),
    )

    # BGR -> RGB for HEF input.
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)

    if rgb.dtype != np.uint8:
        rgb = rgb.astype(np.uint8, copy=False)

    transform = LetterboxTransform(
        target_width=target_size,
        target_height=target_size,
        original_width=int(original_width),
        original_height=int(original_height),
        scale=float(scale),
        pad_left=int(pad_left),
        pad_top=int(pad_top),
        scaled_width=int(scaled_width),
        scaled_height=int(scaled_height),
    )

    return rgb, transform


def map_normalized_box_to_frame(
    *,
    y_min_norm: float,
    x_min_norm: float,
    y_max_norm: float,
    x_max_norm: float,
    transform: LetterboxTransform,
) -> tuple[int, int, int, int] | None:
    """
    Map a YOLO NMS box (normalized [0,1] against the letterboxed 640x640 image)
    back to the original camera frame in integer pixel coordinates.

    Returns (left, top, right, bottom) clamped to the original frame, or None
    if the box is entirely inside the padding region.
    """
    # Normalized coords -> letterboxed pixel coords.
    box_left = x_min_norm * transform.target_width
    box_top = y_min_norm * transform.target_height
    box_right = x_max_norm * transform.target_width
    box_bottom = y_max_norm * transform.target_height

# Remove letterbox padding offset.
    box_left -= transform.pad_left
    box_top -= transform.pad_top
    box_right -= transform.pad_left
    box_bottom -= transform.pad_top

    if transform.scale <= 0:
        return None

    # Early reject: box must overlap the content region after padding removal.
    # Content region spans [0, scaled_width] x [0, scaled_height] in
    # letterboxed pixel coords (once padding offset is removed).
    if box_right <= 0 or box_bottom <= 0:
        return None
    if box_left >= transform.scaled_width or box_top >= transform.scaled_height:
        return None

    # Clip box to the content region before unscaling, so boxes that partially
    # straddle the padding still map to the correct visible portion.
    box_left = max(0.0, min(float(transform.scaled_width), box_left))
    box_top = max(0.0, min(float(transform.scaled_height), box_top))
    box_right = max(0.0, min(float(transform.scaled_width), box_right))
    box_bottom = max(0.0, min(float(transform.scaled_height), box_bottom))

    if box_right <= box_left or box_bottom <= box_top:
        return None

    # Unscale to original resolution.
    inv_scale = 1.0 / transform.scale
    frame_left = box_left * inv_scale
    frame_top = box_top * inv_scale
    frame_right = box_right * inv_scale
    frame_bottom = box_bottom * inv_scale

    left_int = max(0, min(transform.original_width - 1, int(round(frame_left))))
    top_int = max(0, min(transform.original_height - 1, int(round(frame_top))))
    right_int = max(left_int + 1, min(transform.original_width, int(round(frame_right))))
    bottom_int = max(top_int + 1, min(transform.original_height, int(round(frame_bottom))))

    if right_int <= left_int or bottom_int <= top_int:
        return None

    return left_int, top_int, right_int, bottom_int