from __future__ import annotations

from modules.runtime.contracts import RuntimeBackendStatus, SpeechInputBackend


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
                    transcription_timeout_seconds=config.get(
                        "transcription_timeout_seconds",
                        15.0,
                    ),
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


__all__ = ["RuntimeBuilderVoiceInputMixin"]