from __future__ import annotations

import time
from typing import Any

from modules.shared.logging.logger import get_logger

from .frame_packet import FramePacket

LOGGER = get_logger(__name__)


class Picamera2FrameSource:
    backend_label = "picamera2"

    def __init__(
        self,
        *,
        frame_width: int,
        frame_height: int,
        warmup_seconds: float,
        hflip: bool,
        vflip: bool,
    ) -> None:
        self._frame_width = int(frame_width)
        self._frame_height = int(frame_height)
        self._warmup_seconds = float(warmup_seconds)
        self._hflip = bool(hflip)
        self._vflip = bool(vflip)
        self._camera = None
        self._opened = False

    def open(self) -> None:
        if self._opened:
            return

        from picamera2 import Picamera2

        transform = None
        if self._hflip or self._vflip:
            try:
                from libcamera import Transform

                transform = Transform(hflip=int(self._hflip), vflip=int(self._vflip))
            except Exception as error:
                LOGGER.warning(
                    "Vision: failed to apply libcamera Transform, continuing without transform. error=%s",
                    error,
                )

        camera = Picamera2()
        config_kwargs: dict[str, Any] = {
            "main": {
                "size": (self._frame_width, self._frame_height),
                "format": "RGB888",
            }
        }
        if transform is not None:
            config_kwargs["transform"] = transform

        camera_config = camera.create_video_configuration(**config_kwargs)
        camera.configure(camera_config)
        camera.start()

        if self._warmup_seconds > 0.0:
            time.sleep(self._warmup_seconds)

        self._camera = camera
        self._opened = True
        LOGGER.info(
            "Vision capture opened with Picamera2: size=%sx%s hflip=%s vflip=%s",
            self._frame_width,
            self._frame_height,
            self._hflip,
            self._vflip,
        )

    def read_frame(self) -> FramePacket:
        if not self._opened or self._camera is None:
            raise RuntimeError("Picamera2FrameSource is not open.")

        pixels = self._camera.capture_array("main")
        height = int(getattr(pixels, "shape", [0, 0, 0])[0])
        width = int(getattr(pixels, "shape", [0, 0, 0])[1])
        channels = int(getattr(pixels, "shape", [0, 0, 0])[2]) if len(getattr(pixels, "shape", [])) >= 3 else 1

        return FramePacket(
            pixels=pixels,
            width=width,
            height=height,
            channels=channels,
            backend_label=self.backend_label,
            metadata={
                "configured_width": self._frame_width,
                "configured_height": self._frame_height,
                "hflip": self._hflip,
                "vflip": self._vflip,
            },
        )

    def close(self) -> None:
        if self._camera is not None:
            try:
                self._camera.stop()
            finally:
                close_fn = getattr(self._camera, "close", None)
                if callable(close_fn):
                    close_fn()
        self._camera = None
        self._opened = False