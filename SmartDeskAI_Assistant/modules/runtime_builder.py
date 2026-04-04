from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol

from modules.nlu.semantic_companion_router import SemanticCompanionRouter
from modules.parsing.intent_parser import IntentParser
from modules.services.companion_dialogue import CompanionDialogueService
from modules.services.memory import SimpleMemory
from modules.services.reminders import ReminderManager
from modules.services.timer import SessionTimer
from modules.system.utils import BASE_DIR, append_log, load_settings


class SpeechInputBackend(Protocol):
    def listen(self, timeout: float = 8.0, debug: bool = False) -> str | None:
        ...


class SpeechOutputBackend(Protocol):
    def speak(self, text: str, language: str | None = None) -> None:
        ...


class DisplayBackend(Protocol):
    def show_block(self, title: str, lines: list[str], duration: float = 10.0) -> None:
        ...

    def show_status(self, state: dict, timer_status: dict, duration: float = 10.0) -> None:
        ...

    def clear_overlay(self) -> None:
        ...

    def close(self) -> None:
        ...


@dataclass(slots=True)
class RuntimeBackendStatus:
    component: str
    ok: bool
    selected_backend: str
    detail: str = ""
    fallback_used: bool = False


@dataclass(slots=True)
class RuntimeServices:
    settings: dict[str, Any]
    parser: IntentParser
    router: SemanticCompanionRouter
    dialogue: CompanionDialogueService
    voice_input: SpeechInputBackend
    voice_output: SpeechOutputBackend
    display: DisplayBackend
    memory: SimpleMemory
    reminders: ReminderManager
    timer: SessionTimer
    backend_statuses: dict[str, RuntimeBackendStatus] = field(default_factory=dict)

    def backend_status(self, component: str) -> RuntimeBackendStatus | None:
        return self.backend_statuses.get(component)


class SilentVoiceOutput:
    """
    Safe fallback when the real TTS backend cannot be created.
    """

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def speak(self, text: str, language: str | None = None) -> None:
        self.messages.append(
            {
                "text": str(text),
                "language": language,
            }
        )


