from __future__ import annotations

import unittest

from modules.core.flows.action_flow.builders import (
    MemorySkillResponseBuilder,
    ReminderSkillResponseBuilder,
    TimerSkillResponseBuilder,
)


class _BuilderCallbacks:
    @staticmethod
    def localized(language: str, polish_text: str, english_text: str) -> str:
        return polish_text if language == "pl" else english_text

    @staticmethod
    def localized_lines(language: str, polish_lines: list[str], english_lines: list[str]) -> list[str]:
        return list(polish_lines if language == "pl" else english_lines)

    @staticmethod
    def display_lines(text: str) -> list[str]:
        compact = " ".join(str(text or "").split()).strip()
        return [compact] if compact else [""]

    @staticmethod
    def trim_text(text: str, max_len: int) -> str:
        compact = " ".join(str(text or "").split()).strip()
        if len(compact) <= max_len:
            return compact
        return compact[: max_len - 3].rstrip() + "..."

    @staticmethod
    def duration_text(seconds: int, language: str) -> str:
        if language == "pl":
            return f"{seconds} sekund"
        return f"{seconds} seconds"


def _memory_builder() -> MemorySkillResponseBuilder:
    return MemorySkillResponseBuilder(
        localize_text=_BuilderCallbacks.localized,
        localize_lines=_BuilderCallbacks.localized_lines,
        display_lines=_BuilderCallbacks.display_lines,
        trim_text=_BuilderCallbacks.trim_text,
        duration_text=_BuilderCallbacks.duration_text,
    )


def _reminder_builder() -> ReminderSkillResponseBuilder:
    return ReminderSkillResponseBuilder(
        localize_text=_BuilderCallbacks.localized,
        localize_lines=_BuilderCallbacks.localized_lines,
        display_lines=_BuilderCallbacks.display_lines,
        trim_text=_BuilderCallbacks.trim_text,
        duration_text=_BuilderCallbacks.duration_text,
    )


def _timer_builder() -> TimerSkillResponseBuilder:
    return TimerSkillResponseBuilder(
        localize_text=_BuilderCallbacks.localized,
        localize_lines=_BuilderCallbacks.localized_lines,
        display_lines=_BuilderCallbacks.display_lines,
        trim_text=_BuilderCallbacks.trim_text,
        duration_text=_BuilderCallbacks.duration_text,
    )


class ActionResponseBuildersTests(unittest.TestCase):
    def test_memory_builder_returns_follow_up_prompt_spec_for_clear_confirmation(self) -> None:
        builder = _memory_builder()

        spec = builder.build_clear_confirmation(
            language="en",
            action="memory_clear",
            resolved_source="route.primary_intent",
        )

        self.assertEqual(spec.action, "memory_clear")
        self.assertEqual(spec.follow_up_type, "confirm_memory_clear")
        self.assertEqual(spec.source, "action_memory_clear_confirmation")
        self.assertIn("resolved_source", spec.extra_metadata)

    def test_reminder_builder_returns_created_response_with_duration_context(self) -> None:
        builder = _reminder_builder()

        spec = builder.build_create_response(
            language="en",
            action="reminder_create",
            outcome_status="created",
            resolved_source="route.primary_intent",
            seconds=300,
            reminder_id="r-1",
            message="call back",
        )

        self.assertEqual(spec.display_title, "REMINDER SAVED")
        self.assertEqual(spec.extra_metadata["reminder_id"], "r-1")
        self.assertEqual(spec.extra_metadata["seconds"], 300)
        self.assertTrue(any("300 seconds" in line for line in spec.display_lines))

    def test_timer_builder_returns_failure_response_spec(self) -> None:
        builder = _timer_builder()

        spec = builder.build_start_failure(
            language="en",
            action="focus_start",
            outcome_message="Timer busy",
            resolved_source="route.primary_intent",
            phase="start_failed",
            minutes=25,
            mode="focus",
        )

        self.assertEqual(spec.action, "focus_start")
        self.assertEqual(spec.display_title, "TIMER")
        self.assertEqual(spec.spoken_text, "Timer busy")
        self.assertEqual(spec.extra_metadata["mode"], "focus")
        self.assertEqual(spec.extra_metadata["minutes"], 25.0)


if __name__ == "__main__":
    unittest.main()