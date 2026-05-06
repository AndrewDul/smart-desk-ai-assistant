"""
RuntimeBuilder mixin for the in-process LookAtMeSession.

This deliberately does NOT introduce a new "backend" because look-at-me does
not own the camera or the servos — it just borrows the existing CameraService
and PanTiltService backends and runs a small worker thread on top of them.
"""
from __future__ import annotations

from typing import Any

from modules.devices.vision.look_at_me import LookAtMeSession
from modules.runtime.contracts import RuntimeBackendStatus


class RuntimeBuilderLookAtMeMixin:
    """Build the LookAtMeSession after vision and pan/tilt are available."""

    def _build_look_at_me_session(
        self,
        *,
        vision_backend: Any,
        pan_tilt_backend: Any,
    ) -> tuple[Any | None, RuntimeBackendStatus]:
        cfg = self._cfg("look_at_me") if hasattr(self, "_cfg") else dict(
            self.settings.get("look_at_me", {}) or {}
        )

        if not bool(cfg.get("enabled", True)):
            return (
                None,
                RuntimeBackendStatus(
                    component="look_at_me",
                    ok=True,
                    selected_backend="disabled_look_at_me",
                    detail="Look-at-me disabled in config.",
                ),
            )

        if vision_backend is None:
            return (
                None,
                RuntimeBackendStatus(
                    component="look_at_me",
                    ok=False,
                    selected_backend="disabled_look_at_me",
                    detail="Look-at-me requires a vision backend.",
                    fallback_used=True,
                ),
            )

        try:
            session = LookAtMeSession.from_settings(
                settings=self.settings,
                vision_backend=vision_backend,
                pan_tilt_backend=pan_tilt_backend,
            )
        except Exception as error:
            return (
                None,
                RuntimeBackendStatus(
                    component="look_at_me",
                    ok=False,
                    selected_backend="disabled_look_at_me",
                    detail=f"Look-at-me session init failed safely: {error}",
                    fallback_used=True,
                ),
            )

        backend_label = (
            "look_at_me_in_process"
            if pan_tilt_backend is not None
            else "look_at_me_planning_only"
        )
        return (
            session,
            RuntimeBackendStatus(
                component="look_at_me",
                ok=True,
                selected_backend=backend_label,
                detail=(
                    "In-process face tracker ready. Shares CameraService and "
                    "drives the pan/tilt backend via move_delta()."
                ),
            ),
        )
