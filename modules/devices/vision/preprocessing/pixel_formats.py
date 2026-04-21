from __future__ import annotations

from modules.devices.vision.capture import FramePacket


def frame_to_bgr(packet: FramePacket):
    import cv2
    import numpy as np

    pixels = np.asarray(packet.pixels)
    if pixels.dtype != np.uint8:
        pixels = pixels.astype(np.uint8, copy=False)

    if pixels.ndim == 2:
        return cv2.cvtColor(pixels, cv2.COLOR_GRAY2BGR)

    if pixels.ndim != 3:
        raise ValueError(f"Unsupported frame dimensions: ndim={pixels.ndim}")

    channels = int(pixels.shape[2])
    backend = str(packet.backend_label or "").strip().lower()

    if channels == 3:
        if backend == "opencv":
            return pixels.copy()
        return cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)

    if channels == 4:
        if backend == "opencv":
            return cv2.cvtColor(pixels, cv2.COLOR_BGRA2BGR)
        return cv2.cvtColor(pixels, cv2.COLOR_RGBA2BGR)

    raise ValueError(f"Unsupported channel count: channels={channels}")