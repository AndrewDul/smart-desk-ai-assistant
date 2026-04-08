from __future__ import annotations

import threading
import time
from typing import Any

from modules.core.flows.action_flow import ActionFlowOrchestrator
from modules.core.flows.command_flow import CommandFlowOrchestrator
from modules.core.flows.dialogue_flow import DialogueFlowOrchestrator
from modules.core.flows.notification_flow import NotificationFlowOrchestrator
from modules.core.flows.pending_flow import PendingFlowOrchestrator
from modules.core.session.fast_command_lane import FastCommandLane
from modules.core.session.interrupt_controller import InteractionInterruptController
from modules.core.session.voice_session import (
    VOICE_STATE_SHUTDOWN,
    VOICE_STATE_SPEAKING,
    VOICE_STATE_STANDBY,
    VoiceSessionController,
)
from modules.presentation.response_streamer import ResponseStreamer
from modules.presentation.thinking_ack import ThinkingAckService
from modules.runtime.builder import RuntimeBuilder
from modules.runtime.contracts import (
    ChunkKind,
    InputSource,
    IntentMatch,
    ResponsePlan,
    RouteDecision,
    RouteKind,
    StreamMode,
    ToolInvocation,
    create_turn_id,
    normalize_text,
)
from modules.shared.config.settings import load_settings
from modules.shared.logging.logger import append_log, log_exception
from modules.shared.persistence.json_store import JsonStore
from modules.shared.persistence.paths import SESSION_STATE_PATH, USER_PROFILE_PATH


