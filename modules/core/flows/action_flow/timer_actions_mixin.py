from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RouteDecision, RouteKind

from .models import ResolvedAction, SkillRequest


class ActionTimerActionsMixin:
    def _handle_timer_start(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route
        minutes = self._resolve_minutes(payload, fallback=10.0)
        return self._start_timer_mode(
            mode="timer",
            minutes=minutes,
            language=language,
            resolved=resolved,
            request=request,
        )

    def _handle_focus_start(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route
        if not self._payload_has_explicit_minutes(payload):
            default_minutes = float(getattr(self.assistant, "default_focus_minutes", 25))
            return self._prompt_focus_duration(
                language=language,
                source="action_focus_duration_prompt",
                default_minutes=default_minutes,
                resolved_source=resolved.source,
            )

        minutes = self._resolve_minutes(payload, fallback=0.0)
        return self._start_timer_mode(
            mode="focus",
            minutes=minutes,
            language=language,
            resolved=resolved,
            request=request,
        )

    def _handle_focus_offer(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route, payload, request
        self.assistant.pending_follow_up = {
            "type": "focus_start_offer",
            "language": language,
            "default_minutes": float(getattr(self.assistant, "default_focus_minutes", 25)),
            "source": "action_focus_offer",
        }
        self.LOGGER.info(
            "Focus offer follow-up armed: language=%s resolved_source=%s",
            language,
            resolved.source,
        )
        return self.assistant.deliver_text_response(
            self.assistant._localized(
                language,
                "Chcesz uruchomić skupienie?",
                "Do you want to start focus mode?",
            ),
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="action_focus_offer_prompt",
            metadata={
                "follow_up_type": "focus_start_offer",
                "resolved_source": resolved.source,
            },
        )

    def _handle_break_start(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route
        if not self._payload_has_explicit_minutes(payload):
            default_minutes = float(getattr(self.assistant, "default_break_minutes", 5))
            return self._prompt_break_duration(
                language=language,
                source="action_break_duration_prompt",
                default_minutes=default_minutes,
                resolved_source=resolved.source,
            )

        minutes = self._resolve_minutes(payload, fallback=0.0)
        return self._start_timer_mode(
            mode="break",
            minutes=minutes,
            language=language,
            resolved=resolved,
            request=request,
        )

    def _handle_timer_stop(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route, payload
        outcome = self._get_timer_skill_executor().stop()
        if outcome.status == "unavailable":
            return self._deliver_feature_unavailable(language=language, action="timer_stop")

        if outcome.ok:
            self.LOGGER.info("Timer stop accepted by timer executor.")
            return self._accepted_action_result(
                action=request.action if request is not None else "timer_stop",
                extra_metadata={
                    **dict(outcome.metadata or {}),
                    "resolved_source": resolved.source,
                },
            )

        spec = self._get_timer_response_builder().build_stop_failure(
            language=language,
            action="timer_stop",
            outcome_message=outcome.message,
            resolved_source=resolved.source,
            phase=outcome.status or "stop_failed",
            metadata=dict(outcome.metadata or {}),
        )
        return self._deliver_action_response_spec(language=language, spec=spec)

    def _start_timer_mode(
        self,
        *,
        mode: str,
        minutes: float,
        language: str,
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        outcome = self._get_timer_skill_executor().start(mode=mode, minutes=float(minutes))
        if outcome.status == "unavailable":
            return self._deliver_feature_unavailable(language=language, action=f"{mode}_start")

        if outcome.ok:
            self.LOGGER.info("Timer start accepted by timer executor: mode=%s minutes=%s", mode, minutes)
            return self._accepted_action_result(
                action=request.action if request is not None else f"{mode}_start",
                extra_metadata={
                    **dict(outcome.metadata or {}),
                    "resolved_source": resolved.source,
                    "mode": mode,
                    "minutes": float(minutes),
                },
            )

        spec = self._get_timer_response_builder().build_start_failure(
            language=language,
            action=f"{mode}_start",
            outcome_message=outcome.message,
            resolved_source=resolved.source,
            phase=outcome.status or "start_failed",
            minutes=float(minutes),
            mode=mode,
            metadata=dict(outcome.metadata or {}),
        )
        return self._deliver_action_response_spec(language=language, spec=spec)
    def _payload_has_explicit_minutes(self, payload: dict[str, Any]) -> bool:
        try:
            return "minutes" in payload and payload.get("minutes") is not None
        except AttributeError:
            return False

    def _prompt_focus_duration(
        self,
        *,
        language: str,
        source: str,
        default_minutes: float,
        resolved_source: str,
    ) -> bool:
        self.assistant.pending_follow_up = {
            "type": "focus_duration",
            "language": language,
            "mode": "focus",
            "default_minutes": float(default_minutes),
            "source": source,
        }
        self.LOGGER.info(
            "Focus duration follow-up armed: language=%s default_minutes=%s source=%s",
            language,
            default_minutes,
            source,
        )
        return self.assistant.deliver_text_response(
            self.assistant._localized(
                language,
                "Ile czasu chcesz się skupić?",
                "How long do you want to focus?",
            ),
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source=source,
            metadata={
                "follow_up_type": "focus_duration",
                "default_minutes": float(default_minutes),
                "resolved_source": resolved_source,
            },
        )

    def _prompt_break_duration(
        self,
        *,
        language: str,
        source: str,
        default_minutes: float,
        resolved_source: str,
    ) -> bool:
        self.assistant.pending_follow_up = {
            "type": "break_duration",
            "language": language,
            "mode": "break",
            "default_minutes": float(default_minutes),
            "source": source,
        }
        self.LOGGER.info(
            "Break duration follow-up armed: language=%s default_minutes=%s source=%s",
            language,
            default_minutes,
            source,
        )
        return self.assistant.deliver_text_response(
            self.assistant._localized(
                language,
                "Na ile ustawiam odpoczynek?",
                "How long do you want to take a break?",
            ),
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source=source,
            metadata={
                "follow_up_type": "break_duration",
                "default_minutes": float(default_minutes),
                "resolved_source": resolved_source,
            },
        )
