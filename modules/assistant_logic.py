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
    save_json,
)
from modules.voice_in import TextVoiceInput
from modules.voice_out import VoiceOutput


class CoreAssistant:
    def __init__(self) -> None:
        ensure_project_files()

        self.voice_in = TextVoiceInput()
        self.voice_out = VoiceOutput()
        self.display = ConsoleDisplay()
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

        name = self.user_profile.get("name", "User")
        project = self.user_profile.get("project", "Smart Desk AI Assistant")

        self.display.show_block(
            "SMART DESK AI ASSISTANT",
            [
                f"User: {name}",
                f"Project: {project}",
                "Mode: Stage 1 core without camera",
                "Type 'help' to see available commands.",
            ],
        )

        self.voice_out.speak(f"Hello {name}. Smart Desk assistant core is now running.")
        append_log("Assistant booted.")

    def shutdown(self) -> None:
        self._stop_background.set()

        if self.timer.status()["running"]:
            self.timer.stop()

        self.state["assistant_running"] = False
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self.state["current_timer"] = None
        self._save_state()

        self.voice_out.speak("Shutting down Smart Desk assistant.")
        append_log("Assistant shut down.")

    def _save_state(self) -> None:
        save_json(SESSION_STATE_PATH, self.state)

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

    def _on_timer_finished(self, mode: str) -> None:
        self.state["current_timer"] = None
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self._save_state()

        self.voice_out.speak(f"{mode.capitalize()} timer finished.")
        append_log(f"{mode.capitalize()} timer finished.")

    def _on_timer_stopped(self, mode: str) -> None:
        self.state["current_timer"] = None
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self._save_state()

        append_log(f"{mode.capitalize()} timer stopped.")

    def _reminder_loop(self) -> None:
        while not self._stop_background.is_set():
            due_reminders = self.reminders.check_due_reminders()

            for reminder in due_reminders:
                message = reminder.get("message", "Reminder triggered.")
                reminder_id = reminder.get("id", "unknown")

                self.voice_out.speak(f"Reminder. {message}")
                append_log(f"Reminder triggered: id={reminder_id}, message={message}")

            time.sleep(1)

    def handle_command(self, command: str) -> bool:
        cleaned = command.strip()
        lowered = cleaned.lower()

        if not cleaned:
            return True

        append_log(f"User command: {cleaned}")

        if lowered == "help":
            self.voice_out.speak(
                "Available commands: help, status, memory, reminders, "
                "remember key = value, recall key, remind seconds | message, "
                "focus minutes, break minutes, stop timer, exit."
            )
            return True

        if lowered == "status":
            self.display.show_status(self.state, self.timer.status())
            return True

        if lowered == "memory":
            all_memory = self.memory.get_all()
            if not all_memory:
                self.voice_out.speak("Memory is currently empty.")
                return True

            memory_lines = [f"{key} -> {value}" for key, value in all_memory.items()]
            self.display.show_block("MEMORY ITEMS", memory_lines)
            return True

        if lowered == "reminders":
            reminders = self.reminders.list_all()
            if not reminders:
                self.voice_out.speak("There are no reminders saved.")
                return True

            reminder_lines = [
                f"{item['id']} | {item['status']} | {item['message']} | due: {item['due_at']}"
                for item in reminders
            ]
            self.display.show_block("REMINDERS", reminder_lines)
            return True

        if lowered.startswith("remember "):
            payload = cleaned[9:].strip()
            if "=" not in payload:
                self.voice_out.speak("Use format: remember key = value")
                return True

            key, value = payload.split("=", 1)
            key = key.strip().lower()
            value = value.strip()

            if not key or not value:
                self.voice_out.speak("Both key and value are required.")
                return True

            self.memory.remember(key, value)
            self.voice_out.speak(f"I saved memory for {key}.")
            return True

        if lowered.startswith("recall "):
            key = cleaned[7:].strip().lower()
            if not key:
                self.voice_out.speak("Use format: recall key")
                return True

            value = self.memory.recall(key)
            if value is None:
                self.voice_out.speak(f"I do not have anything saved for {key}.")
            else:
                self.voice_out.speak(f"{key} is {value}.")
            return True

        if lowered.startswith("remind "):
            payload = cleaned[7:].strip()

            if "|" not in payload:
                self.voice_out.speak("Use format: remind seconds | message")
                return True

            seconds_text, message = payload.split("|", 1)
            seconds_text = seconds_text.strip()
            message = message.strip()

            try:
                seconds = int(seconds_text)
            except ValueError:
                self.voice_out.speak("Reminder seconds must be a whole number.")
                return True

            if seconds <= 0 or not message:
                self.voice_out.speak("Reminder seconds and message must be valid.")
                return True

            reminder = self.reminders.add_after_seconds(seconds, message)
            self.voice_out.speak(
                f"Reminder saved. ID {reminder['id']}. It will trigger in {seconds} seconds."
            )
            return True

        if lowered.startswith("focus "):
            minutes_text = cleaned[6:].strip()

            try:
                minutes = float(minutes_text)
            except ValueError:
                self.voice_out.speak("Use format: focus minutes")
                return True

            ok, message = self.timer.start(minutes, "focus")
            self.voice_out.speak(message)
            return True

        if lowered.startswith("break "):
            minutes_text = cleaned[6:].strip()

            try:
                minutes = float(minutes_text)
            except ValueError:
                self.voice_out.speak("Use format: break minutes")
                return True

            ok, message = self.timer.start(minutes, "break")
            self.voice_out.speak(message)
            return True

        if lowered == "stop timer":
            ok, message = self.timer.stop()
            self.voice_out.speak(message)
            return True

        if lowered in {"exit", "quit"}:
            return False

        self.voice_out.speak("Unknown command. Type help to see supported commands.")
        return True
