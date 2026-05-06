from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from modules.runtime.contracts import RouteDecision

from .models import ResolvedAction, SkillRequest, SkillResult


class ActionVisualShellActionsMixin:
    """ActionFlow handlers for deterministic Visual Shell commands.

    The handlers deliberately reuse the existing VisualShellCommandLane instead
    of opening another transport path. ActionFlow resolves the command, this
    mixin delegates execution to the Visual Shell lane, and the lane owns
    controller transport plus spoken acknowledgement policy.
    """

    _VISUAL_SHELL_CANONICAL_TEXT: dict[str, dict[str, str]] = {
        "show_desktop": {
            "en": "show desktop",
            "pl": "pokaż pulpit",
        },
        "show_shell": {
            "en": "hide desktop",
            "pl": "schowaj pulpit",
        },
        "show_face_contour": {
            "en": "show face",
            "pl": "pokaż twarz",
        },
        "return_to_idle": {
            "en": "return to idle",
            "pl": "wróć do chmury",
        },
        "show_temperature": {
            "en": "show temperature",
            "pl": "pokaż temperaturę",
        },
        "show_battery": {
            "en": "show battery",
            "pl": "pokaż baterię",
        },
        "show_visual_time": {
            "en": "show the time",
            "pl": "pokaż czas",
        },
        "show_visual_date": {
            "en": "show the date",
            "pl": "pokaż datę",
        },
    }

    def _handle_show_desktop(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> SkillResult:
        return self._handle_visual_shell_action(
            route=route,
            language=language,
            payload=payload,
            resolved=resolved,
            request=request,
            action="show_desktop",
        )

    def _handle_show_shell(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> SkillResult:
        return self._handle_visual_shell_action(
            route=route,
            language=language,
            payload=payload,
            resolved=resolved,
            request=request,
            action="show_shell",
        )




    def _handle_show_face_contour(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> SkillResult:
        return self._handle_visual_shell_action(
            route=route,
            language=language,
            payload=payload,
            resolved=resolved,
            request=request,
            action="show_face_contour",
        )



    def _handle_return_to_idle(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> SkillResult:
        # Stop the look-at-me session if it is running. The session centers
        # pan/tilt on stop. If it was not running, fall through to the
        # default Visual Shell idle response.
        stop_meta: dict[str, Any] = {}
        try:
            session = getattr(self.assistant, "look_at_me_session", None)
            if session is not None:
                stop_meta = dict(session.stop() or {})
        except Exception as error:
            stop_meta = {"error": f"{type(error).__name__}: {error}"}

        if bool(stop_meta.get("stopped", False)):
            self._look_at_me_speak(
                language,
                "Dobrze, przestałam na ciebie patrzeć.",
                "Okay, I stopped looking at you.",
            )
            return SkillResult(
                action="return_to_idle",
                handled=True,
                response_delivered=True,
                status="look_at_user_stopped",
                metadata={
                    "source": "action_flow.look_at_me",
                    "phase": "look_at_user_stopped",
                    "resolved_source": resolved.source,
                    "stop_result": stop_meta,
                },
            )

        return self._handle_visual_shell_action(
            route=route,
            language=language,
            payload=payload,
            resolved=resolved,
            request=request,
            action="return_to_idle",
        )

    def _handle_show_visual_date(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> SkillResult:
        return self._handle_visual_shell_action(
            route=route,
            language=language,
            payload=payload,
            resolved=resolved,
            request=request,
            action="show_visual_date",
        )

    def _handle_show_visual_time(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> SkillResult:
        return self._handle_visual_shell_action(
            route=route,
            language=language,
            payload=payload,
            resolved=resolved,
            request=request,
            action="show_visual_time",
        )

    def _handle_show_temperature(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> SkillResult:
        return self._handle_visual_shell_action(
            route=route,
            language=language,
            payload=payload,
            resolved=resolved,
            request=request,
            action="show_temperature",
        )

    def _handle_show_battery(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> SkillResult:
        return self._handle_visual_shell_action(
            route=route,
            language=language,
            payload=payload,
            resolved=resolved,
            request=request,
            action="show_battery",
        )


    # NEXA_LOOK_AT_ME_PART2_APPLIED
    def _handle_look_at_user(
        self,
        *,
        route,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> SkillResult:
        """Start the in-process LookAtMeSession and deliver an async voice ACK.

        Tracking starts on a worker thread inside the session (non-blocking).
        The spoken acknowledgement runs after start() returns so the head is
        already moving toward the user before they hear the response.
        """
        del route, payload

        session = getattr(self.assistant, "look_at_me_session", None)
        if session is None or not getattr(session, "enabled", True):
            service = self._vision_tracking_service()
            if service is None:
                return SkillResult(
                    action="look_at_user",
                    handled=True,
                    response_delivered=False,
                    status="vision_tracking_unavailable",
                    metadata={
                        "source": "action_flow.look_at_me",
                        "phase": "vision_tracking_unavailable",
                        "resolved_source": resolved.source,
                        "vision_tracking_available": False,
                        "movement_execution_enabled": False,
                        "pan_tilt_movement_executed": False,
                        "base_movement_executed": False,
                    },
                )

            try:
                plan = service.plan_once(force_refresh=False)
            except Exception as error:
                return SkillResult(
                    action="look_at_user",
                    handled=True,
                    response_delivered=False,
                    status="vision_tracking_error",
                    metadata={
                        "source": "action_flow.look_at_me",
                        "phase": "vision_tracking_error",
                        "resolved_source": resolved.source,
                        "vision_tracking_available": True,
                        "movement_execution_enabled": False,
                        "pan_tilt_movement_executed": False,
                        "base_movement_executed": False,
                        "error": f"{type(error).__name__}: {error}",
                    },
                )

            plan_meta = self._tracking_plan_metadata(plan)
            execution_meta = self._tracking_execution_metadata(service=service, plan=plan)
            adapter_meta = self._pan_tilt_adapter_metadata(service=service, execution=execution_meta)
            status = str(plan_meta.get("reason") or execution_meta.get("status") or "look_at_user_dry_run")
            setattr(self.assistant, "_last_vision_tracking_plan", plan_meta)

            return SkillResult(
                action="look_at_user",
                handled=True,
                response_delivered=False,
                status=status,
                metadata={
                    "source": "action_flow.look_at_me",
                    "phase": "vision_tracking_dry_run_fallback",
                    "resolved_source": resolved.source,
                    "vision_tracking_available": True,
                    "dry_run": bool(execution_meta.get("dry_run", True)),
                    "movement_execution_enabled": bool(execution_meta.get("movement_execution_enabled", False)),
                    "pan_tilt_movement_executed": bool(execution_meta.get("pan_tilt_movement_executed", False)),
                    "base_movement_executed": bool(execution_meta.get("base_movement_executed", False)),
                    "base_yaw_assist_required": bool(plan_meta.get("base_yaw_assist_required", False)),
                    "base_yaw_direction": plan_meta.get("base_yaw_direction"),
                    "base_yaw_assist_execution_enabled": bool(execution_meta.get("base_yaw_assist_execution_enabled", False)),
                    "vision_tracking_plan": plan_meta,
                    "vision_tracking_execution_result": execution_meta,
                    "pan_tilt_adapter_result": adapter_meta,
                },
            )

        try:
            start_result = dict(session.start(language=language) or {})
        except Exception as error:
            self._look_at_me_speak_unavailable(language)
            return SkillResult(
                action="look_at_user",
                handled=True,
                response_delivered=True,
                status="look_at_user_start_error",
                metadata={
                    "source": "action_flow.look_at_me",
                    "phase": "look_at_user_unavailable",
                    "resolved_source": resolved.source,
                    "error": f"{type(error).__name__}: {error}",
                },
            )

        # Fire the spoken ACK AFTER session.start() returns. The session is
        # already running on its own worker thread; the speak call is OK to
        # block here.
        delivered = self._look_at_me_speak(
            language,
            "Dobrze, będę teraz na ciebie patrzeć. Gdzie jesteś?",
            "Okay, I will look at you now. Where are you?",
        )

        try:
            session_status = session.status()
        except Exception:
            session_status = {}

        return SkillResult(
            action="look_at_user",
            handled=True,
            response_delivered=bool(delivered),
            status=(
                "look_at_user_started"
                if start_result.get("started")
                else "look_at_user_already_active"
            ),
            metadata={
                "source": "action_flow.look_at_me",
                "phase": "look_at_user_started",
                "resolved_source": resolved.source,
                "vision_tracking_available": True,
                "dry_run": False,
                "movement_execution_enabled": True,
                "pan_tilt_movement_executed": True,
                "start_result": start_result,
                "session_status": session_status,
            },
        )

    def _look_at_me_speak(self, language: str, pl_text: str, en_text: str) -> bool:
        """Direct TTS call. Returns True if speak was attempted successfully."""
        voice_out = getattr(self.assistant, "voice_out", None)
        if voice_out is None:
            return False
        speak = getattr(voice_out, "speak", None)
        if not callable(speak):
            return False
        text = pl_text if str(language or "").lower().startswith("pl") else en_text
        try:
            speak(text, language=language)
            return True
        except Exception:
            return False

    def _look_at_me_speak_unavailable(self, language: str) -> bool:
        return self._look_at_me_speak(
            language,
            "Nie mogę teraz na ciebie patrzeć.",
            "I cannot look at you right now.",
        )

    def _vision_tracking_service(self) -> Any | None:
        service = getattr(self.assistant, "vision_tracking", None)
        if service is not None:
            return service

        runtime = getattr(self.assistant, "runtime", None)
        metadata = getattr(runtime, "metadata", {}) if runtime is not None else {}
        if isinstance(metadata, dict):
            return metadata.get("vision_tracking_service")

        return None

    @staticmethod
    def _pan_tilt_adapter_metadata(*, service: Any, execution: dict[str, Any]) -> dict[str, Any]:
        latest_result = getattr(service, "latest_pan_tilt_adapter_result", None)
        if callable(latest_result):
            result = latest_result()
            if result is not None:
                return ActionVisualShellActionsMixin._tracking_plan_metadata(result)

        prepare_dry_run = getattr(service, "prepare_pan_tilt_dry_run", None)
        if callable(prepare_dry_run):
            result = prepare_dry_run(execution)
            return ActionVisualShellActionsMixin._tracking_plan_metadata(result)

        try:
            from modules.devices.vision.tracking import PanTiltExecutionAdapter

            result = PanTiltExecutionAdapter().prepare(execution)
            return ActionVisualShellActionsMixin._tracking_plan_metadata(result)
        except Exception as error:
            return {
                "status": "pan_tilt_adapter_metadata_error",
                "dry_run": True,
                "backend_command_execution_enabled": False,
                "backend_command_executed": False,
                "error": f"{error.__class__.__name__}: {error}",
            }

    @staticmethod
    def _tracking_execution_metadata(*, service: Any, plan: Any) -> dict[str, Any]:
        latest_result = getattr(service, "latest_execution_result", None)
        if callable(latest_result):
            result = latest_result()
            if result is not None:
                return ActionVisualShellActionsMixin._tracking_plan_metadata(result)

        execute_dry_run = getattr(service, "execute_plan_dry_run", None)
        if callable(execute_dry_run):
            result = execute_dry_run(plan)
            return ActionVisualShellActionsMixin._tracking_plan_metadata(result)

        try:
            from modules.devices.vision.tracking import TrackingMotionExecutor

            result = TrackingMotionExecutor().execute(plan)
            return ActionVisualShellActionsMixin._tracking_plan_metadata(result)
        except Exception as error:
            return {
                "status": "execution_metadata_error",
                "dry_run": True,
                "movement_execution_enabled": False,
                "pan_tilt_movement_executed": False,
                "base_movement_executed": False,
                "error": f"{error.__class__.__name__}: {error}",
            }

    @staticmethod
    def _tracking_plan_metadata(plan: Any) -> dict[str, Any]:
        if plan is None:
            return {"has_target": False, "reason": "no_plan"}

        if is_dataclass(plan):
            return dict(asdict(plan))

        if isinstance(plan, dict):
            return dict(plan)

        metadata: dict[str, Any] = {}
        for key in (
            "has_target",
            "pan_delta_degrees",
            "tilt_delta_degrees",
            "desired_pan_degrees",
            "desired_tilt_degrees",
            "clamped_pan_degrees",
            "clamped_tilt_degrees",
            "pan_at_limit",
            "tilt_at_limit",
            "base_yaw_assist_required",
            "base_yaw_direction",
            "base_forward_velocity",
            "base_backward_velocity",
            "mobile_assist_recommended",
            "reason",
            "diagnostics",
        ):
            if hasattr(plan, key):
                metadata[key] = getattr(plan, key)

        return metadata or {"has_target": False, "reason": "unserializable_plan"}


    def _handle_visual_shell_action(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None,
        action: str,
    ) -> SkillResult:
        lane = self._visual_shell_lane()
        if lane is None:
            return self._visual_shell_unavailable_result(
                language=language,
                action=action,
                reason="visual_shell_lane_unavailable",
            )

        prepared = self._visual_shell_prepared_payload(
            route=route,
            language=language,
            action=action,
        )

        try:
            direct_handler = getattr(lane, "try_handle_action", None)
            if callable(direct_handler):
                handled = direct_handler(
                    action=action,
                    language=language,
                    prepared=prepared,
                    assistant=self.assistant,
                    source="action_flow.visual_shell",
                )
            else:
                handled = lane.try_handle(prepared=prepared, assistant=self.assistant)
        except Exception as error:
            self.LOGGER.warning(
                "Visual Shell action lane failed safely: action=%s error=%s",
                action,
                error,
            )
            return self._visual_shell_unavailable_result(
                language=language,
                action=action,
                reason=f"visual_shell_lane_exception:{type(error).__name__}",
            )

        if handled is None:
            return self._visual_shell_unavailable_result(
                language=language,
                action=action,
                reason="visual_shell_lane_no_match",
            )

        trace = dict(getattr(self.assistant, "_last_visual_shell_command_trace", {}) or {})
        status = self._visual_shell_status_from_trace(trace)

        return SkillResult(
            action=action,
            handled=True,
            response_delivered=bool(trace.get("response_emitted", False)),
            status=status,
            metadata={
                "source": "action_flow.visual_shell",
                "response_kind": (
                    "direct_response"
                    if bool(trace.get("response_emitted", False))
                    else "accepted_only"
                ),
                "visual_shell_action": action,
                "visual_shell_trace": trace,
                "resolved_source": resolved.source,
                "request_source": getattr(request, "source", "") if request else "",
                "payload_keys": sorted(payload.keys()),
            },
        )

    def _visual_shell_lane(self) -> Any | None:
        fast_command_lane = getattr(self.assistant, "fast_command_lane", None)
        lane = getattr(fast_command_lane, "visual_shell_lane", None)
        if lane is not None:
            return lane

        return getattr(self.assistant, "visual_shell_lane", None)

    def _visual_shell_prepared_payload(
        self,
        *,
        route: RouteDecision,
        language: str,
        action: str,
    ) -> dict[str, Any]:
        text = self._visual_shell_route_text(route=route, language=language, action=action)
        normalized_text = str(getattr(route, "normalized_text", "") or text).strip()

        return {
            "routing_text": text,
            "raw_text": str(getattr(route, "raw_text", "") or text).strip(),
            "normalized_text": normalized_text,
            "language": language,
            "command_language": language,
            "source": "action_flow.visual_shell",
        }

    def _visual_shell_route_text(
        self,
        *,
        route: RouteDecision,
        language: str,
        action: str,
    ) -> str:
        matched_phrase = str(getattr(route, "metadata", {}).get("matched_phrase", "") or "").strip()
        if matched_phrase:
            return matched_phrase

        for item in getattr(route, "intents", []) or []:
            metadata = dict(getattr(item, "metadata", {}) or {})
            matched_phrase = str(metadata.get("matched_phrase", "") or "").strip()
            if matched_phrase:
                return matched_phrase

        raw_text = str(getattr(route, "raw_text", "") or "").strip()
        if raw_text:
            return raw_text

        normalized_text = str(getattr(route, "normalized_text", "") or "").strip()
        if normalized_text:
            return normalized_text

        language_key = "pl" if str(language).lower().startswith("pl") else "en"
        return self._VISUAL_SHELL_CANONICAL_TEXT[action][language_key]

    @staticmethod
    def _visual_shell_status_from_trace(trace: dict[str, Any]) -> str:
        reason = str(trace.get("reason", "") or "").strip()
        transport_result = str(trace.get("transport_result", "") or "").strip()

        if reason == "handled" and transport_result == "ok":
            return "accepted"

        if transport_result == "failed" or "unavailable" in reason:
            return "visual_shell_unavailable"

        return "accepted"

    def _visual_shell_unavailable_result(
        self,
        *,
        language: str,
        action: str,
        reason: str,
    ) -> SkillResult:
        delivered = self._deliver_simple_action_response(
            language=language,
            action=action,
            spoken_text=self._localized(
                language,
                "Nie mogę teraz sterować ekranem NEXA.",
                "I cannot control the NEXA screen right now.",
            ),
            display_title="VISUAL SHELL",
            display_lines=self._localized_lines(
                language,
                ["ekran", "niedostepny"],
                ["screen", "unavailable"],
            ),
            extra_metadata={
                "phase": "visual_shell_unavailable",
                "reason": reason,
            },
        )

        return SkillResult(
            action=action,
            handled=True,
            response_delivered=bool(delivered),
            status="visual_shell_unavailable",
            metadata={
                "source": "action_flow.visual_shell",
                "response_kind": "direct_response" if bool(delivered) else "accepted_only",
                "visual_shell_action": action,
                "reason": reason,
            },
        )


__all__ = ["ActionVisualShellActionsMixin"]
