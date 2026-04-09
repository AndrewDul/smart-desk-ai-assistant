from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RuntimeBackendStatus

from .fallbacks import NullMobilityBackend


class RuntimeBuilderMobilityMixin:
    """
    Build the mobility backend with explicit fallback handling.
    """

    def _build_mobility(
        self,
        config: dict[str, object],
    ) -> tuple[Any, RuntimeBackendStatus]:
        if not bool(config.get("enabled", False)):
            return (
                NullMobilityBackend(),
                RuntimeBackendStatus(
                    component="mobility",
                    ok=True,
                    selected_backend="null_mobility",
                    detail="Mobility disabled in config.",
                ),
            )

        try:
            backend_class = self._import_symbol(
                "modules.devices.mobility.base_controller",
                "BaseController",
            )
            backend = backend_class(config=config)
            return (
                backend,
                RuntimeBackendStatus(
                    component="mobility",
                    ok=True,
                    selected_backend=str(config.get("base_type", "base_controller")),
                    detail="Mobility backend loaded successfully.",
                ),
            )
        except Exception as error:
            return (
                NullMobilityBackend(),
                RuntimeBackendStatus(
                    component="mobility",
                    ok=False,
                    selected_backend="null_mobility",
                    detail=f"Mobility backend failed. Using null mobility. Error: {error}",
                    fallback_used=True,
                ),
            )


__all__ = ["RuntimeBuilderMobilityMixin"]