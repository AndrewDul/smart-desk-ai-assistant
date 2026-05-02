from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RuntimeBackendStatus

from .fallbacks import NullPanTiltBackend


class RuntimeBuilderPanTiltMixin:
    """Build the safe pan/tilt backend with explicit fallback handling."""

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
                    selected_backend="disabled_pan_tilt",
                    detail="Pan/tilt disabled in config. No hardware backend loaded.",
                ),
            )

        try:
            backend_class = self._import_symbol(
                "modules.devices.pan_tilt",
                "PanTiltService",
            )
            backend = backend_class(config=config)
            status = backend.status()
            selected_backend = str(status.get("backend", "safe_pan_tilt"))
            return (
                backend,
                RuntimeBackendStatus(
                    component="pan_tilt",
                    ok=True,
                    selected_backend=selected_backend,
                    detail=(
                        "Safe pan/tilt backend loaded. Startup motion is blocked; "
                        "movement requires explicit safety flags and calibration."
                    ),
                ),
            )
        except Exception as error:
            return (
                NullPanTiltBackend(),
                RuntimeBackendStatus(
                    component="pan_tilt",
                    ok=False,
                    selected_backend="null_pan_tilt",
                    detail=f"Safe pan/tilt backend failed. Using null pan/tilt. Error: {error}",
                    fallback_used=True,
                ),
            )


__all__ = ["RuntimeBuilderPanTiltMixin"]
