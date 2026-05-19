from __future__ import annotations

import os

from modules.runtime.contracts import RuntimeBackendStatus, SpeechInputBackend
from modules.shared.logging.logger import get_logger

LOGGER = get_logger(__name__)


def _strict_real_voice_input_required() -> bool:
    return str(os.environ.get("NEXA_REQUIRE_REAL_VOICE_INPUT", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "run",
    }


def _raise_if_strict_real_voice_input_required(detail: str) -> None:
    if _strict_real_voice_input_required():
        raise RuntimeError(
            "Real voice input is required for this runtime, but NeXa would fall back "
            f"to developer text input. {detail}"
        )


class RuntimeBuilderVoiceInputMixin:
    """
    Build the voice input backend with explicit fallback handling.
    """

    def _build_voice_input(
        self,
        config: dict[str, object],
    ) -> tuple[SpeechInputBackend, RuntimeBackendStatus]:
        text_input_class = self._import_symbol(
            "modules.devices.audio.input.text_input",
            "TextInput",
        )

        if not bool(config.get("enabled", True)):
            _raise_if_strict_real_voice_input_required(
                "voice_input.enabled is false in config."
            )
            backend = text_input_class()
            return (
                backend,
                RuntimeBackendStatus(
                    component="voice_input",
                    ok=True,
                    selected_backend="text_input",
                    requested_backend="disabled",
                    runtime_mode="developer_text_input",
                    capabilities=("text_input", "transcribe"),
                    detail="Voice input disabled in config. Using developer text input.",
                ),
            )

        engine = str(config.get("engine", "faster_whisper")).strip().lower()

        _asr_model_env = os.environ.get("NEXA_OPEN_QUESTION_ASR_MODEL", "").strip()
        _asr_beam_env = os.environ.get("NEXA_OPEN_QUESTION_ASR_BEAM_SIZE", "").strip()
        _asr_compute_env = os.environ.get("NEXA_OPEN_QUESTION_ASR_COMPUTE_TYPE", "").strip()

        _asr_model_override: str | None = _asr_model_env or None
        _asr_beam_override: int | None = None
        _asr_compute_override: str | None = _asr_compute_env or None

        _SLOW_MODELS = {"small", "medium", "large", "large-v1", "large-v2", "large-v3"}
        _allow_slow = os.environ.get("NEXA_ALLOW_SLOW_OPEN_QUESTION_ASR", "").strip().lower() in {
            "1", "true", "yes", "on"
        }
        if _asr_model_override and _asr_model_override.lower() in _SLOW_MODELS and not _allow_slow:
            LOGGER.warning(
                "[asr-override] rejected model=%r reason=slow_model_requires_explicit_opt_in"
                " (set NEXA_ALLOW_SLOW_OPEN_QUESTION_ASR=1 to allow)",
                _asr_model_override,
            )
            _asr_model_override = None

        if _asr_beam_env:
            try:
                _asr_beam_override = max(1, int(_asr_beam_env))
            except ValueError:
                LOGGER.warning(
                    "[asr-override] NEXA_OPEN_QUESTION_ASR_BEAM_SIZE=%r is not an integer; ignoring.",
                    _asr_beam_env,
                )

        if _asr_model_override or _asr_beam_override is not None or _asr_compute_override:
            LOGGER.info(
                "[asr-override] model=%r beam_size=%r compute_type=%r"
                " (env vars active; config/settings.json unchanged)",
                _asr_model_override or "(config)",
                _asr_beam_override if _asr_beam_override is not None else "(config)",
                _asr_compute_override or "(config)",
            )

        try:
            if engine in {"faster_whisper", "faster-whisper"}:
                backend_class = self._import_symbol(
                    "modules.devices.audio.input.faster_whisper.backend",
                    "FasterWhisperInputBackend",
                )
                backend = backend_class(
                    model_size_or_path=_asr_model_override or config.get(
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
                    transcription_timeout_seconds=config.get(
                        "transcription_timeout_seconds",
                        15.0,
                    ),
                    compute_type=_asr_compute_override or config.get("compute_type", "int8"),
                    cpu_threads=int(config.get("threads", 4)),
                    beam_size=int(
                        _asr_beam_override
                        if _asr_beam_override is not None
                        else config.get("beam_size", 1)
                    ),
                    best_of=int(config.get("best_of", 1)),
                    vad_enabled=bool(config.get("vad_enabled", True)),
                    vad_threshold=float(config.get("vad_threshold", 0.30)),
                    vad_min_speech_ms=int(config.get("vad_min_speech_ms", 120)),
                    vad_min_silence_ms=int(config.get("vad_min_silence_ms", 250)),
                    vad_speech_pad_ms=int(config.get("vad_speech_pad_ms", 180)),
                    capture_profiles=config.get("capture_profiles"),
                    device_discovery_timeout_seconds=float(
                        config.get("device_discovery_timeout_seconds", 8.0)
                    ),
                    device_discovery_poll_seconds=float(
                        config.get("device_discovery_poll_seconds", 0.35)
                    ),
                )
                return (
                    backend,
                    RuntimeBackendStatus(
                        component="voice_input",
                        ok=True,
                        selected_backend="faster_whisper",
                        requested_backend="faster_whisper",
                        runtime_mode="speech_to_text",
                        capabilities=("listen", "listen_once", "listen_for_command", "listen_for_wake_phrase", "transcribe"),
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
                        config.get(
                            "vad_model_path",
                            "models/whisper/ggml-silero-v6.2.0.bin",
                        ),
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
                    transcription_timeout_seconds=config.get(
                        "transcription_timeout_seconds",
                        15.0,
                    ),
                    cpu_threads=int(config.get("threads", 4)),
                    device_discovery_timeout_seconds=float(
                        config.get("device_discovery_timeout_seconds", 8.0)
                    ),
                    device_discovery_poll_seconds=float(
                        config.get("device_discovery_poll_seconds", 0.35)
                    ),
                )
                return (
                    backend,
                    RuntimeBackendStatus(
                        component="voice_input",
                        ok=True,
                        selected_backend="whisper_cpp",
                        requested_backend="whisper_cpp",
                        runtime_mode="speech_to_text",
                        capabilities=("listen", "listen_once", "listen_for_command", "transcribe"),
                        detail="whisper.cpp voice input loaded successfully.",
                    ),
                )

            _raise_if_strict_real_voice_input_required(
                f"Unsupported voice input engine '{engine}'."
            )
            backend = text_input_class()
            return (
                backend,
                RuntimeBackendStatus(
                    component="voice_input",
                    ok=False,
                    selected_backend="text_input",
                    requested_backend=engine,
                    runtime_mode="developer_text_input",
                    capabilities=("text_input", "transcribe"),
                    detail=f"Unsupported voice input engine '{engine}'. Using text input instead.",
                    fallback_used=True,
                ),
            )

        except Exception as error:
            LOGGER.exception(
                "Voice input backend build failed: engine=%s, device_index=%s, device_name_contains=%s, sample_rate=%s",
                engine,
                config.get("device_index"),
                config.get("device_name_contains"),
                config.get("sample_rate"),
            )
            _raise_if_strict_real_voice_input_required(
                f"Voice input backend '{engine}' failed with {type(error).__name__}: {error}. "
                f"Config: device_index={config.get('device_index')}, "
                f"device_name_contains={config.get('device_name_contains')}, "
                f"sample_rate={config.get('sample_rate')}"
            )
            backend = text_input_class()
            return (
                backend,
                RuntimeBackendStatus(
                    component="voice_input",
                    ok=False,
                    selected_backend="text_input",
                    requested_backend=engine,
                    runtime_mode="developer_text_input",
                    capabilities=("text_input", "transcribe"),
                    detail=(
                        f"Voice input backend '{engine}' failed. "
                        f"Falling back to text input. Error: {type(error).__name__}: {error}. "
                        f"Config: device_index={config.get('device_index')}, "
                        f"device_name_contains={config.get('device_name_contains')}, "
                        f"sample_rate={config.get('sample_rate')}"
                    ),
                    fallback_used=True,
                ),
            )


__all__ = ["RuntimeBuilderVoiceInputMixin"]