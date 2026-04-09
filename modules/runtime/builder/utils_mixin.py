from __future__ import annotations

from importlib import import_module
from typing import Any

from modules.runtime.contracts import RuntimeBackendStatus
from modules.shared.logging.logger import get_logger

LOGGER = get_logger(__name__)


class RuntimeBuilderUtilsMixin:
    """
    Shared utility helpers used by the runtime builder mixins.
    """

    def _cfg(self, key: str) -> dict[str, Any]:
        value = self.settings.get(key, {})
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _cfg_float(config: dict[str, Any], keys: tuple[str, ...], *, fallback: float) -> float:
        for key in keys:
            value = config.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return float(fallback)

    @staticmethod
    def _import_symbol(module_name: str, symbol_name: str) -> Any:
        module = import_module(module_name)
        return getattr(module, symbol_name)

    @staticmethod
    def _log_backend_status(status: RuntimeBackendStatus) -> None:
        message = (
            f"Runtime backend {('ready' if status.ok and not status.fallback_used else 'degraded')}: "
            f"component={status.component}, backend={status.selected_backend}, "
            f"fallback={status.fallback_used}, detail={status.detail}"
        )

        if status.ok and not status.fallback_used:
            LOGGER.info(message)
        else:
            LOGGER.warning(message)

    @staticmethod
    def _single_capture_mode_enabled(config: dict[str, Any]) -> bool:
        value = config.get("single_capture_mode")
        if value is None:
            return True
        return bool(value)


__all__ = ["RuntimeBuilderUtilsMixin"]