from __future__ import annotations

from dataclasses import dataclass

from modules.parsing.intent_parser import IntentResult
from modules.system.utils import append_log


@dataclass(slots=True)
class FastCommandDecision:
    action: str
    intent: IntentResult
    lane: str
    interrupts_pending: bool = False


class FastCommandLane:
    """
    Lightweight deterministic lane for command-first UX.

    Design goals:
    - handle simple system commands without entering the heavier conversation router
    - let a clear new command override an older follow-up flow
    - keep temporal answers fast and non-sticky
    """

    TEMPORAL_ACTIONS = {
        "ask_time",
        "show_time",
        "ask_date",
        "show_date",
        "ask_day",
        "show_day",
        "ask_month",
        "show_month",
        "ask_year",
        "show_year",
    }

    DIRECT_ACTIONS = {
        "timer_start",
        "timer_stop",
        "focus_start",
        "break_start",
        "introduce_self",
        "memory_store",
        "memory_recall",
        "memory_forget",
        "memory_list",
        "memory_clear",
        "reminder_create",
        "reminders_list",
        "reminder_delete",
        "reminders_clear",
        "help",
        "status",
        "exit",
        "shutdown",
    }

    ALL_ACTIONS = TEMPORAL_ACTIONS | DIRECT_ACTIONS

    _TEMPORAL_KIND_BY_ACTION = {
        "ask_time": "time",
        "show_time": "time",
        "ask_date": "date",
        "show_date": "date",
        "ask_day": "day",
        "show_day": "day",
        "ask_month": "month",
        "show_month": "month",
        "ask_year": "year",
        "show_year": "year",
    }

    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = bool(enabled)

    def classify(
        self,
        text: str,
        *,
        parser_result: IntentResult,
        pending_confirmation: bool,
        pending_follow_up: bool,
    ) -> FastCommandDecision | None:
        if not self.enabled:
            return None

        action = str(getattr(parser_result, "action", "") or "").strip().lower()
        if action in {"", "unknown", "unclear", "confirm_yes", "confirm_no"}:
            return None

        if action not in self.ALL_ACTIONS:
            return None

        interrupts_pending = bool(pending_confirmation or pending_follow_up)

        return FastCommandDecision(
            action=action,
            intent=parser_result,
            lane="deterministic_fast_path",
            interrupts_pending=interrupts_pending,
        )

    def execute(self, assistant, decision: FastCommandDecision, lang: str) -> bool:
        self._interrupt_pending_context(assistant, action=decision.action)
        assistant.voice_session.set_state("routing", detail=f"fast_lane:{decision.action}")

        append_log(
            "Fast command lane executing: "
            f"action={decision.action}, interrupts_pending={decision.interrupts_pending}"
        )

        if decision.action in self.TEMPORAL_ACTIONS:
            return self._execute_temporal(assistant, decision, lang)

        assistant._commit_language(lang)
        return assistant._execute_intent(decision.intent, lang)

    def _interrupt_pending_context(self, assistant, *, action: str) -> None:
        clear_context = getattr(assistant, "_clear_interaction_context", None)
        if callable(clear_context):
            clear_context(reason=f"fast_lane_override:{action}", close_active_window=False)
            return

        assistant.pending_confirmation = None
        assistant.pending_follow_up = None

    def _execute_temporal(self, assistant, decision: FastCommandDecision, lang: str) -> bool:
        action = decision.action
        kind = self._TEMPORAL_KIND_BY_ACTION.get(action, "time")
        spoken, title, lines = assistant._format_temporal_text(kind, lang)

        assistant.pending_confirmation = None
        assistant.pending_follow_up = None

        assistant._remember_assistant_turn(
            spoken,
            language=lang,
            metadata={
                "source": "fast_command_lane",
                "route_kind": "fast_command",
                "action": action,
                "temporal_kind": kind,
                "mode": "fast_lane",
            },
        )

        if action.startswith("show_"):
            assistant.display.show_block(
                title,
                lines,
                duration=assistant.default_overlay_seconds,
            )

        assistant.voice_out.speak(spoken, language=lang)
        assistant._commit_language(lang)
        return True