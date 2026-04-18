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
        stop_method = self._first_callable(self.assistant.timer, "stop", "cancel", "stop_timer")
        if stop_method is None:
            return self._deliver_feature_unavailable(language=language, action="timer_stop")

        result = stop_method()
        ok = self._result_ok(result)

        if ok:
            self.LOGGER.info("Timer stop accepted by timer service.")
            return self._accepted_action_result(
                action=request.action if request is not None else "timer_stop",
                extra_metadata={
                    "source": "timer_service.stop",
                    "resolved_source": resolved.source,
                },
            )

        error_text = self._result_message(result) or self._localized(
            language,
            "Nie ma teraz aktywnego timera.",
            "There is no active timer right now.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="timer_stop",
            spoken_text=error_text,
            display_title="TIMER",
            display_lines=self._display_lines(error_text),
            extra_metadata={"resolved_source": resolved.source, "phase": "stop_failed"},
        )

    def _start_timer_mode(
        self,
        *,
        mode: str,
        minutes: float,
        language: str,
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        start_method = self._first_callable(self.assistant.timer, "start", "start_timer")
        if start_method is None:
            return self._deliver_feature_unavailable(language=language, action=f"{mode}_start")

        result = start_method(float(minutes), mode)
        ok = self._result_ok(result)

        if ok:
            self.LOGGER.info("Timer start accepted: mode=%s minutes=%s", mode, minutes)
            return self._accepted_action_result(
                action=request.action if request is not None else f"{mode}_start",
                extra_metadata={
                    "source": "timer_service.start",
                    "resolved_source": resolved.source,
                    "mode": mode,
                    "minutes": float(minutes),
                },
            )

        error_text = self._result_message(result) or self._localized(
            language,
            "Nie mogę teraz uruchomić timera.",
            "I cannot start the timer right now.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action=f"{mode}_start",
            spoken_text=error_text,
            display_title="TIMER",
            display_lines=self._display_lines(error_text),
            extra_metadata={
                "resolved_source": resolved.source,
                "phase": "start_failed",
                "minutes": float(minutes),
                "mode": mode,
            },
        )