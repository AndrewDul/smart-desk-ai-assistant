from __future__ import annotations

import unittest

from modules.core.assistant_impl.response_mixin import CoreAssistantResponseMixin


class _Host(CoreAssistantResponseMixin):
    def __init__(self) -> None:
        self.state = {
            "current_timer": None,
            "focus_mode": False,
            "break_mode": False,
        }
        self.last_language = "en"
        self.notifications: list[dict[str, object]] = []
        self.ai_broker_calls: list[tuple[str, str]] = []

    def _timer_type_from_payload(self, payload):
        return str(payload.get("mode") or payload.get("timer_type") or "timer")

    def _timer_minutes_from_payload(self, payload):
        return float(payload.get("minutes") or 0.0)

    def _normalize_lang(self, language):
        return str(language or "en")

    def _localized(self, language: str, polish: str, english: str) -> str:
        return polish if language == "pl" else english

    def _minutes_text(self, minutes: float, language: str) -> str:
        del language
        if float(minutes).is_integer():
            return str(int(minutes)) + " minutes"
        return f"{minutes:.1f} minutes"

    def _display_lines(self, text: str) -> list[str]:
        return [str(text)]

    def _save_state(self) -> None:
        return None

    def _deliver_async_notification(self, **kwargs) -> None:
        self.notifications.append(dict(kwargs))

    def _enter_ai_broker_focus_sentinel_mode(self, *, reason: str = "") -> dict[str, object] | None:
        self.ai_broker_calls.append(("focus", reason))
        return {
            "mode": "focus_sentinel",
            "owner": "monitor_path",
            "profile": {"heavy_lane_cadence_hz": 1.0},
        }

    def _enter_ai_broker_idle_baseline(self, *, reason: str = "") -> dict[str, object] | None:
        self.ai_broker_calls.append(("idle", reason))
        return {
            "mode": "idle_baseline",
            "owner": "balanced",
            "profile": {"heavy_lane_cadence_hz": 2.0},
        }


class AiBrokerFocusHookTests(unittest.TestCase):
    def test_focus_timer_started_enters_focus_sentinel_mode(self) -> None:
        host = _Host()

        host._on_timer_started(mode="focus", minutes=25, language="en")

        self.assertEqual(host.state["current_timer"], "focus")
        self.assertTrue(host.state["focus_mode"])
        self.assertEqual(host.ai_broker_calls, [("focus", "focus_timer_started")])

    def test_non_focus_timer_started_does_not_switch_into_focus_sentinel(self) -> None:
        host = _Host()

        host._on_timer_started(mode="break", minutes=5, language="en")

        self.assertEqual(host.state["current_timer"], "break")
        self.assertFalse(host.state["focus_mode"])
        self.assertEqual(host.ai_broker_calls, [])

    def test_focus_timer_finished_returns_to_idle_baseline(self) -> None:
        host = _Host()
        host.state["current_timer"] = "focus"
        host.state["focus_mode"] = True

        host._on_timer_finished(mode="focus", minutes=25, language="en")

        self.assertIsNone(host.state["current_timer"])
        self.assertFalse(host.state["focus_mode"])
        self.assertEqual(host.ai_broker_calls, [("idle", "focus_timer_finished")])

    def test_focus_timer_stopped_returns_to_idle_baseline(self) -> None:
        host = _Host()
        host.state["current_timer"] = "focus"
        host.state["focus_mode"] = True

        host._on_timer_stopped(mode="focus", language="en")

        self.assertIsNone(host.state["current_timer"])
        self.assertFalse(host.state["focus_mode"])
        self.assertEqual(host.ai_broker_calls, [("idle", "focus_timer_stopped")])


if __name__ == "__main__":
    unittest.main()