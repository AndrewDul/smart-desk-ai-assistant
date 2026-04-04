from __future__ import annotations

import sys
import tempfile
import types
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

fake_display_module = types.ModuleType("modules.io.display")
fake_voice_out_module = types.ModuleType("modules.io.voice_out")
fake_text_input_module = types.ModuleType("modules.io.text_input")
fake_whisper_input_module = types.ModuleType("modules.io.whisper_input")


class FakeDisplay:
    def __init__(self, *args, **kwargs) -> None:
        self.blocks: list[dict] = []
        self.closed = False

    def show_block(self, title, lines, duration=10.0) -> None:
        self.blocks.append(
            {
                "title": title,
                "lines": list(lines),
                "duration": duration,
            }
        )

    def show_status(self, state, timer_status, duration=10.0) -> None:
        self.blocks.append(
            {
                "title": "STATUS",
                "lines": [str(state), str(timer_status)],
                "duration": duration,
            }
        )

    def clear_overlay(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class FakeVoiceOutput:
    def __init__(self, *args, **kwargs) -> None:
        self.messages: list[dict] = []

    def speak(self, text: str, language: str | None = None) -> None:
        self.messages.append({"text": text, "language": language})


class FakeTextInput:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def listen(self, timeout: float = 8.0, debug: bool = False):
        return None


class FakeWhisperVoiceInput:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def listen(self, timeout: float = 8.0, debug: bool = False):
        return None


fake_display_module.ConsoleDisplay = FakeDisplay
fake_voice_out_module.VoiceOutput = FakeVoiceOutput
fake_text_input_module.TextInput = FakeTextInput
fake_whisper_input_module.WhisperVoiceInput = FakeWhisperVoiceInput

sys.modules["modules.io.display"] = fake_display_module
sys.modules["modules.io.voice_out"] = fake_voice_out_module
sys.modules["modules.io.text_input"] = fake_text_input_module
sys.modules["modules.io.whisper_input"] = fake_whisper_input_module

from modules.core.assistant import CoreAssistant


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
                "enabled": True,
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

        self.load_json_patcher = patch(
            "modules.core.assistant.load_json",
            side_effect=lambda path, default: deepcopy(default),
        )
        self.save_json_patcher = patch("modules.core.assistant.save_json", side_effect=lambda path, data: None)
        self.settings_patcher = patch("modules.core.assistant.load_settings", return_value=deepcopy(self.settings))
        self.ensure_files_patcher = patch("modules.core.assistant.ensure_project_files", side_effect=lambda: None)
        self.log_patcher = patch("modules.core.assistant.append_log", side_effect=lambda message: None)

        self.load_json_patcher.start()
        self.save_json_patcher.start()
        self.settings_patcher.start()
        self.ensure_files_patcher.start()
        self.log_patcher.start()

        self.assistant = CoreAssistant()
        self.assistant.memory.path = Path(self.temp_dir.name) / "memory.json"
        self.assistant.reminders.path = Path(self.temp_dir.name) / "reminders.json"

    def tearDown(self) -> None:
        self.load_json_patcher.stop()
        self.save_json_patcher.stop()
        self.settings_patcher.stop()
        self.ensure_files_patcher.stop()
        self.log_patcher.stop()
        self.temp_dir.cleanup()

    def _last_voice_text(self) -> str:
        self.assertTrue(self.assistant.voice_out.messages, "No voice output captured.")
        return self.assistant.voice_out.messages[-1]["text"]

    def _last_voice_language(self) -> str | None:
        self.assertTrue(self.assistant.voice_out.messages, "No voice output captured.")
        return self.assistant.voice_out.messages[-1]["language"]

    def _last_display_title(self) -> str:
        self.assertTrue(self.assistant.display.blocks, "No display output captured.")
        return self.assistant.display.blocks[-1]["title"]

    def test_help_command_in_english(self) -> None:
        result = self.assistant.handle_command("How can you help me")

        self.assertTrue(result)
        self.assertEqual(self._last_voice_language(), "en")
        self.assertIn("I can help you in a few main ways", self._last_voice_text())
        self.assertEqual(self._last_display_title(), "HOW I CAN HELP")

    def test_help_command_in_polish(self) -> None:
        result = self.assistant.handle_command("Jak możesz mi pomóc")

        self.assertTrue(result)
        self.assertEqual(self._last_voice_language(), "pl")
        self.assertIn("Mogę pomagać ci na kilka głównych sposobów", self._last_voice_text())
        self.assertEqual(self._last_display_title(), "JAK MOGĘ POMÓC")

    def test_introduce_self_in_english_does_not_start_name_capture(self) -> None:
        result = self.assistant.handle_command("Who are you")

        self.assertTrue(result)
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertEqual(self._last_voice_language(), "en")
        self.assertIn("I am Smart Assistant", self._last_voice_text())
        self.assertEqual(self._last_display_title(), "SMART ASSISTANT")

    def test_introduce_self_in_polish_does_not_start_name_capture(self) -> None:
        result = self.assistant.handle_command("Jak się nazywasz")

        self.assertTrue(result)
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertEqual(self._last_voice_language(), "pl")
        self.assertIn("Jestem Smart Assistant", self._last_voice_text())
        self.assertEqual(self._last_display_title(), "SMART ASSISTANT")

    def test_ask_time_offers_display_follow_up(self) -> None:
        result = self.assistant.handle_command("What time is it")

        self.assertTrue(result)
        self.assertIsNotNone(self.assistant.pending_follow_up)
        self.assertEqual(self.assistant.pending_follow_up["type"], "display_offer")
        self.assertEqual(self.assistant.pending_follow_up["lang"], "en")
        self.assertEqual(self._last_voice_language(), "en")
        self.assertIn("Would you like me to show that on the screen", self._last_voice_text())

    def test_show_time_displays_immediately(self) -> None:
        result = self.assistant.handle_command("Pokaż godzinę")

        self.assertTrue(result)
        self.assertEqual(self._last_display_title(), "GODZINA")
        self.assertIsNone(self.assistant.pending_follow_up)

    def test_display_offer_yes_shows_block(self) -> None:
        self.assistant.handle_command("What date is it")
        self.assertEqual(self.assistant.pending_follow_up["type"], "display_offer")

        result = self.assistant.handle_command("yes")

        self.assertTrue(result)
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertEqual(self._last_display_title(), "DATE")
        self.assertIn("showing it on the screen", self._last_voice_text().lower())

    def test_display_offer_no_keeps_existing_overlay_count(self) -> None:
        self.assistant.handle_command("What year is it")
        blocks_after_question = len(self.assistant.display.blocks)

        result = self.assistant.handle_command("no")

        self.assertTrue(result)
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertEqual(len(self.assistant.display.blocks), blocks_after_question)

    def test_exit_command_creates_confirmation_follow_up(self) -> None:
        result = self.assistant.handle_command("go to sleep")

        self.assertTrue(result)
        self.assertIsNotNone(self.assistant.pending_follow_up)
        self.assertEqual(self.assistant.pending_follow_up["type"], "confirm_exit")
        self.assertEqual(self.assistant.pending_follow_up["lang"], "en")
        self.assertEqual(self._last_display_title(), "CLOSE ASSISTANT?")
        self.assertIn("Are you sure I should close the assistant", self._last_voice_text())

    def test_exit_confirmation_no_keeps_assistant_running(self) -> None:
        self.assistant.handle_command("wyłącz asystenta")

        result = self.assistant.handle_command("nie")

        self.assertTrue(result)
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertIn("Zostaję włączona", self._last_voice_text())

    def test_exit_confirmation_yes_stops_flow(self) -> None:
        self.assistant.handle_command("turn off assistant")

        result = self.assistant.handle_command("yes")

        self.assertFalse(result)
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertIn("Closing the assistant", self._last_voice_text())

    def test_shutdown_command_creates_confirmation_follow_up(self) -> None:
        result = self.assistant.handle_command("shutdown")

        self.assertTrue(result)
        self.assertIsNotNone(self.assistant.pending_follow_up)
        self.assertEqual(self.assistant.pending_follow_up["type"], "confirm_shutdown")
        self.assertEqual(self.assistant.pending_follow_up["lang"], "en")
        self.assertEqual(self._last_display_title(), "SHUT DOWN SYSTEM?")

    def test_shutdown_confirmation_yes_sets_shutdown_flag(self) -> None:
        self.assistant.handle_command("wyłącz system")

        result = self.assistant.handle_command("tak")

        self.assertFalse(result)
        self.assertTrue(self.assistant.shutdown_requested)
        self.assertIn("Wyłączam system", self._last_voice_text())


if __name__ == "__main__":
    unittest.main()