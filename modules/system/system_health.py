from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modules.system.utils import (
    BASE_DIR,
    CONFIG_DIR,
    DATA_DIR,
    LOGS_DIR,
    SETTINGS_PATH,
    append_log,
    load_settings,
)


@dataclass
class HealthCheckItem:
    name: str
    ok: bool
    details: str


@dataclass
class HealthCheckReport:
    ok: bool
    items: list[HealthCheckItem] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        if not self.items:
            return ["no checks"]

        failed = [item for item in self.items if not item.ok]
        passed = [item for item in self.items if item.ok]

        if not failed:
            return [
                "all checks passed",
                f"{len(passed)} / {len(self.items)} ready",
            ]

        first_failed = failed[0]
        return [
            f"{len(passed)} / {len(self.items)} ready",
            f"issue: {first_failed.name}",
        ]


class SystemHealthChecker:
    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings if settings is not None else load_settings()

    @staticmethod
    def _resolve_project_path(raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if candidate.is_absolute():
            return candidate
        return BASE_DIR / candidate

    def run(self) -> HealthCheckReport:
        items: list[HealthCheckItem] = []

        items.append(self._check_settings_file())
        items.append(self._check_project_directories())
        items.append(self._check_voice_input())
        items.append(self._check_voice_output())
        items.append(self._check_display_config())

        overall_ok = all(item.ok for item in items)
        report = HealthCheckReport(ok=overall_ok, items=items)

        for item in items:
            level = "OK" if item.ok else "FAIL"
            append_log(f"Startup check [{level}] {item.name}: {item.details}")

        return report

    def _check_settings_file(self) -> HealthCheckItem:
        if SETTINGS_PATH.exists():
            return HealthCheckItem("settings", True, f"found {SETTINGS_PATH.name}")
        return HealthCheckItem("settings", False, f"missing {SETTINGS_PATH.name}")

    def _check_project_directories(self) -> HealthCheckItem:
        required = [DATA_DIR, LOGS_DIR, CONFIG_DIR]
        missing = [path.name for path in required if not path.exists()]

        if missing:
            return HealthCheckItem("directories", False, f"missing: {', '.join(missing)}")

        return HealthCheckItem("directories", True, "data, logs, config ready")

    def _check_voice_input(self) -> HealthCheckItem:
        voice_input_cfg = self.settings.get("voice_input", {})
        enabled = bool(voice_input_cfg.get("enabled", True))

        if not enabled:
            return HealthCheckItem(
                "voice input",
                True,
                "disabled in config, text input fallback available",
            )

        engine = str(voice_input_cfg.get("engine", "whisper")).lower().strip()
        if engine != "whisper":
            return HealthCheckItem(
                "voice input",
                False,
                f"unsupported input engine '{engine}', expected 'whisper'",
            )

        whisper_cli_raw = str(
            voice_input_cfg.get("whisper_cli_path", "whisper.cpp/build/bin/whisper-cli")
        )
        whisper_cli = self._resolve_project_path(whisper_cli_raw)

        if not whisper_cli.exists():
            discovered = shutil.which(whisper_cli.name) or shutil.which("whisper-cli")
            if discovered:
                whisper_cli = Path(discovered)

        model_path = self._resolve_project_path(
            str(voice_input_cfg.get("model_path", "models/ggml-base.bin"))
        )

        problems: list[str] = []

        if not whisper_cli.exists():
            problems.append("whisper-cli missing")

        if not model_path.exists():
            problems.append("whisper model missing")

        vad_enabled = bool(voice_input_cfg.get("vad_enabled", False))
        if vad_enabled:
            vad_model_path = self._resolve_project_path(
                str(voice_input_cfg.get("vad_model_path", "models/ggml-silero-v6.2.0.bin"))
            )
            if not vad_model_path.exists():
                problems.append("vad model missing")

        if problems:
            return HealthCheckItem("voice input", False, ", ".join(problems))

        return HealthCheckItem("voice input", True, "whisper-cli and model ready")

    def _check_voice_output(self) -> HealthCheckItem:
        voice_output_cfg = self.settings.get("voice_output", {})
        enabled = bool(voice_output_cfg.get("enabled", True))

        if not enabled:
            return HealthCheckItem("voice output", True, "disabled by config")

        engine = str(voice_output_cfg.get("engine", "piper")).lower().strip()

        if engine != "piper":
            espeak_ok = bool(shutil.which("espeak-ng") or shutil.which("espeak"))
            if espeak_ok:
                return HealthCheckItem(
                    "voice output",
                    True,
                    f"{engine} configured, espeak available",
                )
            return HealthCheckItem(
                "voice output",
                False,
                f"unsupported voice engine '{engine}'",
            )

        piper_models = voice_output_cfg.get("piper_models", {})

        missing_models: list[str] = []
        for lang in ("pl", "en"):
            model_info = piper_models.get(lang, {})
            model_raw = str(model_info.get("model", "")).strip()
            config_raw = str(model_info.get("config", "")).strip()

            model_path = self._resolve_project_path(model_raw) if model_raw else Path()
            config_path = self._resolve_project_path(config_raw) if config_raw else Path()

            if not model_raw or not config_raw or not model_path.exists() or not config_path.exists():
                missing_models.append(lang)

        playback_ok = bool(shutil.which("aplay") or shutil.which("ffplay"))
        fallback_ok = bool(shutil.which("espeak-ng") or shutil.which("espeak"))
        python_ok = bool(shutil.which("python") or shutil.which("python3"))

        if missing_models:
            return HealthCheckItem(
                "voice output",
                False,
                f"missing Piper files for: {', '.join(missing_models)}",
            )

        if not playback_ok and not fallback_ok:
            return HealthCheckItem(
                "voice output",
                False,
                "no audio playback tool and no eSpeak fallback",
            )

        if not python_ok:
            return HealthCheckItem(
                "voice output",
                False,
                "python runtime for Piper not available",
            )

        return HealthCheckItem("voice output", True, "piper models ready")

    def _check_display_config(self) -> HealthCheckItem:
        display_cfg = self.settings.get("display", {})
        enabled = bool(display_cfg.get("enabled", True))

        if not enabled:
            return HealthCheckItem("display", True, "disabled by config")

        width = int(display_cfg.get("width", 128))
        height = int(display_cfg.get("height", 64))
        port = int(display_cfg.get("port", 1))
        address = int(display_cfg.get("address", 60))

        if width <= 0 or height <= 0:
            return HealthCheckItem("display", False, "invalid width or height")

        return HealthCheckItem(
            "display",
            True,
            f"configured {width}x{height}, i2c port {port}, address {address}",
        )