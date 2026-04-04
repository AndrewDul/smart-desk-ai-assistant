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

        self.log_assistant_patcher = patch("modules.core.assistant.append_log", side_effect=lambda message: None)
        self.log_timer_patcher = patch("modules.core.handlers_timer.append_log", side_effect=lambda message: None)
        self.log_focus_patcher = patch("modules.core.handlers_focus.append_log", side_effect=lambda message: None)
        self.log_break_patcher = patch("modules.core.handlers_break.append_log", side_effect=lambda message: None)

        self.load_json_patcher.start()
        self.save_json_patcher.start()
        self.settings_patcher.start()
        self.ensure_files_patcher.start()
        self.log_assistant_patcher.start()
        self.log_timer_patcher.start()
        self.log_focus_patcher.start()
        self.log_break_patcher.start()

        self.assistant = CoreAssistant()
        self.assistant.memory.path = Path(self.temp_dir.name) / "memory.json"
        self.assistant.reminders.path = Path(self.temp_dir.name) / "reminders.json"

    def tearDown(self) -> None:
        if self.assistant.timer.status()["running"]:
            self.assistant.timer.stop()

        self.load_json_patcher.stop()
        self.save_json_patcher.stop()
        self.settings_patcher.stop()
        self.ensure_files_patcher.stop()
        self.log_assistant_patcher.stop()
        self.log_timer_patcher.stop()
        self.log_focus_patcher.stop()
        self.log_break_patcher.stop()
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

    def _simulate_timer_finish(self, mode: str) -> None:
        with self.assistant.timer._lock:
            self.assistant.timer._running = False
            self.assistant.timer._mode = None
            self.assistant.timer._remaining_seconds = 0
            self.assistant.timer._started_at = 0.0
            self.assistant.timer._ends_at = 0.0

            stop_event = self.assistant.timer._stop_event

        if stop_event:
            stop_event.set()

        self.assistant._on_timer_finished(mode)

    def test_timer_start_and_stop_in_english(self) -> None:
        start_result = self.assistant.handle_command("Set timer for 10 minutes")

        self.assertTrue(start_result)
        self.assertTrue(self.assistant.timer.status()["running"])
        self.assertEqual(self.assistant.timer.status()["mode"], "timer")
        self.assertEqual(self.assistant.state["current_timer"], "timer")
        self.assertFalse(self.assistant.state["focus_mode"])
        self.assertFalse(self.assistant.state["break_mode"])
        self.assertEqual(self._last_voice_language(), "en")
        self.assertIn("I set a timer for 10 minutes", self._last_voice_text())
        self.assertEqual(self._last_display_title(), "TIMER START")

        stop_result = self.assistant.handle_command("stop timer")

        self.assertTrue(stop_result)
        self.assertFalse(self.assistant.timer.status()["running"])
        self.assertIsNone(self.assistant.state["current_timer"])
        self.assertEqual(self._last_display_title(), "TIMER STOP")
        self.assertIn("I stopped the timer", self._last_voice_text())

    def test_focus_start_and_stop_in_english(self) -> None:
        start_result = self.assistant.handle_command("Focus mode twenty five minutes")

        self.assertTrue(start_result)
        self.assertTrue(self.assistant.timer.status()["running"])
        self.assertEqual(self.assistant.timer.status()["mode"], "focus")
        self.assertEqual(self.assistant.state["current_timer"], "focus")
        self.assertTrue(self.assistant.state["focus_mode"])
        self.assertFalse(self.assistant.state["break_mode"])
        self.assertEqual(self._last_display_title(), "FOCUS MODE")
        self.assertIn("I started focus mode for 25 minutes", self._last_voice_text())

        stop_result = self.assistant.handle_command("stop focus mode")

        self.assertTrue(stop_result)
        self.assertFalse(self.assistant.timer.status()["running"])
        self.assertIsNone(self.assistant.state["current_timer"])
        self.assertFalse(self.assistant.state["focus_mode"])
        self.assertEqual(self._last_display_title(), "FOCUS STOP")
        self.assertIn("I stopped focus mode", self._last_voice_text())

    def test_break_start_in_polish(self) -> None:
        result = self.assistant.handle_command("Przerwa dziesięć minut")

        self.assertTrue(result)
        self.assertTrue(self.assistant.timer.status()["running"])
        self.assertEqual(self.assistant.timer.status()["mode"], "break")
        self.assertEqual(self.assistant.state["current_timer"], "break")
        self.assertFalse(self.assistant.state["focus_mode"])
        self.assertTrue(self.assistant.state["break_mode"])
        self.assertEqual(self._last_voice_language(), "pl")
        self.assertEqual(self._last_display_title(), "BREAK MODE")
        self.assertIn("Uruchomiłam break mode na 10 minut", self._last_voice_text())

    def test_focus_finish_creates_break_offer(self) -> None:
        self.assistant.handle_command("Focus mode 25 minutes")

        self._simulate_timer_finish("focus")

        self.assertIsNotNone(self.assistant.pending_follow_up)
        self.assertEqual(self.assistant.pending_follow_up["type"], "post_focus_break_offer")
        self.assertEqual(self.assistant.pending_follow_up["lang"], "en")
        self.assertIsNone(self.assistant.state["current_timer"])
        self.assertFalse(self.assistant.state["focus_mode"])
        self.assertFalse(self.assistant.state["break_mode"])
        self.assertEqual(self._last_display_title(), "FOCUS DONE")
        self.assertIn("I can start a break now", self._last_voice_text())

    def test_yes_after_focus_finish_starts_default_break(self) -> None:
        self.assistant.handle_command("Focus mode 25 minutes")
        self._simulate_timer_finish("focus")

        result = self.assistant.handle_command("yes")

        self.assertTrue(result)
        self.assertTrue(self.assistant.timer.status()["running"])
        self.assertEqual(self.assistant.timer.status()["mode"], "break")
        self.assertEqual(self.assistant.state["current_timer"], "break")
        self.assertFalse(self.assistant.state["focus_mode"])
        self.assertTrue(self.assistant.state["break_mode"])
        self.assertEqual(self._last_display_title(), "BREAK MODE")
        self.assertIn("I started break mode for 5 minutes", self._last_voice_text())

    def test_no_after_focus_finish_does_not_start_break(self) -> None:
        self.assistant.handle_command("Focus mode 25 minutes")
        self._simulate_timer_finish("focus")

        result = self.assistant.handle_command("no")

        self.assertTrue(result)
        self.assertFalse(self.assistant.timer.status()["running"])
        self.assertIsNone(self.assistant.state["current_timer"])
        self.assertFalse(self.assistant.state["break_mode"])
        self.assertIn("I will not start a break", self._last_voice_text())

    def test_direct_break_duration_after_focus_finish(self) -> None:
        self.assistant.handle_command("Focus mode 25 minutes")
        self._simulate_timer_finish("focus")

        result = self.assistant.handle_command("7 minutes")

        self.assertTrue(result)
        self.assertTrue(self.assistant.timer.status()["running"])
        self.assertEqual(self.assistant.timer.status()["mode"], "break")
        self.assertEqual(self.assistant.state["current_timer"], "break")
        self.assertTrue(self.assistant.state["break_mode"])
        self.assertIn("I started break mode for 7 minutes", self._last_voice_text())


if __name__ == "__main__":
    unittest.main()