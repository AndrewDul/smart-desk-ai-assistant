from __future__ import annotations

from typing import Any

from modules.runtime.ai_broker import AiBrokerMode, AiBrokerService
from modules.runtime.contracts import RuntimeBackendStatus

from .fallbacks import NullAiBroker


class RuntimeBuilderAiBrokerMixin:
    """
    Build the central AI broker with explicit fallback handling.

    The broker is the single policy owner for heavy AI lane coordination.
    It should exist even when the current runtime only uses its idle baseline.
    """

    def _build_ai_broker(
        self,
        config: dict[str, object],
        *,
        vision_backend: Any,
    ) -> tuple[Any, RuntimeBackendStatus]:
        enabled = bool(config.get("enabled", True))
        if not enabled:
            return (
                NullAiBroker(),
                RuntimeBackendStatus(
                    component="ai_broker",
                    ok=True,
                    selected_backend="null_ai_broker",
                    detail="AI broker disabled in config.",
                ),
            )

        try:
            broker = AiBrokerService(
                vision_backend=vision_backend,
                settings=self.settings,
            )
            snapshot = broker.snapshot()
            return (
                broker,
                RuntimeBackendStatus(
                    component="ai_broker",
                    ok=True,
                    selected_backend="ai_broker",
                    detail="AI broker initialized successfully.",
                    capabilities=tuple(mode.value for mode in AiBrokerMode),
                    metadata={
                        "vision_control_available": bool(
                            snapshot.get("vision_control_available", False)
                        ),
                    },
                ),
            )
        except Exception as error:
            return (
                NullAiBroker(),
                RuntimeBackendStatus(
                    component="ai_broker",
                    ok=False,
                    selected_backend="null_ai_broker",
                    detail=f"AI broker failed. Using null AI broker. Error: {error}",
                    fallback_used=True,
                ),
            )


__all__ = ["RuntimeBuilderAiBrokerMixin"]