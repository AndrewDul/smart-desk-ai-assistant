from __future__ import annotations

import re
import threading
import time
from datetime import datetime

from modules.display import ConsoleDisplay
from modules.intent_parser import IntentParser, IntentResult
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
from modules.whisper_input import WhisperVoiceInput


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

        self.parser = IntentParser(
            default_focus_minutes=float(self.settings.get("timers", {}).get("default_focus_minutes", 25)),
            default_break_minutes=float(self.settings.get("timers", {}).get("default_break_minutes", 5)),
        )

        self.pending_confirmation: dict | None = None
        self.pending_name_request = False
        self.pending_name_language = "pl"
        self.last_language = "pl"

        if voice_input_cfg.get("enabled", True):
            engine = voice_input_cfg.get("engine", "whisper").lower()

            if engine == "whisper":
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
            else:
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
            default_language=voice_output_cfg.get("default_language", "pl"),
            speed=int(voice_output_cfg.get("speed", 155)),
            pitch=int(voice_output_cfg.get("pitch", 58)),
            voices=voice_output_cfg.get("voices", {"pl": "pl+f3", "en": "en+f3"}),
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
        self._reminder_thread = threading.Thread(
            target=self._reminder_loop,
            daemon=True,
        )

    def boot(self) -> None:
        self.state["assistant_running"] = True
        self._save_state()
        self._reminder_thread.start()

        self.display.show_block(
            "SMART ASSISTANT",
            [
                "prototype ready",
                "assessment mode",
                "powiedz: pomoc/help",
            ],
            duration=self.boot_overlay_seconds,
        )

        self.voice_out.speak("Smart Assistant prototype is ready.", language="en")
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

        if self.last_language == "pl":
            self.voice_out.speak("Wyłączam Smart Assistant.", language="pl")
        else:
            self.voice_out.speak("Shutting down Smart Assistant.", language="en")

        append_log("Assistant shut down.")
        time.sleep(2.0)
        self.display.close()

    def _save_state(self) -> None:
        save_json(SESSION_STATE_PATH, self.state)

    def _save_user_profile(self) -> None:
        save_json(USER_PROFILE_PATH, self.user_profile)

    def _normalize_text(self, text: str) -> str:
        return self.parser._normalize_text(text)

    def _detect_language(self, text: str) -> str:
        normalized = self._normalize_text(text)
        tokens = set(normalized.split())

        polish_markers = {
            "pomoc", "pokaz", "menu", "stan", "godzina", "ktora", "ktora",
            "jestes", "przedstaw", "przypomnij", "gdzie", "komendy", "imie",
            "nazywasz", "czas", "przerwa", "tak", "nie", "kim",
        }
        english_markers = {
            "help", "show", "menu", "status", "time", "who", "what",
            "introduce", "yourself", "remember", "where", "remind",
            "commands", "assistant", "focus", "break", "yes", "no", "name",
        }

        if any(ch in text for ch in "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"):
            return "pl"
        if tokens & polish_markers:
            return "pl"
        if tokens & english_markers:
            return "en"

        if normalized in {"menu", "status"}:
            return self.last_language

        return self.last_language or "pl"

    def _localized(self, lang: str, pl_text: str, en_text: str) -> str:
        return pl_text if lang == "pl" else en_text

    def _speak_localized(self, lang: str, pl_text: str, en_text: str) -> None:
        self.voice_out.speak(self._localized(lang, pl_text, en_text), language=lang)

    def _show_localized_block(
        self,
        lang: str,
        title_pl: str,
        title_en: str,
        lines_pl: list[str],
        lines_en: list[str],
        duration: float | None = None,
    ) -> None:
        self.display.show_block(
            self._localized(lang, title_pl, title_en),
            lines_pl if lang == "pl" else lines_en,
            duration=self.default_overlay_seconds if duration is None else duration,
        )

    def _action_label(self, action: str, lang: str) -> str:
        labels = {
            "help": {"pl": "pomoc", "en": "help"},
            "show_menu": {"pl": "menu", "en": "menu"},
            "status": {"pl": "stan", "en": "status"},
            "memory_list": {"pl": "pamięć", "en": "memory"},
            "reminders_list": {"pl": "przypomnienia", "en": "reminders"},
            "timer_stop": {"pl": "zatrzymaj timer", "en": "stop timer"},
            "introduce_self": {"pl": "przedstaw się", "en": "introduce yourself"},
            "ask_time": {"pl": "godzina", "en": "time"},
            "exit": {"pl": "wyjście", "en": "exit"},
        }
        return labels.get(action, {}).get(lang, action)

    def _extract_name(self, text: str) -> str | None:
        raw = text.strip()

        patterns = [
            r"\b(?:mam na imie|mam na imię|nazywam sie|nazywam się|jestem)\s+([A-Za-zÀ-ÿ' -]{2,})$",
            r"\b(?:my name is|i am|i'm)\s+([A-Za-zÀ-ÿ' -]{2,})$",
        ]

        for pattern in patterns:
            match = re.search(pattern, raw, flags=re.IGNORECASE)
            if match:
                name = match.group(1).strip().split()[0]
                return name[:1].upper() + name[1:].lower()

        simple_tokens = re.findall(r"[A-Za-zÀ-ÿ'-]+", raw)
        if 1 <= len(simple_tokens) <= 2:
            token = simple_tokens[0]
            blocked = {
                "help", "pomoc", "menu", "status", "stan", "tak", "nie",
                "yes", "no", "focus", "break", "time", "godzina",
            }
            if token.lower() not in blocked and len(token) >= 2:
                return token[:1].upper() + token[1:].lower()

        return None

    def _try_handle_name_capture(self, text: str, lang: str) -> bool:
        if not self.pending_name_request:
            return False

        name = self._extract_name(text)
        if name:
            self.user_profile["name"] = name
            self.user_profile["conversation_partner_name"] = name
            self._save_user_profile()
            self.pending_name_request = False

            self._show_localized_block(
                lang,
                "MIŁO MI",
                "NICE TO MEET YOU",
                [f"{name}", "zapisałam imię"],
                [f"{name}", "name saved"],
                duration=8.0,
            )
            self._speak_localized(
                lang,
                f"Miło mi, {name}. Zapisałam twoje imię.",
                f"Nice to meet you, {name}. I saved your name.",
            )
            return True

        return False

    def _show_menu(self, lang: str, duration: float | None = None) -> None:
        menu_duration = self.default_overlay_seconds if duration is None else duration

        self._show_localized_block(
            lang,
            "MENU GŁOSOWE",
            "VOICE MENU",
            [
                "pomoc / menu / stan",
                "przedstaw się / godzina",
                "gdzie są klucze",
                "przypomnij za 10 sek",
                "focus 1 / break 1",
            ],
            [
                "help / menu / status",
                "introduce / time",
                "where are my keys",
                "remind me in 10 sec",
                "focus 1 / break 1",
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

        lang = self.last_language
        self.display.show_block(
            "TIMER START",
            [f"mode: {mode}", f"{minutes:g} min", "running"],
            duration=6.0,
        )

        self._speak_localized(
            lang,
            f"Uruchomiłam timer {mode} na {minutes:g} minut.",
            f"I started the {mode} timer for {minutes:g} minutes.",
        )

    def _on_timer_finished(self, mode: str) -> None:
        self.state["current_timer"] = None
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self._save_state()

        self.display.show_block(
            "TIMER DONE",
            [f"mode: {mode}", "finished", "cleared"],
            duration=6.0,
        )

        self._speak_localized(
            self.last_language,
            f"Timer {mode} został zakończony.",
            f"The {mode} timer has finished.",
        )
        append_log(f"{mode.capitalize()} timer finished.")

    def _on_timer_stopped(self, mode: str) -> None:
        self.state["current_timer"] = None
        self.state["focus_mode"] = False
        self.state["break_mode"] = False
        self._save_state()

        self.display.show_block(
            "TIMER STOPPED",
            [f"mode: {mode}", "stopped", "cleared"],
            duration=6.0,
        )

        self._speak_localized(
            self.last_language,
            f"Zatrzymałam timer {mode}.",
            f"I stopped the {mode} timer.",
        )
        append_log(f"{mode.capitalize()} timer stopped.")

    def _reminder_loop(self) -> None:
        while not self._stop_background.is_set():
            due_reminders = self.reminders.check_due_reminders()

            for reminder in due_reminders:
                message = reminder.get("message", "Reminder triggered.")
                reminder_id = reminder.get("id", "unknown")
                lang = self.last_language

                self.display.show_block(
                    self._localized(lang, "PRZYPOMNIENIE", "REMINDER"),
                    [message, f"id: {reminder_id}"],
                    duration=self.default_overlay_seconds,
                )
                self._speak_localized(
                    lang,
                    f"Przypomnienie. {message}",
                    f"Reminder. {message}",
                )
                append_log(f"Reminder triggered: id={reminder_id}, message={message}")

            time.sleep(1)

    def _ask_for_confirmation(self, suggestions: list[dict], lang: str) -> bool:
        self.pending_confirmation = {
            "suggestions": suggestions,
            "language": lang,
        }

        first = self._action_label(suggestions[0]["action"], lang)
        second = self._action_label(suggestions[1]["action"], lang) if len(suggestions) > 1 else None

        if lang == "pl":
            lines = [f"1: {first}"]
            voice_text = f"Czy chodziło ci o {first}"
            if second:
                lines.append(f"2: {second}")
                voice_text += f" czy o {second}"
            lines.append("powiedz tak/nie")
            voice_text += "? Powiedz tak albo nie."
            title = "POTWIERDŹ"
        else:
            lines = [f"1: {first}"]
            voice_text = f"Did you mean {first}"
            if second:
                lines.append(f"2: {second}")
                voice_text += f" or {second}"
            lines.append("say yes/no")
            voice_text += "? Say yes or no."
            title = "CONFIRM"

        self.display.show_block(title, lines, duration=self.default_overlay_seconds)
        self.voice_out.speak(voice_text, language=lang)
        return True

    def _handle_pending_confirmation(self, text: str, current_lang: str) -> bool:
        lang = self.pending_confirmation.get("language", current_lang) if self.pending_confirmation else current_lang
        result = self.parser.parse(text)
        suggestions = self.pending_confirmation.get("suggestions", []) if self.pending_confirmation else []
        allowed_actions = [item["action"] for item in suggestions]

        if result.action == "confirm_yes":
            chosen = suggestions[0]["action"] if suggestions else None
            self.pending_confirmation = None
            if chosen:
                return self._execute_intent(IntentResult(action=chosen, data={}, normalized_text=text), lang)
            return True

        if result.action == "confirm_no":
            self.pending_confirmation = None
            self._speak_localized(
                lang,
                "Dobrze. Powtórz proszę komendę.",
                "Okay. Please repeat the command.",
            )
            return True

        direct_choice = self.parser.find_action_in_text(text, allowed_actions=allowed_actions)
        if direct_choice:
            self.pending_confirmation = None
            return self._execute_intent(IntentResult(action=direct_choice, data={}, normalized_text=text), lang)

        self._speak_localized(
            lang,
            "Powiedz tak albo nie.",
            "Please say yes or no.",
        )
        return True

    def _format_time_answer(self, lang: str) -> str:
        now = datetime.now().strftime("%H:%M")
        return self._localized(lang, f"Jest {now}.", f"It is {now}.")

    def _execute_intent(self, result: IntentResult, lang: str) -> bool:
        self.last_language = lang
        append_log(
            f"Parsed intent: action={result.action}, data={result.data}, text={result.normalized_text}, lang={lang}"
        )

        if result.action == "show_menu":
            self._show_menu(lang)
            self._speak_localized(lang, "Wyświetlam menu.", "Showing the menu.")
            return True

        if result.action == "help":
            self._show_localized_block(
                lang,
                "POMOC",
                "HELP",
                [
                    "pomoc / menu / stan",
                    "przedstaw się / godzina",
                    "gdzie są klucze",
                    "klucze są w kuchni",
                    "przypomnij za 10 sek",
                ],
                [
                    "help / menu / status",
                    "introduce / time",
                    "where are my keys",
                    "keys are in kitchen",
                    "remind me in 10 sec",
                ],
            )
            self._speak_localized(
                lang,
                "Mogę pokazać menu, powiedzieć godzinę, przedstawić się, zapamiętać informacje, odczytać pamięć i ustawić przypomnienie.",
                "I can show the menu, tell the time, introduce myself, remember information, recall memory, and create reminders.",
            )
            return True

        if result.action == "introduce_self":
            self.pending_name_request = True
            self.pending_name_language = lang

            self._show_localized_block(
                lang,
                "O MNIE",
                "ABOUT ME",
                [
                    "jestem prototypem",
                    "na assessment",
                    "roboczo: Smart",
                    "czekam na imię",
                ],
                [
                    "I am a prototype",
                    "for assessment",
                    "working name: Smart",
                    "still waiting for a name",
                ],
            )
            self._speak_localized(
                lang,
                "Jestem prototypem na assessment. Roboczo nazywam się Smart Assistant i nadal czekam na swoje prawdziwe imię. A ty jak się nazywasz?",
                "I am a prototype for the assessment. My working name is Smart Assistant and I am still waiting for my real name. What is your name?",
            )
            return True

        if result.action == "ask_time":
            answer = self._format_time_answer(lang)
            self.display.show_block(
                self._localized(lang, "GODZINA", "TIME"),
                [answer],
                duration=6.0,
            )
            self.voice_out.speak(answer, language=lang)
            return True

        if result.action == "status":
            timer_status = self.timer.status()
            if lang == "pl":
                lines = [
                    f"skupienie: {'ON' if self.state.get('focus_mode') else 'OFF'}",
                    f"przerwa: {'ON' if self.state.get('break_mode') else 'OFF'}",
                    f"timer: {self.state.get('current_timer') or 'brak'}",
                    f"działa: {'TAK' if timer_status.get('running') else 'NIE'}",
                ]
                title = "STAN"
                spoken = "Pokazuję aktualny stan."
            else:
                lines = [
                    f"focus: {'ON' if self.state.get('focus_mode') else 'OFF'}",
                    f"break: {'ON' if self.state.get('break_mode') else 'OFF'}",
                    f"timer: {self.state.get('current_timer') or 'none'}",
                    f"running: {'YES' if timer_status.get('running') else 'NO'}",
                ]
                title = "STATUS"
                spoken = "Showing the current status."

            self.display.show_block(title, lines, duration=self.default_overlay_seconds)
            self.voice_out.speak(spoken, language=lang)
            return True

        if result.action == "memory_list":
            all_memory = self.memory.get_all()
            if not all_memory:
                self._speak_localized(
                    lang,
                    "Pamięć jest obecnie pusta.",
                    "Memory is currently empty.",
                )
                return True

            memory_lines = [f"{key} -> {value}" for key, value in all_memory.items()]
            self.display.show_block(
                self._localized(lang, "PAMIĘĆ", "MEMORY"),
                memory_lines,
                duration=self.default_overlay_seconds,
            )
            self._speak_localized(
                lang,
                "Pokazuję zapisane elementy pamięci.",
                "Showing saved memory items.",
            )
            return True

        if result.action == "reminders_list":
            reminders = self.reminders.list_all()
            if not reminders:
                self._speak_localized(
                    lang,
                    "Nie ma zapisanych przypomnień.",
                    "There are no reminders saved.",
                )
                return True

            reminder_lines = [f"{item['id']} {item['status']}" for item in reminders]
            self.display.show_block(
                self._localized(lang, "PRZYPOMNIENIA", "REMINDERS"),
                reminder_lines,
                duration=self.default_overlay_seconds,
            )
            self._speak_localized(
                lang,
                "Pokazuję przypomnienia.",
                "Showing reminders.",
            )
            return True

        if result.action == "memory_store":
            key = result.data["key"].strip().lower()
            value = result.data["value"].strip()
            self.memory.remember(key, value)
            self.display.show_block(
                self._localized(lang, "PAMIĘĆ ZAPISANA", "MEMORY SAVED"),
                [key, value],
                duration=8.0,
            )
            self._speak_localized(
                lang,
                f"Zapisałam, że {key} jest {value}.",
                f"I saved that {key} is {value}.",
            )
            return True

        if result.action == "memory_recall":
            key = result.data["key"].strip().lower()
            value = self.memory.recall(key)

            if value is None:
                self.display.show_block(
                    self._localized(lang, "ODCZYT", "RECALL"),
                    [key, self._localized(lang, "nie znaleziono", "not found")],
                    duration=8.0,
                )
                self._speak_localized(
                    lang,
                    f"Nie mam zapisanej informacji dla {key}.",
                    f"I do not have anything saved for {key}.",
                )
            else:
                self.display.show_block(
                    self._localized(lang, "ODCZYT", "RECALL"),
                    [key, value],
                    duration=8.0,
                )
                self._speak_localized(
                    lang,
                    f"{key} jest {value}.",
                    f"{key} is {value}.",
                )
            return True

        if result.action == "reminder_create":
            seconds = int(result.data["seconds"])
            message = result.data["message"].strip()
            reminder = self.reminders.add_after_seconds(seconds, message)

            self.display.show_block(
                self._localized(lang, "PRZYPOMNIENIE UST.", "REMINDER SET"),
                [
                    f"id: {reminder['id']}",
                    self._localized(lang, f"za {seconds}s", f"in {seconds}s"),
                ],
                duration=8.0,
            )
            self._speak_localized(
                lang,
                f"Zapisałam przypomnienie. Włączy się za {seconds} sekund.",
                f"Reminder saved. It will trigger in {seconds} seconds.",
            )
            return True

        if result.action == "focus_start":
            minutes = float(result.data["minutes"])
            self.timer.start(minutes, "focus")
            return True

        if result.action == "break_start":
            minutes = float(result.data["minutes"])
            self.timer.start(minutes, "break")
            return True

        if result.action == "timer_stop":
            ok, _ = self.timer.stop()
            if not ok:
                self._speak_localized(
                    lang,
                    "Żaden timer nie jest teraz uruchomiony.",
                    "No timer is currently running.",
                )
            return True

        if result.action == "exit":
            return False

        if result.action in {"confirm_yes", "confirm_no"}:
            self._speak_localized(
                lang,
                "Nie ma teraz nic do potwierdzenia.",
                "There is nothing to confirm right now.",
            )
            return True

        if result.action == "unclear" and result.suggestions:
            return self._ask_for_confirmation(result.suggestions, lang)

        self.display.show_block(
            self._localized(lang, "NIEJASNA KOMENDA", "UNCLEAR COMMAND"),
            [
                result.normalized_text[:18] or self._localized(lang, "brak", "none"),
                self._localized(lang, "co miała znaczyć?", "what did you mean?"),
            ],
            duration=8.0,
        )
        self._speak_localized(
            lang,
            "Nie do końca zrozumiałam. Co miałeś na myśli?",
            "I did not fully understand. What did you mean?",
        )
        return True

    def handle_command(self, text: str) -> bool:
        cleaned = text.strip()
        if not cleaned:
            return True

        lang = self._detect_language(cleaned)
        self.last_language = lang

        append_log(f"User said: {cleaned}")

        if self.pending_name_request and self._try_handle_name_capture(cleaned, lang):
            return True

        if self.pending_confirmation:
            return self._handle_pending_confirmation(cleaned, lang)

        result = self.parser.parse(cleaned)
        return self._execute_intent(result, lang)