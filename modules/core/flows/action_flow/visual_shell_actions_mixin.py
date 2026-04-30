from __future__ import annotations

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
        "show_self": {
            "en": "show yourself",
            "pl": "pokaż się",
        },
        "show_eyes": {
            "en": "show eyes",
            "pl": "pokaż oczy",
        },
        "show_face_contour": {
            "en": "show face",
            "pl": "pokaż twarz",
        },
        "look_at_user": {
            "en": "look at me",
            "pl": "spójrz na mnie",
        },
        "start_scanning": {
            "en": "scan room",
            "pl": "sprawdź pokój",
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


    def _handle_show_self(
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
            action="show_self",
        )

    def _handle_show_eyes(
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
            action="show_eyes",
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

    def _handle_look_at_user(
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
            action="look_at_user",
        )

    def _handle_start_scanning(
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
            action="start_scanning",
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
