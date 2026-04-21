from __future__ import annotations

from modules.runtime.contracts import RuntimeBackendStatus, SpeechOutputBackend

from .fallbacks import SilentVoiceOutput


class RuntimeBuilderVoiceOutputMixin:
    """
    Build the voice output backend with explicit fallback handling.
    """

    def _build_voice_output(
        self,
        config: dict[str, object],
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
                process_poll_seconds=float(config.get("process_poll_seconds", 0.02) or 0.02),
                synthesis_poll_seconds=float(config.get("synthesis_poll_seconds", 0.005) or 0.005),
                playback_poll_seconds=float(config.get("playback_poll_seconds", 0.005) or 0.005),
                preferred_playback_backend=str(config.get("preferred_playback_backend", "") or ""),
                console_echo_enabled=bool(config.get("console_echo_enabled", False)),
                spoken_text_log_enabled=bool(config.get("spoken_text_log_enabled", False)),
                hot_path_success_log_enabled=bool(config.get("hot_path_success_log_enabled", False)),
                runtime_wav_directory=str(config.get("runtime_wav_directory", "") or ""),
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


__all__ = ["RuntimeBuilderVoiceOutputMixin"]