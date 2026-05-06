from __future__ import annotations

import unittest

from modules.core.assistant_impl.focus_vision_mixin import CoreAssistantFocusVisionMixin
from modules.core.assistant_impl.response_mixin import CoreAssistantResponseMixin


class _FakeFocusVisionService:
    def __init__(self) -> None:
        self.started_languages: list[str] = []
        self.stop_count = 0
        self.running = False

    def start(self, *, language: str = "en") -> bool:
        self.started_languages.append(language)
        self.running = True
        return True

    def stop(self) -> None:
        self.stop_count += 1
        self.running = False

    def status(self) -> dict[str, object]:
        return {
            "running": self.running,
            "started_languages": list(self.started_languages),
            "stop_count": self.stop_count,
        }


class _Host(CoreAssistantFocusVisionMixin, CoreAssistantResponseMixin):
    def __init__(self) -> None:
        self.state = {
            "current_timer": None,
            "focus_mode": False,
            "break_mode": False,
        }
        self.last_language = "en"
        self.focus_vision = _FakeFocusVisionService()
        self.ai_broker_calls: list[tuple[str, str]] = []
        self.notifications: list[dict[str, object]] = []

    def _timer_type_from_payload(self, payload):
        return str(payload.get("mode") or payload.get("timer_type") or "timer")

    def _timer_minutes_from_payload(self, payload):
        return float(payload.get("minutes") or 0.0)

    def _normalize_lang(self, language):
        return "pl" if str(language or "").lower().startswith("pl") else "en"

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
        return {"mode": "focus_sentinel"}

    def _enter_ai_broker_idle_baseline(self, *, reason: str = "") -> dict[str, object] | None:
        self.ai_broker_calls.append(("idle", reason))
        return {"mode": "idle_baseline"}

    def _send_timer_countdown_to_visual_shell(self, **kwargs) -> None:
        return None

    def _clear_timer_countdown_from_visual_shell(self, **kwargs) -> None:
        return None


class FocusVisionFocusModeHookTests(unittest.TestCase):
    def test_focus_timer_start_starts_focus_vision_with_turn_language(self) -> None:
        host = _Host()

        host._on_timer_started(mode="focus", minutes=25, language="pl")

        self.assertTrue(host.state["focus_mode"])
        self.assertEqual(host.ai_broker_calls, [("focus", "focus_timer_started")])
        self.assertEqual(host.focus_vision.started_languages, ["pl"])
        self.assertTrue(host.focus_vision.running)

    def test_non_focus_timer_does_not_start_focus_vision(self) -> None:
        host = _Host()

        host._on_timer_started(mode="timer", minutes=5, language="en")

        self.assertFalse(host.state["focus_mode"])
        self.assertEqual(host.focus_vision.started_languages, [])
        self.assertFalse(host.focus_vision.running)

    def test_focus_timer_finished_stops_focus_vision(self) -> None:
        host = _Host()
        host.focus_vision.start(language="en")
        host.state["focus_mode"] = True

        host._on_timer_finished(mode="focus", minutes=25, language="en")

        self.assertFalse(host.state["focus_mode"])
        self.assertEqual(host.focus_vision.stop_count, 1)
        self.assertFalse(host.focus_vision.running)
        self.assertEqual(host.ai_broker_calls, [("idle", "focus_timer_finished")])

    def test_focus_timer_stopped_stops_focus_vision(self) -> None:
        host = _Host()
        host.focus_vision.start(language="en")
        host.state["focus_mode"] = True

        host._on_timer_stopped(mode="focus", language="en")

        self.assertFalse(host.state["focus_mode"])
        self.assertEqual(host.focus_vision.stop_count, 1)
        self.assertFalse(host.focus_vision.running)
        self.assertEqual(host.ai_broker_calls, [("idle", "focus_timer_stopped")])


if __name__ == "__main__":
    unittest.main()
