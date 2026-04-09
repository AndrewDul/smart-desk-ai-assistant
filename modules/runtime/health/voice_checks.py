from __future__ import annotations

import shutil
from typing import Any

from .helpers import HealthCheckHelpers
from .models import HealthCheckItem


class HealthVoiceChecks(HealthCheckHelpers):
    """Voice-related runtime health checks."""

    settings: dict[str, Any]

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


__all__ = ["HealthVoiceChecks"]