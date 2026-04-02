from __future__ import annotations

import sys
import tempfile
import types
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


fake_display_module = types.ModuleType("modules.display")
fake_voice_out_module = types.ModuleType("modules.voice_out")
fake_text_input_module = types.ModuleType("modules.text_input")
fake_whisper_input_module = types.ModuleType("modules.whisper_input")


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

sys.modules["modules.display"] = fake_display_module
sys.modules["modules.voice_out"] = fake_voice_out_module
sys.modules["modules.text_input"] = fake_text_input_module
sys.modules["modules.whisper_input"] = fake_whisper_input_module

from modules.assistant_logic import CoreAssistant


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
            "modules.assistant_logic.load_json",
            side_effect=lambda path, default: deepcopy(default),
        )
        self.save_json_patcher = patch("modules.assistant_logic.save_json", side_effect=lambda path, data: None)
        self.settings_patcher = patch("modules.assistant_logic.load_settings", return_value=deepcopy(self.settings))
        self.ensure_files_patcher = patch("modules.assistant_logic.ensure_project_files", side_effect=lambda: None)
        self.log_patcher = patch("modules.assistant_logic.append_log", side_effect=lambda message: None)

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
        self.assertIn("I can remember information", self._last_voice_text())
        self.assertEqual(self._last_display_title(), "HOW I CAN HELP")

    def test_help_command_in_polish(self) -> None:
        result = self.assistant.handle_command("Jak możesz mi pomóc")

        self.assertTrue(result)
        self.assertEqual(self._last_voice_language(), "pl")
        self.assertIn("Mogę zapamiętywać informacje", self._last_voice_text())
        self.assertEqual(self._last_display_title(), "CO POTRAFIĘ")

    def test_introduce_self_then_capture_and_save_name(self) -> None:
        first = self.assistant.handle_command("Introduce yourself")
        self.assertTrue(first)
        self.assertEqual(self.assistant.pending_follow_up["type"], "capture_name")

        second = self.assistant.handle_command("My name is Andrew")
        self.assertTrue(second)
        self.assertEqual(self.assistant.pending_follow_up["type"], "confirm_save_name")
        self.assertEqual(self.assistant.pending_follow_up["name"], "Andrew")

        third = self.assistant.handle_command("yes")
        self.assertTrue(third)
        self.assertEqual(self.assistant.user_profile["conversation_partner_name"], "Andrew")
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertIn("remember your name", self._last_voice_text().lower())

    def test_introduce_self_then_decline_name_save(self) -> None:
        self.assistant.handle_command("Introduce yourself")
        self.assistant.handle_command("Mam na imię Andrzej")
        self.assistant.handle_command("nie")

        self.assertEqual(self.assistant.user_profile["conversation_partner_name"], "")
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertIn("Nie zapisuję twojego imienia", self._last_voice_text())

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

    def test_display_offer_no_does_not_create_new_overlay(self) -> None:
        initial_blocks = len(self.assistant.display.blocks)
        self.assistant.handle_command("What year is it")
        blocks_after_question = len(self.assistant.display.blocks)

        result = self.assistant.handle_command("no")

        self.assertTrue(result)
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertEqual(len(self.assistant.display.blocks), blocks_after_question)
        self.assertGreaterEqual(blocks_after_question, initial_blocks)

    def test_memory_store_and_recall_flow(self) -> None:
        save_result = self.assistant.handle_command("Remember that keys are in the kitchen")
        self.assertTrue(save_result)

        recall_result = self.assistant.handle_command("Where are my keys")
        self.assertTrue(recall_result)

        self.assertIn("kitchen", self._last_voice_text().lower())
        self.assertIsNotNone(self.assistant.pending_follow_up)
        self.assertEqual(self.assistant.pending_follow_up["type"], "display_offer")

    def test_memory_store_and_recall_in_polish(self) -> None:
        self.assistant.handle_command("Zapamiętaj że klucze są w kuchni")
        self.assistant.handle_command("Gdzie są moje klucze")

        self.assertIn("kuchni", self._last_voice_text().lower())
        self.assertEqual(self.assistant.pending_follow_up["type"], "display_offer")
        self.assertEqual(self.assistant.pending_follow_up["lang"], "pl")

    def test_memory_forget_requires_confirmation(self) -> None:
        self.assistant.handle_command("Remember that keys are in the kitchen")

        result = self.assistant.handle_command("Forget keys")

        self.assertTrue(result)
        self.assertEqual(self.assistant.pending_follow_up["type"], "confirm_memory_forget")
        self.assertIn("remove keys from memory", self._last_voice_text().lower())

    def test_memory_forget_yes_deletes_item(self) -> None:
        self.assistant.handle_command("Remember that keys are in the kitchen")
        self.assistant.handle_command("Forget keys")

        result = self.assistant.handle_command("yes")

        self.assertTrue(result)
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertIn("removed", self._last_voice_text().lower())
        self.assertIsNone(self.assistant.memory.recall("keys"))

    def test_memory_forget_no_keeps_item(self) -> None:
        self.assistant.handle_command("Zapamiętaj że klucze są w kuchni")
        self.assistant.handle_command("Zapomnij o kluczach")

        result = self.assistant.handle_command("nie")

        self.assertTrue(result)
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertIn("nie usuwam", self._last_voice_text().lower())
        self.assertIsNotNone(self.assistant.memory.recall("klucz"))

    def test_memory_clear_requires_confirmation(self) -> None:
        self.assistant.handle_command("Remember that keys are in the kitchen")

        result = self.assistant.handle_command("clear memory")

        self.assertTrue(result)
        self.assertEqual(self.assistant.pending_follow_up["type"], "confirm_memory_clear")
        self.assertIn("clear all memory", self._last_voice_text().lower())

    def test_memory_clear_yes_clears_items(self) -> None:
        self.assistant.handle_command("Remember that keys are in the kitchen")
        self.assistant.handle_command("Remember that phone is on desk")
        self.assistant.handle_command("clear memory")

        result = self.assistant.handle_command("yes")

        self.assertTrue(result)
        self.assertEqual(self.assistant.memory.get_all(), {})
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertIn("cleared memory", self._last_voice_text().lower())

    def test_memory_clear_no_keeps_items(self) -> None:
        self.assistant.handle_command("Remember that keys are in the kitchen")
        self.assistant.handle_command("clear memory")

        result = self.assistant.handle_command("no")

        self.assertTrue(result)
        self.assertIsNotNone(self.assistant.memory.recall("keys"))
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertIn("will not clear memory", self._last_voice_text().lower())

    def test_follow_up_yes_keeps_polish_context(self) -> None:
        self.assistant.handle_command("Która godzina")

        result = self.assistant.handle_command("yes")

        self.assertTrue(result)
        self.assertEqual(self._last_voice_language(), "pl")
        self.assertIn("Pokazuję", self._last_voice_text())

    def test_follow_up_yes_keeps_english_context(self) -> None:
        self.assistant.handle_command("What date is it")

        result = self.assistant.handle_command("tak")

        self.assertTrue(result)
        self.assertEqual(self._last_voice_language(), "en")
        self.assertIn("showing it on the screen", self._last_voice_text().lower())

    def test_reminder_creation_flow(self) -> None:
        result = self.assistant.handle_command("Remind me in 30 seconds to drink water")

        self.assertTrue(result)
        reminders = self.assistant.reminders.list_all()
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["message"], "drink water")
        self.assertIn("30 seconds", self._last_voice_text())

    def test_reminder_delete_requires_confirmation(self) -> None:
        self.assistant.handle_command("Remind me in 30 seconds to drink water")

        result = self.assistant.handle_command("delete reminder drink water")

        self.assertTrue(result)
        self.assertEqual(self.assistant.pending_follow_up["type"], "confirm_reminder_delete")
        self.assertIn("delete the reminder drink water", self._last_voice_text().lower())

    def test_reminder_delete_yes_removes_item(self) -> None:
        self.assistant.handle_command("Remind me in 30 seconds to drink water")
        self.assistant.handle_command("delete reminder drink water")

        result = self.assistant.handle_command("yes")

        self.assertTrue(result)
        self.assertEqual(len(self.assistant.reminders.list_all()), 0)
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertIn("deleted the reminder", self._last_voice_text().lower())

    def test_reminder_delete_no_keeps_item(self) -> None:
        self.assistant.handle_command("Remind me in 30 seconds to drink water")
        self.assistant.handle_command("delete reminder drink water")

        result = self.assistant.handle_command("no")

        self.assertTrue(result)
        self.assertEqual(len(self.assistant.reminders.list_all()), 1)
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertIn("will not delete the reminder", self._last_voice_text().lower())

    def test_clear_reminders_requires_confirmation(self) -> None:
        self.assistant.handle_command("Remind me in 30 seconds to drink water")
        self.assistant.handle_command("Remind me in 60 seconds to stand up")

        result = self.assistant.handle_command("clear reminders")

        self.assertTrue(result)
        self.assertEqual(self.assistant.pending_follow_up["type"], "confirm_reminders_clear")
        self.assertIn("delete all reminders", self._last_voice_text().lower())

    def test_clear_reminders_yes_removes_all(self) -> None:
        self.assistant.handle_command("Remind me in 30 seconds to drink water")
        self.assistant.handle_command("Remind me in 60 seconds to stand up")
        self.assistant.handle_command("clear reminders")

        result = self.assistant.handle_command("yes")

        self.assertTrue(result)
        self.assertEqual(len(self.assistant.reminders.list_all()), 0)
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertIn("deleted all reminders", self._last_voice_text().lower())

    def test_clear_reminders_no_keeps_all(self) -> None:
        self.assistant.handle_command("Remind me in 30 seconds to drink water")
        self.assistant.handle_command("clear reminders")

        result = self.assistant.handle_command("no")

        self.assertTrue(result)
        self.assertEqual(len(self.assistant.reminders.list_all()), 1)
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertIn("will not delete reminders", self._last_voice_text().lower())

    def test_timer_without_duration_asks_follow_up(self) -> None:
        result = self.assistant.handle_command("Set timer")

        self.assertTrue(result)
        self.assertEqual(self.assistant.pending_follow_up["type"], "timer_duration")
        self.assertIn("How long should I set the timer for", self._last_voice_text())

    def test_timer_follow_up_starts_timer(self) -> None:
        self.assistant.pending_follow_up = {"type": "timer_duration", "lang": "en"}
        self.assistant._start_timer_mode = MagicMock(return_value=True)

        result = self.assistant.handle_command("10 minutes")

        self.assertTrue(result)
        self.assistant._start_timer_mode.assert_called_once_with(10.0, "timer", "en")
        self.assertIsNone(self.assistant.pending_follow_up)

    def test_focus_without_duration_asks_follow_up(self) -> None:
        result = self.assistant.handle_command("Focus mode")

        self.assertTrue(result)
        self.assertEqual(self.assistant.pending_follow_up["type"], "focus_duration")
        self.assertIn("How long should the focus session be", self._last_voice_text())

    def test_focus_follow_up_starts_focus_session(self) -> None:
        self.assistant.pending_follow_up = {"type": "focus_duration", "lang": "en"}
        self.assistant._start_timer_mode = MagicMock(return_value=True)

        result = self.assistant.handle_command("25 minutes")

        self.assertTrue(result)
        self.assistant._start_timer_mode.assert_called_once_with(25.0, "focus", "en")
        self.assertIsNone(self.assistant.pending_follow_up)

    def test_post_focus_break_offer_yes_then_duration(self) -> None:
        self.assistant.pending_follow_up = {"type": "post_focus_break_offer", "lang": "en"}
        self.assistant._start_timer_mode = MagicMock(return_value=True)

        first = self.assistant.handle_command("yes")
        self.assertTrue(first)
        self.assertEqual(self.assistant.pending_follow_up["type"], "break_duration")

        second = self.assistant.handle_command("5 minutes")
        self.assertTrue(second)
        self.assistant._start_timer_mode.assert_called_once_with(5.0, "break", "en")
        self.assertIsNone(self.assistant.pending_follow_up)

    def test_post_focus_break_offer_direct_duration(self) -> None:
        self.assistant.pending_follow_up = {"type": "post_focus_break_offer", "lang": "pl"}
        self.assistant._start_timer_mode = MagicMock(return_value=True)

        result = self.assistant.handle_command("10 minut")

        self.assertTrue(result)
        self.assistant._start_timer_mode.assert_called_once_with(10.0, "break", "pl")
        self.assertIsNone(self.assistant.pending_follow_up)

    def test_timer_stop_when_nothing_is_running(self) -> None:
        result = self.assistant.handle_command("focus off")

        self.assertTrue(result)
        self.assertIn("No timer is currently running", self._last_voice_text())

    def test_exit_requires_confirmation(self) -> None:
        result = self.assistant.handle_command("goodbye")

        self.assertTrue(result)
        self.assertEqual(self.assistant.pending_follow_up["type"], "confirm_exit")
        self.assertIn("close the assistant", self._last_voice_text().lower())

    def test_exit_yes_returns_false(self) -> None:
        self.assistant.handle_command("goodbye")

        result = self.assistant.handle_command("yes")

        self.assertFalse(result)
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertIn("closing the assistant", self._last_voice_text().lower())

    def test_exit_no_keeps_running(self) -> None:
        self.assistant.handle_command("goodbye")

        result = self.assistant.handle_command("no")

        self.assertTrue(result)
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertIn("stay on", self._last_voice_text().lower())

    def test_shutdown_requires_confirmation(self) -> None:
        result = self.assistant.handle_command("shutdown")

        self.assertTrue(result)
        self.assertEqual(self.assistant.pending_follow_up["type"], "confirm_shutdown")
        self.assertIn("shut down the system", self._last_voice_text().lower())

    def test_shutdown_yes_returns_false_and_sets_flag(self) -> None:
        self.assistant.handle_command("shutdown")

        result = self.assistant.handle_command("yes")

        self.assertFalse(result)
        self.assertTrue(self.assistant.shutdown_requested)
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertIn("shutting down the system", self._last_voice_text().lower())

    def test_shutdown_no_keeps_running(self) -> None:
        self.assistant.handle_command("shutdown")

        result = self.assistant.handle_command("no")

        self.assertTrue(result)
        self.assertFalse(self.assistant.shutdown_requested)
        self.assertIsNone(self.assistant.pending_follow_up)
        self.assertIn("will not shut down the system", self._last_voice_text().lower())

    def test_unclear_command_produces_confirmation(self) -> None:
        result = self.assistant.handle_command("statu")

        self.assertTrue(result)
        self.assertIsNotNone(self.assistant.pending_confirmation)
        self.assertIn("Did you mean", self._last_voice_text())

    def test_confirmation_yes_executes_suggested_action(self) -> None:
        self.assistant.handle_command("statu")
        result = self.assistant.handle_command("yes")

        self.assertTrue(result)
        self.assertIsNone(self.assistant.pending_confirmation)
        self.assertEqual(self._last_display_title(), "STATUS")


if __name__ == "__main__":
    unittest.main()