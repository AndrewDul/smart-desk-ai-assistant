from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from modules.devices.vision.config import VisionRuntimeConfig

from .frame_packet import FramePacket
from .opencv_source import OpenCvFrameSource
from .picamera2_source import Picamera2FrameSource

FrameSourceFactory = Callable[[], Any]


@dataclass(slots=True)
class VisionCaptureReader:
    config: VisionRuntimeConfig
    primary_factory: FrameSourceFactory | None = None
    fallback_factory: FrameSourceFactory | None = None
    _active_source: Any | None = field(init=False, default=None)
    _active_backend: str = field(init=False, default="")

    def __post_init__(self) -> None:
        if self.primary_factory is None:
            self.primary_factory = self._factory_for_backend(self.config.backend)
        if self.fallback_factory is None and self.config.fallback_backend not in {"", "none", self.config.backend}:
            self.fallback_factory = self._factory_for_backend(self.config.fallback_backend)

    @property
    def active_backend(self) -> str:
        return self._active_backend

    def read_frame(self) -> FramePacket:
        if self._active_source is None:
            self._open_source_chain()

        return self._active_source.read_frame()

    def close(self) -> None:
        if self._active_source is None:
            return
        self._active_source.close()
        self._active_source = None
        self._active_backend = ""

    def _open_source_chain(self) -> None:
        attempts: list[tuple[str, FrameSourceFactory]] = []
        if self.primary_factory is not None:
            attempts.append((self.config.backend, self.primary_factory))
        if self.fallback_factory is not None:
            attempts.append((self.config.fallback_backend, self.fallback_factory))

        errors: list[str] = []
        for backend_name, factory in attempts:
            try:
                source = factory()
                source.open()
                self._active_source = source
                self._active_backend = str(getattr(source, "backend_label", backend_name))
                return
            except Exception as error:
                errors.append(f"{backend_name}: {error}")

        raise RuntimeError("Vision capture failed to open. " + " | ".join(errors))

    def _factory_for_backend(self, backend_name: str) -> FrameSourceFactory:
        normalized = str(backend_name or "").strip().lower()
        if normalized == "picamera2":
            return lambda: Picamera2FrameSource(
                frame_width=self.config.frame_width,
                frame_height=self.config.frame_height,
                warmup_seconds=self.config.warmup_seconds,
                hflip=self.config.hflip,
                vflip=self.config.vflip,
            )
        if normalized == "opencv":
            return lambda: OpenCvFrameSource(
                camera_index=self.config.camera_index,
                frame_width=self.config.frame_width,
                frame_height=self.config.frame_height,
            )
        raise ValueError(f"Unsupported vision backend: {backend_name}")