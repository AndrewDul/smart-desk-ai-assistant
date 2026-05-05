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


    def _build_vision_tracking(
        self,
        config: dict[str, object],
        *,
        vision_backend: Any,
        pan_tilt_backend: Any | None,
    ) -> tuple[Any | None, RuntimeBackendStatus]:
        """
        Build the dry-run vision tracking service.

        This service is runtime-visible but does not execute pan/tilt or
        mobile-base movement. It only computes tracking plans from cached
        vision observations.
        """
        if not bool(config.get("enabled", True)):
            return (
                None,
                RuntimeBackendStatus(
                    component="vision_tracking",
                    ok=True,
                    selected_backend="disabled_vision_tracking",
                    detail="Vision tracking service disabled in config.",
                    runtime_mode="disabled",
                ),
            )

        try:
            service_class = self._import_symbol(
                "modules.devices.vision.tracking",
                "VisionTrackingService",
            )
            service = service_class(
                vision_backend=vision_backend,
                pan_tilt_backend=pan_tilt_backend,
                config=config,
            )
            service_status = service.status() if hasattr(service, "status") else {}
            return (
                service,
                RuntimeBackendStatus(
                    component="vision_tracking",
                    ok=True,
                    selected_backend="vision_tracking_service",
                    detail=(
                        "Dry-run vision tracking service loaded. "
                        "Hardware movement remains blocked."
                    ),
                    runtime_mode="dry_run",
                    capabilities=(
                        "target_selection",
                        "pan_tilt_dry_run_plan",
                        "base_yaw_assist_required_decision",
                    ),
                    metadata=dict(service_status or {}),
                ),
            )
        except Exception as error:
            return (
                None,
                RuntimeBackendStatus(
                    component="vision_tracking",
                    ok=False,
                    selected_backend="null_vision_tracking",
                    detail=(
                        "Vision tracking service failed. "
                        f"Using null tracking. Error: {error}"
                    ),
                    fallback_used=True,
                    runtime_mode="dry_run",
                ),
            )


__all__ = ["RuntimeBuilderVisionMixin"]