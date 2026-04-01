from __future__ import annotations

import re
import threading
import time
from datetime import datetime
from typing import Any

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
        self.boot_overlay_seconds = float(display_cfg.get("boot_overlay_seconds", 2.8))

        self.parser = IntentParser(
            default_focus_minutes=float(self.settings.get("timers", {}).get("default_focus_minutes", 25)),
            default_break_minutes=float(self.settings.get("timers", {}).get("default_break_minutes", 5)),
        )

        self.pending_confirmation: dict[str, Any] | None = None
        self.pending_follow_up: dict[str, Any] | None = None
        self.last_language = "en"

        if voice_input_cfg.get("enabled", True):
            engine = str(voice_input_cfg.get("engine", "whisper")).lower()

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
            piper_models=voice_output_cfg.get("piper_models"),
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

        time.sleep(self.boot_overlay_seconds + 0.1)
        time.sleep(1.2)

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
        return self.parser._normalize_text(text)

    def _detect_language(self, text: str) -> str:
        normalized = self._normalize_text(text)
        tokens = set(normalized.split())

        polish_markers = {
            "pomoc",
            "potrafisz",
            "godzina",
            "data",
            "dzien",
            "rok",
            "przypomnij",
            "zapamietaj",
            "gdzie",
            "imie",
            "przerwa",
            "skupienie",
            "ucze",
            "pokaz",
            "wyswietl",
            "tak",
            "nie",
        }
        english_markers = {
            "help",
            "time",
            "date",
            "day",
            "year",
            "remember",
            "remind",
            "where",
            "name",
            "focus",
            "break",
            "timer",
            "show",
            "display",
            "yes",
            "no",
            "assistant",
        }

        if any(ch in text for ch in "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"):
            return "pl"
        if tokens & polish_markers:
            return "pl"
        if tokens & english_markers:
            return "en"
        return self.last_language or "en"

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
            "status": {"pl": "stan", "en": "status"},
            "memory_list": {"pl": "pamięć", "en": "memory"},
            "reminders_list": {"pl": "przypomnienia", "en": "reminders"},
            "timer_stop": {"pl": "wyłącz timer", "en": "stop timer"},
            "introduce_self": {"pl": "przedstaw się", "en": "introduce yourself"},
            "ask_time": {"pl": "godzina", "en": "time"},
            "show_time": {"pl": "pokaż godzinę", "en": "show time"},
            "ask_date": {"pl": "data", "en": "date"},
            "show_date": {"pl": "pokaż datę", "en": "show date"},
            "ask_day": {"pl": "dzień", "en": "day"},
            "show_day": {"pl": "pokaż dzień", "en": "show day"},
            "ask_year": {"pl": "rok", "en": "year"},
            "show_year": {"pl": "pokaż rok", "en": "show year"},
            "timer_start": {"pl": "timer", "en": "timer"},
            "focus_start": {"pl": "focus mode", "en": "focus mode"},
            "break_start": {"pl": "tryb przerwy", "en": "break mode"},
            "memory_store": {"pl": "zapamiętywanie", "en": "remembering"},
            "memory_recall": {"pl": "odczyt pamięci", "en": "memory recall"},
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
                "help",
                "pomoc",
                "status",
                "stan",
                "tak",
                "nie",
                "yes",
                "no",
                "focus",
                "break",
                "time",
                "godzina",
            }
            if token.lower() not in blocked and len(token) >= 2:
                return token[:1].upper() + token[1:].lower()

        return None

    def _extract_minutes_from_text(self, text: str) -> float | None:
        normalized = self._normalize_text(text)
        match = re.search(
            r"(\d+(?:[\.,]\d+)?)\s*(second|seconds|sec|sekunda|sekundy|sekund|minute|minutes|min|minuta|minuty|minut)?",
            normalized,
        )
        if not match:
            return None

        value = float(match.group(1).replace(",", "."))
        unit = (match.group(2) or "minutes").strip()

        if unit.startswith("sec") or unit.startswith("sek"):
            return round(value / 60.0, 2)
        return value

    def _is_yes(self, text: str) -> bool:
        return self.parser.parse(text).action == "confirm_yes"

    def _is_no(self, text: str) -> bool:
        return self.parser.parse(text).action == "confirm_no"

    def _show_capabilities(self, lang: str) -> None:
        self._show_localized_block(
            lang,
            "CO POTRAFIĘ",
            "HOW I CAN HELP",
            [
                "zapamietam rzeczy",
                "przypomnienia i timer",
                "godzina data dzien",
                "focus i przerwa",
                "pokaze info na OLED",
            ],
            [
                "remember things",
                "reminders and timer",
                "time date and day",
                "focus and break",
                "show info on OLED",
            ],
            duration=12.0,
        )

    def _offer_oled_display(self, lang: str, title: str, lines: list[str]) -> None:
        self.pending_follow_up = {
            "type": "display_offer",
            "lang": lang,
            "title": title,
            "lines": lines,
        }
        self._speak_localized(
            lang,
            "Czy chcesz, żebym pokazała to na ekranie?",
            "Would you like me to show that on the screen?",
        )

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

    def _format_temporal_text(self, kind: str, lang: str) -> tuple[str, str, list[str]]:
        now = datetime.now()

        if kind == "time":
            value = now.strftime("%H:%M")
            spoken = self._localized(lang, f"Jest {value}.", f"It is {value}.")
            title = self._localized(lang, "GODZINA", "TIME")
            lines = [value]
            return spoken, title, lines

        if kind == "date":
            value = now.strftime("%d-%m-%Y")
            spoken = self._localized(lang, f"Dzisiejsza data to {value}.", f"Today's date is {value}.")
            title = self._localized(lang, "DATA", "DATE")
            lines = [value]
            return spoken, title, lines

        if kind == "day":
            days_en = [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
            days_pl = [
                "poniedziałek",
                "wtorek",
                "środa",
                "czwartek",
                "piątek",
                "sobota",
                "niedziela",
            ]
            value = days_pl[now.weekday()] if lang == "pl" else days_en[now.weekday()]
            spoken = self._localized(lang, f"Dzisiaj jest {value}.", f"Today is {value}.")
            title = self._localized(lang, "DZIEŃ", "DAY")
            lines = [value]
            return spoken, title, lines

        value = str(now.year)
        spoken = self._localized(lang, f"Mamy rok {value}.", f"The year is {value}.")
        title = self._localized(lang, "ROK", "YEAR")
        lines = [value]
        return spoken, title, lines

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

        self.display.show_block(
            self._localized(lang, "TIMER START", "TIMER START"),
            [self._localized(lang, mode_label_pl, mode_label_en), f"{minutes:g} min"],
            duration=6.0,
        )

        self._speak_localized(
            lang,
            f"Uruchomiłam {mode_label_pl} na {minutes:g} minut.",
            f"I started the {mode_label_en} for {minutes:g} minutes.",
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

    def _ask_for_confirmation(self, suggestions: list[dict[str, Any]], lang: str) -> bool:
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
            lines.append("powiedz tak lub nie")
            voice_text += "? Powiedz tak albo nie."
            title = "POTWIERDŹ"
        else:
            lines = [f"1: {first}"]
            voice_text = f"Did you mean {first}"
            if second:
                lines.append(f"2: {second}")
                voice_text += f" or {second}"
            lines.append("say yes or no")
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
                "Dobrze. Powiedz to jeszcze raz inaczej.",
                "Okay. Please say it again in a different way.",
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

    def _handle_pending_follow_up(self, text: str, lang: str) -> bool:
        follow_up = self.pending_follow_up or {}
        follow_type = follow_up.get("type")

        if follow_type == "capture_name":
            name = self._extract_name(text)
            if not name:
                self._speak_localized(
                    lang,
                    "Nie usłyszałam wyraźnie imienia. Powiedz proszę jeszcze raz swoje imię.",
                    "I did not catch your name clearly. Please say your name again.",
                )
                return True

            self.pending_follow_up = {
                "type": "confirm_save_name",
                "lang": lang,
                "name": name,
            }
            self._speak_localized(
                lang,
                f"Miło mi, {name}. Czy chcesz, żebym zapamiętała twoje imię?",
                f"Nice to meet you, {name}. Would you like me to remember your name?",
            )
            return True

        if follow_type == "confirm_save_name":
            name = follow_up.get("name", "")
            if self._is_yes(text):
                self.user_profile["conversation_partner_name"] = name
                self._save_user_profile()
                self.pending_follow_up = None
                self._show_localized_block(
                    lang,
                    "IMIĘ ZAPISANE",
                    "NAME SAVED",
                    [name, "zapamiętałam imię"],
                    [name, "I remembered your name"],
                    duration=8.0,
                )
                self._speak_localized(
                    lang,
                    f"Dobrze. Zapamiętałam twoje imię, {name}.",
                    f"Okay. I will remember your name, {name}.",
                )
                return True

            if self._is_no(text):
                self.pending_follow_up = None
                self._speak_localized(
                    lang,
                    "Dobrze. Nie zapisuję twojego imienia.",
                    "Okay. I will not save your name.",
                )
                return True

            self._speak_localized(
                lang,
                "Powiedz tak albo nie.",
                "Please say yes or no.",
            )
            return True

        if follow_type in {"timer_duration", "focus_duration", "break_duration"}:
            minutes = self._extract_minutes_from_text(text)
            if minutes is None or minutes <= 0:
                self._speak_localized(
                    lang,
                    "Podaj proszę czas w minutach albo sekundach.",
                    "Please tell me the duration in minutes or seconds.",
                )
                return True

            self.pending_follow_up = None

            if follow_type == "timer_duration":
                return self._start_timer_mode(minutes, "timer", lang)
            if follow_type == "focus_duration":
                return self._start_timer_mode(minutes, "focus", lang)
            return self._start_timer_mode(minutes, "break", lang)

        if follow_type == "display_offer":
            if self._is_yes(text):
                self.pending_follow_up = None
                self.display.show_block(
                    follow_up.get("title", "INFO"),
                    follow_up.get("lines", []),
                    duration=self.default_overlay_seconds,
                )
                self._speak_localized(
                    lang,
                    "Dobrze. Pokazuję to na ekranie.",
                    "Okay. I am showing it on the screen.",
                )
                return True

            if self._is_no(text):
                self.pending_follow_up = None
                self._speak_localized(
                    lang,
                    "Dobrze.",
                    "Okay.",
                )
                return True

            self._speak_localized(
                lang,
                "Powiedz tak albo nie.",
                "Please say yes or no.",
            )
            return True

        if follow_type == "post_focus_break_offer":
            direct_minutes = self._extract_minutes_from_text(text)
            if direct_minutes is not None and direct_minutes > 0 and not self._is_no(text):
                self.pending_follow_up = None
                return self._start_timer_mode(direct_minutes, "break", lang)

            if self._is_yes(text):
                self.pending_follow_up = {
                    "type": "break_duration",
                    "lang": lang,
                }
                self._speak_localized(
                    lang,
                    "Jak długa ma być przerwa?",
                    "How long should the break be?",
                )
                return True

            if self._is_no(text):
                self.pending_follow_up = None
                self._speak_localized(
                    lang,
                    "Dobrze. Nie uruchamiam przerwy.",
                    "Okay. I will not start a break.",
                )
                return True

            self._speak_localized(
                lang,
                "Powiedz tak, nie albo od razu podaj długość przerwy.",
                "Say yes, no, or tell me the break duration right away.",
            )
            return True

        self.pending_follow_up = None
        return False

    def _execute_intent(self, result: IntentResult, lang: str) -> bool:
        self.last_language = lang
        append_log(
            f"Parsed intent: action={result.action}, data={result.data}, text={result.normalized_text}, lang={lang}"
        )

        if result.action == "help":
            self._show_capabilities(lang)
            self._speak_localized(
                lang,
                "Mogę zapamiętywać informacje, ustawiać przypomnienia i timery, podawać godzinę, datę, dzień i rok, prowadzić focus mode i przerwę oraz pokazywać informacje na ekranie.",
                "I can remember information, set reminders and timers, tell you the time, date, day and year, run focus and break sessions, and show information on the screen.",
            )
            return True

        if result.action == "introduce_self":
            self.pending_follow_up = {
                "type": "capture_name",
                "lang": lang,
            }
            self._show_localized_block(
                lang,
                "CZEŚĆ",
                "HELLO",
                [
                    "jestem Smart Assistant",
                    "mogę ci pomagać",
                    "jak masz na imię?",
                ],
                [
                    "I am Smart Assistant",
                    "I can help you",
                    "what is your name?",
                ],
                duration=10.0,
            )
            self._speak_localized(
                lang,
                "Jestem Smart Assistant. Mogę zapamiętywać rzeczy, ustawiać przypomnienia i pomagać ci podczas nauki. Jak masz na imię?",
                "I am Smart Assistant. I can remember things, set reminders, and help you during study sessions. What is your name?",
            )
            return True

        if result.action in {
            "ask_time",
            "show_time",
            "ask_date",
            "show_date",
            "ask_day",
            "show_day",
            "ask_year",
            "show_year",
        }:
            if "time" in result.action:
                kind = "time"
            elif "date" in result.action:
                kind = "date"
            elif "day" in result.action:
                kind = "day"
            else:
                kind = "year"

            spoken, title, lines = self._format_temporal_text(kind, lang)
            self.voice_out.speak(spoken, language=lang)

            if result.action.startswith("show_"):
                self.display.show_block(title, lines, duration=self.default_overlay_seconds)
            else:
                self._offer_oled_display(lang, title, lines)
            return True

        if result.action == "status":
            timer_status = self.timer.status()
            if lang == "pl":
                lines = [
                    f"focus: {'ON' if self.state.get('focus_mode') else 'OFF'}",
                    f"przerwa: {'ON' if self.state.get('break_mode') else 'OFF'}",
                    f"timer: {self.state.get('current_timer') or 'brak'}",
                    f"działa: {'TAK' if timer_status.get('running') else 'NIE'}",
                ]
                spoken = "Pokazuję aktualny stan asystenta."
            else:
                lines = [
                    f"focus: {'ON' if self.state.get('focus_mode') else 'OFF'}",
                    f"break: {'ON' if self.state.get('break_mode') else 'OFF'}",
                    f"timer: {self.state.get('current_timer') or 'none'}",
                    f"running: {'YES' if timer_status.get('running') else 'NO'}",
                ]
                spoken = "Showing the current assistant status."

            self.display.show_block(
                self._localized(lang, "STATUS", "STATUS"),
                lines,
                duration=self.default_overlay_seconds,
            )
            self.voice_out.speak(spoken, language=lang)
            return True

        if result.action == "memory_list":
            all_memory = self.memory.get_all()
            if not all_memory:
                self._speak_localized(
                    lang,
                    "Na razie niczego nie zapamiętałam.",
                    "I have not remembered anything yet.",
                )
                return True

            memory_lines = [f"{key} -> {value}" for key, value in list(all_memory.items())[:5]]
            self.display.show_block(
                self._localized(lang, "PAMIĘĆ", "MEMORY"),
                memory_lines,
                duration=self.default_overlay_seconds,
            )
            self._speak_localized(
                lang,
                "Pokazuję zapisane rzeczy.",
                "I am showing the saved items.",
            )
            return True

        if result.action == "reminders_list":
            reminders = self.reminders.list_all()
            if not reminders:
                self._speak_localized(
                    lang,
                    "Nie ma zapisanych przypomnień.",
                    "There are no saved reminders.",
                )
                return True

            reminder_lines = [f"{item['id']} {item['status']}" for item in reminders[:5]]
            self.display.show_block(
                self._localized(lang, "PRZYPOMNIENIA", "REMINDERS"),
                reminder_lines,
                duration=self.default_overlay_seconds,
            )
            self._speak_localized(
                lang,
                "Pokazuję zapisane przypomnienia.",
                "I am showing the saved reminders.",
            )
            return True

        if result.action == "memory_store":
            key = result.data.get("key", "").strip().lower()
            value = result.data.get("value", "").strip()
            memory_text = result.data.get("memory_text", "").strip()

            if key and value:
                self.memory.remember(key, value)
                spoken_pl = f"Dobrze. Zapamiętałam, że {key} jest {value}."
                spoken_en = f"Okay. I remembered that {key} is {value}."
                title = self._localized(lang, "PAMIĘĆ", "MEMORY")
                lines = [key, value]
            elif memory_text:
                self.memory.remember(memory_text, memory_text)
                spoken_pl = "Dobrze. Zapamiętałam tę informację."
                spoken_en = "Okay. I remembered that information."
                title = self._localized(lang, "PAMIĘĆ", "MEMORY")
                lines = [memory_text]
            else:
                self._speak_localized(
                    lang,
                    "Nie usłyszałam, co mam zapamiętać.",
                    "I did not catch what I should remember.",
                )
                return True

            self.voice_out.speak(self._localized(lang, spoken_pl, spoken_en), language=lang)
            self.display.show_block(title, lines, duration=8.0)
            return True

        if result.action == "memory_recall":
            key = result.data["key"].strip().lower()
            value = self.memory.recall(key)

            if value is None:
                self._speak_localized(
                    lang,
                    f"Nie mam zapisanej informacji dla {key}.",
                    f"I do not have anything saved for {key}.",
                )
                return True

            answer = self._localized(lang, f"{key} jest {value}.", f"{key} is {value}.")
            self.voice_out.speak(answer, language=lang)
            self._offer_oled_display(
                lang,
                self._localized(lang, "ODPOWIEDŹ", "ANSWER"),
                [f"{key}: {value}"],
            )
            return True

        if result.action == "reminder_create":
            seconds = int(result.data["seconds"])
            message = result.data["message"].strip()
            reminder = self.reminders.add_after_seconds(seconds, message)

            self.display.show_block(
                self._localized(lang, "PRZYPOMNIENIE", "REMINDER"),
                [message, self._localized(lang, f"za {seconds} s", f"in {seconds} s")],
                duration=8.0,
            )
            self._speak_localized(
                lang,
                f"Dobrze. Przypomnę ci o tym za {seconds} sekund.",
                f"Okay. I will remind you about that in {seconds} seconds.",
            )
            append_log(f"Reminder created: {reminder['id']}")
            return True

        if result.action == "timer_start":
            minutes = result.data.get("minutes")
            if minutes is None:
                self.pending_follow_up = {"type": "timer_duration", "lang": lang}
                self._speak_localized(
                    lang,
                    "Na jak długo mam ustawić timer?",
                    "How long should I set the timer for?",
                )
                return True
            return self._start_timer_mode(float(minutes), "timer", lang)

        if result.action == "focus_start":
            minutes = result.data.get("minutes")
            if minutes is None:
                self.pending_follow_up = {"type": "focus_duration", "lang": lang}
                self._speak_localized(
                    lang,
                    "Jak długa ma być sesja focus?",
                    "How long should the focus session be?",
                )
                return True
            return self._start_timer_mode(float(minutes), "focus", lang)

        if result.action == "break_start":
            minutes = result.data.get("minutes")
            if minutes is None:
                self.pending_follow_up = {"type": "break_duration", "lang": lang}
                self._speak_localized(
                    lang,
                    "Jak długa ma być przerwa?",
                    "How long should the break be?",
                )
                return True
            return self._start_timer_mode(float(minutes), "break", lang)

        if result.action == "timer_stop":
            self.pending_follow_up = None
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

        lang = self._detect_language(cleaned)
        self.last_language = lang
        append_log(f"User said: {cleaned}")

        if self.pending_confirmation:
            return self._handle_pending_confirmation(cleaned, lang)

        if self.pending_follow_up:
            handled = self._handle_pending_follow_up(cleaned, lang)
            if handled:
                return True

        result = self.parser.parse(cleaned)
        return self._execute_intent(result, lang)