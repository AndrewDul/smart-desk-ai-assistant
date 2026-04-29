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


class TestVoiceCommandScenarios(unittest.TestCase):
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

    def test_help_command_in_english(self) -> None:
        result = self.assistant.handle_command("How can you help me")

        self.assertTrue(result)
        self.assertEqual(self._last_voice_language(), "en")
        self.assertIn("I can talk with you", self._last_voice_text())
        self.assertEqual(self._last_display_title(), "HOW I CAN HELP")
        self.assertIsNone(self.assistant.pending_follow_up)

    def test_help_command_in_polish(self) -> None:
        result = self.assistant.handle_command("Jak możesz mi pomóc")

        self.assertTrue(result)
        self.assertEqual(self._last_voice_language(), "pl")
        self.assertIn("Mogę rozmawiać z Tobą", self._last_voice_text())
        self.assertEqual(self._last_display_title(), "JAK MOGĘ POMÓC")
        self.assertIsNone(self.assistant.pending_follow_up)

    def test_introduce_self_in_english(self) -> None:
        result = self.assistant.handle_command("Who are you")

        self.assertTrue(result)
        self.assertEqual(self._last_voice_language(), "en")
        self.assertIn("My name is NeXa", self._last_voice_text())
        self.assertEqual(self._last_display_title(), "NeXa")
        self.assertIsNone(self.assistant.pending_follow_up)

    def test_introduce_self_in_polish(self) -> None:
        result = self.assistant.handle_command("Jak się nazywasz")

        self.assertTrue(result)
        self.assertEqual(self._last_voice_language(), "pl")
        self.assertIn("Nazywam się NeXa", self._last_voice_text())
        self.assertEqual(self._last_display_title(), "NeXa")
        self.assertIsNone(self.assistant.pending_follow_up)

    def test_ask_time_displays_immediately(self) -> None:
        result = self.assistant.handle_command("What time is it")

        self.assertTrue(result)
        self.assertEqual(self._last_voice_language(), "en")
        self.assertRegex(self._last_voice_text(), r"^\d{2} \d{2}$")
        self.assertEqual(self._last_display_title(), "TIME")
        self.assertIsNone(self.assistant.pending_follow_up)

    def test_show_time_in_polish_displays_time_block(self) -> None:
        result = self.assistant.handle_command("Pokaż godzinę")

        self.assertTrue(result)
        self.assertEqual(self._last_voice_language(), "pl")
        self.assertRegex(self._last_voice_text(), r"^\d{2} \d{2}$")
        self.assertEqual(self._last_display_title(), "TIME")
        self.assertIsNone(self.assistant.pending_follow_up)

    def test_exit_command_creates_confirmation_follow_up(self) -> None:
        result = self.assistant.handle_command("go to sleep")

        self.assertTrue(result)
        self.assertEqual(self._last_voice_language(), "en")
        self.assertIn("Close?", self._last_voice_text())
        self.assertEqual(self._last_display_title(), "CHAT")
        self.assertEqual(self.assistant.pending_follow_up, {"type": "confirm_exit", "lang": "en"})

    def test_exit_confirmation_no_keeps_assistant_running(self) -> None:
        self.assistant.handle_command("go to sleep")

        result = self.assistant.handle_command("no")

        self.assertTrue(result)
        self.assertEqual(self._last_voice_language(), "en")
        self.assertIn("Staying on.", self._last_voice_text())
        self.assertEqual(self._last_display_title(), "CHAT")
        self.assertIsNone(self.assistant.pending_follow_up)

    def test_exit_confirmation_yes_stops_flow(self) -> None:
        self.assistant.handle_command("go to sleep")

        result = self.assistant.handle_command("yes")

        self.assertFalse(result)
        self.assertEqual(self._last_voice_language(), "en")
        self.assertIn("Closing.", self._last_voice_text())
        self.assertEqual(self._last_display_title(), "ACTION")
        self.assertIsNone(self.assistant.pending_follow_up)

    def test_shutdown_command_reports_disabled_when_system_shutdown_is_off(self) -> None:
        result = self.assistant.handle_command("shutdown")

        self.assertTrue(result)
        self.assertEqual(self._last_voice_language(), "en")
        self.assertIn("shutdown is currently disabled", self._last_voice_text())
        self.assertEqual(self._last_display_title(), "SHUTDOWN DISABLED")
        self.assertIsNone(self.assistant.pending_follow_up)

    def test_shutdown_confirmation_reply_after_disabled_command_reports_nothing_to_confirm(self) -> None:
        self.assistant.handle_command("wyłącz system")

        result = self.assistant.handle_command("tak")

        self.assertTrue(result)
        self.assertEqual(self._last_voice_language(), "pl")
        self.assertIn("Nie ma teraz nic do potwierdzenia", self._last_voice_text())
        self.assertEqual(self._last_display_title(), "CONFIRMATION")
        self.assertIsNone(self.assistant.pending_follow_up)


if __name__ == "__main__":
    unittest.main()
