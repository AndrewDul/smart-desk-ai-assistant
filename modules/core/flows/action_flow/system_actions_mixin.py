from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RouteDecision, RouteKind

from .models import ResolvedAction


class ActionSystemActionsMixin:
    def _handle_help(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        spoken = self._localized(
            language,
            "Mogę rozmawiać z Tobą, zapamiętywać informacje, ustawiać przypomnienia, uruchamiać timery, focus mode i break mode oraz podawać czas i datę.",
            "I can talk with you, remember information, set reminders, start timers, focus mode and break mode, and tell you the time and date.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="help",
            spoken_text=spoken,
            display_title=self._localized(language, "JAK MOGĘ POMÓC", "HOW I CAN HELP"),
            display_lines=self._localized_lines(
                language,
                ["rozmowa", "pamiec", "przypomnienia", "timery i focus"],
                ["conversation", "memory", "reminders", "timers and focus"],
            ),
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_status(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload

        timer_status = self._timer_status()
        memory_count = len(self._memory_items())
        reminder_count = len(self._reminder_items())
        current_timer = self.assistant.state.get("current_timer") or self._localized(language, "brak", "none")
        focus_on = bool(self.assistant.state.get("focus_mode"))
        break_on = bool(self.assistant.state.get("break_mode"))
        timer_running = bool(timer_status.get("running"))

        if language == "pl":
            spoken = (
                f"Focus jest {'włączony' if focus_on else 'wyłączony'}, "
                f"przerwa jest {'włączona' if break_on else 'wyłączona'}, "
                f"aktywny timer to {current_timer}, "
                f"w pamięci mam {memory_count} wpisów, "
                f"a przypomnień jest {reminder_count}."
            )
            lines = [
                f"focus: {'ON' if focus_on else 'OFF'}",
                f"przerwa: {'ON' if break_on else 'OFF'}",
                f"timer: {current_timer}",
                f"pamiec: {memory_count}",
                f"przyp: {reminder_count}",
                f"dziala: {'TAK' if timer_running else 'NIE'}",
            ]
        else:
            spoken = (
                f"Focus is {'on' if focus_on else 'off'}, "
                f"break is {'on' if break_on else 'off'}, "
                f"the current timer is {current_timer}, "
                f"I have {memory_count} memory items, "
                f"and there are {reminder_count} reminders."
            )
            lines = [
                f"focus: {'ON' if focus_on else 'OFF'}",
                f"break: {'ON' if break_on else 'OFF'}",
                f"timer: {current_timer}",
                f"memory: {memory_count}",
                f"remind: {reminder_count}",
                f"running: {'YES' if timer_running else 'NO'}",
            ]

        return self._deliver_simple_action_response(
            language=language,
            action="status",
            spoken_text=spoken,
            display_title="STATUS",
            display_lines=lines,
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_introduce_self(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload

        spoken = self._localized(
            language,
            "Nazywam się NeXa. Jestem lokalnym asystentem biurkowym działającym na Raspberry Pi.",
            "My name is NeXa. I am a local desk assistant running on Raspberry Pi.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="introduce_self",
            spoken_text=spoken,
            display_title="NeXa",
            display_lines=self._localized_lines(
                language,
                ["lokalny", "desk assistant", "raspberry pi"],
                ["local", "desk assistant", "raspberry pi"],
            ),
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_ask_time(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        now = self._now_london()
        spoken = self._localized(language, f"Jest {now.strftime('%H:%M')}.", f"It is {now.strftime('%H:%M')}.")
        return self._deliver_simple_action_response(
            language=language,
            action="ask_time",
            spoken_text=spoken,
            display_title="TIME",
            display_lines=[now.strftime("%H:%M")],
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_show_time(self, **kwargs: Any) -> bool:
        return self._handle_ask_time(**kwargs)

    def _handle_ask_date(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        now = self._now_london()
        spoken = self._localized(
            language,
            f"Dzisiaj jest {now.strftime('%d.%m.%Y')}.",
            f"Today is {now.strftime('%d.%m.%Y')}.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="ask_date",
            spoken_text=spoken,
            display_title="DATE",
            display_lines=[now.strftime("%d.%m.%Y")],
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_show_date(self, **kwargs: Any) -> bool:
        return self._handle_ask_date(**kwargs)

    def _handle_ask_day(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        now = self._now_london()
        day_name = self._localized_day_name(now.weekday(), language)
        spoken = self._localized(language, f"Dzisiaj jest {day_name}.", f"Today is {day_name}.")
        return self._deliver_simple_action_response(
            language=language,
            action="ask_day",
            spoken_text=spoken,
            display_title="DAY",
            display_lines=[day_name],
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_show_day(self, **kwargs: Any) -> bool:
        return self._handle_ask_day(**kwargs)

    def _handle_ask_month(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        now = self._now_london()
        month_name = self._localized_month_name(now.month, language)
        spoken = self._localized(language, f"Jest miesiąc {month_name}.", f"It is {month_name}.")
        return self._deliver_simple_action_response(
            language=language,
            action="ask_month",
            spoken_text=spoken,
            display_title="MONTH",
            display_lines=[month_name],
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_show_month(self, **kwargs: Any) -> bool:
        return self._handle_ask_month(**kwargs)

    def _handle_ask_year(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        now = self._now_london()
        spoken = self._localized(language, f"Mamy rok {now.year}.", f"The year is {now.year}.")
        return self._deliver_simple_action_response(
            language=language,
            action="ask_year",
            spoken_text=spoken,
            display_title="YEAR",
            display_lines=[str(now.year)],
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_show_year(self, **kwargs: Any) -> bool:
        return self._handle_ask_year(**kwargs)

    def _handle_exit(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        self.assistant.pending_follow_up = {"type": "confirm_exit", "lang": language}
        spoken = self._localized(
            language,
            "Czy chcesz, żebym zamknęła asystenta?",
            "Do you want me to close the assistant?",
        )
        return self.assistant.deliver_text_response(
            spoken,
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="action_exit_confirmation",
            metadata={"resolved_source": resolved.source, "follow_up_type": "confirm_exit"},
        )

    def _handle_shutdown(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload

        allow_shutdown = bool(self.assistant.settings.get("system", {}).get("allow_shutdown_commands", False))
        if not allow_shutdown:
            return self._deliver_simple_action_response(
                language=language,
                action="shutdown",
                spoken_text=self._localized(
                    language,
                    "Wyłączanie systemu jest teraz wyłączone w ustawieniach.",
                    "System shutdown is currently disabled in settings.",
                ),
                display_title="SHUTDOWN DISABLED",
                display_lines=self._localized_lines(language, ["sprawdz ustawienia"], ["check settings"]),
                extra_metadata={"resolved_source": resolved.source, "phase": "blocked_by_config"},
            )

        self.assistant.pending_follow_up = {"type": "confirm_shutdown", "lang": language}
        spoken = self._localized(
            language,
            "Czy chcesz, żebym wyłączyła system?",
            "Do you want me to shut down the system?",
        )
        return self.assistant.deliver_text_response(
            spoken,
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="action_shutdown_confirmation",
            metadata={"resolved_source": resolved.source, "follow_up_type": "confirm_shutdown"},
        )

    def _handle_confirm_yes(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        return self._deliver_simple_action_response(
            language=language,
            action="confirm_yes",
            spoken_text=self._localized(
                language,
                "Nie ma teraz nic do potwierdzenia.",
                "There is nothing to confirm right now.",
            ),
            display_title="CONFIRMATION",
            display_lines=self._localized_lines(
                language,
                ["brak aktywnego", "potwierdzenia"],
                ["nothing active", "to confirm"],
            ),
            extra_metadata={"resolved_source": resolved.source, "phase": "orphan_confirmation"},
        )

    def _handle_confirm_no(self, **kwargs: Any) -> bool:
        return self._handle_confirm_yes(**kwargs)

    def _handle_unknown(
        self,
        *,
        route: RouteDecision,
        language: str,
        resolved: ResolvedAction,
    ) -> bool:
        del route
        return self._deliver_simple_action_response(
            language=language,
            action="unknown",
            spoken_text=self._localized(
                language,
                "Nie mam jeszcze tej funkcji w obecnej wersji, ale mogę pomóc z pamięcią, przypomnieniami, timerami, focus mode, break mode oraz czasem i datą.",
                "I do not have that feature in this version yet, but I can help with memory, reminders, timers, focus mode, break mode, and time or date questions.",
            ),
            display_title="ACTION",
            display_lines=self._localized_lines(
                language,
                ["funkcja", "jeszcze niedostepna"],
                ["feature", "not ready yet"],
            ),
            extra_metadata={"resolved_source": resolved.source, "phase": "unsupported_action"},
        )