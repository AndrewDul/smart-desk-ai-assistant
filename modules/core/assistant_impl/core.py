from __future__ import annotations

import threading
from typing import Any

from modules.runtime.telemetry import TurnBenchmarkService
from modules.core.flows.action_flow import ActionFlowOrchestrator
from modules.core.flows.command_flow import CommandFlowOrchestrator
from modules.core.flows.dialogue_flow import DialogueFlowOrchestrator
from modules.core.flows.notification_flow import NotificationFlowOrchestrator
from modules.core.flows.pending_flow import PendingFlowOrchestrator
from modules.core.session.fast_command_lane import FastCommandLane
from modules.core.session.visual_shell_command_lane import VisualShellCommandLane
from modules.core.session.interrupt_controller import InteractionInterruptController
from modules.core.session.voice_session import VoiceSessionController

from modules.presentation.developer_overlay import DeveloperOverlayService
from modules.presentation.response_streamer import ResponseStreamer
from modules.presentation.runtime_debug_snapshot import RuntimeDebugSnapshotService
from modules.presentation.thinking_ack import ThinkingAckService
from modules.presentation.wake_ack import WakeAcknowledgementService

from modules.runtime.audio_runtime_snapshot import AudioRuntimeSnapshotService
from modules.runtime.builder import RuntimeBuilder
from modules.runtime.contracts import StreamMode
from modules.runtime.product import RuntimeProductService
from modules.runtime.stt import SpeechRecognitionService
from modules.shared.config.settings import load_settings
from modules.shared.persistence.repositories import (
    SessionStateRepository,
    UserProfileRepository,
)

from .ai_broker_mixin import CoreAssistantAiBrokerMixin
from .helpers_mixin import CoreAssistantHelpersMixin
from .interaction_mixin import CoreAssistantInteractionMixin
from .lifecycle_mixin import CoreAssistantLifecycleMixin
from .memory_background_mixin import CoreAssistantMemoryBackgroundMixin
from .persistence_mixin import CoreAssistantPersistenceMixin
from .response_mixin import CoreAssistantResponseMixin
from .routing_mixin import CoreAssistantRoutingMixin


