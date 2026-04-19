from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from modules.core.assistant import CoreAssistant
from modules.features.memory.service import MemoryService
from modules.features.reminders.service import ReminderService
from modules.shared.persistence.repositories import MemoryRepository, ReminderRepository


class TestTimerFocusBreakFlow(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

        self.settings = {
            "voice_input": {
                "enabled": False,
                "timeout_seconds": 8,
                "debug": False,
            },
            "voice_output": {
                "enabled": False,
                "engine": "piper",
                "default_language": "en",
                "speed": 155,
                "pitch": 58,
                "voices": {
                    "pl": "pl+f3",
                    "en": "en+f3",
                },
            },
            "display": {
                "enabled": False,
                "port": 1,
                "address": 60,
                "rotate": 0,
                "width": 128,
                "height": 64,
                "default_overlay_seconds": 10,
                "boot_overlay_seconds": 2.8,
            },
            "timers": {
                "default_focus_minutes": 25,
                "default_break_minutes": 5,
            },
            "logging": {
                "enabled": False,
            },
        }

        self.settings_patcher = patch(
            "modules.core.assistant_impl.core.load_settings",
            return_value=deepcopy(self.settings),
        )
        self.settings_patcher.start()

        self.assistant = CoreAssistant()
        self.assistant.memory = MemoryService(
            store=MemoryRepository(path=str(Path(self.temp_dir.name) / "memory.json"))
        )
        self.assistant.reminders = ReminderService(
            store=ReminderRepository(path=str(Path(self.temp_dir.name) / "reminders.json"))
        )

    def tearDown(self) -> None:
        if self.assistant.timer.status()["running"]:
            self.assistant.timer.stop()

        self.settings_patcher.stop()
        self.temp_dir.cleanup()

    def _last_voice_text(self) -> str:
        self.assertTrue(self.assistant.voice_out.messages, "No voice output captured.")
        return str(self.assistant.voice_out.messages[-1]["text"])

    def _last_voice_language(self) -> str | None:
        self.assertTrue(self.assistant.voice_out.messages, "No voice output captured.")
        return self.assistant.voice_out.messages[-1]["language"]

    def _last_display_title(self) -> str:
        self.assertTrue(self.assistant.display.blocks, "No display output captured.")
        return str(self.assistant.display.blocks[-1]["title"])

    def _finish_timer(self, *, mode: str, minutes: float, language: str) -> None:
        with self.assistant.timer._lock:
            self.assistant.timer._running = False
            self.assistant.timer._mode = None
            self.assistant.timer._remaining_seconds = 0
            self.assistant.timer._started_at = 0.0
            self.assistant.timer._ends_at = 0.0
            stop_event = self.assistant.timer._stop_event
            self.assistant.timer._stop_event = None

        if stop_event is not None:
            stop_event.set()

        self.assistant._on_timer_finished(mode=mode, minutes=minutes, language=language)

    def test_timer_start_and_stop_in_english(self) -> None:
        start_result = self.assistant.handle_command("Set timer for 10 minutes")

        self.assertTrue(start_result)
        self.assertTrue(self.assistant.timer.status()["running"])
        self.assertEqual(self.assistant.timer.status()["mode"], "timer")
        self.assertEqual(self.assistant.state["current_timer"], "timer")
        self.assertFalse(self.assistant.state["focus_mode"])
        self.assertFalse(self.assistant.state["break_mode"])
        self.assertEqual(self._last_voice_language(), "en")
        self.assertIn("Starting a timer for 10 minutes", self._last_voice_text())
        self.assertEqual(self._last_display_title(), "TIMER")

        stop_result = self.assistant.handle_command("stop timer")

        self.assertTrue(stop_result)
        self.assertFalse(self.assistant.timer.status()["running"])
        self.assertIsNone(self.assistant.state["current_timer"])
        self.assertEqual(self._last_display_title(), "TIMER STOPPED")
        self.assertIn("I stopped the active timer", self._last_voice_text())

    def test_focus_start_and_stop_in_english(self) -> None:
        start_result = self.assistant.handle_command("Focus mode twenty five minutes")

        self.assertTrue(start_result)
        self.assertTrue(self.assistant.timer.status()["running"])
        self.assertEqual(self.assistant.timer.status()["mode"], "focus")
        self.assertEqual(self.assistant.state["current_timer"], "focus")
        self.assertTrue(self.assistant.state["focus_mode"])
        self.assertFalse(self.assistant.state["break_mode"])
        self.assertEqual(self._last_display_title(), "FOCUS")
        self.assertIn("Starting focus mode for 25 minutes", self._last_voice_text())

        stop_result = self.assistant.handle_command("stop focus mode")

        self.assertTrue(stop_result)
        self.assertFalse(self.assistant.timer.status()["running"])
        self.assertIsNone(self.assistant.state["current_timer"])
        self.assertFalse(self.assistant.state["focus_mode"])
        self.assertEqual(self._last_display_title(), "TIMER STOPPED")
        self.assertIn("I stopped the active timer", self._last_voice_text())

    def test_break_start_in_polish(self) -> None:
        result = self.assistant.handle_command("Przerwa dziesięć minut")

        self.assertTrue(result)
        self.assertTrue(self.assistant.timer.status()["running"])
        self.assertEqual(self.assistant.timer.status()["mode"], "break")
        self.assertEqual(self.assistant.state["current_timer"], "break")
        self.assertFalse(self.assistant.state["focus_mode"])
        self.assertTrue(self.assistant.state["break_mode"])
        self.assertEqual(self._last_voice_language(), "pl")
        self.assertEqual(self._last_display_title(), "BREAK")
        self.assertIn("Rozpoczynam przerwę na 10 minut", self._last_voice_text())

    def test_focus_finish_clears_state_and_reports_completion(self) -> None:
        self.assistant.handle_command("Focus mode 25 minutes")

        self._finish_timer(mode="focus", minutes=25, language="en")

        self.assertFalse(self.assistant.timer.status()["running"])
        self.assertIsNone(self.assistant.state["current_timer"])
        self.assertFalse(self.assistant.state["focus_mode"])
        self.assertFalse(self.assistant.state["break_mode"])
        self.assertEqual(self._last_display_title(), "FOCUS DONE")
        self.assertIn("Focus mode finished after 25 minutes", self._last_voice_text())
        self.assertIsNone(self.assistant.pending_follow_up)

    def test_break_finish_clears_state_and_reports_completion(self) -> None:
        self.assistant.handle_command("Break mode 5 minutes")

        self._finish_timer(mode="break", minutes=5, language="en")

        self.assertFalse(self.assistant.timer.status()["running"])
        self.assertIsNone(self.assistant.state["current_timer"])
        self.assertFalse(self.assistant.state["focus_mode"])
        self.assertFalse(self.assistant.state["break_mode"])
        self.assertEqual(self._last_display_title(), "BREAK DONE")
        self.assertIn("Break finished after 5 minutes", self._last_voice_text())

    def test_timer_finish_clears_state_and_reports_completion(self) -> None:
        self.assistant.handle_command("Set timer for 3 minutes")

        self._finish_timer(mode="timer", minutes=3, language="en")

        self.assertFalse(self.assistant.timer.status()["running"])
        self.assertIsNone(self.assistant.state["current_timer"])
        self.assertEqual(self._last_display_title(), "TIMER DONE")
        self.assertIn("Timer finished after 3 minutes", self._last_voice_text())


if __name__ == "__main__":
    unittest.main()