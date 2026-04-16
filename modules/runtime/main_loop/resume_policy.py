from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from modules.shared.logging.logger import append_log

if TYPE_CHECKING:
    from modules.core.assistant import CoreAssistant


@dataclass(slots=True)
class ResumeWindowDecision:
    action: str
    reason: str
    response_delivered: bool
    follow_up_required: bool
    full_text_chars: int
    route_kind: str = ""
    response_source: str = ""


class ResumePolicyService:
    """
    Decide how the assistant should resume listening after finishing a response.

    Actions:
    - follow_up: keep a dedicated follow-up window open
    - grace: keep a short grace window open for natural continued conversation
    - standby: return immediately to wake-gate standby
    """

    def decide(self, assistant: CoreAssistant) -> ResumeWindowDecision:
        if bool(getattr(assistant, "shutdown_requested", False)):
            decision = ResumeWindowDecision(
                action="standby",
                reason="shutdown_requested",
                response_delivered=False,
                follow_up_required=False,
                full_text_chars=0,
            )
            self._store_last_decision(assistant, decision)
            return decision

        follow_up_required = bool(
            getattr(assistant, "pending_confirmation", None)
            or getattr(assistant, "pending_follow_up", None)
        )
        if follow_up_required:
            decision = ResumeWindowDecision(
                action="follow_up",
                reason="pending_follow_up",
                response_delivered=self._response_delivered(assistant),
                follow_up_required=True,
                full_text_chars=self._full_text_chars(assistant),
                route_kind=self._route_kind(assistant),
                response_source=self._response_source(assistant),
            )
            self._store_last_decision(assistant, decision)
            return decision

        delivered = self._response_delivered(assistant)
        full_text_chars = self._full_text_chars(assistant)
        if delivered or full_text_chars > 0:
            decision = ResumeWindowDecision(
                action="grace",
                reason="response_delivered",
                response_delivered=delivered,
                follow_up_required=False,
                full_text_chars=full_text_chars,
                route_kind=self._route_kind(assistant),
                response_source=self._response_source(assistant),
            )
            self._store_last_decision(assistant, decision)
            return decision

        decision = ResumeWindowDecision(
            action="standby",
            reason="no_delivered_response",
            response_delivered=False,
            follow_up_required=False,
            full_text_chars=full_text_chars,
            route_kind=self._route_kind(assistant),
            response_source=self._response_source(assistant),
        )
        self._store_last_decision(assistant, decision)
        return decision

    def _response_snapshot(self, assistant: CoreAssistant) -> dict[str, Any]:
        snapshot = getattr(assistant, "_last_response_delivery_snapshot", None)
        return dict(snapshot or {}) if isinstance(snapshot, dict) else {}

    def _response_delivered(self, assistant: CoreAssistant) -> bool:
        snapshot = self._response_snapshot(assistant)
        return bool(snapshot.get("delivered", False))

    def _full_text_chars(self, assistant: CoreAssistant) -> int:
        snapshot = self._response_snapshot(assistant)
        try:
            return max(0, int(snapshot.get("full_text_chars", 0) or 0))
        except (TypeError, ValueError):
            return 0

    def _route_kind(self, assistant: CoreAssistant) -> str:
        snapshot = self._response_snapshot(assistant)
        return str(snapshot.get("route_kind", "") or "").strip()

    def _response_source(self, assistant: CoreAssistant) -> str:
        snapshot = self._response_snapshot(assistant)
        return str(snapshot.get("source", "") or "").strip()

    def _store_last_decision(
        self,
        assistant: CoreAssistant,
        decision: ResumeWindowDecision,
    ) -> None:
        assistant._last_resume_policy_snapshot = {
            "action": decision.action,
            "reason": decision.reason,
            "response_delivered": decision.response_delivered,
            "follow_up_required": decision.follow_up_required,
            "full_text_chars": decision.full_text_chars,
            "route_kind": decision.route_kind,
            "response_source": decision.response_source,
        }

        benchmark_service = getattr(assistant, "turn_benchmark_service", None)
        annotate = getattr(benchmark_service, "annotate_last_completed_turn", None)
        if callable(annotate):
            try:
                annotate(resume_policy=dict(assistant._last_resume_policy_snapshot))
            except Exception:
                pass

        append_log(
            "Resume policy decided: "
            f"action={decision.action}, "
            f"reason={decision.reason}, "
            f"response_delivered={decision.response_delivered}, "
            f"follow_up_required={decision.follow_up_required}, "
            f"chars={decision.full_text_chars}, "
            f"route_kind={decision.route_kind or '-'}, "
            f"source={decision.response_source or '-'}"
        )


__all__ = ["ResumePolicyService", "ResumeWindowDecision"]