class CoreAssistant(
    CoreAssistantPersistenceMixin,
    CoreAssistantHelpersMixin,
    CoreAssistantMemoryBackgroundMixin,
    CoreAssistantRoutingMixin,
    CoreAssistantResponseMixin,
    CoreAssistantAiBrokerMixin,
    CoreAssistantInteractionMixin,
    CoreAssistantLifecycleMixin,
):
    """
    Product-grade interaction orchestrator for NeXa.

    Responsibilities:
    - build and own runtime dependencies
    - persist assistant state and lightweight user profile
    - prepare commands, manage pending state, and route interactions
    - deliver responses through the presentation layer
    - expose stable helper methods used by the interaction loop

    This class stays intentionally orchestration-focused.
    """

    ASSISTANT_NAME = "NeXa"

    def __init__(self) -> None:
        self.settings = load_settings()

        voice_input_cfg = self.settings.get("voice_input", {})
        display_cfg = self.settings.get("display", {})
        streaming_cfg = self.settings.get("streaming", {})
        timers_cfg = self.settings.get("timers", {})
        project_cfg = self.settings.get("project", {})
        user_cfg = self.settings.get("user", {})
        runtime_product_cfg = self.settings.get("runtime_product", {})
        benchmark_cfg = self.settings.get("benchmarks", {})
        developer_overlay_cfg = display_cfg.get("developer_overlay", {})

        self.project_name = str(project_cfg.get("name", self.ASSISTANT_NAME))
        self.default_user_name = str(user_cfg.get("name", "Andrzej"))

        self.voice_listen_timeout = float(voice_input_cfg.get("timeout_seconds", 8.0))
        self.voice_debug = bool(voice_input_cfg.get("debug", False))
        self.default_overlay_seconds = float(display_cfg.get("default_overlay_seconds", 8.0))
        self.boot_overlay_seconds = float(display_cfg.get("boot_overlay_seconds", 2.4))
        self.default_focus_minutes = float(timers_cfg.get("default_focus_minutes", 25))
        self.default_break_minutes = float(timers_cfg.get("default_break_minutes", 5))
        self.stream_mode = self._resolve_stream_mode(
            streaming_cfg.get("dialogue_stream_mode", StreamMode.SENTENCE.value)
        )

        self.pending_confirmation: dict[str, Any] | None = None
        self.pending_follow_up: dict[str, Any] | None = None
        self.last_language = "en"
        self.shutdown_requested = False

        self._last_response_stream_report = None
        self._last_response_delivery_snapshot = None
        self._last_input_capture: dict[str, Any] = {}
        self._last_capture_handoff: dict[str, Any] = {}
        self._last_resume_policy_snapshot: dict[str, Any] = {}
        self._last_command_window_policy_snapshot: dict[str, Any] = {}
        self._last_session_continuity_snapshot: dict[str, Any] = {}
        self._last_interrupt_snapshot: dict[str, Any] = {}
        self._last_audio_runtime_snapshot: dict[str, Any] = {}
        self._last_ai_broker_snapshot: dict[str, Any] = {}

        self.turn_benchmark_service = TurnBenchmarkService(
            enabled=bool(benchmark_cfg.get("enabled", True)),
            persist_turns=bool(benchmark_cfg.get("persist_turns", True)),
            path=str(benchmark_cfg.get("path", "var/data/turn_benchmarks.json")),
            max_samples=int(benchmark_cfg.get("max_samples", 300)),
            summary_window=int(benchmark_cfg.get("summary_window", 30)),
        )

        self.interrupt_controller = InteractionInterruptController()
        self.voice_session = VoiceSessionController(
            wake_phrases=("nexa",),
            wake_acknowledgements=(
                "Yes?",
                "I'm listening.",
                "I'm here.",
            ),
            active_listen_window_seconds=float(
                voice_input_cfg.get("active_listen_window_seconds", 12.0)
            ),
            thinking_ack_seconds=float(voice_input_cfg.get("thinking_ack_seconds", 1.2)),
        )

        self.wake_ack_service: WakeAcknowledgementService | None = None
        self.audio_runtime_snapshot_service = AudioRuntimeSnapshotService(
            voice_session=self.voice_session,
        )

        self.state_store = SessionStateRepository()
        self.user_profile_store = UserProfileRepository(
            default_user_name=self.default_user_name,
            project_name=self.project_name,
        )
        self.state = self.state_store.ensure_valid()
        self.user_profile = self.user_profile_store.ensure_valid()

        self.runtime = RuntimeBuilder(self.settings).build(
            on_timer_started=self._on_timer_started,
            on_timer_finished=self._on_timer_finished,
            on_timer_stopped=self._on_timer_stopped,
        )

        self.parser = self.runtime.parser
        self.router = self.runtime.router
        self.dialogue = self.runtime.dialogue
        self.voice_in = self.runtime.voice_input
        self.voice_out = self.runtime.voice_output
        self.wake_gate = self.runtime.wake_gate
        self.display = self.runtime.display

        voice_input_status = self.runtime.backend_statuses.get("voice_input")
        self.speech_recognition = SpeechRecognitionService(
            backend=self.voice_in,
            backend_label=str(
                getattr(voice_input_status, "selected_backend", "") or ""
            ).strip(),
        )

        self.wake_ack_service = WakeAcknowledgementService(
            voice_output=self.voice_out,
            phrase_builder=self.voice_session.build_wake_acknowledgement,
            phrase_inventory=self.voice_session.wake_acknowledgements,
            prefetch_on_boot=bool(voice_input_cfg.get("wake_ack_prefetch_on_boot", True)),
            prefer_fast_phrase_on_wake=bool(voice_input_cfg.get("wake_ack_prefer_fast_phrase", True)),
            fast_phrase_max_words=int(voice_input_cfg.get("wake_ack_fast_phrase_max_words", 2)),
            fast_output_hold_seconds=float(voice_input_cfg.get("wake_ack_output_hold_seconds", 0.04)),
        )
        self.memory = self.runtime.memory
        self.reminders = self.runtime.reminders
        self.timer = self.runtime.timer
        self.audio_coordinator = self.runtime.metadata.get("audio_coordinator")
        self.vision = self.runtime.metadata.get("vision_backend")
        self.ai_broker = self.runtime.metadata.get("ai_broker")
        self.pan_tilt = self.runtime.metadata.get("pan_tilt_backend")
        self.mobility = self.runtime.metadata.get("mobility_backend")
        self.voice_engine_v2_shadow_runtime_hook = self.runtime.metadata.get(
            "voice_engine_v2_shadow_runtime_hook"
        )
        self.backend_statuses = dict(self.runtime.backend_statuses)

        self.runtime_product = RuntimeProductService(
            settings=self.settings,
            persist_enabled=bool(runtime_product_cfg.get("persist_status", True)),
            path=str(runtime_product_cfg.get("status_path", "var/data/runtime_status.json")),
            required_ready_components=tuple(
                runtime_product_cfg.get(
                    "required_ready_components",
                    ["voice_input", "voice_output", "display"],
                )
            ),
            auto_recovery_components=tuple(
                runtime_product_cfg.get("auto_recovery_components", ["llm"])
            ),
            treat_llm_as_required_when_enabled=bool(
                runtime_product_cfg.get("treat_llm_as_required_when_enabled", False)
            ),
        )
        self.runtime_product.bind_runtime(runtime=self.runtime, dialogue=self.dialogue)
        self._runtime_startup_snapshot: dict[str, Any] = self.runtime_product.snapshot()

        self.runtime_debug_snapshot_service = RuntimeDebugSnapshotService(
            runtime_snapshot_provider=self._runtime_status_snapshot,
            benchmark_snapshot_provider=self.turn_benchmark_service.latest_snapshot,
            audio_snapshot_provider=self._audio_runtime_snapshot,
            ai_broker_snapshot_provider=lambda: self._ai_broker_status_snapshot(tick=True),
        )

        self.developer_overlay = DeveloperOverlayService(
            display=self.display,
            runtime_snapshot_provider=self._runtime_status_snapshot,
            benchmark_snapshot_provider=self.turn_benchmark_service.latest_snapshot,
            audio_snapshot_provider=self._audio_runtime_snapshot,
            debug_snapshot_provider=self.runtime_debug_snapshot_service.snapshot,
            enabled=bool(developer_overlay_cfg.get("enabled", True)),
            title=str(developer_overlay_cfg.get("title", "DEV")),
            refresh_on_boot=bool(developer_overlay_cfg.get("refresh_on_boot", True)),
            refresh_on_turn_finish=bool(
                developer_overlay_cfg.get("refresh_on_turn_finish", True)
            ),
        )

        self.response_streamer = ResponseStreamer(
            voice_output=self.voice_out,
            display=self.display,
            default_display_seconds=self.default_overlay_seconds,
            inter_chunk_pause_seconds=float(
                streaming_cfg.get("inter_chunk_pause_seconds", 0.0)
            ),
            max_display_lines=int(streaming_cfg.get("max_display_lines", 2)),
            max_display_chars_per_line=int(
                streaming_cfg.get("max_display_chars_per_line", 20)
            ),
            interrupt_requested=self._interrupt_requested,
        )
        self.thinking_ack_service = ThinkingAckService(
            voice_output=self.voice_out,
            voice_session=self.voice_session,
            delay_seconds=self.voice_session.thinking_ack_seconds,
        )

        self.command_flow = CommandFlowOrchestrator(self)
        self.pending_flow = PendingFlowOrchestrator(self)
        self.action_flow = ActionFlowOrchestrator(self)
        self.dialogue_flow = DialogueFlowOrchestrator(self)
        self.notification_flow = NotificationFlowOrchestrator(self)
        self.fast_command_lane = FastCommandLane(
            enabled=bool(self.settings.get("fast_command_lane", {}).get("enabled", True)),
            visual_shell_lane=VisualShellCommandLane.from_settings(
                self.settings.get("visual_shell", {})
            ),
        )

        self._boot_report_ok = all(status.ok for status in self.backend_statuses.values())
        self._stop_background = threading.Event()
        self._reminder_thread = threading.Thread(
            target=self._reminder_loop,
            name="nexa-reminders",
            daemon=True,
        )