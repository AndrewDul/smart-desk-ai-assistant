from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RuntimeServices
from modules.shared.config.settings import load_settings

from .ai_broker_mixin import RuntimeBuilderAiBrokerMixin
from .audio_coordination_mixin import RuntimeBuilderAudioCoordinationMixin
from .display_mixin import RuntimeBuilderDisplayMixin
from .features_mixin import RuntimeBuilderFeaturesMixin
from .mobility_mixin import RuntimeBuilderMobilityMixin
from .pan_tilt_mixin import RuntimeBuilderPanTiltMixin
from .understanding_mixin import RuntimeBuilderUnderstandingMixin
from .utils_mixin import RuntimeBuilderUtilsMixin
from .vision_mixin import RuntimeBuilderVisionMixin
from .voice_engine_v2_mixin import RuntimeBuilderVoiceEngineV2Mixin
from .voice_input_mixin import RuntimeBuilderVoiceInputMixin
from .voice_output_mixin import RuntimeBuilderVoiceOutputMixin
from .wake_gate_mixin import RuntimeBuilderWakeGateMixin


class RuntimeBuilder(
    RuntimeBuilderUtilsMixin,
    RuntimeBuilderUnderstandingMixin,
    RuntimeBuilderFeaturesMixin,
    RuntimeBuilderAudioCoordinationMixin,
    RuntimeBuilderAiBrokerMixin,
    RuntimeBuilderVoiceEngineV2Mixin,
    RuntimeBuilderVoiceInputMixin,
    RuntimeBuilderWakeGateMixin,
    RuntimeBuilderVoiceOutputMixin,
    RuntimeBuilderDisplayMixin,
    RuntimeBuilderVisionMixin,
    RuntimeBuilderPanTiltMixin,
    RuntimeBuilderMobilityMixin,
):
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
        ai_broker_cfg = self._cfg("ai_broker")
        pan_tilt_cfg = self._cfg("pan_tilt")
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
        ai_broker, ai_broker_status = self._build_ai_broker(
            ai_broker_cfg,
            vision_backend=vision,
        )
        pan_tilt, pan_tilt_status = self._build_pan_tilt(pan_tilt_cfg)
        mobility, mobility_status = self._build_mobility(mobility_cfg)
        voice_engine_v2_bundle = self._build_voice_engine_v2()

        self._attach_audio_coordinator(voice_input, audio_coordinator)
        self._attach_audio_coordinator(wake_gate, audio_coordinator)
        self._attach_audio_coordinator(voice_output, audio_coordinator)

        backend_statuses = {
            "voice_input": voice_input_status,
            "wake_gate": wake_gate_status,
            "voice_output": voice_output_status,
            "display": display_status,
            "vision": vision_status,
            "ai_broker": ai_broker_status,
            "pan_tilt": pan_tilt_status,
            "mobility": mobility_status,
        }
        provider_inventory = {
            name: status.to_snapshot()
            for name, status in backend_statuses.items()
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
                "ai_broker": ai_broker,
                "pan_tilt_backend": pan_tilt,
                "mobility_backend": mobility,
                "voice_engine_v2": voice_engine_v2_bundle.engine,
                "voice_engine_v2_settings": voice_engine_v2_bundle.settings,
                "voice_engine_v2_status": voice_engine_v2_bundle.status,
                "voice_engine_v2_metadata": voice_engine_v2_bundle.to_metadata(),
                "wake_backend": wake_gate,
                "single_capture_mode": self._single_capture_mode_enabled(voice_input_cfg),
                "provider_inventory": provider_inventory,
            },
        )


__all__ = ["RuntimeBuilder"]