class CoreAssistant:
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

        self.state_store = JsonStore(
            path=SESSION_STATE_PATH,
            default_factory=self._default_state_payload,
        )
        self.user_profile_store = JsonStore(
            path=USER_PROFILE_PATH,
            default_factory=self._default_user_profile_payload,
        )
        self.state = self.state_store.ensure_exists()
        self.user_profile = self.user_profile_store.ensure_exists()

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
        self.memory = self.runtime.memory
        self.reminders = self.runtime.reminders
        self.timer = self.runtime.timer
        self.audio_coordinator = self.runtime.metadata.get("audio_coordinator")
        self.vision = self.runtime.metadata.get("vision_backend")
        self.mobility = self.runtime.metadata.get("mobility_backend")
        self.backend_statuses = dict(self.runtime.backend_statuses)

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
        )

        self._boot_report_ok = all(status.ok for status in self.backend_statuses.values())
        self._stop_background = threading.Event()
        self._reminder_thread = threading.Thread(
            target=self._reminder_loop,
            name="nexa-reminders",
            daemon=True,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def boot(self) -> None:
        self.shutdown_requested = False
        self.last_language = "en"
        self._clear_interaction_context(close_active_window=True)

        self.state["assistant_running"] = True
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self.state["current_timer"] = None
        self._save_state()

        if not self._reminder_thread.is_alive():
            self._reminder_thread.start()

        self.display.show_block(
            self.ASSISTANT_NAME,
            [
                "starting up...",
                "voice assistant ready",
            ],
            duration=self.boot_overlay_seconds,
        )
        append_log("Assistant boot sequence started.")

        time.sleep(max(self.boot_overlay_seconds, 0.8))
        self.display.clear_overlay()

        startup_text = self._startup_greeting(report_ok=self._boot_report_ok)
        self.voice_out.speak(startup_text, language="en")
        self._remember_assistant_turn(
            startup_text,
            language="en",
            metadata={
                "source": "system_boot",
                "route_kind": "system_boot",
            },
        )

        self.voice_session.set_state(VOICE_STATE_STANDBY, detail="startup_complete")
        append_log("Assistant booted.")

    def shutdown(self) -> None:
        append_log("Assistant shutdown started.")
        self._stop_background.set()
        self.request_interrupt(reason="shutdown", source="assistant.shutdown")
        self._thinking_ack_stop()

        try:
            timer_status = self._safe_timer_status()
            if timer_status.get("running"):
                stop_method = getattr(self.timer, "stop", None)
                if callable(stop_method):
                    stop_method()
        except Exception as error:
            log_exception("Failed to stop timer during shutdown", error)

        self.state["assistant_running"] = False
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self.state["current_timer"] = None
        self._save_state()

        shutdown_text = self._localized(
            self.last_language,
            f"Wyłączam {self.ASSISTANT_NAME}.",
            f"Shutting down {self.ASSISTANT_NAME}.",
        )

        self.display.show_block(
            "SHUTDOWN",
            [
                "assistant stopped",
                "see you later",
            ],
            duration=2.0,
        )
        self._remember_assistant_turn(
            shutdown_text,
            language=self.last_language,
            metadata={
                "source": "system_shutdown",
                "route_kind": "system_shutdown",
            },
        )
        self.voice_out.speak(shutdown_text, language=self.last_language)

        self._safe_stop_mobility()
        self._safe_close_runtime_components()

        time.sleep(2.0)
        self.voice_session.set_state(VOICE_STATE_SHUTDOWN, detail="assistant_shutdown")
        append_log("Assistant shut down.")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _default_state_payload(self) -> dict[str, Any]:
        return {
            "assistant_running": False,
            "focus_mode": False,
            "break_mode": False,
            "current_timer": None,
        }

    def _default_user_profile_payload(self) -> dict[str, Any]:
        return {
            "name": self.default_user_name,
            "conversation_partner_name": "",
            "project": self.project_name,
        }

    def _save_state(self) -> None:
        self.state = self.state_store.write(self.state)

    def _save_user_profile(self) -> None:
        self.user_profile = self.user_profile_store.write(self.user_profile)

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def handle_command(self, text: str) -> bool:
        self.interrupt_controller.clear()

        cleaned = str(text or "").strip()
        if not cleaned:
            return True

        prepared = self._prepare_command(cleaned)
        if prepared["ignore"]:
            return True

        command_lang = self._commit_language(prepared["language"])
        routing_text = prepared["routing_text"]

        if not prepared.get("already_remembered", False):
            self._remember_user_turn(
                cleaned,
                language=command_lang,
                metadata={
                    "source": prepared["source"].value,
                    "normalized_text": prepared["normalized_text"],
                },
            )

        if prepared["cancel_requested"]:
            return self._cancel_active_request(command_lang)

        pending_result = self._handle_pending_state(prepared)
        if pending_result is not None:
            return bool(pending_result)

        fast_lane_result = self._handle_fast_lane(prepared)
        if fast_lane_result is not None:
            return bool(fast_lane_result)

        self.voice_session.set_state("routing", detail="route_command")
        self._thinking_ack_start(language=command_lang, detail="route_command")
        try:
            routed = self.router.route(routing_text, preferred_language=command_lang)
        finally:
            self._thinking_ack_stop()

        route = self._coerce_route_decision(
            routed,
            raw_text=cleaned,
            normalized_text=prepared["normalized_text"],
            language=command_lang,
        )

        log_route_decision = getattr(self.command_flow, "log_route_decision", None)
        if callable(log_route_decision):
            try:
                log_route_decision(route)
            except Exception:
                pass

        if route.kind == RouteKind.ACTION:
            self.pending_confirmation = None
            return self._execute_action_route(route, command_lang)

        if route.kind == RouteKind.MIXED:
            self.pending_confirmation = None
            return self._handle_mixed_route(route, command_lang)

        if route.kind == RouteKind.CONVERSATION:
            self.pending_confirmation = None
            return self._handle_conversation_route(route, command_lang)

        return self._handle_unclear_route(route, command_lang)

    def request_interrupt(
        self,
        *,
        reason: str = "manual_interrupt",
        source: str = "assistant",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.interrupt_controller.request(
            reason=reason,
            source=source,
            metadata=metadata,
        )

    def _interrupt_requested(self) -> bool:
        return bool(self.interrupt_controller.is_requested())

    # ------------------------------------------------------------------
    # Response delivery
    # ------------------------------------------------------------------

    def deliver_response_plan(
        self,
        plan: ResponsePlan,
        *,
        source: str,
        remember: bool = True,
        extra_metadata: dict[str, Any] | None = None,
    ) -> bool:
        if not plan.chunks and not plan.tool_results:
            return True

        route_kind_value = plan.route_kind.value
        self.voice_session.set_state(VOICE_STATE_SPEAKING, detail=f"response:{route_kind_value}")

        try:
            delivered = False

            execute_method = getattr(self.response_streamer, "execute", None)
            if callable(execute_method):
                execute_method(plan)
                delivered = True
            else:
                deliver_method = getattr(self.response_streamer, "deliver", None)
                if callable(deliver_method):
                    deliver_method(plan)
                    delivered = True
                else:
                    stream_method = getattr(self.response_streamer, "stream", None)
                    if callable(stream_method):
                        stream_method(plan)
                        delivered = True

            if not delivered:
                fallback_text = plan.full_text()
                if fallback_text:
                    self.voice_out.speak(fallback_text, language=plan.language)
                    self.display.show_block(
                        self.ASSISTANT_NAME,
                        self._display_lines(fallback_text),
                        duration=self.default_overlay_seconds,
                    )

            if remember:
                remembered_text = plan.full_text()
                if remembered_text:
                    metadata = {
                        "source": source,
                        "route_kind": route_kind_value,
                        "tool_count": len(plan.tool_results),
                    }
                    if extra_metadata:
                        metadata.update(extra_metadata)
                    self._remember_assistant_turn(
                        remembered_text,
                        language=plan.language,
                        metadata=metadata,
                    )

            return True
        finally:
            if self.shutdown_requested:
                self.voice_session.set_state(VOICE_STATE_SHUTDOWN, detail="shutdown_requested")
            else:
                self.voice_session.set_state(VOICE_STATE_STANDBY, detail="response_complete")

    def deliver_text_response(
        self,
        text: str,
        *,
        language: str,
        route_kind: RouteKind,
        source: str,
        remember: bool = True,
        chunk_kind: ChunkKind = ChunkKind.CONTENT,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        plan = ResponsePlan(
            turn_id=create_turn_id(),
            language=language,
            route_kind=route_kind,
            stream_mode=self.stream_mode,
        )
        plan.add_text(text, kind=chunk_kind, mode=self.stream_mode)
        return self.deliver_response_plan(
            plan,
            source=source,
            remember=remember,
            extra_metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Async notifications and timer callbacks
    # ------------------------------------------------------------------

    def _deliver_async_notification(
        self,
        *,
        lang: str,
        spoken_text: str,
        display_title: str,
        display_lines: list[str],
        source: str,
        route_kind: str,
        action: str | None = None,
        display_duration: float | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        deliver_method = getattr(self.notification_flow, "deliver_async_notification", None)
        if callable(deliver_method):
            deliver_method(
                lang=lang,
                spoken_text=spoken_text,
                display_title=display_title,
                display_lines=display_lines,
                source=source,
                route_kind=route_kind,
                action=action,
                display_duration=display_duration,
                extra_metadata=extra_metadata,
            )
            return

        self.deliver_text_response(
            spoken_text,
            language=lang,
            route_kind=RouteKind.CONVERSATION,
            source=source,
            remember=True,
            metadata=extra_metadata,
        )

    def _on_timer_started(self, **payload: Any) -> None:
        timer_type = self._timer_type_from_payload(payload)
        minutes = self._timer_minutes_from_payload(payload)
        lang = self._normalize_lang(payload.get("language") or self.last_language)

        self.state["current_timer"] = timer_type
        self.state["focus_mode"] = timer_type == "focus"
        self.state["break_mode"] = timer_type == "break"
        self._save_state()

        if timer_type == "focus":
            spoken = self._localized(
                lang,
                f"Rozpoczynam tryb skupienia na {self._minutes_text(minutes, 'pl')}.",
                f"Starting focus mode for {self._minutes_text(minutes, 'en')}.",
            )
            title = "FOCUS"
        elif timer_type == "break":
            spoken = self._localized(
                lang,
                f"Rozpoczynam przerwę na {self._minutes_text(minutes, 'pl')}.",
                f"Starting break mode for {self._minutes_text(minutes, 'en')}.",
            )
            title = "BREAK"
        else:
            spoken = self._localized(
                lang,
                f"Uruchamiam timer na {self._minutes_text(minutes, 'pl')}.",
                f"Starting a timer for {self._minutes_text(minutes, 'en')}.",
            )
            title = "TIMER"

        self._deliver_async_notification(
            lang=lang,
            spoken_text=spoken,
            display_title=title,
            display_lines=self._display_lines(spoken),
            source="timer_started",
            route_kind="timer_status",
            action=timer_type,
            extra_metadata={
                "minutes": minutes,
                "timer_type": timer_type,
            },
        )

    def _on_timer_finished(self, **payload: Any) -> None:
        timer_type = self._timer_type_from_payload(payload)
        minutes = self._timer_minutes_from_payload(payload)
        lang = self._normalize_lang(payload.get("language") or self.last_language)

        self.state["current_timer"] = None
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self._save_state()

        if timer_type == "focus":
            spoken = self._localized(
                lang,
                f"Tryb skupienia zakończony po {self._minutes_text(minutes, 'pl')}.",
                f"Focus mode finished after {self._minutes_text(minutes, 'en')}.",
            )
            title = "FOCUS DONE"
        elif timer_type == "break":
            spoken = self._localized(
                lang,
                f"Przerwa zakończona po {self._minutes_text(minutes, 'pl')}.",
                f"Break finished after {self._minutes_text(minutes, 'en')}.",
            )
            title = "BREAK DONE"
        else:
            spoken = self._localized(
                lang,
                f"Timer zakończył się po {self._minutes_text(minutes, 'pl')}.",
                f"Timer finished after {self._minutes_text(minutes, 'en')}.",
            )
            title = "TIMER DONE"

        self._deliver_async_notification(
            lang=lang,
            spoken_text=spoken,
            display_title=title,
            display_lines=self._display_lines(spoken),
            source="timer_finished",
            route_kind="timer_status",
            action=timer_type,
            extra_metadata={
                "minutes": minutes,
                "timer_type": timer_type,
            },
        )

    def _on_timer_stopped(self, **payload: Any) -> None:
        timer_type = self._timer_type_from_payload(payload)
        lang = self._normalize_lang(payload.get("language") or self.last_language)

        self.state["current_timer"] = None
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self._save_state()

        spoken = self._localized(
            lang,
            "Zatrzymałem aktywny timer.",
            "I stopped the active timer.",
        )

        self._deliver_async_notification(
            lang=lang,
            spoken_text=spoken,
            display_title="TIMER STOPPED",
            display_lines=self._display_lines(spoken),
            source="timer_stopped",
            route_kind="timer_status",
            action=timer_type,
            extra_metadata={"timer_type": timer_type},
        )

    # ------------------------------------------------------------------
    # Route execution
    # ------------------------------------------------------------------

    def _execute_action_route(self, route: RouteDecision, language: str) -> bool:
        return bool(self.action_flow.execute(route=route, language=language))

    def _handle_mixed_route(self, route: RouteDecision, language: str) -> bool:
        handle_method = getattr(self.dialogue_flow, "handle_mixed_route", None)
        if callable(handle_method):
            return bool(handle_method(route=route, language=language))
        return bool(self.dialogue_flow.handle_mixed(route=route, language=language))

    def _handle_conversation_route(self, route: RouteDecision, language: str) -> bool:
        handle_method = getattr(self.dialogue_flow, "handle_conversation_route", None)
        if callable(handle_method):
            return bool(handle_method(route=route, language=language))
        return bool(self.dialogue_flow.handle_conversation(route=route, language=language))

    def _handle_unclear_route(self, route: RouteDecision, language: str) -> bool:
        handle_method = getattr(self.dialogue_flow, "handle_unclear_route", None)
        if callable(handle_method):
            return bool(handle_method(route=route, language=language))
        return bool(self.dialogue_flow.handle_unclear(route=route, language=language))

    # ------------------------------------------------------------------
    # Command preparation and pending routing
    # ------------------------------------------------------------------

    def _prepare_command(self, text: str) -> dict[str, Any]:
        process_method = getattr(self.command_flow, "process", None)
        if callable(process_method):
            prepared = process_method(text=text, fallback_language=self.last_language)
            if isinstance(prepared, dict):
                prepared.setdefault("cancel_requested", self._looks_like_cancel_request(text))
                prepared.setdefault("normalized_text", normalize_text(text))
                prepared.setdefault("routing_text", text.strip())
                prepared.setdefault("language", self._detect_language(text))
                prepared.setdefault("source", InputSource.VOICE)
                prepared.setdefault("ignore", not bool(prepared["normalized_text"]))
                return prepared

            return {
                "ignore": bool(getattr(prepared, "ignore", False)),
                "language": str(getattr(prepared, "language", self.last_language)),
                "routing_text": str(getattr(prepared, "routing_text", text)),
                "normalized_text": str(getattr(prepared, "normalized_text", normalize_text(text))),
                "cancel_requested": bool(
                    getattr(prepared, "cancel_requested", self._looks_like_cancel_request(text))
                ),
                "source": getattr(prepared, "source", InputSource.VOICE),
                "already_remembered": bool(getattr(prepared, "already_remembered", False)),
            }

        normalized_text = normalize_text(text)
        language = self._detect_language(text)
        return {
            "ignore": not bool(normalized_text),
            "language": language,
            "routing_text": text.strip(),
            "normalized_text": normalized_text,
            "cancel_requested": self._looks_like_cancel_request(text),
            "source": InputSource.VOICE,
            "already_remembered": False,
        }

    def _handle_pending_state(self, prepared: dict[str, Any]) -> bool | None:
        process_method = getattr(self.pending_flow, "process", None)
        if not callable(process_method):
            return None

        return process_method(
            prepared=prepared,
            language=str(prepared.get("language", self.last_language)),
        )

    def _handle_fast_lane(self, prepared: dict[str, Any]) -> bool | None:
        if self.fast_command_lane is None:
            return None

        handle_method = getattr(self.fast_command_lane, "try_handle", None)
        if not callable(handle_method):
            return None

        return handle_method(prepared=prepared, assistant=self)

    # ------------------------------------------------------------------
    # Route coercion
    # ------------------------------------------------------------------

    def _coerce_route_decision(
        self,
        value: Any,
        *,
        raw_text: str,
        normalized_text: str,
        language: str,
    ) -> RouteDecision:
        if isinstance(value, RouteDecision):
            return value

        if isinstance(value, dict):
            kind_value = str(value.get("kind", RouteKind.UNCLEAR.value)).strip().lower()
            kind = self._coerce_route_kind(kind_value)

            intents: list[IntentMatch] = []
            for item in value.get("intents", []) or []:
                if isinstance(item, IntentMatch):
                    intents.append(item)

            tool_invocations: list[ToolInvocation] = []
            for item in value.get("tool_invocations", []) or []:
                if isinstance(item, ToolInvocation):
                    tool_invocations.append(item)
                elif isinstance(item, dict):
                    tool_invocations.append(
                        ToolInvocation(
                            tool_name=str(item.get("tool_name", item.get("name", ""))),
                            payload=dict(item.get("payload", {})),
                            reason=str(item.get("reason", "")),
                            confidence=float(item.get("confidence", 1.0)),
                            execute_immediately=bool(item.get("execute_immediately", True)),
                        )
                    )

            return RouteDecision(
                turn_id=str(value.get("turn_id", create_turn_id())),
                raw_text=raw_text,
                normalized_text=normalized_text,
                language=self._normalize_lang(value.get("language", language)),
                kind=kind,
                confidence=float(value.get("confidence", 0.0)),
                primary_intent=str(value.get("primary_intent", "unknown")),
                intents=intents,
                conversation_topics=list(value.get("conversation_topics", []) or []),
                tool_invocations=tool_invocations,
                notes=list(value.get("notes", []) or []),
                metadata=dict(value.get("metadata", {})),
            )

        route_kind = RouteKind.UNCLEAR
        primary_intent = "unknown"

        if isinstance(value, str):
            lowered = normalize_text(value)
            if lowered in {"action", "tool", "task"}:
                route_kind = RouteKind.ACTION
            elif lowered in {"conversation", "chat", "dialogue"}:
                route_kind = RouteKind.CONVERSATION
            elif lowered == "mixed":
                route_kind = RouteKind.MIXED
            primary_intent = lowered or "unknown"

        return RouteDecision(
            turn_id=create_turn_id(),
            raw_text=raw_text,
            normalized_text=normalized_text,
            language=self._normalize_lang(language),
            kind=route_kind,
            confidence=0.0,
            primary_intent=primary_intent,
            intents=[],
            conversation_topics=[],
            tool_invocations=[],
            notes=[],
            metadata={},
        )

    def _coerce_route_kind(self, raw_value: str) -> RouteKind:
        normalized = str(raw_value or "").strip().lower()
        for kind in RouteKind:
            if kind.value == normalized:
                return kind
        return RouteKind.UNCLEAR

    # ------------------------------------------------------------------
    # Conversation memory hooks
    # ------------------------------------------------------------------

    def _remember_user_turn(
        self,
        text: str,
        *,
        language: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        memory = getattr(self.dialogue, "conversation_memory", None)
        remember_method = getattr(memory, "remember_user_turn", None)
        if callable(remember_method):
            try:
                remember_method(text=text, language=language, metadata=metadata or {})
            except TypeError:
                remember_method(text, language)

    def _remember_assistant_turn(
        self,
        text: str,
        *,
        language: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        memory = getattr(self.dialogue, "conversation_memory", None)
        remember_method = getattr(memory, "remember_assistant_turn", None)
        if callable(remember_method):
            try:
                remember_method(text=text, language=language, metadata=metadata or {})
            except TypeError:
                remember_method(text, language)

    def _build_dialogue_user_profile(self, preferred_language: str) -> dict[str, Any]:
        profile = dict(self.user_profile)
        profile["preferred_language"] = self._normalize_lang(preferred_language)

        memory = getattr(self.dialogue, "conversation_memory", None)
        if memory is not None:
            build_method = getattr(memory, "build_recent_context", None)
            if callable(build_method):
                try:
                    profile["recent_conversation_context"] = build_method(
                        limit=6,
                        preferred_language=preferred_language,
                        include_timestamps=False,
                    )
                except TypeError:
                    profile["recent_conversation_context"] = build_method(6)

        return profile

    # ------------------------------------------------------------------
    # Background work
    # ------------------------------------------------------------------

    def _reminder_loop(self) -> None:
        while not self._stop_background.is_set():
            try:
                checker = getattr(self.reminders, "check_due_reminders", None)
                due_reminders = checker() if callable(checker) else []

                for reminder in due_reminders or []:
                    deliver_method = getattr(self.notification_flow, "deliver_due_reminder", None)
                    if callable(deliver_method):
                        deliver_method(reminder)
            except Exception as error:
                log_exception("Reminder loop iteration failed", error)

            time.sleep(1.0)

    # ------------------------------------------------------------------
    # Localized helpers
    # ------------------------------------------------------------------

    def _detect_language(self, text: str) -> str:
        lowered = normalize_text(text)
        tokens = set(lowered.split())

        polish_markers = {
            "jest",
            "czy",
            "pokaz",
            "godzina",
            "czas",
            "data",
            "dzien",
            "przerwa",
            "skupienia",
            "zapamietaj",
            "usun",
            "przypomnij",
            "ktora",
            "jaka",
            "miesiac",
            "rok",
            "pamietasz",
            "pomoc",
            "wytlumacz",
            "wyjasnij",
            "zamknij",
            "wylacz",
            "gdzie",
            "klucze",
        }
        english_markers = {
            "what",
            "time",
            "date",
            "day",
            "month",
            "year",
            "show",
            "help",
            "explain",
            "close",
            "turn",
            "off",
            "remember",
            "remind",
            "where",
            "keys",
            "assistant",
            "shutdown",
            "timer",
            "focus",
            "break",
        }

        polish_hits = len(tokens & polish_markers)
        english_hits = len(tokens & english_markers)

        if polish_hits > english_hits:
            return "pl"
        if english_hits > polish_hits:
            return "en"
        if any(char in text for char in "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"):
            return "pl"
        return self._normalize_lang(self.last_language)

    def _normalize_lang(self, language: str | None) -> str:
        normalized = str(language or "en").strip().lower()
        if normalized.startswith("pl"):
            return "pl"
        return "en"

    def _commit_language(self, language: str | None) -> str:
        self.last_language = self._normalize_lang(language)
        return self.last_language

    def _localized(self, lang: str, polish_text: str, english_text: str) -> str:
        return polish_text if self._normalize_lang(lang) == "pl" else english_text

    def _looks_like_cancel_request(self, text: str) -> bool:
        if self.voice_session.looks_like_cancel_request(text):
            return True

        normalized = normalize_text(text)
        cancel_markers = {
            "cancel",
            "stop",
            "never mind",
            "leave it",
            "anuluj",
            "zostaw to",
            "niewazne",
            "przestan",
        }
        return normalized in cancel_markers

    def _cancel_active_request(self, lang: str) -> bool:
        had_pending = bool(self.pending_confirmation or self.pending_follow_up)
        self.pending_confirmation = None
        self.pending_follow_up = None

        spoken_text = self._localized(
            lang,
            "Dobrze. Anuluję to." if had_pending else "Nie ma teraz nic do anulowania.",
            "Okay. I will cancel that." if had_pending else "There is nothing to cancel right now.",
        )
        return self.deliver_text_response(
            spoken_text,
            language=lang,
            route_kind=RouteKind.CONVERSATION,
            source="assistant_cancel_request",
            metadata={"had_pending": had_pending},
        )

    def _clear_interaction_context(self, *, close_active_window: bool = False) -> None:
        self.pending_confirmation = None
        self.pending_follow_up = None
        self.interrupt_controller.clear()
        if close_active_window:
            self.voice_session.close_active_window()

    # ------------------------------------------------------------------
    # Small shared formatting helpers
    # ------------------------------------------------------------------

    def _startup_greeting(self, *, report_ok: bool) -> str:
        if report_ok:
            return (
                f"Hello. I am {self.ASSISTANT_NAME}. "
                "Startup checks look good. Say NeXa when you need me."
            )

        degraded = self._degraded_component_names()
        if degraded:
            degraded_text = ", ".join(degraded[:3])
            return (
                f"Hello. I am {self.ASSISTANT_NAME}. "
                f"Startup checks found some degraded modules: {degraded_text}. "
                "I am still ready to help."
            )

        return (
            f"Hello. I am {self.ASSISTANT_NAME}. "
            "Startup checks completed. I am ready to help."
        )

    def _degraded_component_names(self) -> list[str]:
        return [
            name
            for name, status in self.backend_statuses.items()
            if not bool(getattr(status, "ok", False))
        ]

    def _minutes_text(self, minutes: float | None, language: str) -> str:
        safe_minutes = int(round(float(minutes or 0)))
        if safe_minutes <= 0:
            safe_minutes = 1

        if language == "pl":
            if safe_minutes == 1:
                return "1 minutę"
            return f"{safe_minutes} minut"

        if safe_minutes == 1:
            return "1 minute"
        return f"{safe_minutes} minutes"

    def _display_lines(self, text: str) -> list[str]:
        cleaned = " ".join(str(text or "").split()).strip()
        if not cleaned:
            return [""]

        max_chars = int(
            self.settings.get("streaming", {}).get("max_display_chars_per_line", 20)
        )
        if len(cleaned) <= max_chars:
            return [cleaned]

        words = cleaned.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > max_chars:
                lines.append(current)
                current = word
                if len(lines) == 2:
                    break
            else:
                current = candidate

        if current and len(lines) < 2:
            lines.append(current)

        return lines[:2] or [cleaned[:max_chars]]

    def _resolve_stream_mode(self, raw_value: Any) -> StreamMode:
        normalized = str(raw_value or StreamMode.SENTENCE.value).strip().lower()
        for member in StreamMode:
            if member.value == normalized:
                return member
        return StreamMode.SENTENCE

    # ------------------------------------------------------------------
    # Thinking acknowledgements
    # ------------------------------------------------------------------

    def _thinking_ack_start(self, *, language: str, detail: str = "thinking") -> None:
        for method_name in ("arm", "start", "schedule"):
            method = getattr(self.thinking_ack_service, method_name, None)
            if not callable(method):
                continue
            try:
                method(language=language, detail=detail)
            except TypeError:
                try:
                    method(language=language)
                except TypeError:
                    method()
            return

    def _thinking_ack_stop(self) -> None:
        for method_name in ("cancel", "stop", "clear"):
            method = getattr(self.thinking_ack_service, method_name, None)
            if callable(method):
                method()
                return

    # ------------------------------------------------------------------
    # Timer payload helpers
    # ------------------------------------------------------------------

    def _timer_type_from_payload(self, payload: dict[str, Any]) -> str:
        for key in ("timer_type", "mode", "kind", "label", "action"):
            value = payload.get(key)
            if value:
                normalized = normalize_text(str(value))
                if "focus" in normalized:
                    return "focus"
                if "break" in normalized:
                    return "break"
                return "timer"
        return "timer"

    def _timer_minutes_from_payload(self, payload: dict[str, Any]) -> float:
        for key in ("minutes", "duration_minutes", "duration", "length_minutes"):
            value = payload.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return self.default_focus_minutes

    # ------------------------------------------------------------------
    # Safe component operations
    # ------------------------------------------------------------------

    def _safe_timer_status(self) -> dict[str, Any]:
        status_method = getattr(self.timer, "status", None)
        if callable(status_method):
            try:
                value = status_method()
                if isinstance(value, dict):
                    return value
            except Exception as error:
                log_exception("Failed to read timer status", error)
        return {"running": False}

    def _safe_stop_mobility(self) -> None:
        if self.mobility is None:
            return
        stop_method = getattr(self.mobility, "stop", None)
        if callable(stop_method):
            try:
                stop_method()
            except Exception as error:
                log_exception("Failed to stop mobility backend", error)

    def _safe_close_runtime_components(self) -> None:
        seen_ids: set[int] = set()
        components = [
            ("wake_gate", self.wake_gate),
            ("voice_input", self.voice_in),
            ("voice_output", self.voice_out),
            ("vision", self.vision),
            ("mobility", self.mobility),
            ("display", self.display),
        ]

        for label, component in components:
            if component is None:
                continue

            component_id = id(component)
            if component_id in seen_ids:
                continue
            seen_ids.add(component_id)

            close_method = getattr(component, "close", None)
            if callable(close_method):
                try:
                    close_method()
                except Exception as error:
                    log_exception(f"Failed to close runtime component: {label}", error)


__all__ = ["CoreAssistant"]