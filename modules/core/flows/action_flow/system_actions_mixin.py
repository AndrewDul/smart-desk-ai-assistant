from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RouteDecision, RouteKind

from .models import ResolvedAction


class ActionSystemActionsMixin:
    def _runtime_snapshot(self) -> dict[str, Any]:
        assistant = getattr(self, "assistant", None)

        snapshot_method = getattr(assistant, "_runtime_status_snapshot", None)
        if callable(snapshot_method):
            try:
                snapshot = snapshot_method()
                return dict(snapshot or {}) if isinstance(snapshot, dict) else {}
            except Exception:
                return {}

        runtime_product = getattr(assistant, "runtime_product", None)
        snapshot_method = getattr(runtime_product, "snapshot", None)
        if callable(snapshot_method):
            try:
                snapshot = snapshot_method()
                return dict(snapshot or {}) if isinstance(snapshot, dict) else {}
            except Exception:
                return {}

        return {}

    @staticmethod
    def _runtime_service_payload(
        snapshot: dict[str, Any],
        component: str,
    ) -> dict[str, Any]:
        services = snapshot.get("services", {})
        if not isinstance(services, dict):
            return {}

        payload = services.get(component, {})
        return dict(payload or {}) if isinstance(payload, dict) else {}

    @staticmethod
    def _runtime_named_components(
        snapshot: dict[str, Any],
        key: str,
        *,
        fallback_states: tuple[str, ...] = (),
        compatibility_only: bool = False,
    ) -> list[str]:
        direct = [
            str(item).strip()
            for item in snapshot.get(key, [])
            if str(item).strip()
        ]
        if direct:
            return direct

        services = snapshot.get("services", {})
        if not isinstance(services, dict):
            return []

        names: list[str] = []
        for name, payload in services.items():
            if not isinstance(payload, dict):
                continue

            if compatibility_only and bool(payload.get("compatibility_mode", False)):
                names.append(str(name))
                continue

            state = str(payload.get("state", "") or "").strip().lower()
            if fallback_states and state in fallback_states:
                names.append(str(name))

        return names

    @staticmethod
    def _runtime_backend_token(payload: dict[str, Any]) -> str:
        raw = str(
            payload.get("backend")
            or payload.get("selected_backend")
            or payload.get("requested_backend")
            or "n/a"
        ).strip().lower()

        aliases = {
            "compatibility_voice_input": "compat",
            "faster_whisper": "faster",
            "openwakeword": "oww",
            "hailo-ollama": "hailo",
            "text_input": "text",
            "disabled": "off",
            "waveshare_2inch": "waveshare",
        }
        normalized = aliases.get(raw, raw or "n/a")
        return normalized[:14]

    def _build_runtime_status_summary(
        self,
        language: str,
    ) -> tuple[str, list[str], dict[str, Any]]:
        snapshot = self._runtime_snapshot()
        if not snapshot:
            spoken = self._localized(
                language,
                "Nie mam jeszcze pełnego snapshotu runtime, ale podstawowe funkcje asystenta są dostępne.",
                "I do not have a full runtime snapshot yet, but the core assistant features are available.",
            )
            lines = self._localized_lines(
                language,
                ["premium: brak", "core: brak", "wake: n/a", "stt: n/a", "llm: n/a"],
                ["premium: n/a", "core: n/a", "wake: n/a", "stt: n/a", "llm: n/a"],
            )
            return spoken, lines, {"runtime_snapshot_available": False}

        lifecycle_state = str(snapshot.get("lifecycle_state", "unknown") or "unknown").strip().lower()
        premium_ready = bool(snapshot.get("premium_ready", False))
        primary_ready = bool(snapshot.get("primary_ready", snapshot.get("ready", False)))
        status_message = str(snapshot.get("status_message", "") or "").strip()

        compatibility = self._runtime_named_components(
            snapshot,
            "compatibility_components",
            compatibility_only=True,
        )
        degraded_components = self._runtime_named_components(
            snapshot,
            "degraded_components",
            fallback_states=("degraded", "failed"),
        )
        blockers = self._runtime_named_components(
            snapshot,
            "blockers",
            fallback_states=("failed",),
        )

        voice_input = self._runtime_service_payload(snapshot, "voice_input")
        wake_gate = self._runtime_service_payload(snapshot, "wake_gate")
        llm = self._runtime_service_payload(snapshot, "llm")

        voice_token = self._runtime_backend_token(voice_input)
        wake_token = self._runtime_backend_token(wake_gate)
        llm_token = self._runtime_backend_token(llm)

        if language == "pl":
            if premium_ready:
                runtime_sentence = "Tryb premium jest gotowy."
            elif primary_ready and compatibility:
                runtime_sentence = (
                    "Rdzeń runtime działa, ale aktywna jest ścieżka kompatybilności dla: "
                    f"{', '.join(compatibility[:2])}."
                )
            elif blockers:
                runtime_sentence = (
                    "Część wymaganych usług wymaga uwagi: "
                    f"{', '.join(blockers[:2])}."
                )
            elif degraded_components:
                runtime_sentence = (
                    "Runtime działa w trybie ograniczonym. "
                    f"Zdegradowane moduły: {', '.join(degraded_components[:2])}."
                )
            else:
                runtime_sentence = "Runtime jest dostępny, ale raportuje stan pośredni."

            backend_sentence = (
                f"Wake używa {wake_token}, STT używa {voice_token}, a LLM używa {llm_token}."
            )
        else:
            if premium_ready:
                runtime_sentence = "Premium mode is ready."
            elif primary_ready and compatibility:
                runtime_sentence = (
                    "The runtime core is ready, but a compatibility path is active for: "
                    f"{', '.join(compatibility[:2])}."
                )
            elif blockers:
                runtime_sentence = (
                    "Some required services need attention: "
                    f"{', '.join(blockers[:2])}."
                )
            elif degraded_components:
                runtime_sentence = (
                    "The runtime is operating in a limited mode. "
                    f"Degraded modules: {', '.join(degraded_components[:2])}."
                )
            else:
                runtime_sentence = "The runtime is available, but it is reporting an intermediate state."

            backend_sentence = (
                f"Wake uses {wake_token}, STT uses {voice_token}, and LLM uses {llm_token}."
            )

        if status_message and lifecycle_state not in {"ready", "degraded"}:
            runtime_sentence = f"{runtime_sentence} {status_message}"

        lines = self._localized_lines(
            language,
            [
                f"premium: {'TAK' if premium_ready else 'NIE'}",
                f"core: {'TAK' if primary_ready else 'NIE'}",
                f"wake: {wake_token}",
                f"stt: {voice_token}",
                f"llm: {llm_token}",
            ],
            [
                f"premium: {'YES' if premium_ready else 'NO'}",
                f"core: {'YES' if primary_ready else 'NO'}",
                f"wake: {wake_token}",
                f"stt: {voice_token}",
                f"llm: {llm_token}",
            ],
        )

        runtime_services = {}
        for component in ("voice_input", "wake_gate", "voice_output", "display", "llm"):
            payload = self._runtime_service_payload(snapshot, component)
            if not payload:
                continue
            runtime_services[component] = {
                "backend": str(payload.get("backend", "") or "").strip(),
                "state": str(payload.get("state", "") or "").strip(),
                "requested_backend": str(payload.get("requested_backend", "") or "").strip(),
                "runtime_mode": str(payload.get("runtime_mode", "") or "").strip(),
                "primary": bool(payload.get("primary", False)),
                "compatibility_mode": bool(payload.get("compatibility_mode", False)),
            }

        metadata = {
            "runtime_snapshot_available": True,
            "runtime_lifecycle_state": lifecycle_state,
            "runtime_status_message": status_message,
            "runtime_primary_ready": primary_ready,
            "runtime_premium_ready": premium_ready,
            "runtime_compatibility_components": compatibility,
            "runtime_degraded_components": degraded_components,
            "runtime_blockers": blockers,
            "runtime_services": runtime_services,
        }

        return f"{runtime_sentence} {backend_sentence}".strip(), lines, metadata
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
            "Mogę rozmawiać z Tobą, zapamiętywać informacje, ustawiać przypomnienia, uruchamiać timery, focus mode i break mode, podawać czas i datę oraz raportować stan runtime i backendów.",
            "I can talk with you, remember information, set reminders, start timers, focus mode and break mode, tell you the time and date, and report the runtime or backend status.",
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

        runtime_spoken, runtime_lines, runtime_metadata = self._build_runtime_status_summary(language)

        if language == "pl":
            feature_spoken = (
                f"Focus jest {'włączony' if focus_on else 'wyłączony'}, "
                f"przerwa jest {'włączona' if break_on else 'wyłączona'}, "
                f"aktywny timer to {current_timer}, "
                f"w pamięci mam {memory_count} wpisów, "
                f"a przypomnień jest {reminder_count}."
            )
            timer_line = f"timer: {str(current_timer)[:12]}"
        else:
            feature_spoken = (
                f"Focus is {'on' if focus_on else 'off'}, "
                f"break is {'on' if break_on else 'off'}, "
                f"the current timer is {current_timer}, "
                f"I have {memory_count} memory items, "
                f"and there are {reminder_count} reminders."
            )
            timer_line = f"timer: {str(current_timer)[:12]}"

        spoken = f"{runtime_spoken} {feature_spoken}".strip()
        lines = [*runtime_lines[:5], timer_line]

        return self._deliver_simple_action_response(
            language=language,
            action="status",
            spoken_text=spoken,
            display_title="STATUS",
            display_lines=lines,
            extra_metadata={
                "resolved_source": resolved.source,
                "timer_running": timer_running,
                "focus_mode": focus_on,
                "break_mode": break_on,
                "memory_count": memory_count,
                "reminder_count": reminder_count,
                "current_timer": str(current_timer),
                **runtime_metadata,
            },
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