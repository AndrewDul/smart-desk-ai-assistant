from __future__ import annotations

import threading
import time
from typing import Any

from modules.core.dispatch import dispatch_intent
from modules.core.followups import (
    ask_for_confirmation,
    extract_name,
    handle_pending_confirmation,
    handle_pending_follow_up,
)
from modules.core.language import (
    context_language,
    detect_language,
    extract_minutes_from_text,
    format_duration_text,
    is_no,
    is_yes,
    localized,
    normalize_text,
    speak_localized,
)
from modules.core.responses import (
    action_label,
    format_temporal_text,
    offer_oled_display,
    show_capabilities,
    show_localized_block,
)
from modules.io.display import ConsoleDisplay
from modules.io.text_input import TextInput
from modules.io.voice_out import VoiceOutput
from modules.io.whisper_input import WhisperVoiceInput
from modules.parsing.intent_parser import IntentParser, IntentResult
from modules.services.memory import SimpleMemory
from modules.services.reminders import ReminderManager
from modules.services.timer import SessionTimer
from modules.system.utils import (
    SESSION_STATE_PATH,
    USER_PROFILE_PATH,
    append_log,
    ensure_project_files,
    load_json,
    load_settings,
    save_json,
)


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
        self.boot_overlay_seconds = float(display_cfg.get("boot_overlay_seconds", 2.8))

        self.parser = IntentParser(
            default_focus_minutes=float(self.settings.get("timers", {}).get("default_focus_minutes", 25)),
            default_break_minutes=float(self.settings.get("timers", {}).get("default_break_minutes", 5)),
        )

        self.pending_confirmation: dict[str, Any] | None = None
        self.pending_follow_up: dict[str, Any] | None = None
        self.last_language = "en"
        self.shutdown_requested = False

        if voice_input_cfg.get("enabled", True):
            engine = str(voice_input_cfg.get("engine", "whisper")).lower().strip()

            if engine == "whisper":
                try:
                    self.voice_in = WhisperVoiceInput(
                        whisper_cli_path=voice_input_cfg.get("whisper_cli_path", "whisper.cpp/build/bin/whisper-cli"),
                        model_path=voice_input_cfg.get("model_path", "models/ggml-base.bin"),
                        vad_enabled=bool(voice_input_cfg.get("vad_enabled", False)),
                        vad_model_path=voice_input_cfg.get("vad_model_path", "models/ggml-silero-v6.2.0.bin"),
                        language=voice_input_cfg.get("language", "auto"),
                        device_index=voice_input_cfg.get("device_index"),
                        device_name_contains=voice_input_cfg.get("device_name_contains"),
                        sample_rate=voice_input_cfg.get("sample_rate"),
                        max_record_seconds=float(voice_input_cfg.get("max_record_seconds", 8.0)),
                        silence_threshold=float(voice_input_cfg.get("silence_threshold", 350.0)),
                        end_silence_seconds=float(voice_input_cfg.get("end_silence_seconds", 1.0)),
                        pre_roll_seconds=float(voice_input_cfg.get("pre_roll_seconds", 0.4)),
                        threads=int(voice_input_cfg.get("threads", 4)),
                    )
                except Exception as error:
                    append_log(f"Whisper input init failed, falling back to text input: {error}")
                    self.voice_in = TextInput()
            else:
                append_log(f"Unsupported voice input engine '{engine}', falling back to text input.")
                self.voice_in = TextInput()
        else:
            self.voice_in = TextInput()

        self.voice_out = VoiceOutput(
            enabled=voice_output_cfg.get("enabled", True),
            preferred_engine=voice_output_cfg.get("engine", "espeak-ng"),
            default_language=voice_output_cfg.get("default_language", "pl"),
            speed=int(voice_output_cfg.get("speed", 155)),
            pitch=int(voice_output_cfg.get("pitch", 58)),
            voices=voice_output_cfg.get("voices", {"pl": "pl+f3", "en": "en+f3"}),
            piper_models=voice_output_cfg.get("piper_models"),
        )

        self.display = ConsoleDisplay(
            driver=str(display_cfg.get("driver", "ssd1306")),
            interface=str(display_cfg.get("interface", "i2c")),
            port=int(display_cfg.get("port", 1)),
            address=int(display_cfg.get("address", 60)),
            rotate=int(display_cfg.get("rotate", 0)),
            width=int(display_cfg.get("width", 128)),
            height=int(display_cfg.get("height", 64)),
            spi_port=int(display_cfg.get("spi_port", 0)),
            spi_device=int(display_cfg.get("spi_device", 0)),
            gpio_dc=int(display_cfg.get("gpio_dc", 25)),
            gpio_rst=int(display_cfg.get("gpio_rst", 27)),
            gpio_light=int(display_cfg.get("gpio_light", 18)),
        )

        self.memory = SimpleMemory()
        self.reminders = ReminderManager()

        self.user_profile = load_json(
            USER_PROFILE_PATH,
            {
                "name": "Andrzej",
                "conversation_partner_name": "",
                "project": "Smart Desk AI Assistant",
            },
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
        self._reminder_thread = threading.Thread(target=self._reminder_loop, daemon=True)

    def boot(self) -> None:
        self.state["assistant_running"] = True
        self._save_state()
        self._reminder_thread.start()

        self.display.show_block(
            "DevDul",
            [
                "Smart Assistant",
                "starting up...",
            ],
            duration=self.boot_overlay_seconds,
        )

        append_log("Boot screen: DevDul.")

        time.sleep(max(self.boot_overlay_seconds, 0.8))
        self.display.clear_overlay()
        time.sleep(0.15)

        self.voice_out.speak(
            "Hello. If you want to hear how I can help, ask me, how can you help me?",
            language="en",
        )

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

        self.display.show_block(
            "SHUTDOWN",
            [
                "assistant stopped",
                "see you later",
            ],
            duration=2.0,
        )

        self._speak_localized(
            self.last_language,
            "Wyłączam Smart Assistant.",
            "Shutting down Smart Assistant.",
        )

        append_log("Assistant shut down.")
        time.sleep(2.0)
        self.display.close()

    def _save_state(self) -> None:
        save_json(SESSION_STATE_PATH, self.state)

    def _save_user_profile(self) -> None:
        save_json(USER_PROFILE_PATH, self.user_profile)

    def _normalize_text(self, text: str) -> str:
        return normalize_text(self, text)

    def _detect_language(self, text: str) -> str:
        return detect_language(self, text)

    def _localized(self, lang: str, pl_text: str, en_text: str) -> str:
        return localized(lang, pl_text, en_text)

    def _speak_localized(self, lang: str, pl_text: str, en_text: str) -> None:
        speak_localized(self, lang, pl_text, en_text)

    def _context_language(self, text: str, detected_lang: str) -> str:
        return context_language(self, text, detected_lang)

    def _format_duration_text(self, total_seconds: int, lang: str) -> str:
        return format_duration_text(total_seconds, lang)

    def _extract_minutes_from_text(self, text: str) -> float | None:
        return extract_minutes_from_text(self, text)

    def _is_yes(self, text: str) -> bool:
        return is_yes(self, text)

    def _is_no(self, text: str) -> bool:
        return is_no(self, text)

    def _action_label(self, action: str, lang: str) -> str:
        return action_label(action, lang)

    def _show_capabilities(self, lang: str) -> None:
        show_capabilities(self, lang)

    def _show_localized_block(
        self,
        lang: str,
        title_pl: str,
        title_en: str,
        lines_pl: list[str],
        lines_en: list[str],
        duration: float | None = None,
    ) -> None:
        show_localized_block(self, lang, title_pl, title_en, lines_pl, lines_en, duration)

    def _offer_oled_display(self, lang: str, title: str, lines: list[str], speak_prompt: bool = True) -> None:
        offer_oled_display(self, lang, title, lines, speak_prompt)

    def _format_temporal_text(self, kind: str, lang: str) -> tuple[str, str, list[str]]:
        return format_temporal_text(kind, lang)

    def _extract_name(self, text: str) -> str | None:
        return extract_name(text)

    def _ask_for_confirmation(self, suggestions: list[dict[str, Any]], lang: str) -> bool:
        return ask_for_confirmation(self, suggestions, lang)

    def _handle_pending_confirmation(self, text: str, current_lang: str) -> bool:
        return handle_pending_confirmation(self, text, current_lang)

    def _handle_pending_follow_up(self, text: str, lang: str) -> bool | None:
        return handle_pending_follow_up(self, text, lang)

    def _delete_all_reminders(self) -> int:
        reminders = self.reminders.list_all()
        count = 0
        for reminder in reminders:
            reminder_id = reminder.get("id")
            if reminder_id and self.reminders.delete(reminder_id):
                count += 1
        return count

    def _start_timer_mode(self, minutes: float, mode: str, lang: str) -> bool:
        ok, message = self.timer.start(minutes, mode)
        if not ok:
            self._speak_localized(
                lang,
                "Timer już działa. Najpierw go zatrzymaj.",
                "A timer is already running. Please stop it first.",
            )
            append_log(message)
            return True
        return True

    def _on_timer_started(self, mode: str, minutes: float) -> None:
        self.state["current_timer"] = mode

        if mode == "focus":
            self.state["focus_mode"] = True
            self.state["break_mode"] = False
        elif mode == "break":
            self.state["focus_mode"] = False
            self.state["break_mode"] = True
        else:
            self.state["focus_mode"] = False
            self.state["break_mode"] = False

        self._save_state()
        append_log(f"{mode.capitalize()} timer started for {minutes:g} minute(s).")

        lang = self.last_language
        mode_label_pl = {"focus": "sesja focus", "break": "przerwa", "timer": "timer"}.get(mode, mode)
        mode_label_en = {"focus": "focus session", "break": "break", "timer": "timer"}.get(mode, mode)
        spoken_duration = self._format_duration_text(int(round(minutes * 60)), lang)

        self.display.show_block(
            self._localized(lang, "TIMER START", "TIMER START"),
            [self._localized(lang, mode_label_pl, mode_label_en), f"{minutes:g} min"],
            duration=6.0,
        )

        self._speak_localized(
            lang,
            f"Uruchomiłam {mode_label_pl} na {spoken_duration}.",
            f"I started the {mode_label_en} for {spoken_duration}.",
        )

    def _on_timer_finished(self, mode: str) -> None:
        self.state["current_timer"] = None
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self._save_state()
        append_log(f"{mode.capitalize()} timer finished.")

        if mode == "focus":
            self.display.show_block(
                self._localized(self.last_language, "FOCUS KONIEC", "FOCUS DONE"),
                [
                    self._localized(self.last_language, "czas sesji minął", "your session is over"),
                    self._localized(self.last_language, "chcesz przerwę?", "would you like a break?"),
                ],
                duration=8.0,
            )
            self.pending_follow_up = {"type": "post_focus_break_offer", "lang": self.last_language}
            self._speak_localized(
                self.last_language,
                "Focus time dobiegł końca. Czy chcesz teraz przerwę?",
                "Your focus session is over. Would you like a break now?",
            )
            return

        if mode == "break":
            self.display.show_block(
                self._localized(self.last_language, "KONIEC PRZERWY", "BREAK DONE"),
                [
                    self._localized(self.last_language, "przerwa skończona", "break is over"),
                    self._localized(self.last_language, "wróć do nauki", "back to studying"),
                ],
                duration=8.0,
            )
            self._speak_localized(
                self.last_language,
                "Przerwa dobiegła końca. Wracaj do nauki, kiedy będziesz gotowy.",
                "Your break is over. Come back to studying when you are ready.",
            )
            return

        self.display.show_block(
            self._localized(self.last_language, "CZAS MINĄŁ", "TIME IS UP"),
            [self._localized(self.last_language, "timer zakończony", "timer finished")],
            duration=6.0,
        )
        self._speak_localized(
            self.last_language,
            "Minął ustawiony czas.",
            "Your timer has finished.",
        )

    def _on_timer_stopped(self, mode: str) -> None:
        self.state["current_timer"] = None
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self._save_state()

        self.display.show_block(
            self._localized(self.last_language, "TIMER STOP", "TIMER STOP"),
            [self._localized(self.last_language, "timer zatrzymany", "timer stopped")],
            duration=6.0,
        )

        self._speak_localized(
            self.last_language,
            "Zatrzymałam timer.",
            "I stopped the timer.",
        )
        append_log(f"{mode.capitalize()} timer stopped.")

    def _reminder_loop(self) -> None:
        while not self._stop_background.is_set():
            due_reminders = self.reminders.check_due_reminders()

            for reminder in due_reminders:
                message = reminder.get("message", "Reminder triggered.")
                lang = self.last_language

                self.display.show_block(
                    self._localized(lang, "PRZYPOMNIENIE", "REMINDER"),
                    [message],
                    duration=self.default_overlay_seconds,
                )
                self._speak_localized(
                    lang,
                    f"Przypomnienie. {message}",
                    f"Reminder. {message}",
                )
                append_log(f"Reminder triggered: message={message}")

            time.sleep(1)

    def _execute_intent(self, result: IntentResult, lang: str) -> bool:
        self.last_language = lang
        append_log(
            f"Parsed intent: action={result.action}, data={result.data}, text={result.normalized_text}, lang={lang}"
        )

        handled = dispatch_intent(self, result, lang)
        if handled is not None:
            return handled

        if result.action in {"confirm_yes", "confirm_no"}:
            self._speak_localized(
                lang,
                "Nie ma teraz nic do potwierdzenia.",
                "There is nothing to confirm right now.",
            )
            return True

        if result.action == "unclear" and result.suggestions:
            return self._ask_for_confirmation(result.suggestions, lang)

        self._speak_localized(
            lang,
            "Nie zrozumiałam tego do końca. Powiedz to jeszcze raz trochę inaczej.",
            "I did not fully understand that. Please say it again in a slightly different way.",
        )
        return True

    def handle_command(self, text: str) -> bool:
        cleaned = text.strip()
        if not cleaned:
            return True

        detected_lang = self._detect_language(cleaned)
        lang = self._context_language(cleaned, detected_lang)
        self.last_language = lang
        append_log(f"User said: {cleaned}")

        if self.pending_confirmation:
            return self._handle_pending_confirmation(cleaned, lang)

        if self.pending_follow_up:
            handled = self._handle_pending_follow_up(cleaned, lang)
            if handled is not None:
                return handled

        result = self.parser.parse(cleaned)
        return self._execute_intent(result, lang)