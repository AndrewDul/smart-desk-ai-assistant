from __future__ import annotations

from typing import Any


class RuntimeBuilderAudioCoordinationMixin:
    """
    Build and attach the shared audio coordination layer.
    """

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


__all__ = ["RuntimeBuilderAudioCoordinationMixin"]