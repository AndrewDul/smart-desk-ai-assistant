from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RuntimeBackendStatus

from .fallbacks import NullPanTiltBackend


class RuntimeBuilderPanTiltMixin:
    """Build the pan/tilt backend with explicit fallback handling."""

    def _build_pan_tilt(
        self,
        config: dict[str, object],
    ) -> tuple[Any, RuntimeBackendStatus]:
        if not bool(config.get("enabled", False)):
            return (
                NullPanTiltBackend(),
                RuntimeBackendStatus(
                    component="pan_tilt",
                    ok=True,
                    selected_backend="null_pan_tilt",
                    detail="Pan/tilt disabled in config.",
                ),
            )

        try:
            backend_class = self._import_symbol(
                "modules.devices.pan_tilt",
                "PanTiltService",
            )
            backend = backend_class(config=config)
            return (
                backend,
                RuntimeBackendStatus(
                    component="pan_tilt",
                    ok=True,
                    selected_backend="pca9685_pan_tilt",
                    detail="Pan/tilt backend loaded successfully.",
                ),
            )
        except Exception as error:
            return (
                NullPanTiltBackend(),
                RuntimeBackendStatus(
                    component="pan_tilt",
                    ok=False,
                    selected_backend="null_pan_tilt",
                    detail=f"Pan/tilt backend failed. Using null pan/tilt. Error: {error}",
                    fallback_used=True,
                ),
            )


__all__ = ["RuntimeBuilderPanTiltMixin"]