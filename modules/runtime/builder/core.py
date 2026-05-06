from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RuntimeServices
from modules.runtime.voice_engine_v2.faster_whisper_audio_bus_tap import (
    configure_faster_whisper_audio_bus_shadow_tap,
)
from modules.runtime.voice_engine_v2.vad_shadow import (
    build_voice_engine_v2_vad_shadow_observer,
)
from modules.runtime.voice_engine_v2.vad_timing_bridge import (
    build_voice_engine_v2_vad_timing_bridge_adapter,
)
from modules.runtime.voice_engine_v2.vosk_pre_whisper_candidate import (
    build_voice_engine_v2_vosk_pre_whisper_candidate_adapter,
)
from modules.shared.config.settings import load_settings

from .ai_broker_mixin import RuntimeBuilderAiBrokerMixin
from .audio_coordination_mixin import RuntimeBuilderAudioCoordinationMixin
from .display_mixin import RuntimeBuilderDisplayMixin
from .features_mixin import RuntimeBuilderFeaturesMixin
from .mobility_mixin import RuntimeBuilderMobilityMixin
from .pan_tilt_mixin import RuntimeBuilderPanTiltMixin
from .look_at_me_mixin import RuntimeBuilderLookAtMeMixin  # NEXA_LOOK_AT_ME_CORE_IMPORT
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
    RuntimeBuilderLookAtMeMixin,  # NEXA_LOOK_AT_ME_CORE_MIXIN
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
        on_timer_tick=None,
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
            on_timer_tick=on_timer_tick,
        )

        audio_coordinator = self._build_audio_coordinator()

        voice_input_cfg = self._cfg("voice_input")
        voice_output_cfg = self._cfg("voice_output")
        display_cfg = self._cfg("display")
        vision_cfg = self._cfg("vision")
        ai_broker_cfg = self._cfg("ai_broker")
        pan_tilt_cfg = self._cfg("pan_tilt")
        vision_tracking_cfg = self._cfg("vision_tracking")
        focus_vision_cfg = self._cfg("focus_vision")
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
        focus_vision, focus_vision_status = self._build_focus_vision(
            focus_vision_cfg,
            vision_backend=vision,
        )
        ai_broker, ai_broker_status = self._build_ai_broker(
            ai_broker_cfg,
            vision_backend=vision,
        )
        pan_tilt, pan_tilt_status = self._build_pan_tilt(pan_tilt_cfg)
        vision_tracking, vision_tracking_status = self._build_vision_tracking(
            vision_tracking_cfg,
            vision_backend=vision,
            pan_tilt_backend=pan_tilt,
        )
        mobility, mobility_status = self._build_mobility(mobility_cfg)
        # NEXA_LOOK_AT_ME_CORE_BUILD
        look_at_me_session, look_at_me_status = self._build_look_at_me_session(
            vision_backend=vision,
            pan_tilt_backend=pan_tilt,
            vision_tracking_service=vision_tracking,
        )
        voice_engine_v2_bundle = self._build_voice_engine_v2()
        vosk_pre_whisper_candidate_adapter = (
            build_voice_engine_v2_vosk_pre_whisper_candidate_adapter(
                settings=self.settings,
                runtime_candidate_adapter=voice_engine_v2_bundle.runtime_candidate_adapter,
            )
        )
        vad_shadow_observer = build_voice_engine_v2_vad_shadow_observer(
            self.settings
        )
        vad_timing_bridge_adapter = build_voice_engine_v2_vad_timing_bridge_adapter(
            self.settings
        )

        realtime_audio_bus, audio_bus_tap_status = (
            configure_faster_whisper_audio_bus_shadow_tap(
                voice_input=voice_input,
                settings=self.settings,
                capture_window_observer=getattr(
                    vad_timing_bridge_adapter,
                    "observe_after_capture_window_publish",
                    None,
                ),
            )
        )

        attach_pre_whisper_candidate = getattr(
            voice_input,
            "set_voice_engine_v2_vosk_pre_whisper_candidate_adapter",
            None,
        )
        if callable(attach_pre_whisper_candidate):
            attach_pre_whisper_candidate(vosk_pre_whisper_candidate_adapter)
        else:
            try:
                setattr(
                    voice_input,
                    "voice_engine_v2_vosk_pre_whisper_candidate_adapter",
                    vosk_pre_whisper_candidate_adapter,
                )
            except Exception:
                pass

        self._attach_audio_coordinator(voice_input, audio_coordinator)
        self._attach_audio_coordinator(wake_gate, audio_coordinator)
        self._attach_audio_coordinator(voice_output, audio_coordinator)

        backend_statuses = {
            "voice_input": voice_input_status,
            "wake_gate": wake_gate_status,
            "voice_output": voice_output_status,
            "display": display_status,
            "vision": vision_status,
            "focus_vision": focus_vision_status,
            "ai_broker": ai_broker_status,
            "pan_tilt": pan_tilt_status,
            "vision_tracking": vision_tracking_status,
            "mobility": mobility_status,
            "look_at_me": look_at_me_status,  # NEXA_LOOK_AT_ME_CORE_STATUS
        }
        provider_inventory = {
            name: status.to_snapshot()
            for name, status in backend_statuses.items()
        }

        for status in backend_statuses.values():
            self._log_backend_status(status)

        metadata = {
            "audio_coordinator": audio_coordinator,
            "vision_backend": vision,
            "focus_vision_sentinel_service": focus_vision,
            "focus_vision_status": focus_vision_status.to_snapshot(),
            "ai_broker": ai_broker,
            "pan_tilt_backend": pan_tilt,
            "vision_tracking_service": vision_tracking,
            "vision_tracking_status": vision_tracking_status.to_snapshot(),
            "mobility_backend": mobility,
            "look_at_me_session": look_at_me_session,  # NEXA_LOOK_AT_ME_CORE_METADATA
            "voice_engine_v2": voice_engine_v2_bundle.engine,
            "voice_engine_v2_settings": voice_engine_v2_bundle.settings,
            "voice_engine_v2_status": voice_engine_v2_bundle.status,
            "voice_engine_v2_metadata": voice_engine_v2_bundle.to_metadata(),
            "voice_engine_v2_acceptance_adapter": (
                voice_engine_v2_bundle.acceptance_adapter
            ),
            "voice_engine_v2_runtime_candidate_adapter": (
                voice_engine_v2_bundle.runtime_candidate_adapter
            ),
            "voice_engine_v2_vosk_pre_whisper_candidate_adapter": (
                vosk_pre_whisper_candidate_adapter
            ),
            "voice_engine_v2_pre_stt_shadow_adapter": (
                voice_engine_v2_bundle.pre_stt_shadow_adapter
            ),
            "voice_engine_v2_shadow_mode_adapter": (
                voice_engine_v2_bundle.shadow_mode_adapter
            ),
            "voice_engine_v2_shadow_runtime_hook": (
                voice_engine_v2_bundle.shadow_runtime_hook
            ),
            "voice_engine_v2_audio_bus_tap_status": (
                audio_bus_tap_status.to_metadata()
            ),
            "voice_engine_v2_vad_shadow_observer": vad_shadow_observer,
            "voice_engine_v2_vad_timing_bridge_adapter": vad_timing_bridge_adapter,
            "wake_backend": wake_gate,
            "single_capture_mode": self._single_capture_mode_enabled(voice_input_cfg),
            "provider_inventory": provider_inventory,
        }

        if realtime_audio_bus is not None:
            metadata["realtime_audio_bus"] = realtime_audio_bus

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
            metadata=metadata,
        )


__all__ = ["RuntimeBuilder"]