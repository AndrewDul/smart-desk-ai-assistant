from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .camera_service import CameraService

__all__ = ["CameraService"]


def __getattr__(name: str):
    if name == "CameraService":
        from .camera_service import CameraService

        return CameraService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")