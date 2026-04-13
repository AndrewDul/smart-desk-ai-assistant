from __future__ import annotations

from typing import Any

from modules.shared.persistence.paths import (
    APP_ROOT,
    CACHE_DIR,
    CONFIG_DIR,
    DATA_DIR,
    LOGS_DIR,
    MODELS_DIR,
    SETTINGS_PATH,
)

from .helpers import HealthCheckHelpers
from .models import HealthCheckItem


class HealthSystemChecks(HealthCheckHelpers):
    """System and feature runtime health checks."""

    settings: dict[str, Any]

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

        runner = str(llm_cfg.get("runner", "hailo-ollama")).strip().lower()
        require_persistent_backend = bool(llm_cfg.get("require_persistent_backend", True))
        allow_cli_fallback = bool(llm_cfg.get("allow_cli_fallback", False))
        stream_responses = bool(llm_cfg.get("stream_responses", True))

        if runner == "llama-cli":
            if require_persistent_backend and not allow_cli_fallback:
                return self._error(
                    "llm",
                    "persistent llm service is required, but runner is llama-cli",
                )

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

            return self._info("llm", f"llama-cli fallback ready, model={model_path.name}")

        if runner in {"llama-server", "server", "ollama-server", "hailo-ollama", "openai-server"}:
            server_url = str(llm_cfg.get("server_url", "")).strip()
            if not self._is_valid_url(server_url):
                return self._error("llm", "llm server URL is missing or invalid")

            chat_path = str(llm_cfg.get("server_chat_path", "/api/chat")).strip() or "/api/chat"
            stream_note = "streaming on" if stream_responses else "streaming off"
            return self._info("llm", f"{runner} configured at {server_url}{chat_path} ({stream_note})")

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


__all__ = ["HealthSystemChecks"]