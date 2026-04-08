from __future__ import annotations

from importlib import import_module
import re
from typing import Any

from modules.runtime.contracts import (
    DisplayBackend,
    RuntimeBackendStatus,
    RuntimeServices,
    SpeechInputBackend,
    SpeechOutputBackend,
    WakeGateBackend,
)
from modules.shared.config.settings import load_settings
from modules.shared.logging.logger import get_logger

LOGGER = get_logger(__name__)


class SilentVoiceOutput:
    """
    Safe no-audio fallback.

    This backend reports success so the higher presentation layer can keep
    running normally even when TTS is disabled or unavailable.
    """

    def __init__(self) -> None:
        self.audio_coordinator = None
        self.messages: list[dict[str, Any]] = []

    def set_audio_coordinator(self, audio_coordinator: Any | None) -> None:
        self.audio_coordinator = audio_coordinator

    def speak(
        self,
        text: str,
        language: str | None = None,
        prepare_next: tuple[str, str] | None = None,
    ) -> bool:
        del prepare_next
        self.messages.append(
            {
                "text": str(text),
                "language": language,
            }
        )
        return True

    def prepare_speech(self, text: str, language: str | None = None) -> None:
        self.messages.append(
            {
                "prefetch_text": str(text),
                "language": language,
            }
        )

    def stop_playback(self) -> None:
        return None

    def clear_stop_request(self) -> None:
        return None


