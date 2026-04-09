from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RuntimeBackendStatus

from .fallbacks import NullVisionBackend


class RuntimeBuilderVisionMixin:
    """
    Build the vision backend with explicit fallback handling.
    """

    def _build_vision(
        self,
        config: dict[str, object],
    ) -> tuple[Any, RuntimeBackendStatus]:
        if not bool(config.get("enabled", False)):
            return (
                NullVisionBackend(),
                RuntimeBackendStatus(
                    component="vision",
                    ok=True,
                    selected_backend="null_vision",
                    detail="Vision disabled in config.",
                ),
            )

        try:
            backend_class = self._import_symbol(
                "modules.devices.vision.camera_service",
                "CameraService",
            )
            backend = backend_class(config=config)
            return (
                backend,
                RuntimeBackendStatus(
                    component="vision",
                    ok=True,
                    selected_backend="camera_service",
                    detail="Vision backend loaded successfully.",
                ),
            )
        except Exception as error:
            return (
                NullVisionBackend(),
                RuntimeBackendStatus(
                    component="vision",
                    ok=False,
                    selected_backend="null_vision",
                    detail=f"Vision backend failed. Using null vision. Error: {error}",
                    fallback_used=True,
                ),
            )


__all__ = ["RuntimeBuilderVisionMixin"]