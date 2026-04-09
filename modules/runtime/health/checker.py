from __future__ import annotations

from typing import Any

from modules.shared.config.settings import load_settings
from modules.shared.logging.logger import append_log
from modules.shared.persistence.paths import ensure_runtime_directories

from .models import HealthCheckItem, HealthCheckReport
from .system_checks import HealthSystemChecks
from .voice_checks import HealthVoiceChecks


class RuntimeHealthChecker(HealthVoiceChecks, HealthSystemChecks):
    """
    Lightweight startup diagnostics for the NeXa runtime.

    Design goals:
    - validate local configuration and runtime dependencies early
    - stay aligned with the current runtime builder and real module paths
    - allow graceful degraded startup when a safe fallback exists
    - keep the output simple enough for small display overlays and logs
    """

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings if settings is not None else load_settings()

    def run(self) -> HealthCheckReport:
        ensure_runtime_directories()

        items: list[HealthCheckItem] = [
            self._check_settings_file(),
            self._check_project_directories(),
            self._check_voice_input(),
            self._check_wake_gate(),
            self._check_voice_output(),
            self._check_display_config(),
            self._check_llm_runtime(),
            self._check_vision_runtime(),
            self._check_mobility_runtime(),
        ]

        report = HealthCheckReport(
            ok=not any((not item.ok) and item.critical for item in items),
            items=items,
        )

        for item in report.items:
            level = "OK" if item.ok else item.severity.value.upper()
            append_log(f"Startup check [{level}] {item.name}: {item.details}")

        append_log(
            "Startup health summary: "
            f"startup_allowed={report.startup_allowed}, "
            f"passed={len(report.passed)}, "
            f"warnings={len(report.warnings)}, "
            f"errors={len(report.errors)}"
        )

        return report


SystemHealthChecker = RuntimeHealthChecker


__all__ = [
    "RuntimeHealthChecker",
    "SystemHealthChecker",
]