class NullDisplay:
    """
    Safe display fallback used when the physical display is disabled or fails.
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

    def show_status(
        self,
        state: dict[str, Any],
        timer_status: dict[str, Any],
        duration: float = 10.0,
    ) -> None:
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
        return None

    def close(self) -> None:
        self.closed = True


class NullWakeGate:
    """
    No-op wake gate used only when wake-word listening is intentionally disabled.
    """

    def __init__(self) -> None:
        self.audio_coordinator = None

    def set_audio_coordinator(self, audio_coordinator: Any | None) -> None:
        self.audio_coordinator = audio_coordinator

    def listen_for_wake_phrase(
        self,
        timeout: float = 2.0,
        debug: bool = False,
        ignore_audio_block: bool = False,
    ) -> str | None:
        del timeout, debug, ignore_audio_block
        return None

    def close(self) -> None:
        return None


class CompatibilityWakeGate:
    """
    Wake compatibility layer that reuses the main voice input backend.

    This is the stable single-capture mode:
    - there is only one input owner
    - standby wake and active command capture both flow through voice_input
    - dedicated openWakeWord is not required to keep the runtime usable
    """

    _WAKE_ALIASES = (
        "nexa",
        "nexta",
        "neksa",
        "nexaah",
        "nex",
    )

    def __init__(self, voice_input: SpeechInputBackend) -> None:
        self.voice_input = voice_input
        self.audio_coordinator = None

    def set_audio_coordinator(self, audio_coordinator: Any | None) -> None:
        self.audio_coordinator = audio_coordinator
        setter = getattr(self.voice_input, "set_audio_coordinator", None)
        if callable(setter):
            try:
                setter(audio_coordinator)
            except Exception:
                pass

    def listen_for_wake_phrase(
        self,
        timeout: float = 2.0,
        debug: bool = False,
        ignore_audio_block: bool = False,
    ) -> str | None:
        del ignore_audio_block

        heard_text: str | None = None
        for method_name in ("listen_for_wake_phrase", "listen", "listen_once", "listen_for_command"):
            method = getattr(self.voice_input, method_name, None)
            if not callable(method):
                continue
            try:
                heard_text = method(timeout=timeout, debug=debug)
            except TypeError:
                heard_text = method(timeout=timeout)
            break

        if heard_text is None:
            return None

        normalized = self._normalize_text(heard_text)
        if not normalized:
            return None

        tokens = [token for token in normalized.split()[:4] if token]
        if any(token in self._WAKE_ALIASES or token.startswith("nex") for token in tokens):
            return "nexa"

        compact = normalized.replace(" ", "")
        if compact.startswith("nex") and len(compact) <= 12:
            return "nexa"

        return None

    def close(self) -> None:
        return None

    @staticmethod
    def _normalize_text(text: str) -> str:
        value = str(text or "").strip().lower()
        value = re.sub(r"[^a-z0-9\s]", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        return value


class NullVisionBackend:
    """
    Placeholder backend until the camera stack is fully enabled.
    """

    def latest_observation(self) -> Any:
        return None

    def close(self) -> None:
        return None


class NullMobilityBackend:
    """
    Placeholder backend until the mobile base stack is fully enabled.
    """

    def stop(self) -> None:
        return None

    def close(self) -> None:
        return None


class RuntimeBuilder:
    """
    Final composition root for the premium NeXa runtime.

    Responsibilities:
    - assemble the new architecture only
    - keep backend degradation isolated and explicit
    - wire the half-duplex audio coordinator across input/output/wake
    - prefer stable single-capture ownership for microphone access
    - return one clean runtime container for the assistant layer
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
        parser = self._build_parser()
        router = self._build_router(parser)
        dialogue = self._build_dialogue()

        memory = self._build_memory()
        reminders = self._build_reminders()
        timer = self._build_timer(
            on_timer_started=on_timer_started,
            on_timer_finished=on_timer_finished,
            on_timer_stopped=on_timer_stopped,
        )

        audio_coordinator = self._build_audio_coordinator()

        voice_input_cfg = self._cfg("voice_input")
        voice_output_cfg = self._cfg("voice_output")
        display_cfg = self._cfg("display")
        vision_cfg = self._cfg("vision")
        mobility_cfg = self._cfg("mobility")

        voice_input, voice_input_status = self._build_voice_input(voice_input_cfg)
        wake_gate, wake_gate_status = self._build_wake_gate(
            voice_input_cfg,
            voice_input=voice_input,
            voice_input_status=voice_input_status,
        )
        voice_output, voice_output_status = self._build_voice_output(voice_output_cfg)
        display, display_status = self._build_display(display_cfg)
        vision, vision_status = self._build_vision(vision_cfg)
        mobility, mobility_status = self._build_mobility(mobility_cfg)

        self._attach_audio_coordinator(voice_input, audio_coordinator)
        self._attach_audio_coordinator(wake_gate, audio_coordinator)
        self._attach_audio_coordinator(voice_output, audio_coordinator)

        backend_statuses = {
            "voice_input": voice_input_status,
            "wake_gate": wake_gate_status,
            "voice_output": voice_output_status,
            "display": display_status,
            "vision": vision_status,
            "mobility": mobility_status,
        }

        for status in backend_statuses.values():
            self._log_backend_status(status)

        return RuntimeServices(
            settings=self.settings,
            voice_input=voice_input,
            voice_output=voice_output,
            display=display,
            wake_gate=wake_gate,
            parser=parser,
            router=router,
            dialogue=dialogue,
            memory=memory,
            reminders=reminders,
            timer=timer,
            backend_statuses=backend_statuses,
            metadata={
                "audio_coordinator": audio_coordinator,
                "vision_backend": vision,
                "mobility_backend": mobility,
                "wake_backend": wake_gate,
                "single_capture_mode": self._single_capture_mode_enabled(voice_input_cfg),
            },
        )

    # ------------------------------------------------------------------
    # Understanding
    # ------------------------------------------------------------------

    def _build_parser(self) -> Any:
        parser_class = self._import_symbol(
            "modules.understanding.parsing.parser",
            "IntentParser",
        )
        timers_cfg = self._cfg("timers")

        return parser_class(
            default_focus_minutes=float(timers_cfg.get("default_focus_minutes", 25)),
            default_break_minutes=float(timers_cfg.get("default_break_minutes", 5)),
        )

    def _build_router(self, parser: Any) -> Any:
        router_class = self._import_symbol(
            "modules.understanding.routing.companion_router",
            "SemanticCompanionRouter",
        )
        return router_class(parser)

    def _build_dialogue(self) -> Any:
        dialogue_class = self._import_symbol(
            "modules.understanding.dialogue.companion_dialogue",
            "CompanionDialogueService",
        )
        return dialogue_class()

    # ------------------------------------------------------------------
    # Features
    # ------------------------------------------------------------------

    def _build_memory(self) -> Any:
        memory_class = self._import_symbol(
            "modules.features.memory.service",
            "MemoryService",
        )
        return memory_class()

    def _build_reminders(self) -> Any:
        reminders_class = self._import_symbol(
            "modules.features.reminders.service",
            "ReminderService",
        )
        return reminders_class()

    def _build_timer(
        self,
        *,
        on_timer_started=None,
        on_timer_finished=None,
        on_timer_stopped=None,
    ) -> Any:
        timer_class = self._import_symbol(
            "modules.features.timer.service",
            "TimerService",
        )
        return timer_class(
            on_started=on_timer_started,
            on_finished=on_timer_finished,
            on_stopped=on_timer_stopped,
        )

    # ------------------------------------------------------------------
    # Audio coordination
    # ------------------------------------------------------------------

    def _build_audio_coordinator(self) -> Any:
        coordinator_class = self._import_symbol(
            "modules.devices.audio.coordination",
            "AudioCoordinator",
        )
        coordination_cfg = self._cfg("audio_coordination")
        legacy_audio_cfg = self._cfg("audio")

        post_speech_hold_seconds = self._cfg_float(
            coordination_cfg,
            ("self_hearing_hold_seconds", "post_speech_hold_seconds"),
            fallback=float(legacy_audio_cfg.get("post_speech_hold_seconds", 0.72)),
        )
        input_poll_interval_seconds = self._cfg_float(
            coordination_cfg,
            ("listen_resume_poll_seconds", "input_poll_interval_seconds"),
            fallback=float(legacy_audio_cfg.get("input_poll_interval_seconds", 0.05)),
        )

        return coordinator_class(
            post_speech_hold_seconds=post_speech_hold_seconds,
            input_poll_interval_seconds=input_poll_interval_seconds,
        )

    def _attach_audio_coordinator(
        self,
        component: Any | None,
        audio_coordinator: Any,
    ) -> None:
        if component is None:
            return

        setter = getattr(component, "set_audio_coordinator", None)
        if callable(setter):
            setter(audio_coordinator)
            return

        if hasattr(component, "audio_coordinator"):
            try:
                setattr(component, "audio_coordinator", audio_coordinator)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Devices: voice input
    # ------------------------------------------------------------------

    def _build_voice_input(
        self,
        config: dict[str, Any],
    ) -> tuple[SpeechInputBackend, RuntimeBackendStatus]:
        text_input_class = self._import_symbol(
            "modules.devices.audio.input.text_input",
            "TextInput",
        )

        if not bool(config.get("enabled", True)):
            backend = text_input_class()
            return (
                backend,
                RuntimeBackendStatus(
                    component="voice_input",
                    ok=True,
                    selected_backend="text_input",
                    detail="Voice input disabled in config. Using developer text input.",
                ),
            )

        engine = str(config.get("engine", "faster_whisper")).strip().lower()

        try:
            if engine in {"faster_whisper", "faster-whisper"}:
                backend_class = self._import_symbol(
                    "modules.devices.audio.input.faster_whisper.backend",
                    "FasterWhisperInputBackend",
                )
                backend = backend_class(
                    model_size_or_path=config.get(
                        "model_size_or_path",
                        config.get("model_path", "small"),
                    ),
                    language=config.get("language", "auto"),
                    device_index=config.get("device_index"),
                    device_name_contains=config.get("device_name_contains"),
                    sample_rate=config.get("sample_rate", 16000),
                    max_record_seconds=config.get("max_record_seconds", 8.0),
                    end_silence_seconds=config.get("end_silence_seconds", 0.65),
                    pre_roll_seconds=config.get("pre_roll_seconds", 0.45),
                    blocksize=config.get("blocksize", 512),
                    min_speech_seconds=config.get("min_speech_seconds", 0.20),
                    transcription_timeout_seconds=config.get("transcription_timeout_seconds", 15.0),
                    compute_type=config.get("compute_type", "int8"),
                    cpu_threads=int(config.get("threads", 4)),
                    beam_size=int(config.get("beam_size", 1)),
                    best_of=int(config.get("best_of", 1)),
                    vad_enabled=bool(config.get("vad_enabled", True)),
                    vad_threshold=float(config.get("vad_threshold", 0.30)),
                    vad_min_speech_ms=int(config.get("vad_min_speech_ms", 120)),
                    vad_min_silence_ms=int(config.get("vad_min_silence_ms", 250)),
                    vad_speech_pad_ms=int(config.get("vad_speech_pad_ms", 180)),
                )
                return (
                    backend,
                    RuntimeBackendStatus(
                        component="voice_input",
                        ok=True,
                        selected_backend="faster_whisper",
                        detail="Faster-Whisper voice input loaded successfully.",
                    ),
                )

            if engine in {"whisper_cpp", "whisper.cpp", "whisper"}:
                backend_class = self._import_symbol(
                    "modules.devices.audio.input.whisper_cpp.backend",
                    "WhisperCppInputBackend",
                )
                backend = backend_class(
                    whisper_cli_path=config.get(
                        "whisper_cli_path",
                        "third_party/whisper.cpp/build/bin/whisper-cli",
                    ),
                    model_path=config.get(
                        "whisper_model_path",
                        config.get("model_path", "models/whisper/ggml-base.bin"),
                    ),
                    vad_enabled=bool(config.get("vad_enabled", True)),
                    vad_model_path=config.get(
                        "whisper_vad_model_path",
                        config.get("vad_model_path", "models/whisper/ggml-silero-v6.2.0.bin"),
                    ),
                    language=config.get("language", "auto"),
                    device_index=config.get("device_index"),
                    device_name_contains=config.get("device_name_contains"),
                    sample_rate=config.get("sample_rate", 16000),
                    max_record_seconds=config.get("max_record_seconds", 8.0),
                    end_silence_seconds=config.get("end_silence_seconds", 0.65),
                    pre_roll_seconds=config.get("pre_roll_seconds", 0.45),
                    blocksize=config.get("blocksize", 512),
                    min_speech_seconds=config.get("min_speech_seconds", 0.20),
                    transcription_timeout_seconds=config.get("transcription_timeout_seconds", 15.0),
                    cpu_threads=int(config.get("threads", 4)),
                )
                return (
                    backend,
                    RuntimeBackendStatus(
                        component="voice_input",
                        ok=True,
                        selected_backend="whisper_cpp",
                        detail="whisper.cpp voice input loaded successfully.",
                    ),
                )

            backend = text_input_class()
            return (
                backend,
                RuntimeBackendStatus(
                    component="voice_input",
                    ok=False,
                    selected_backend="text_input",
                    detail=f"Unsupported voice input engine '{engine}'. Using text input instead.",
                    fallback_used=True,
                ),
            )

        except Exception as error:
            backend = text_input_class()
            return (
                backend,
                RuntimeBackendStatus(
                    component="voice_input",
                    ok=False,
                    selected_backend="text_input",
                    detail=(
                        f"Voice input backend '{engine}' failed. "
                        f"Falling back to text input. Error: {error}"
                    ),
                    fallback_used=True,
                ),
            )

    def _build_wake_gate(
        self,
        config: dict[str, Any],
        *,
        voice_input: SpeechInputBackend,
        voice_input_status: RuntimeBackendStatus,
    ) -> tuple[WakeGateBackend | None, RuntimeBackendStatus]:
        if hasattr(voice_input, "listen_for_wake_phrase"):
            class_name = voice_input.__class__.__name__.lower()
            if "textinput" in class_name:
                return (
                    voice_input,  # type: ignore[return-value]
                    RuntimeBackendStatus(
                        component="wake_gate",
                        ok=True,
                        selected_backend="text_input",
                        detail="Wake gate handled by text input backend.",
                    ),
                )

        if not bool(config.get("enabled", True)):
            return (
                NullWakeGate(),
                RuntimeBackendStatus(
                    component="wake_gate",
                    ok=True,
                    selected_backend="disabled",
                    detail="Wake gate disabled because voice input is disabled.",
                ),
            )

        engine = str(config.get("wake_engine", "openwakeword")).strip().lower()
        if engine in {"off", "none", "disabled"}:
            return (
                NullWakeGate(),
                RuntimeBackendStatus(
                    component="wake_gate",
                    ok=True,
                    selected_backend="disabled",
                    detail="Wake gate disabled in config.",
                ),
            )

        single_capture_mode = self._single_capture_mode_enabled(config)
        if single_capture_mode and bool(voice_input_status.ok):
            compatibility_gate = CompatibilityWakeGate(voice_input)
            return (
                compatibility_gate,
                RuntimeBackendStatus(
                    component="wake_gate",
                    ok=True,
                    selected_backend="compatibility_voice_input",
                    detail="Wake gate reuses the main voice input backend in single-capture mode.",
                ),
            )

        try:
            if engine == "openwakeword":
                backend_class = self._import_symbol(
                    "modules.devices.audio.input.wake.openwakeword_gate",
                    "OpenWakeWordGate",
                )
                backend = backend_class(
                    model_path=config.get("wake_model_path", "models/wake/nexa.onnx"),
                    device_index=config.get("device_index"),
                    device_name_contains=config.get("device_name_contains"),
                    threshold=float(config.get("wake_threshold", 0.50)),
                    trigger_level=int(config.get("wake_trigger_level", 2)),
                    block_ms=int(config.get("wake_block_ms", 80)),
                    vad_threshold=float(config.get("wake_vad_threshold", 0.0)),
                    enable_speex_noise_suppression=bool(
                        config.get("wake_enable_speex_noise_suppression", False)
                    ),
                    activation_cooldown_seconds=float(config.get("wake_activation_cooldown_seconds", 1.25)),
                    block_release_settle_seconds=float(config.get("wake_block_release_settle_seconds", 0.18)),
                    energy_rms_threshold=float(config.get("wake_energy_rms_threshold", 0.0085)),
                    score_smoothing_window=int(config.get("wake_score_smoothing_window", 3)),
                    debug=bool(config.get("wake_debug", False)),
                )
                return (
                    backend,
                    RuntimeBackendStatus(
                        component="wake_gate",
                        ok=True,
                        selected_backend="openwakeword",
                        detail="OpenWakeWord wake gate loaded successfully.",
                    ),
                )

            compatibility_gate = CompatibilityWakeGate(voice_input)
            return (
                compatibility_gate,
                RuntimeBackendStatus(
                    component="wake_gate",
                    ok=True,
                    selected_backend="compatibility_voice_input",
                    detail=(
                        f"Unsupported wake engine '{engine}'. "
                        "Using compatibility wake through the main voice input backend."
                    ),
                    fallback_used=True,
                ),
            )

        except Exception as error:
            if bool(voice_input_status.ok):
                compatibility_gate = CompatibilityWakeGate(voice_input)
                return (
                    compatibility_gate,
                    RuntimeBackendStatus(
                        component="wake_gate",
                        ok=True,
                        selected_backend="compatibility_voice_input",
                        detail=(
                            f"Wake gate backend '{engine}' failed. "
                            "Using compatibility wake through the main voice input backend. "
                            f"Error: {error}"
                        ),
                        fallback_used=True,
                    ),
                )

            return (
                NullWakeGate(),
                RuntimeBackendStatus(
                    component="wake_gate",
                    ok=False,
                    selected_backend="disabled",
                    detail=(
                        f"Wake gate backend '{engine}' failed and voice input is unavailable. "
                        f"Error: {error}"
                    ),
                    fallback_used=True,
                ),
            )

    # ------------------------------------------------------------------
    # Devices: voice output
    # ------------------------------------------------------------------

    def _build_voice_output(
        self,
        config: dict[str, Any],
    ) -> tuple[SpeechOutputBackend, RuntimeBackendStatus]:
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
            backend_class = self._import_symbol(
                "modules.devices.audio.output.tts_pipeline",
                "TTSPipeline",
            )
            backend = backend_class(
                enabled=bool(config.get("enabled", True)),
                preferred_engine=str(config.get("engine", "piper")),
                default_language=str(config.get("default_language", "en")),
                speed=int(config.get("speed", 155)),
                pitch=int(config.get("pitch", 58)),
                voices=config.get("voices"),
                piper_models=config.get("piper_models"),
            )
            return (
                backend,
                RuntimeBackendStatus(
                    component="voice_output",
                    ok=True,
                    selected_backend=str(config.get("engine", "piper")),
                    detail="Voice output backend loaded successfully.",
                ),
            )
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

    # ------------------------------------------------------------------
    # Devices: display
    # ------------------------------------------------------------------

    def _build_display(
        self,
        config: dict[str, Any],
    ) -> tuple[DisplayBackend, RuntimeBackendStatus]:
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
            display_class = self._import_symbol(
                "modules.devices.display.display_service",
                "DisplayService",
            )
            backend = display_class(
                driver=str(config.get("driver", "ssd1306")),
                interface=str(config.get("interface", "i2c")),
                port=int(config.get("port", 1)),
                address=int(config.get("address", 0x3C)),
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

    # ------------------------------------------------------------------
    # Devices: vision / mobility
    # ------------------------------------------------------------------

    def _build_vision(self, config: dict[str, Any]) -> tuple[Any, RuntimeBackendStatus]:
        if not bool(config.get("enabled", False)):
            return (
                NullVisionBackend(),
                RuntimeBackendStatus(
                    component="vision",
                    ok=True,
                    selected_backend="null_vision",
                    detail="Vision disabled in config.",
                ),
            )

        try:
            backend_class = self._import_symbol(
                "modules.devices.vision.camera_service",
                "CameraService",
            )
            backend = backend_class(config=config)
            return (
                backend,
                RuntimeBackendStatus(
                    component="vision",
                    ok=True,
                    selected_backend="camera_service",
                    detail="Vision backend loaded successfully.",
                ),
            )
        except Exception as error:
            return (
                NullVisionBackend(),
                RuntimeBackendStatus(
                    component="vision",
                    ok=False,
                    selected_backend="null_vision",
                    detail=f"Vision backend failed. Using null vision. Error: {error}",
                    fallback_used=True,
                ),
            )

    def _build_mobility(self, config: dict[str, Any]) -> tuple[Any, RuntimeBackendStatus]:
        if not bool(config.get("enabled", False)):
            return (
                NullMobilityBackend(),
                RuntimeBackendStatus(
                    component="mobility",
                    ok=True,
                    selected_backend="null_mobility",
                    detail="Mobility disabled in config.",
                ),
            )

        try:
            backend_class = self._import_symbol(
                "modules.devices.mobility.base_controller",
                "BaseController",
            )
            backend = backend_class(config=config)
            return (
                backend,
                RuntimeBackendStatus(
                    component="mobility",
                    ok=True,
                    selected_backend=str(config.get("base_type", "base_controller")),
                    detail="Mobility backend loaded successfully.",
                ),
            )
        except Exception as error:
            return (
                NullMobilityBackend(),
                RuntimeBackendStatus(
                    component="mobility",
                    ok=False,
                    selected_backend="null_mobility",
                    detail=f"Mobility backend failed. Using null mobility. Error: {error}",
                    fallback_used=True,
                ),
            )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

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
    def _import_symbol(module_name: str, symbol_name: str):
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


__all__ = [
    "CompatibilityWakeGate",
    "NullDisplay",
    "NullMobilityBackend",
    "NullVisionBackend",
    "NullWakeGate",
    "RuntimeBuilder",
    "SilentVoiceOutput",
]