class NullDisplay:
    """
    Safe fallback when the real display backend cannot be created.
    """

    def __init__(self) -> None:
        self.blocks: list[dict[str, Any]] = []
        self.closed = False

    def show_block(self, title: str, lines: list[str], duration: float = 10.0) -> None:
        self.blocks.append(
            {
                "title": str(title),
                "lines": [str(line) for line in lines],
                "duration": float(duration),
            }
        )

    def show_status(self, state: dict, timer_status: dict, duration: float = 10.0) -> None:
        self.blocks.append(
            {
                "title": "STATUS",
                "lines": [
                    f"focus: {'ON' if state.get('focus_mode') else 'OFF'}",
                    f"break: {'ON' if state.get('break_mode') else 'OFF'}",
                    f"timer: {state.get('current_timer') or 'none'}",
                    f"run: {'ON' if timer_status.get('running') else 'OFF'}",
                ],
                "duration": float(duration),
            }
        )

    def clear_overlay(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class RuntimeBuilder:
    """
    Composition root for the new NeXa runtime.

    Why this exists:
    - keep current working domain modules
    - stop CoreAssistant from constructing every dependency itself
    - load hardware and audio backends lazily
    - degrade gracefully when optional runtime dependencies are missing
    - prepare the project for streaming-first and future vision integration
    """

    def __init__(self, settings: dict[str, Any] | None = None) -> None:
        self.settings = settings or load_settings()

    def build(
        self,
        *,
        on_timer_started=None,
        on_timer_finished=None,
        on_timer_stopped=None,
    ) -> RuntimeServices:
        parser = IntentParser(
            default_focus_minutes=float(self.settings.get("timers", {}).get("default_focus_minutes", 25)),
            default_break_minutes=float(self.settings.get("timers", {}).get("default_break_minutes", 5)),
        )

        router = SemanticCompanionRouter(parser)
        dialogue = CompanionDialogueService()

        voice_input, voice_input_status = self._build_voice_input(self.settings.get("voice_input", {}))
        voice_output, voice_output_status = self._build_voice_output(self.settings.get("voice_output", {}))
        display, display_status = self._build_display(self.settings.get("display", {}))

        memory = SimpleMemory()
        reminders = ReminderManager()
        timer = SessionTimer(
            on_started=on_timer_started,
            on_finished=on_timer_finished,
            on_stopped=on_timer_stopped,
        )

        backend_statuses = {
            "voice_input": voice_input_status,
            "voice_output": voice_output_status,
            "display": display_status,
        }

        for status in backend_statuses.values():
            self._log_backend_status(status)

        return RuntimeServices(
            settings=self.settings,
            parser=parser,
            router=router,
            dialogue=dialogue,
            voice_input=voice_input,
            voice_output=voice_output,
            display=display,
            memory=memory,
            reminders=reminders,
            timer=timer,
            backend_statuses=backend_statuses,
        )

    def _build_voice_input(self, config: dict[str, Any]) -> tuple[SpeechInputBackend, RuntimeBackendStatus]:
        text_input_class = self._import_symbol("modules.io.text_input", "TextInput")

        if not bool(config.get("enabled", True)):
            return (
                text_input_class(),
                RuntimeBackendStatus(
                    component="voice_input",
                    ok=True,
                    selected_backend="text_input",
                    detail="Voice input disabled in config. Using text input backend.",
                ),
            )

        engine = str(config.get("engine", "faster_whisper")).strip().lower()

        if engine in {"faster_whisper", "faster-whisper"}:
            missing_dependencies = self._missing_voice_input_dependencies(config)
            if missing_dependencies:
                return (
                    text_input_class(),
                    RuntimeBackendStatus(
                        component="voice_input",
                        ok=False,
                        selected_backend="text_input",
                        detail=(
                            "Missing voice input runtime dependencies for Faster-Whisper: "
                            f"{', '.join(missing_dependencies)}. Falling back to text input."
                        ),
                        fallback_used=True,
                    ),
                )

        if engine == "whisper":
            missing_whisper_assets = self._missing_whisper_cpp_assets(config)
            if missing_whisper_assets:
                return (
                    text_input_class(),
                    RuntimeBackendStatus(
                        component="voice_input",
                        ok=False,
                        selected_backend="text_input",
                        detail=(
                            "Whisper.cpp voice input assets are missing: "
                            f"{', '.join(missing_whisper_assets)}. Falling back to text input."
                        ),
                        fallback_used=True,
                    ),
                )

        try:
            if engine in {"faster_whisper", "faster-whisper"}:
                backend_class = self._import_symbol(
                    "modules.io.faster_whisper_input",
                    "FasterWhisperVoiceInput",
                )
                backend = backend_class(
                    model_size_or_path=config.get("model_size_or_path", config.get("model_path", "small")),
                    language=config.get("language", "auto"),
                    device_index=config.get("device_index"),
                    device_name_contains=config.get("device_name_contains"),
                    sample_rate=config.get("sample_rate", 16000),
                    max_record_seconds=float(config.get("max_record_seconds", 8.0)),
                    end_silence_seconds=float(config.get("end_silence_seconds", 0.75)),
                    pre_roll_seconds=float(config.get("pre_roll_seconds", 0.6)),
                    blocksize=int(config.get("blocksize", 512)),
                    min_speech_seconds=float(config.get("min_speech_seconds", 0.28)),
                    transcription_timeout_seconds=float(config.get("transcription_timeout_seconds", 45.0)),
                    compute_type=str(config.get("compute_type", "int8")),
                    cpu_threads=int(config.get("threads", 4)),
                    beam_size=int(config.get("beam_size", 1)),
                    best_of=int(config.get("best_of", 1)),
                    vad_enabled=bool(config.get("vad_enabled", True)),
                    vad_threshold=float(config.get("vad_threshold", 0.5)),
                    vad_min_speech_ms=int(config.get("vad_min_speech_ms", 250)),
                    vad_min_silence_ms=int(config.get("vad_min_silence_ms", 500)),
                    vad_speech_pad_ms=int(config.get("vad_speech_pad_ms", 120)),
                )
                detail = "Faster-Whisper input backend loaded successfully."
                model_reference = str(config.get("model_size_or_path", config.get("model_path", "small"))).strip()
                if self._looks_like_path_reference(model_reference):
                    detail = f"{detail} Model path resolved: {self._resolve_project_path(model_reference)}"
                return (
                    backend,
                    RuntimeBackendStatus(
                        component="voice_input",
                        ok=True,
                        selected_backend="faster_whisper",
                        detail=detail,
                    ),
                )

            if engine == "whisper":
                backend_class = self._import_symbol("modules.io.whisper_input", "WhisperVoiceInput")
                backend = backend_class(
                    whisper_cli_path=config.get("whisper_cli_path", "whisper.cpp/build/bin/whisper-cli"),
                    model_path=config.get("model_path", "models/ggml-base.bin"),
                    vad_enabled=bool(config.get("vad_enabled", False)),
                    vad_model_path=config.get("vad_model_path", "models/ggml-silero-v6.2.0.bin"),
                    language=config.get("language", "auto"),
                    device_index=config.get("device_index"),
                    device_name_contains=config.get("device_name_contains"),
                    sample_rate=config.get("sample_rate"),
                    max_record_seconds=float(config.get("max_record_seconds", 8.0)),
                    silence_threshold=float(config.get("silence_threshold", 350.0)),
                    end_silence_seconds=float(config.get("end_silence_seconds", 1.0)),
                    pre_roll_seconds=float(config.get("pre_roll_seconds", 0.4)),
                    threads=int(config.get("threads", 4)),
                    min_speech_seconds=float(config.get("min_speech_seconds", 0.28)),
                    transcription_timeout_seconds=float(config.get("transcription_timeout_seconds", 45.0)),
                )
                return (
                    backend,
                    RuntimeBackendStatus(
                        component="voice_input",
                        ok=True,
                        selected_backend="whisper",
                        detail="Whisper.cpp input backend loaded successfully.",
                    ),
                )

            if engine == "text":
                return (
                    text_input_class(),
                    RuntimeBackendStatus(
                        component="voice_input",
                        ok=True,
                        selected_backend="text_input",
                        detail="Text input backend configured explicitly.",
                    ),
                )

            return (
                text_input_class(),
                RuntimeBackendStatus(
                    component="voice_input",
                    ok=False,
                    selected_backend="text_input",
                    detail=f"Unsupported voice input engine '{engine}'. Falling back to text input.",
                    fallback_used=True,
                ),
            )

        except Exception as error:
            return (
                text_input_class(),
                RuntimeBackendStatus(
                    component="voice_input",
                    ok=False,
                    selected_backend="text_input",
                    detail=f"Voice input backend '{engine}' failed. Falling back to text input. Error: {error}",
                    fallback_used=True,
                ),
            )

    def _build_voice_output(self, config: dict[str, Any]) -> tuple[SpeechOutputBackend, RuntimeBackendStatus]:
        if not bool(config.get("enabled", True)):
            return (
                SilentVoiceOutput(),
                RuntimeBackendStatus(
                    component="voice_output",
                    ok=True,
                    selected_backend="silent_voice_output",
                    detail="Voice output disabled in config. Using silent backend.",
                ),
            )

        try:
            voice_output_class = self._import_symbol("modules.io.voice_out", "VoiceOutput")
            backend = voice_output_class(
                enabled=config.get("enabled", True),
                preferred_engine=config.get("engine", "piper"),
                default_language=config.get("default_language", "pl"),
                speed=int(config.get("speed", 155)),
                pitch=int(config.get("pitch", 58)),
                voices=config.get("voices", {"pl": "pl+f3", "en": "en+f3"}),
                piper_models=config.get("piper_models"),
            )
            status = self._assess_voice_output_backend(config, backend)
            return backend, status
        except Exception as error:
            return (
                SilentVoiceOutput(),
                RuntimeBackendStatus(
                    component="voice_output",
                    ok=False,
                    selected_backend="silent_voice_output",
                    detail=f"Voice output backend failed. Using silent backend. Error: {error}",
                    fallback_used=True,
                ),
            )

    def _build_display(self, config: dict[str, Any]) -> tuple[DisplayBackend, RuntimeBackendStatus]:
        if not bool(config.get("enabled", True)):
            return (
                NullDisplay(),
                RuntimeBackendStatus(
                    component="display",
                    ok=True,
                    selected_backend="null_display",
                    detail="Display disabled in config. Using null display backend.",
                ),
            )

        try:
            display_class = self._import_symbol("modules.io.display", "ConsoleDisplay")
            backend = display_class(
                driver=str(config.get("driver", "ssd1306")),
                interface=str(config.get("interface", "i2c")),
                port=int(config.get("port", 1)),
                address=int(config.get("address", 60)),
                rotate=int(config.get("rotate", 0)),
                width=int(config.get("width", 128)),
                height=int(config.get("height", 64)),
                spi_port=int(config.get("spi_port", 0)),
                spi_device=int(config.get("spi_device", 0)),
                gpio_dc=int(config.get("gpio_dc", 25)),
                gpio_rst=int(config.get("gpio_rst", 27)),
                gpio_light=int(config.get("gpio_light", 18)),
            )
            return (
                backend,
                RuntimeBackendStatus(
                    component="display",
                    ok=True,
                    selected_backend=str(config.get("driver", "ssd1306")),
                    detail="Display backend loaded successfully.",
                ),
            )
        except Exception as error:
            return (
                NullDisplay(),
                RuntimeBackendStatus(
                    component="display",
                    ok=False,
                    selected_backend="null_display",
                    detail=f"Display backend failed. Using null display. Error: {error}",
                    fallback_used=True,
                ),
            )

    def _assess_voice_output_backend(self, config: dict[str, Any], backend: Any) -> RuntimeBackendStatus:
        preferred_engine = str(config.get("engine", "piper") or "piper").strip().lower()
        default_language = str(config.get("default_language", "pl") or "pl").strip().lower()

        has_espeak = bool(getattr(backend, "espeak_path", None))
        has_wav_playback = bool(getattr(backend, "aplay_path", None) or getattr(backend, "ffplay_path", None))

        if preferred_engine != "piper":
            if has_espeak:
                return RuntimeBackendStatus(
                    component="voice_output",
                    ok=True,
                    selected_backend=preferred_engine,
                    detail="Voice output backend loaded successfully.",
                )

            return RuntimeBackendStatus(
                component="voice_output",
                ok=False,
                selected_backend=preferred_engine,
                detail=(
                    f"Preferred voice output engine '{preferred_engine}' is configured, but no working eSpeak binary "
                    "was found. Voice output may fail at runtime."
                ),
                fallback_used=False,
            )

        piper_module_available = self._python_module_available("piper")
        piper_ready = self._safe_check_piper_ready(backend, default_language)

        if piper_module_available and piper_ready and has_wav_playback:
            return RuntimeBackendStatus(
                component="voice_output",
                ok=True,
                selected_backend="piper",
                detail="Voice output backend loaded successfully.",
            )

        issues: list[str] = []
        if not piper_module_available:
            issues.append("missing piper Python package")
        if not piper_ready:
            issues.append(f"missing Piper model for language '{default_language}'")
        if not has_wav_playback:
            issues.append("missing WAV playback command (aplay or ffplay)")

        if has_espeak:
            return RuntimeBackendStatus(
                component="voice_output",
                ok=False,
                selected_backend="piper",
                detail=(
                    "Preferred Piper output is degraded because "
                    f"{', '.join(issues)}. eSpeak fallback is available."
                ),
                fallback_used=True,
            )

        return RuntimeBackendStatus(
            component="voice_output",
            ok=False,
            selected_backend="piper",
            detail=(
                "Voice output is degraded because "
                f"{', '.join(issues)} and no eSpeak fallback was found."
            ),
            fallback_used=False,
        )

    def _missing_voice_input_dependencies(self, config: dict[str, Any]) -> list[str]:
        missing: list[str] = []

        if not self._python_module_available("faster_whisper"):
            missing.append("faster-whisper")

        if bool(config.get("vad_enabled", True)):
            if not self._python_module_available("silero_vad"):
                missing.append("silero-vad")
            if not self._python_module_available("onnxruntime"):
                missing.append("onnxruntime")

        model_reference = str(config.get("model_size_or_path", config.get("model_path", "small")) or "").strip()
        if self._looks_like_path_reference(model_reference) and not self._path_exists_if_explicit(model_reference):
            missing.append(f"model path '{model_reference}'")

        return missing

    def _missing_whisper_cpp_assets(self, config: dict[str, Any]) -> list[str]:
        missing: list[str] = []

        whisper_cli_path = str(config.get("whisper_cli_path", "whisper.cpp/build/bin/whisper-cli") or "").strip()
        model_path = str(config.get("model_path", "models/ggml-base.bin") or "").strip()

        if whisper_cli_path and not self._path_exists_if_explicit(whisper_cli_path):
            missing.append(f"whisper cli '{whisper_cli_path}'")

        if model_path and not self._path_exists_if_explicit(model_path):
            missing.append(f"model '{model_path}'")

        if bool(config.get("vad_enabled", False)):
            vad_model_path = str(config.get("vad_model_path", "models/ggml-silero-v6.2.0.bin") or "").strip()
            if vad_model_path and not self._path_exists_if_explicit(vad_model_path):
                missing.append(f"vad model '{vad_model_path}'")

        return missing

    @staticmethod
    def _safe_check_piper_ready(backend: Any, language: str) -> bool:
        checker = getattr(backend, "_piper_model_ready", None)
        if not callable(checker):
            return False

        try:
            return bool(checker(language))
        except Exception:
            return False

    @staticmethod
    def _python_module_available(module_name: str) -> bool:
        try:
            import_module(module_name)
            return True
        except Exception:
            return False

    @staticmethod
    def _looks_like_path_reference(raw_value: str) -> bool:
        raw = str(raw_value or "").strip()
        if not raw:
            return False

        if any(separator in raw for separator in ("/", "\\")):
            return True

        suffix = Path(raw).suffix.lower()
        return suffix in {".bin", ".onnx", ".json", ".exe", ".pt"}

    @staticmethod
    def _resolve_project_path(raw_path: str) -> Path:
        candidate = Path(str(raw_path or "").strip()).expanduser()
        if candidate.is_absolute():
            return candidate
        return BASE_DIR / candidate

    def _path_exists_if_explicit(self, raw_path: str) -> bool:
        candidate = self._resolve_project_path(raw_path)
        return candidate.exists()

    @staticmethod
    def _import_symbol(module_name: str, symbol_name: str):
        module = import_module(module_name)
        return getattr(module, symbol_name)

    @staticmethod
    def _log_backend_status(status: RuntimeBackendStatus) -> None:
        prefix = "Runtime backend ready" if status.ok and not status.fallback_used else "Runtime backend degraded"
        append_log(
            f"{prefix}: component={status.component}, backend={status.selected_backend}, "
            f"fallback={status.fallback_used}, detail={status.detail}"
        )