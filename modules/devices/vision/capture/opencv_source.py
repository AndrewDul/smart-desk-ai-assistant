from __future__ import annotations

from modules.shared.logging.logger import get_logger

from .frame_packet import FramePacket

LOGGER = get_logger(__name__)


class OpenCvFrameSource:
    backend_label = "opencv"

    def __init__(
        self,
        *,
        camera_index: int,
        frame_width: int,
        frame_height: int,
    ) -> None:
        self._camera_index = int(camera_index)
        self._frame_width = int(frame_width)
        self._frame_height = int(frame_height)
        self._capture = None

    def open(self) -> None:
        if self._capture is not None:
            return

        import cv2

        capture = cv2.VideoCapture(self._camera_index)
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"OpenCV camera index {self._camera_index} failed to open.")

        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._frame_width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._frame_height)
        self._capture = capture
        LOGGER.info(
            "Vision capture opened with OpenCV: index=%s size=%sx%s",
            self._camera_index,
            self._frame_width,
            self._frame_height,
        )

    def read_frame(self) -> FramePacket:
        if self._capture is None:
            raise RuntimeError("OpenCvFrameSource is not open.")

        ok, pixels = self._capture.read()
        if not ok or pixels is None:
            raise RuntimeError("OpenCV failed to read a frame.")

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
                "camera_index": self._camera_index,
                "configured_width": self._frame_width,
                "configured_height": self._frame_height,
            },
        )

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
        self._capture = None