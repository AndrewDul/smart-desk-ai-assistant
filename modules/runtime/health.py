from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from modules.shared.config.settings import load_settings, resolve_settings_path
from modules.shared.logging.logger import append_log
from modules.shared.persistence.paths import (
    APP_ROOT,
    CACHE_DIR,
    CONFIG_DIR,
    DATA_DIR,
    LOGS_DIR,
    MODELS_DIR,
    SETTINGS_PATH,
    THIRD_PARTY_DIR,
    ensure_runtime_directories,
)


class HealthSeverity(str, Enum):
    """Severity assigned to one runtime health item."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(slots=True)
class HealthCheckItem:
    """One startup/runtime diagnostic result."""

    name: str
    ok: bool
    details: str
    severity: HealthSeverity = HealthSeverity.INFO
    critical: bool = True

    @property
    def is_warning(self) -> bool:
        return self.severity == HealthSeverity.WARNING

    @property
    def is_error(self) -> bool:
        return self.severity == HealthSeverity.ERROR


@dataclass(slots=True)
class HealthCheckReport:
    """Aggregate startup/runtime diagnostic result."""

    ok: bool
    items: list[HealthCheckItem] = field(default_factory=list)

    @property
    def startup_allowed(self) -> bool:
        return not any((not item.ok) and item.critical for item in self.items)

    @property
    def warnings(self) -> list[HealthCheckItem]:
        return [item for item in self.items if item.is_warning]

    @property
    def errors(self) -> list[HealthCheckItem]:
        return [item for item in self.items if item.is_error]

    @property
    def passed(self) -> list[HealthCheckItem]:
        return [item for item in self.items if item.ok]

    @property
    def failed(self) -> list[HealthCheckItem]:
        return [item for item in self.items if not item.ok]

    def summary_lines(self) -> list[str]:
        if not self.items:
            return ["no checks"]

        passed_count = len(self.passed)
        total_count = len(self.items)

        if self.failed:
            first_failed = self.failed[0]
            return [
                f"{passed_count} / {total_count} ready",
                f"issue: {first_failed.name}",
            ]

        if self.warnings:
            return [
                "startup checks ok",
                f"{passed_count} / {total_count} ready, warnings={len(self.warnings)}",
            ]

        return [
            "startup checks ok",
            f"{passed_count} / {total_count} ready",
        ]


class RuntimeHealthChecker:
    """
    Lightweight startup diagnostics for the NeXa runtime.

    Design goals:
    - validate local configuration and runtime dependencies early
    - stay aligned with the current runtime builder and real module paths
    - allow graceful degraded startup when a safe fallback exists
    - keep the output simple enough for small display overlays and logs
    """

    _MODEL_FILE_SUFFIXES = (".bin", ".gguf", ".pt", ".onnx", ".json")

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

    # ------------------------------------------------------------------
    # Base checks
    # ------------------------------------------------------------------

    def _check_settings_file(self) -> HealthCheckItem:
        if SETTINGS_PATH.exists():
            return self._info("settings", f"found {SETTINGS_PATH.name}")
        return self._error("settings", f"missing {SETTINGS_PATH.name}")

    def _check_project_directories(self) -> HealthCheckItem:
        required = [CONFIG_DIR, DATA_DIR, LOGS_DIR]
        missing = [path.name for path in required if not path.exists()]

        if missing:
            return self._error("directories", f"missing: {', '.join(missing)}")

        notes: list[str] = ["config", "data", "logs"]
        if CACHE_DIR.exists():
            notes.append("cache")
        if MODELS_DIR.exists():
            notes.append("models")

        return self._info("directories", f"ready: {', '.join(notes)}")

    # ------------------------------------------------------------------
    # Voice input
    # ------------------------------------------------------------------

    def _check_voice_input(self) -> HealthCheckItem:
        voice_input_cfg = self._cfg("voice_input")
        if not bool(voice_input_cfg.get("enabled", True)):
            return self._info(
                "voice input",
                "disabled in config, developer text input fallback available",
                critical=False,
            )

        engine = str(voice_input_cfg.get("engine", "faster_whisper")).strip().lower()

        if engine in {"faster_whisper", "faster-whisper"}:
            return self._check_faster_whisper_input(voice_input_cfg)

        if engine in {"whisper_cpp", "whisper.cpp", "whisper"}:
            return self._check_whisper_cpp_input(voice_input_cfg)

        if engine == "text":
            return self._info(
                "voice input",
                "text input backend configured explicitly",
                critical=False,
            )

        return self._error("voice input", f"unsupported input engine '{engine}'")

    def _check_faster_whisper_input(self, voice_input_cfg: dict[str, Any]) -> HealthCheckItem:
        missing_modules: list[str] = []
        for module_name, label in (
            ("numpy", "numpy"),
            ("sounddevice", "sounddevice"),
            ("soundfile", "soundfile"),
            ("faster_whisper", "faster-whisper"),
        ):
            if not self._module_exists(module_name):
                missing_modules.append(label)

        vad_enabled = bool(voice_input_cfg.get("vad_enabled", True))
        if vad_enabled:
            for module_name, label in (
                ("silero_vad", "silero-vad"),
                ("onnxruntime", "onnxruntime"),
            ):
                if not self._module_exists(module_name):
                    missing_modules.append(label)

        model_ref = str(
            voice_input_cfg.get(
                "model_size_or_path",
                voice_input_cfg.get("model_path", "small"),
            )
        ).strip()

        if missing_modules:
            return self._error(
                "voice input",
                "missing Python packages for faster-whisper runtime: "
                + ", ".join(sorted(set(missing_modules))),
            )

        if model_ref and not self._looks_like_model_alias(model_ref):
            model_path = self._resolve_local_path(model_ref)
            if not model_path.exists():
                return self._error(
                    "voice input",
                    f"faster-whisper model path missing: {model_path}",
                )
            model_detail = f"custom model path ready: {model_path.name}"
        else:
            model_detail = f"preset model alias: {model_ref or 'default'}"

        return self._info(
            "voice input",
            f"faster-whisper runtime ready, {model_detail}, VAD={'on' if vad_enabled else 'off'}",
        )

    def _check_whisper_cpp_input(self, voice_input_cfg: dict[str, Any]) -> HealthCheckItem:
        whisper_cli_raw = str(
            voice_input_cfg.get(
                "whisper_cli_path",
                "third_party/whisper.cpp/build/bin/whisper-cli",
            )
        ).strip()
        whisper_cli = self._resolve_command(whisper_cli_raw)

        model_path = self._resolve_local_path(
            str(
                voice_input_cfg.get(
                    "whisper_model_path",
                    voice_input_cfg.get("model_path", "models/ggml-base.bin"),
                )
            ).strip()
        )

        problems: list[str] = []
        if whisper_cli is None:
            problems.append("whisper-cli missing")
        if not model_path.exists():
            problems.append("whisper model missing")

        vad_enabled = bool(voice_input_cfg.get("vad_enabled", False))
        if vad_enabled:
            vad_model_path = self._resolve_local_path(
                str(
                    voice_input_cfg.get(
                        "whisper_vad_model_path",
                        voice_input_cfg.get("vad_model_path", "models/ggml-silero-v6.2.0.bin"),
                    )
                ).strip()
            )
            if not vad_model_path.exists():
                problems.append("vad model missing")

        if problems:
            return self._error("voice input", ", ".join(problems))

        return self._info(
            "voice input",
            f"whisper.cpp ready, model={model_path.name}, VAD={'on' if vad_enabled else 'off'}",
        )

    # ------------------------------------------------------------------
    # Wake gate
    # ------------------------------------------------------------------

    def _check_wake_gate(self) -> HealthCheckItem:
        voice_input_cfg = self._cfg("voice_input")
        if not bool(voice_input_cfg.get("enabled", True)):
            return self._info(
                "wake gate",
                "voice input disabled, wake gate not required",
                critical=False,
            )

        voice_engine = str(voice_input_cfg.get("engine", "faster_whisper")).strip().lower()
        if voice_engine == "text":
            return self._info(
                "wake gate",
                "text input backend handles activation directly",
                critical=False,
            )

        wake_engine = str(voice_input_cfg.get("wake_engine", "openwakeword")).strip().lower()
        if wake_engine in {"", "off", "none", "disabled"}:
            return self._warning(
                "wake gate",
                "wake gate disabled in config",
                critical=False,
            )

        if wake_engine != "openwakeword":
            return self._error("wake gate", f"unsupported wake engine '{wake_engine}'")

        missing_modules: list[str] = []
        for module_name, label in (
            ("numpy", "numpy"),
            ("sounddevice", "sounddevice"),
            ("openwakeword", "openwakeword"),
            ("onnxruntime", "onnxruntime"),
        ):
            if not self._module_exists(module_name):
                missing_modules.append(label)

        if missing_modules:
            return self._error(
                "wake gate",
                "missing wake runtime packages: " + ", ".join(sorted(set(missing_modules))),
            )

        model_path = self._resolve_local_path(
            str(voice_input_cfg.get("wake_model_path", "models/wake/nexa.onnx")).strip()
        )
        if not model_path.exists():
            return self._error("wake gate", f"wake model missing: {model_path}")

        threshold = float(voice_input_cfg.get("wake_threshold", 0.50))
        trigger_level = int(voice_input_cfg.get("wake_trigger_level", 2))
        block_ms = int(voice_input_cfg.get("wake_block_ms", 80))

        return self._info(
            "wake gate",
            (
                f"openWakeWord ready, model={model_path.name}, "
                f"threshold={threshold:.2f}, trigger_level={max(trigger_level, 1)}, block_ms={max(block_ms, 1)}"
            ),
        )

    # ------------------------------------------------------------------
    # Voice output
    # ------------------------------------------------------------------

    def _check_voice_output(self) -> HealthCheckItem:
        voice_output_cfg = self._cfg("voice_output")
        if not bool(voice_output_cfg.get("enabled", True)):
            return self._info("voice output", "disabled by config", critical=False)

        engine = str(voice_output_cfg.get("engine", "piper")).strip().lower()
        if engine != "piper":
            espeak_ok = bool(shutil.which("espeak-ng") or shutil.which("espeak"))
            if espeak_ok:
                return self._warning(
                    "voice output",
                    f"{engine} configured, eSpeak fallback available",
                    critical=False,
                    ok=True,
                )
            return self._error(
                "voice output",
                f"voice engine '{engine}' configured but no working eSpeak fallback found",
            )

        piper_python_ok = self._module_exists("piper")
        piper_models = voice_output_cfg.get("piper_models", {})
        missing_models: list[str] = []

        for lang in ("pl", "en"):
            model_info = piper_models.get(lang, {}) if isinstance(piper_models, dict) else {}
            model_raw = str(model_info.get("model", "")).strip()
            config_raw = str(model_info.get("config", "")).strip()

            if not model_raw or not config_raw:
                missing_models.append(lang)
                continue

            model_path = self._resolve_local_path(model_raw)
            config_path = self._resolve_local_path(config_raw)
            if not model_path.exists() or not config_path.exists():
                missing_models.append(lang)

        playback_ok = bool(
            shutil.which("pw-play")
            or shutil.which("paplay")
            or shutil.which("aplay")
            or shutil.which("ffplay")
        )
        fallback_ok = bool(shutil.which("espeak-ng") or shutil.which("espeak"))
        python_ok = bool(shutil.which("python") or shutil.which("python3"))

        if missing_models and not fallback_ok:
            return self._error(
                "voice output",
                "missing Piper files for: "
                f"{', '.join(sorted(set(missing_models)))} and no eSpeak fallback found",
            )

        if not piper_python_ok and not fallback_ok:
            return self._error(
                "voice output",
                "missing piper Python package and no eSpeak fallback found",
            )

        if not playback_ok and not fallback_ok:
            return self._error(
                "voice output",
                "no WAV playback tool and no eSpeak fallback found",
            )

        if not python_ok:
            return self._error("voice output", "python runtime for Piper not available")

        degraded_reasons: list[str] = []
        if not piper_python_ok:
            degraded_reasons.append("missing piper Python package")
        if missing_models:
            degraded_reasons.append(f"missing Piper files for: {', '.join(sorted(set(missing_models)))}")
        if not playback_ok:
            degraded_reasons.append("missing WAV playback tool")

        if degraded_reasons:
            return self._warning(
                "voice output",
                f"Piper degraded ({'; '.join(degraded_reasons)}), eSpeak fallback available",
                critical=False,
                ok=True,
            )

        return self._info("voice output", "piper runtime and voices ready")

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _check_display_config(self) -> HealthCheckItem:
        display_cfg = self._cfg("display")
        if not bool(display_cfg.get("enabled", True)):
            return self._info("display", "disabled by config", critical=False)

        driver = str(display_cfg.get("driver", "ssd1306")).strip().lower()
        interface = str(display_cfg.get("interface", "i2c")).strip().lower()
        width = int(display_cfg.get("width", 128))
        height = int(display_cfg.get("height", 64))

        if width <= 0 or height <= 0:
            return self._error("display", "invalid width or height")

        if driver == "waveshare_2inch":
            vendor_path = (
                APP_ROOT
                / "modules"
                / "devices"
                / "display"
                / "vendors"
                / "waveshare_lcd"
                / "LCD_2inch.py"
            )

            if interface != "spi":
                return self._error("display", "waveshare_2inch requires interface='spi'")
            if not vendor_path.exists():
                return self._error("display", f"waveshare LCD driver file is missing: {vendor_path}")

            missing_modules: list[str] = []
            for module_name, label in (
                ("PIL", "Pillow"),
                ("spidev", "spidev"),
                ("gpiozero", "gpiozero"),
            ):
                if not self._module_exists(module_name):
                    missing_modules.append(label)

            if missing_modules:
                return self._error(
                    "display",
                    "missing Waveshare display packages: " + ", ".join(sorted(set(missing_modules))),
                )

            gpio_dc = int(display_cfg.get("gpio_dc", 25))
            gpio_rst = int(display_cfg.get("gpio_rst", 27))
            gpio_light = int(display_cfg.get("gpio_light", 18))
            spi_port = int(display_cfg.get("spi_port", 0))
            spi_device = int(display_cfg.get("spi_device", 0))
            return self._info(
                "display",
                (
                    f"configured {driver} {width}x{height}, "
                    f"spi {spi_port}.{spi_device}, dc={gpio_dc}, rst={gpio_rst}, light={gpio_light}"
                ),
            )

        if driver.startswith("ssd") or driver in {"sh1106", "ssd1325", "ssd1331", "ws0010"}:
            missing_modules: list[str] = []
            for module_name, label in (("PIL", "Pillow"), ("luma.oled", "luma.oled")):
                if not self._module_exists(module_name):
                    missing_modules.append(label)

            if missing_modules:
                return self._error(
                    "display",
                    "missing OLED runtime packages: " + ", ".join(sorted(set(missing_modules))),
                )

            if interface == "i2c":
                port = int(display_cfg.get("port", 1))
                address = int(display_cfg.get("address", 60))
                return self._info(
                    "display",
                    f"configured {driver} {width}x{height}, i2c port {port}, address {address}",
                )

            if interface == "spi":
                spi_port = int(display_cfg.get("spi_port", 0))
                spi_device = int(display_cfg.get("spi_device", 0))
                return self._info(
                    "display",
                    f"configured {driver} {width}x{height}, spi {spi_port}.{spi_device}",
                )

            return self._error("display", f"unsupported display interface '{interface}'")

        return self._error("display", f"unsupported display driver '{driver}'")

    # ------------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------------

    def _check_llm_runtime(self) -> HealthCheckItem:
        llm_cfg = self._cfg("llm")
        if not bool(llm_cfg.get("enabled", False)):
            return self._info("llm", "disabled by config", critical=False)

        runner = str(llm_cfg.get("runner", "llama-cli")).strip().lower()

        if runner == "llama-cli":
            command = str(llm_cfg.get("command", "llama-cli")).strip() or "llama-cli"
            command_path = self._resolve_command(command)
            if not command_path:
                return self._error("llm", f"llama-cli command not found: {command}")

            model_raw = str(llm_cfg.get("model_path", "")).strip()
            if not model_raw:
                return self._error("llm", "llm model_path is empty")

            model_path = self._resolve_local_path(model_raw)
            if not model_path.exists():
                return self._error("llm", f"llm model missing: {model_path}")

            return self._info("llm", f"llama-cli ready, model={model_path.name}")

        if runner in {"llama-server", "server", "ollama-server", "hailo-ollama"}:
            server_url = str(llm_cfg.get("server_url", "")).strip()
            if not self._is_valid_url(server_url):
                return self._error("llm", "llm server URL is missing or invalid")

            chat_path = str(llm_cfg.get("server_chat_path", "/v1/chat/completions")).strip()
            chat_path = chat_path or "/v1/chat/completions"
            return self._info("llm", f"{runner} configured at {server_url}{chat_path}")

        return self._error("llm", f"unsupported llm runner '{runner}'")

    # ------------------------------------------------------------------
    # Vision
    # ------------------------------------------------------------------

    def _check_vision_runtime(self) -> HealthCheckItem:
        vision_cfg = self._cfg("vision")
        if not bool(vision_cfg.get("enabled", False)):
            return self._info("vision", "disabled by config", critical=False)

        missing_modules: list[str] = []
        for module_name, label in (("cv2", "opencv-python"), ("numpy", "numpy")):
            if not self._module_exists(module_name):
                missing_modules.append(label)

        if missing_modules:
            return self._error(
                "vision",
                "missing vision runtime packages: " + ", ".join(sorted(set(missing_modules))),
            )

        camera_index = int(vision_cfg.get("camera_index", 0))
        capabilities: list[str] = []
        if bool(vision_cfg.get("face_detection_enabled", False)):
            capabilities.append("face")
        if bool(vision_cfg.get("object_detection_enabled", False)):
            capabilities.append("object")
        if bool(vision_cfg.get("scene_understanding_enabled", False)):
            capabilities.append("scene")
        if bool(vision_cfg.get("gesture_recognition_enabled", False)):
            capabilities.append("gesture")
        if bool(vision_cfg.get("behavior_interpretation_enabled", False)):
            capabilities.append("behavior")

        capability_text = ", ".join(capabilities) if capabilities else "camera-only"
        return self._info(
            "vision",
            f"camera index {camera_index} configured, capabilities={capability_text}",
            critical=False,
        )

    # ------------------------------------------------------------------
    # Mobility
    # ------------------------------------------------------------------

    def _check_mobility_runtime(self) -> HealthCheckItem:
        mobility_cfg = self._cfg("mobility")
        if not bool(mobility_cfg.get("enabled", False)):
            return self._info("mobility", "disabled by config", critical=False)

        base_type = str(mobility_cfg.get("base_type", "differential")).strip().lower()
        safety_stop_enabled = bool(mobility_cfg.get("safety_stop_enabled", True))
        max_linear_speed = float(mobility_cfg.get("max_linear_speed", 0.3))
        max_turn_speed = float(mobility_cfg.get("max_turn_speed", 0.5))

        supported_base_types = {"differential", "mecanum", "omni", "tracked"}
        if base_type not in supported_base_types:
            return self._error("mobility", f"unsupported base_type '{base_type}'")
        if max_linear_speed < 0 or max_turn_speed < 0:
            return self._error("mobility", "invalid mobility speed limits")

        return self._info(
            "mobility",
            (
                f"configured base={base_type}, "
                f"safety_stop={'on' if safety_stop_enabled else 'off'}, "
                f"v={max_linear_speed:.2f}, turn={max_turn_speed:.2f}"
            ),
            critical=False,
        )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

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


SystemHealthChecker = RuntimeHealthChecker


__all__ = [
    "HealthCheckItem",
    "HealthCheckReport",
    "HealthSeverity",
    "RuntimeHealthChecker",
    "SystemHealthChecker",
]