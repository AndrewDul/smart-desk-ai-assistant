from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from modules.system.utils import (
    BASE_DIR,
    CACHE_DIR,
    CONFIG_DIR,
    DATA_DIR,
    LOGS_DIR,
    SETTINGS_PATH,
    append_log,
    load_settings,
)


@dataclass(slots=True)
class HealthCheckItem:
    name: str
    ok: bool
    details: str


@dataclass(slots=True)
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
                "startup checks ok",
                f"{len(passed)} / {len(self.items)} ready",
            ]

        first_failed = failed[0]
        return [
            f"{len(passed)} / {len(self.items)} ready",
            f"issue: {first_failed.name}",
        ]


class SystemHealthChecker:
    """
    Lightweight startup diagnostics for the current NeXa runtime.

    Goals:
    - reflect the real current stack
    - validate config and paths without importing heavy runtime modules
    - catch environment problems early
    - distinguish between fully ready and degraded-but-usable setups
    """

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings if settings is not None else load_settings()

    def run(self) -> HealthCheckReport:
        items: list[HealthCheckItem] = [
            self._check_settings_file(),
            self._check_project_directories(),
            self._check_voice_input(),
            self._check_voice_output(),
            self._check_display_config(),
            self._check_llm_runtime(),
        ]

        report = HealthCheckReport(
            ok=all(item.ok for item in items),
            items=items,
        )

        for item in items:
            level = "OK" if item.ok else "WARN"
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

        cache_note = "cache ready" if CACHE_DIR.exists() else "cache optional"
        return HealthCheckItem("directories", True, f"data, logs, config ready; {cache_note}")

    def _check_voice_input(self) -> HealthCheckItem:
        voice_input_cfg = self.settings.get("voice_input", {})
        enabled = bool(voice_input_cfg.get("enabled", True))

        if not enabled:
            return HealthCheckItem(
                "voice input",
                True,
                "disabled in config, text input fallback available",
            )

        engine = str(voice_input_cfg.get("engine", "faster_whisper")).strip().lower()

        if engine in {"faster_whisper", "faster-whisper"}:
            return self._check_faster_whisper_input(voice_input_cfg)

        if engine == "whisper":
            return self._check_whisper_cpp_input(voice_input_cfg)

        if engine == "text":
            return HealthCheckItem(
                "voice input",
                True,
                "text input backend configured explicitly",
            )

        return HealthCheckItem(
            "voice input",
            False,
            f"unsupported input engine '{engine}'",
        )

    def _check_faster_whisper_input(self, voice_input_cfg: dict[str, Any]) -> HealthCheckItem:
        missing_modules: list[str] = []

        for module_name, label in [
            ("numpy", "numpy"),
            ("sounddevice", "sounddevice"),
            ("soundfile", "soundfile"),
            ("faster_whisper", "faster-whisper"),
        ]:
            if not self._module_exists(module_name):
                missing_modules.append(label)

        vad_enabled = bool(voice_input_cfg.get("vad_enabled", True))
        if vad_enabled:
            for module_name, label in [
                ("silero_vad", "silero-vad"),
                ("onnxruntime", "onnxruntime"),
            ]:
                if not self._module_exists(module_name):
                    missing_modules.append(label)

        model_ref = str(
            voice_input_cfg.get(
                "model_size_or_path",
                voice_input_cfg.get("model_path", "small"),
            )
        ).strip()

        model_detail = "preset model alias"
        if model_ref and not self._looks_like_model_alias(model_ref):
            model_path = self._resolve_project_path(model_ref)
            if not model_path.exists():
                return HealthCheckItem(
                    "voice input",
                    False,
                    f"faster-whisper model path missing: {model_path}",
                )
            model_detail = f"custom model path ready: {model_path.name}"
        elif model_ref:
            model_detail = f"preset model alias: {model_ref}"

        if missing_modules:
            return HealthCheckItem(
                "voice input",
                False,
                "missing Python packages for faster-whisper runtime: "
                + ", ".join(sorted(set(missing_modules))),
            )

        return HealthCheckItem(
            "voice input",
            True,
            f"faster-whisper runtime ready, {model_detail}, VAD={'on' if vad_enabled else 'off'}",
        )

    def _check_whisper_cpp_input(self, voice_input_cfg: dict[str, Any]) -> HealthCheckItem:
        whisper_cli_raw = str(
            voice_input_cfg.get("whisper_cli_path", "whisper.cpp/build/bin/whisper-cli")
        ).strip()
        whisper_cli = self._resolve_project_path(whisper_cli_raw)

        if not whisper_cli.exists():
            discovered = shutil.which(whisper_cli.name) or shutil.which("whisper-cli")
            if discovered:
                whisper_cli = Path(discovered)

        model_path = self._resolve_project_path(
            str(voice_input_cfg.get("model_path", "models/ggml-base.bin")).strip()
        )

        problems: list[str] = []

        if not whisper_cli.exists():
            problems.append("whisper-cli missing")

        if not model_path.exists():
            problems.append("whisper model missing")

        vad_enabled = bool(voice_input_cfg.get("vad_enabled", False))
        if vad_enabled:
            vad_model_path = self._resolve_project_path(
                str(voice_input_cfg.get("vad_model_path", "models/ggml-silero-v6.2.0.bin")).strip()
            )
            if not vad_model_path.exists():
                problems.append("vad model missing")

        if problems:
            return HealthCheckItem("voice input", False, ", ".join(problems))

        return HealthCheckItem(
            "voice input",
            True,
            f"whisper.cpp ready, model={model_path.name}, VAD={'on' if vad_enabled else 'off'}",
        )

    def _check_voice_output(self) -> HealthCheckItem:
        voice_output_cfg = self.settings.get("voice_output", {})
        enabled = bool(voice_output_cfg.get("enabled", True))

        if not enabled:
            return HealthCheckItem("voice output", True, "disabled by config")

        engine = str(voice_output_cfg.get("engine", "piper")).strip().lower()

        if engine != "piper":
            espeak_ok = bool(shutil.which("espeak-ng") or shutil.which("espeak"))
            if espeak_ok:
                return HealthCheckItem(
                    "voice output",
                    True,
                    f"{engine} configured, eSpeak fallback available",
                )
            return HealthCheckItem(
                "voice output",
                False,
                f"voice engine '{engine}' configured but no working eSpeak fallback found",
            )

        piper_python_ok = self._module_exists("piper")
        piper_models = voice_output_cfg.get("piper_models", {})
        missing_models: list[str] = []

        for lang in ("pl", "en"):
            model_info = piper_models.get(lang, {})
            model_raw = str(model_info.get("model", "")).strip()
            config_raw = str(model_info.get("config", "")).strip()

            model_path = self._resolve_project_path(model_raw) if model_raw else None
            config_path = self._resolve_project_path(config_raw) if config_raw else None

            if not model_raw or not config_raw:
                missing_models.append(lang)
                continue

            if model_path is None or not model_path.exists():
                missing_models.append(lang)
                continue

            if config_path is None or not config_path.exists():
                missing_models.append(lang)
                continue

        playback_ok = bool(shutil.which("aplay") or shutil.which("ffplay"))
        fallback_ok = bool(shutil.which("espeak-ng") or shutil.which("espeak"))
        python_ok = bool(shutil.which("python") or shutil.which("python3"))

        if missing_models and not fallback_ok:
            return HealthCheckItem(
                "voice output",
                False,
                f"missing Piper files for: {', '.join(sorted(set(missing_models)))} and no eSpeak fallback found",
            )

        if not piper_python_ok and not fallback_ok:
            return HealthCheckItem(
                "voice output",
                False,
                "missing piper Python package and no eSpeak fallback found",
            )

        if not playback_ok and not fallback_ok:
            return HealthCheckItem(
                "voice output",
                False,
                "no WAV playback tool and no eSpeak fallback found",
            )

        if not python_ok:
            return HealthCheckItem(
                "voice output",
                False,
                "python runtime for Piper not available",
            )

        degraded_reasons: list[str] = []
        if not piper_python_ok:
            degraded_reasons.append("missing piper Python package")
        if missing_models:
            degraded_reasons.append(f"missing Piper files for: {', '.join(sorted(set(missing_models)))}")
        if not playback_ok:
            degraded_reasons.append("missing WAV playback tool")

        if degraded_reasons:
            return HealthCheckItem(
                "voice output",
                False,
                f"Piper is degraded ({'; '.join(degraded_reasons)}), but eSpeak fallback is available",
            )

        return HealthCheckItem("voice output", True, "piper runtime and voices ready")

    def _check_display_config(self) -> HealthCheckItem:
        display_cfg = self.settings.get("display", {})
        enabled = bool(display_cfg.get("enabled", True))

        if not enabled:
            return HealthCheckItem("display", True, "disabled by config")

        driver = str(display_cfg.get("driver", "ssd1306")).strip().lower()
        interface = str(display_cfg.get("interface", "i2c")).strip().lower()
        width = int(display_cfg.get("width", 128))
        height = int(display_cfg.get("height", 64))

        if width <= 0 or height <= 0:
            return HealthCheckItem("display", False, "invalid width or height")

        if driver == "waveshare_2inch":
            vendor_path = BASE_DIR / "modules" / "io" / "vendors" / "waveshare_lcd" / "LCD_2inch.py"

            if interface != "spi":
                return HealthCheckItem(
                    "display",
                    False,
                    "waveshare_2inch requires interface='spi'",
                )

            if not vendor_path.exists():
                return HealthCheckItem(
                    "display",
                    False,
                    "waveshare LCD driver file is missing",
                )

            missing_modules: list[str] = []
            for module_name, label in [
                ("spidev", "spidev"),
                ("gpiozero", "gpiozero"),
            ]:
                if not self._module_exists(module_name):
                    missing_modules.append(label)

            if missing_modules:
                return HealthCheckItem(
                    "display",
                    False,
                    "missing display runtime packages: " + ", ".join(missing_modules),
                )

            gpio_dc = int(display_cfg.get("gpio_dc", 25))
            gpio_rst = int(display_cfg.get("gpio_rst", 27))
            gpio_light = int(display_cfg.get("gpio_light", 18))
            spi_port = int(display_cfg.get("spi_port", 0))
            spi_device = int(display_cfg.get("spi_device", 0))

            return HealthCheckItem(
                "display",
                True,
                f"configured {driver} {width}x{height}, spi {spi_port}.{spi_device}, "
                f"dc={gpio_dc}, rst={gpio_rst}, light={gpio_light}",
            )

        if driver.startswith("ssd") or driver in {"sh1106", "ssd1325", "ssd1331", "ws0010"}:
            missing_modules: list[str] = []
            for module_name, label in [
                ("PIL", "Pillow"),
                ("luma.oled", "luma.oled"),
            ]:
                if not self._module_exists(module_name):
                    missing_modules.append(label)

            if missing_modules:
                return HealthCheckItem(
                    "display",
                    False,
                    "missing OLED runtime packages: " + ", ".join(missing_modules),
                )

        if interface == "i2c":
            port = int(display_cfg.get("port", 1))
            address = int(display_cfg.get("address", 60))
            return HealthCheckItem(
                "display",
                True,
                f"configured {driver} {width}x{height}, i2c port {port}, address {address}",
            )

        if interface == "spi":
            spi_port = int(display_cfg.get("spi_port", 0))
            spi_device = int(display_cfg.get("spi_device", 0))
            return HealthCheckItem(
                "display",
                True,
                f"configured {driver} {width}x{height}, spi {spi_port}.{spi_device}",
            )

        return HealthCheckItem(
            "display",
            False,
            f"unsupported display interface '{interface}'",
        )

    def _check_llm_runtime(self) -> HealthCheckItem:
        llm_cfg = self.settings.get("llm", {})
        enabled = bool(llm_cfg.get("enabled", False))

        if not enabled:
            return HealthCheckItem("llm", True, "disabled by config")

        runner = str(llm_cfg.get("runner", "llama-cli")).strip().lower()

        if runner == "llama-cli":
            command = str(llm_cfg.get("command", "llama-cli")).strip() or "llama-cli"
            command_path = self._resolve_command(command)
            if not command_path:
                return HealthCheckItem(
                    "llm",
                    False,
                    f"llama-cli command not found: {command}",
                )

            model_raw = str(llm_cfg.get("model_path", "")).strip()
            if not model_raw:
                return HealthCheckItem(
                    "llm",
                    False,
                    "llm model_path is empty",
                )

            model_path = self._resolve_project_path(model_raw)
            if not model_path.exists():
                return HealthCheckItem(
                    "llm",
                    False,
                    f"llm model missing: {model_path}",
                )

            return HealthCheckItem(
                "llm",
                True,
                f"llama-cli ready, model={model_path.name}",
            )

        if runner == "llama-server":
            server_url = str(llm_cfg.get("server_url", "")).strip()
            if not self._is_valid_url(server_url):
                return HealthCheckItem(
                    "llm",
                    False,
                    "llama-server URL is missing or invalid",
                )

            chat_path = str(llm_cfg.get("server_chat_path", "/v1/chat/completions")).strip() or "/v1/chat/completions"
            return HealthCheckItem(
                "llm",
                True,
                f"llama-server configured at {server_url}{chat_path}",
            )

        return HealthCheckItem(
            "llm",
            False,
            f"unsupported llm runner '{runner}'",
        )

    @staticmethod
    def _resolve_project_path(raw_path: str) -> Path:
        candidate = Path(str(raw_path or "")).expanduser()
        if candidate.is_absolute():
            return candidate
        return BASE_DIR / candidate

    @staticmethod
    def _module_exists(module_name: str) -> bool:
        try:
            return importlib.util.find_spec(module_name) is not None
        except Exception:
            return False

    @staticmethod
    def _looks_like_model_alias(value: str) -> bool:
        normalized = str(value or "").strip()
        if not normalized:
            return False

        if "/" in normalized or "\\" in normalized:
            return False

        if normalized.endswith((".bin", ".gguf", ".pt", ".onnx", ".json")):
            return False

        return True

    @staticmethod
    def _is_valid_url(value: str) -> bool:
        parsed = urlparse(str(value or "").strip())
        return bool(parsed.scheme and parsed.netloc)

    @staticmethod
    def _resolve_command(raw_command: str) -> str | None:
        expanded = str(raw_command or "").strip()
        if not expanded:
            return None

        candidate = Path(expanded).expanduser()
        if candidate.is_absolute() and candidate.exists() and candidate.is_file():
            return str(candidate)

        if "/" in expanded or "\\" in expanded:
            resolved = (BASE_DIR / candidate).resolve()
            if resolved.exists() and resolved.is_file():
                return str(resolved)

        which_match = shutil.which(expanded)
        if which_match:
            return which_match

        default_local = BASE_DIR / "llama.cpp" / "build" / "bin" / expanded
        if default_local.exists() and default_local.is_file():
            return str(default_local)

        return None