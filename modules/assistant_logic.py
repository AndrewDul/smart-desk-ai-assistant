from __future__ import annotations

import threading
import time

from modules.display import ConsoleDisplay
from modules.memory import SimpleMemory
from modules.reminders import ReminderManager
from modules.timer import SessionTimer
from modules.utils import (
    SESSION_STATE_PATH,
    USER_PROFILE_PATH,
    append_log,
    ensure_project_files,
    load_json,
    load_settings,
    save_json,
)
from modules.voice_in import TextVoiceInput, VoiceInput
from modules.voice_out import VoiceOutput


class CoreAssistant:
    def __init__(self) -> None:
        ensure_project_files()

        self.settings = load_settings()

        voice_input_cfg = self.settings.get("voice_input", {})
        voice_output_cfg = self.settings.get("voice_output", {})
        display_cfg = self.settings.get("display", {})

        self.voice_listen_timeout = float(voice_input_cfg.get("timeout_seconds", 8))
        self.voice_debug = bool(voice_input_cfg.get("debug", False))
        self.default_overlay_seconds = float(display_cfg.get("default_overlay_seconds", 10))
        self.boot_overlay_seconds = float(display_cfg.get("boot_overlay_seconds", 4))

        if voice_input_cfg.get("enabled", True):
            self.voice_in = VoiceInput(
                model_path=voice_input_cfg.get("model_path", "models/vosk-model-small-en-us-0.15"),
                device=voice_input_cfg.get("device_index", 2),
                use_grammar=voice_input_cfg.get("use_grammar", False),
            )
        else:
            self.voice_in = TextVoiceInput()

        self.voice_out = VoiceOutput(
            enabled=voice_output_cfg.get("enabled", True),
            preferred_engine=voice_output_cfg.get("engine", "espeak-ng"),
        )

        self.display = ConsoleDisplay(
            port=int(display_cfg.get("port", 1)),
            address=int(display_cfg.get("address", 60)),
            rotate=int(display_cfg.get("rotate", 0)),
            width=int(display_cfg.get("width", 128)),
            height=int(display_cfg.get("height", 64)),
        )

        self.memory = SimpleMemory()
        self.reminders = ReminderManager()

        self.user_profile = load_json(
            USER_PROFILE_PATH,
            {"name": "Andrzej", "project": "Smart Desk AI Assistant"},
        )
        self.state = load_json(
            SESSION_STATE_PATH,
            {
                "assistant_running": False,
                "focus_mode": False,
                "break_mode": False,
                "current_timer": None,
            },
        )

        self.timer = SessionTimer(
            on_started=self._on_timer_started,
            on_finished=self._on_timer_finished,
            on_stopped=self._on_timer_stopped,
        )

        self._stop_background = threading.Event()
        self._reminder_thread = threading.Thread(
            target=self._reminder_loop,
            daemon=True,
        )

    def boot(self) -> None:
        self.state["assistant_running"] = True
        self._save_state()
        self._reminder_thread.start()

        name = self.user_profile.get("name", self.settings.get("user", {}).get("name", "User"))
        project = self.user_profile.get("project", self.settings.get("project", {}).get("name", "Smart Desk AI Assistant"))

        self.display.show_block(
            "SMART DESK AI",
            [
                f"user: {name}",
                "eyes animation ready",
                "say: show menu",
            ],
            duration=self.boot_overlay_seconds,
        )

        self.voice_out.speak(f"Hello {name}. Smart Desk assistant core is now running.")
        append_log(f"Assistant booted for project: {project}")

    def shutdown(self) -> None:
        self._stop_background.set()

        if self.timer.status()["running"]:
            self.timer.stop()

        self.state["assistant_running"] = False
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self.state["current_timer"] = None
        self._save_state()

        self.display.show_block(
            "SHUTDOWN",
            [
                "assistant stopped",
                "see you later",
            ],
            duration=2.0,
        )

        self.voice_out.speak("Shutting down Smart Desk assistant.")
        append_log("Assistant shut down.")

        time.sleep(2.0)
        self.display.close()

    def _save_state(self) -> None:
        save_json(SESSION_STATE_PATH, self.state)

    def _show_menu(self, duration: float | None = None) -> None:
        menu_duration = self.default_overlay_seconds if duration is None else duration

        self.display.show_block(
            "VOICE MENU",
            [
                "show help / status",
                "show memory",
                "show reminders",
                "focus 1 / break 1",
                "stop timer / exit",
            ],
            duration=menu_duration,
        )

    def _on_timer_started(self, mode: str, minutes: float) -> None:
        self.state["current_timer"] = mode

        if mode == "focus":
            self.state["focus_mode"] = True
            self.state["break_mode"] = False
        elif mode == "break":
            self.state["focus_mode"] = False
            self.state["break_mode"] = True

        self._save_state()
        append_log(f"{mode.capitalize()} timer started for {minutes:g} minute(s).")

        self.display.show_block(
            f"{mode.upper()} START",
            [
                f"{minutes:g} minute(s)",
                "timer running",
            ],
            duration=6.0,
        )

        self.voice_out.speak(f"{mode.capitalize()} timer started for {minutes:g} minutes.")

    def _on_timer_finished(self, mode: str) -> None:
        self.state["current_timer"] = None
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self._save_state()

        self.display.show_block(
            f"{mode.upper()} DONE",
            [
                "timer finished",
                "mode cleared",
            ],
            duration=6.0,
        )

        self.voice_out.speak(f"{mode.capitalize()} timer finished.")
        append_log(f"{mode.capitalize()} timer finished.")

    def _on_timer_stopped(self, mode: str) -> None:
        self.state["current_timer"] = None
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self._save_state()

        self.display.show_block(
            "TIMER STOPPED",
            [
                f"mode: {mode}",
                "state cleared",
            ],
            duration=6.0,
        )

        self.voice_out.speak(f"{mode.capitalize()} timer stopped.")
        append_log(f"{mode.capitalize()} timer stopped.")

    def _reminder_loop(self) -> None:
        while not self._stop_background.is_set():
            due_reminders = self.reminders.check_due_reminders()

            for reminder in due_reminders:
                message = reminder.get("message", "Reminder triggered.")
                reminder_id = reminder.get("id", "unknown")

                self.display.show_block(
                    "REMINDER",
                    [
                        message,
                        f"id: {reminder_id}",
                    ],
                    duration=self.default_overlay_seconds,
                )

                self.voice_out.speak(f"Reminder. {message}")
                append_log(f"Reminder triggered: id={reminder_id}, message={message}")

            time.sleep(1)

    def handle_command(self, command: str) -> bool:
        cleaned = command.strip()
        lowered = cleaned.lower()

        alias_map = {
            "show help": "help",
            "what can you do": "help",
            "show commands": "help",
            "show status": "status",
            "show memory": "memory",
            "show reminders": "reminders",
            "list reminders": "reminders",
            "show menu": "show menu",
            "open menu": "show menu",
            "menu": "show menu",
            "quit": "exit",
            "quit assistant": "exit",
            "exit assistant": "exit",
            "close assistant": "exit",
        }
        lowered = alias_map.get(lowered, lowered)

        if not cleaned:
            return True

        append_log(f"User command: {cleaned}")

        if lowered == "show menu":
            self._show_menu()
            self.voice_out.speak("Showing menu.")
            return True

        if lowered == "help":
            self.display.show_block(
                "HELP",
                [
                    "help / status / memory",
                    "reminders / recall key",
                    "remember key = value",
                    "remind 10 | message",
                    "focus 1 / break 1",
                ],
                duration=self.default_overlay_seconds,
            )
            self.voice_out.speak(
                "Available commands: help, status, memory, reminders, "
                "remember key equals value, recall key, remind seconds and message, "
                "focus minutes, break minutes, stop timer, show menu, exit."
            )
            return True

        if lowered == "status":
            self.display.show_status(self.state, self.timer.status(), duration=self.default_overlay_seconds)
            self.voice_out.speak("Showing current status.")
            return True

        if lowered == "memory":
            all_memory = self.memory.get_all()
            if not all_memory:
                self.display.show_block("MEMORY", ["empty"], duration=8.0)
                self.voice_out.speak("Memory is currently empty.")
                return True

            memory_lines = [f"{key} -> {value}" for key, value in all_memory.items()]
            self.display.show_block("MEMORY ITEMS", memory_lines, duration=self.default_overlay_seconds)
            self.voice_out.speak("Showing saved memory items.")
            return True

        if lowered == "reminders":
            reminders = self.reminders.list_all()
            if not reminders:
                self.display.show_block("REMINDERS", ["no reminders"], duration=8.0)
                self.voice_out.speak("There are no reminders saved.")
                return True

            reminder_lines = [f"{item['id']} {item['status']}" for item in reminders]
            self.display.show_block("REMINDERS", reminder_lines, duration=self.default_overlay_seconds)
            self.voice_out.speak("Showing reminders.")
            return True

        if lowered.startswith("remember "):
            payload = cleaned[9:].strip()
            if "=" not in payload:
                self.display.show_block("MEMORY ERROR", ["use key = value"], duration=8.0)
                self.voice_out.speak("Use format: remember key equals value")
                return True

            key, value = payload.split("=", 1)
            key = key.strip().lower()
            value = value.strip()

            if not key or not value:
                self.display.show_block("MEMORY ERROR", ["missing key/value"], duration=8.0)
                self.voice_out.speak("Both key and value are required.")
                return True

            self.memory.remember(key, value)
            self.display.show_block(
                "MEMORY SAVED",
                [
                    key,
                    value,
                ],
                duration=8.0,
            )
            self.voice_out.speak(f"I saved memory for {key}.")
            return True

        if lowered.startswith("recall "):
            key = cleaned[7:].strip().lower()
            if not key:
                self.display.show_block("RECALL ERROR", ["use recall key"], duration=8.0)
                self.voice_out.speak("Use format: recall key")
                return True

            value = self.memory.recall(key)
            if value is None:
                self.display.show_block(
                    "RECALL",
                    [
                        key,
                        "not found",
                    ],
                    duration=8.0,
                )
                self.voice_out.speak(f"I do not have anything saved for {key}.")
            else:
                self.display.show_block(
                    "RECALL",
                    [
                        key,
                        value,
                    ],
                    duration=8.0,
                )
                self.voice_out.speak(f"{key} is {value}.")
            return True

        if lowered.startswith("remind "):
            payload = cleaned[7:].strip()

            if "|" not in payload:
                self.display.show_block("REMINDER ERROR", ["use sec | msg"], duration=8.0)
                self.voice_out.speak("Use format: remind seconds and message")
                return True

            seconds_text, message = payload.split("|", 1)
            seconds_text = seconds_text.strip()
            message = message.strip()

            try:
                seconds = int(seconds_text)
            except ValueError:
                self.display.show_block("REMINDER ERROR", ["seconds invalid"], duration=8.0)
                self.voice_out.speak("Reminder seconds must be a whole number.")
                return True

            if seconds <= 0 or not message:
                self.display.show_block("REMINDER ERROR", ["bad values"], duration=8.0)
                self.voice_out.speak("Reminder seconds and message must be valid.")
                return True

            reminder = self.reminders.add_after_seconds(seconds, message)
            self.display.show_block(
                "REMINDER SET",
                [
                    f"id: {reminder['id']}",
                    f"in {seconds}s",
                ],
                duration=8.0,
            )
            self.voice_out.speak(
                f"Reminder saved. ID {reminder['id']}. It will trigger in {seconds} seconds."
            )
            return True

        if lowered.startswith("focus "):
            minutes_text = lowered[6:].strip()

            try:
                minutes = float(minutes_text)
            except ValueError:
                self.display.show_block("FOCUS ERROR", ["use minutes"], duration=8.0)
                self.voice_out.speak("Use format: focus minutes")
                return True

            ok, message = self.timer.start(minutes, "focus")
            self.voice_out.speak(message)
            return True

        if lowered.startswith("break "):
            minutes_text = lowered[6:].strip()

            try:
                minutes = float(minutes_text)
            except ValueError:
                self.display.show_block("BREAK ERROR", ["use minutes"], duration=8.0)
                self.voice_out.speak("Use format: break minutes")
                return True

            ok, message = self.timer.start(minutes, "break")
            self.voice_out.speak(message)
            return True

        if lowered == "stop timer":
            ok, message = self.timer.stop()
            self.voice_out.speak(message)
            return True

        if lowered == "exit":
            return False

        self.display.show_block(
            "UNKNOWN CMD",
            [
                cleaned,
                "say: show menu",
            ],
            duration=8.0,
        )
        self.voice_out.speak("Unknown command. Say show menu or help.")
        return True