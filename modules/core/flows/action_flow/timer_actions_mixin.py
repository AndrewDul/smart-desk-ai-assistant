from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RouteDecision

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
        minutes = self._resolve_minutes(
            payload,
            fallback=float(getattr(self.assistant, "default_focus_minutes", 25)),
        )
        return self._start_timer_mode(
            mode="focus",
            minutes=minutes,
            language=language,
            resolved=resolved,
            request=request,
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
        minutes = self._resolve_minutes(
            payload,
            fallback=float(getattr(self.assistant, "default_break_minutes", 5)),
        )
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