from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from modules.shared.config.settings import resolve_settings_path
from modules.shared.persistence.paths import APP_ROOT, MODELS_DIR, THIRD_PARTY_DIR

from .models import HealthCheckItem, HealthSeverity


class HealthCheckHelpers:
    """Shared helper methods used by runtime health checks."""

    _MODEL_FILE_SUFFIXES = (".bin", ".gguf", ".pt", ".onnx", ".json")

    settings: dict[str, Any]

    def _cfg(self, key: str) -> dict[str, Any]:
        value = self.settings.get(key, {})
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _module_exists(module_name: str) -> bool:
        try:
            return importlib.util.find_spec(module_name) is not None
        except Exception:
            return False

    def _resolve_local_path(self, raw_path: str) -> Path:
        resolved = resolve_settings_path(raw_path)
        if resolved is not None:
            return resolved
        return MODELS_DIR / "missing"

    def _resolve_command(self, raw_command: str) -> str | None:
        expanded = str(raw_command or "").strip()
        if not expanded:
            return None

        direct_candidate = Path(expanded).expanduser()
        if direct_candidate.is_absolute() and direct_candidate.is_file():
            return str(direct_candidate)

        candidate_names: list[Path] = [direct_candidate]
        if "/" not in expanded and "\\" not in expanded:
            candidate_names.extend(
                [
                    APP_ROOT / expanded,
                    APP_ROOT / "llama.cpp" / "build" / "bin" / expanded,
                    APP_ROOT / "whisper.cpp" / "build" / "bin" / expanded,
                    THIRD_PARTY_DIR / "llama.cpp" / "build" / "bin" / expanded,
                    THIRD_PARTY_DIR / "whisper.cpp" / "build" / "bin" / expanded,
                ]
            )
        else:
            candidate_names.extend(
                [
                    APP_ROOT / direct_candidate,
                    THIRD_PARTY_DIR / direct_candidate,
                ]
            )

        for candidate in candidate_names:
            try:
                resolved = candidate.resolve()
            except Exception:
                continue
            if resolved.is_file():
                return str(resolved)

        which_match = shutil.which(expanded)
        if which_match:
            return which_match

        return None

    @classmethod
    def _looks_like_model_alias(cls, value: str) -> bool:
        normalized = str(value or "").strip()
        if not normalized:
            return False
        if "/" in normalized or "\\" in normalized:
            return False
        if normalized.endswith(cls._MODEL_FILE_SUFFIXES):
            return False
        return True

    @staticmethod
    def _is_valid_url(value: str) -> bool:
        parsed = urlparse(str(value or "").strip())
        return bool(parsed.scheme and parsed.netloc)

    @staticmethod
    def _info(name: str, details: str, *, critical: bool = True) -> HealthCheckItem:
        return HealthCheckItem(
            name=name,
            ok=True,
            details=details,
            severity=HealthSeverity.INFO,
            critical=critical,
        )

    @staticmethod
    def _warning(
        name: str,
        details: str,
        *,
        critical: bool = False,
        ok: bool = True,
    ) -> HealthCheckItem:
        return HealthCheckItem(
            name=name,
            ok=ok,
            details=details,
            severity=HealthSeverity.WARNING,
            critical=critical,
        )

    @staticmethod
    def _error(name: str, details: str, *, critical: bool = True) -> HealthCheckItem:
        return HealthCheckItem(
            name=name,
            ok=False,
            details=details,
            severity=HealthSeverity.ERROR,
            critical=critical,
        )

    @staticmethod
    def project_root() -> Path:
        return APP_ROOT


__all__ = ["HealthCheckHelpers"]