from __future__ import annotations

import re

from dataclasses import dataclass, field
from typing import Any

from modules.core.session.visual_shell_command_lane import VisualShellCommandLane

from modules.runtime.contracts import (
    EntityValue,
    IntentMatch,
    RouteDecision,
    RouteKind,
    ToolInvocation,
    create_turn_id,
)
from modules.shared.logging.logger import get_logger
from modules.core.session.fast_calculator import (
    looks_like_arithmetic,
    try_handle_arithmetic,
)
from modules.understanding.parsing.normalization import (
    is_exit_request,
    is_micro_reply,
    is_no,
    is_yes,
    normalize_text,
)

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class FastCommandDecision:
    action: str
    language: str
    source: str
    confidence: float
    payload: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    normalized_text: str = ""
    interrupts_pending: bool = False


class FastCommandLane:
    """
    Deterministic low-latency command lane.

    Purpose:
    - bypass the heavier semantic router for obvious commands
    - keep short command interactions feeling instant
    - allow a new clear command to override stale follow-up state
    - hand off execution to ActionFlow in a stable route format
    """

    TEMPORAL_ACTIONS = {
        "ask_time",
        "show_time",
        "ask_date",
        "show_date",
        "ask_day",
        "show_day",
        "ask_month",
        "show_month",
        "ask_year",
        "show_year",
    }

    DIRECT_ACTIONS = {
        "timer_start",
        "timer_stop",
        "focus_start",
        "break_start",
        "introduce_self",
        "memory_store",
        "memory_recall",
        "memory_forget",
        "memory_list",
        "memory_clear",
        "reminder_create",
        "reminders_list",
        "reminder_delete",
        "reminders_clear",
        "feedback_on",
        "feedback_off",
        "help",
        "status",
        "calculate",
        "exit",
        "shutdown",
        "confirm_yes",
        "confirm_no",
        "look_direction",
        
    }

    ALL_ACTIONS = TEMPORAL_ACTIONS | DIRECT_ACTIONS

    DIAGNOSTIC_CLOSE_ALIASES = {
        # English close aliases
        "feedback mode off",
        "close feedback",
        "hide feedback",
        "close feedback center",
        "hide feedback center",
        "close diagnostics",
        "hide diagnostics",
        "close diagnostic center",
        "hide diagnostic center",
        "close diagnostics center",
        "hide diagnostics center",
        "close system status",
        "hide system status",
        "close status panel",
        "hide status panel",
        "close health panel",
        "hide health panel",
        "close logs",
        "hide logs",
        "close dashboard",
        "hide dashboard",
        "close the window",
        "hide the window",
        "close this window",
        "hide this window",
        "close panel",
        "hide panel",
        "exit diagnostics",
        "leave diagnostics",
        # Polish close aliases (normalized — no diacritics)
        "wylacz feedback",
        "zamknij feedback",
        "ukryj feedback",
        "zamknij centrum feedback",
        "ukryj centrum feedback",
        "zamknij diagnostyke",
        "ukryj diagnostyke",
        "zamknij centrum diagnostyczne",
        "ukryj centrum diagnostyczne",
        "zamknij panel diagnostyczny",
        "ukryj panel diagnostyczny",
        "zamknij status systemu",
        "ukryj status systemu",
        "zamknij panel statusu",
        "ukryj panel statusu",
        "zamknij logi",
        "ukryj logi",
        "zamknij dashboard",
        "ukryj dashboard",
        "zamknij okno",
        "ukryj okno",
        "zamknij to okno",
        "ukryj to okno",
        "zamknij panel",
        "ukryj panel",
        "wyjdz z diagnostyki",
        # Polish stt_recovery close variants
        "zamknij diagnostyka",
        # English shortened close variants
        "close window",
        "close diagnostic",
        "hide diagnostic",
        # ASR mishear: "close" → "Klaus"/"Claus"
        "klaus system status",
        "claus system status",
        # "close systems" mishear (drops "status")
        "close systems",
        # Polish: "zamknij" mishear → "zamiń"/"zamień"
        "zamien okno",
        "zamień okno",
    }

    DIAGNOSTIC_FEEDBACK_ALIASES = {
        "open feedback center",
        "show feedback center",
        "open diagnostics",
        "show diagnostics",
        "diagnostic center",
        "open diagnostic center",
        "show diagnostic center",
        "system status",
        "show system status",
        "shows system status",
        "health check",
        "show health",
        "open health panel",
        "show runtime health",
        "show logs",
        "show benchmarks",
        "show audio diagnostics",
        "show llm status",
        "show memory status",
        "show camera status",
        "show power status",
        "otworz feedback",
        "otworz centrum feedback",
        "pokaz feedback",
        "otworz diagnostyke",
        "pokaz diagnostyke",
        "pokaz diagnostyka",
        "pokaz diagnostike",
        "polkaz diagnostike",
        "polkaz diagnostyke",
        "centrum diagnostyczne",
        "otworz centrum diagnostyczne",
        "pokaz centrum diagnostyczne",
        "status systemu",
        "pokaz status systemu",
        "sprawdz zdrowie systemu",
        "pokaz zdrowie systemu",
        "otworz panel diagnostyczny",
        "pokaz runtime",
        "pokaz logi",
        "pokaz benchmarki",
        "pokaz diagnostyke audio",
        "pokaz status llm",
        "pokaz pamiec",
        "pokaz status kamery",
        "pokaz baterie",
        "pokaz zasilanie",
        # Polish ASR mishear variants — djagnostyk*, okaz*, pokasz patterns
        "pokaz djagnostyka",
        "pokaz djagnostyke",
        "pokaz djagnostike",
        "okaze diagnostyka",
        "okaz diagnostyka",
        "o kasz diagnostyke",
        "o kasz diagnostike",
        "pokasz logi",
        # English singular variants
        "open diagnostic",
        "show diagnostic",
        # ASR mishear EN
        "or almost diagnostica",
        "all cash diagnostics",
    }

    def __init__(
        self,
        *,
        enabled: bool = True,
        visual_shell_lane: VisualShellCommandLane | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.visual_shell_lane = visual_shell_lane

    def try_handle(self, *, prepared: dict[str, Any], assistant: Any) -> bool | None:
        if not self.enabled:
            return None

        visual_shell_result = self._try_handle_visual_shell(
            prepared=prepared,
            assistant=assistant,
        )
        if visual_shell_result is not None:
            return visual_shell_result

        raw_text = str(
            prepared.get("raw_text") or prepared.get("routing_text") or ""
        ).strip()
        if raw_text and looks_like_arithmetic(raw_text):
            language = assistant._normalize_lang(prepared.get("language") or "en")
            if self._handle_arithmetic(
                assistant=assistant,
                raw_text=raw_text,
                language=language,
            ):
                return True

        decision = self.classify(prepared=prepared, assistant=assistant)
        if decision is None:
            return None
        return self.execute(assistant=assistant, decision=decision)


    def _try_handle_visual_shell(
        self,
        *,
        prepared: dict[str, Any],
        assistant: Any,
    ) -> bool | None:
        if self.visual_shell_lane is None:
            return None

        try:
            return self.visual_shell_lane.try_handle(
                prepared=prepared,
                assistant=assistant,
            )
        except Exception as error:
            LOGGER.warning("Visual Shell command lane failed safely: %s", error)
            return None


    def _handle_arithmetic(
        self,
        *,
        assistant: Any,
        raw_text: str,
        language: str,
    ) -> bool:
        clear_context = getattr(assistant, "_clear_interaction_context", None)
        if callable(clear_context):
            try:
                clear_context(close_active_window=False)
            except TypeError:
                try:
                    clear_context()
                except Exception:
                    pass
            except Exception:
                pass
        else:
            assistant.pending_confirmation = None
            assistant.pending_follow_up = None

        assistant.voice_session.set_state("routing", detail="fast_lane:calculate")
        assistant._commit_language(language)

        LOGGER.info(
            "Fast command lane arithmetic: text=%s, language=%s",
            raw_text,
            language,
        )

        assistant._last_fast_lane_route_snapshot = {
            "route_kind": "action",
            "route_confidence": 0.95,
            "primary_intent": "calculate",
            "topics": [],
            "route_notes": ["deterministic_fast_calculator"],
            "route_metadata": {
                "lane": "fast_command",
                "action": "calculate",
                "source": "fast_calculator",
            },
        }

        return bool(
            try_handle_arithmetic(
                assistant=assistant,
                raw_text=raw_text,
                language=language,
            )
        )

    def classify(self, *, prepared: dict[str, Any], assistant: Any) -> FastCommandDecision | None:
        if not self.enabled:
            return None

        raw_text = str(prepared.get("routing_text") or prepared.get("raw_text") or "").strip()
        prepared_normalized = str(prepared.get("normalized_text") or "").strip()
        normalized_text = normalize_text(prepared_normalized or raw_text)
        if not normalized_text:
            return None

        language = assistant._normalize_lang(prepared.get("language") or "en")
        if self._looks_like_polish_feedback_command(normalized_text):
            language = "pl"
        interrupts_pending = bool(assistant.pending_confirmation or assistant.pending_follow_up)

        if self._is_diagnostic_close_alias(normalized_text):
            if self._looks_polish_close_alias(normalized_text):
                language = "pl"
            return FastCommandDecision(
                action="feedback_off",
                language=language,
                source="fast_command_lane:diagnostics_close_alias",
                confidence=0.98,
                raw_text=raw_text,
                normalized_text=normalized_text,
                interrupts_pending=interrupts_pending,
            )

        if self._is_diagnostic_feedback_alias(normalized_text):
            if self._looks_polish_diagnostic_alias(normalized_text):
                language = "pl"
            return FastCommandDecision(
                action="feedback_on",
                language=language,
                source="fast_command_lane:diagnostics_alias",
                confidence=0.98,
                raw_text=raw_text,
                normalized_text=normalized_text,
                interrupts_pending=interrupts_pending,
            )

        parser_result = prepared.get("parser_result")
        if parser_result is None:
            parser_result = self._parse_fast(assistant=assistant, text=raw_text)
            if parser_result is not None:
                prepared["parser_result"] = parser_result

        action = self._extract_action(parser_result)
        payload = self._extract_payload(parser_result)
        confidence = self._extract_confidence(parser_result)

        if action in {"", "unknown", "unclear"}:
            heuristic = self._heuristic_decision(
                raw_text=raw_text,
                normalized_text=normalized_text,
                language=language,
                interrupts_pending=interrupts_pending,
            )
            if heuristic is None:
                return None
            return heuristic

        if action in {"confirm_yes", "confirm_no"} and not interrupts_pending:
            return None

        if action not in self.ALL_ACTIONS:
            return None

        if confidence <= 0.0:
            confidence = 0.96 if is_micro_reply(raw_text) else 0.90

        return FastCommandDecision(
            action=action,
            language=language,
            source="fast_command_lane",
            confidence=confidence,
            payload=payload,
            raw_text=raw_text,
            normalized_text=normalized_text,
            interrupts_pending=interrupts_pending,
        )

    def execute(self, *, assistant: Any, decision: FastCommandDecision) -> bool:
        self._interrupt_pending_context(assistant=assistant, action=decision.action)

        assistant.voice_session.set_state("routing", detail=f"fast_lane:{decision.action}")
        assistant._commit_language(decision.language)

        LOGGER.info(
            "Fast command lane executing: action=%s, language=%s, interrupts_pending=%s, source=%s",
            decision.action,
            decision.language,
            decision.interrupts_pending,
            decision.source,
        )

        route = self._build_route_decision(decision)
        self._store_last_route_snapshot(assistant=assistant, route=route)
        return bool(assistant.action_flow.execute(route=route, language=decision.language))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _parse_fast(self, *, assistant: Any, text: str) -> Any | None:
        parser = getattr(assistant, "parser", None)
        if parser is None:
            return None

        for method_name in ("parse", "parse_intent", "match", "classify"):
            method = getattr(parser, method_name, None)
            if not callable(method):
                continue
            try:
                return method(text)
            except TypeError:
                try:
                    return method(text=text)
                except TypeError:
                    continue
            except Exception as error:
                LOGGER.warning("Fast command parser call failed on %s: %s", method_name, error)
                return None

        return None

    def _heuristic_decision(
        self,
        *,
        raw_text: str,
        normalized_text: str,
        language: str,
        interrupts_pending: bool,
    ) -> FastCommandDecision | None:
        action = ""
        confidence = 0.0
        source = "fast_command_lane_heuristic"

        if interrupts_pending:
            if is_yes(normalized_text):
                action = "confirm_yes"
                confidence = 0.99
            elif is_no(normalized_text):
                action = "confirm_no"
                confidence = 0.99

        if not action and is_exit_request(normalized_text):
            action = "exit"
            confidence = 0.98 if is_micro_reply(normalized_text) else 0.94

        if not action:
            action = self._match_simple_action(normalized_text)
            if action:
                confidence = 0.94 if is_micro_reply(normalized_text) else 0.90

        

        if not action:
            return None

        if action not in self.ALL_ACTIONS:
            return None

        return FastCommandDecision(
            action=action,
            language=language,
            source=source,
            confidence=confidence,
            payload={},
            raw_text=raw_text,
            normalized_text=normalized_text,
            interrupts_pending=interrupts_pending,
        )

    @staticmethod
    def _store_last_route_snapshot(*, assistant: Any, route: RouteDecision) -> None:
        assistant._last_fast_lane_route_snapshot = {
            "route_kind": getattr(route.kind, "value", str(route.kind)),
            "route_confidence": float(getattr(route, "confidence", 0.0) or 0.0),
            "primary_intent": str(getattr(route, "primary_intent", "") or ""),
            "topics": list(getattr(route, "conversation_topics", []) or []),
            "route_notes": list(getattr(route, "notes", []) or []),
            "route_metadata": dict(getattr(route, "metadata", {}) or {}),
        }

    @staticmethod
    def _looks_like_polish_feedback_command(normalized_text: str) -> bool:
        normalized = normalize_text(normalized_text)
        tokens = set(normalized.split())

        polish_start_tokens = {
            "uruchom",
            "urucham",
            "uruchamiam",
            "oruham",
            "orucham",
            "wlacz",
            "włącz",
            "tryb",
            "zamknij",
            "wylacz",
            "wyłącz",
        }

        feedback_like_tokens = {
            "feedback",
            "feed",
            "back",
            "fitbit",
        }

        if tokens & polish_start_tokens and tokens & feedback_like_tokens:
            return True

        if normalized in {
            "oruham feedback",
            "oruham feed back",
            "oruham fitbit",
            "orucham feedback",
            "orucham fitbit",
        }:
            return True

        return False

    @classmethod
    def _is_diagnostic_close_alias(cls, normalized_text: str) -> bool:
        normalized = str(normalized_text or "").strip()
        return normalized in cls.DIAGNOSTIC_CLOSE_ALIASES

    @staticmethod
    def _looks_polish_close_alias(normalized_text: str) -> bool:
        tokens = set(str(normalized_text or "").split())
        return bool(tokens & {
            "zamknij", "ukryj", "wylacz", "wyjdz",
            "diagnostyke", "diagnostyczne", "diagnostyczny",
            "okno", "logi", "panel", "dashboard",
        })

    @classmethod
    def _is_diagnostic_feedback_alias(cls, normalized_text: str) -> bool:
        normalized = str(normalized_text or "").strip()
        return normalized in cls.DIAGNOSTIC_FEEDBACK_ALIASES

    @staticmethod
    def _looks_polish_diagnostic_alias(normalized_text: str) -> bool:
        tokens = set(str(normalized_text or "").split())
        return bool(tokens & {
            "pokaz", "polkaz", "otworz",
            "diagnostyke", "diagnostyka", "diagnostike",
            "diagnostyczne", "systemu", "zdrowie",
            "logi", "baterie", "zasilanie", "pamiec",
        })


    @staticmethod
    def _match_simple_action(normalized_text: str) -> str:
        normalized = str(normalized_text or "").strip()
        if not normalized:
            return ""

        direct_map = {
            "feedback on": "feedback_on", "feedback start": "feedback_on",
            "open feedback center": "feedback_on", "show feedback center": "feedback_on",
            "open diagnostics": "feedback_on", "show diagnostics": "feedback_on",
            "diagnostic center": "feedback_on", "open diagnostic center": "feedback_on",
            "show diagnostic center": "feedback_on", "system status": "feedback_on",
            "show system status": "feedback_on", "shows system status": "feedback_on",
            "health check": "feedback_on",
            "show health": "feedback_on", "open health panel": "feedback_on",
            "show runtime health": "feedback_on", "show logs": "feedback_on",
            "show benchmarks": "feedback_on", "show audio diagnostics": "feedback_on",
            "show llm status": "feedback_on", "show memory status": "feedback_on",
            "show camera status": "feedback_on", "show power status": "feedback_on",
            "feedback uruchom": "feedback_on", "feedback wlacz": "feedback_on",
            "feedback włącz": "feedback_on", "uruchom feedback": "feedback_on",
            "urucham feedback": "feedback_on", "uruchamiam feedback": "feedback_on",
            "wlacz feedback": "feedback_on", "włącz feedback": "feedback_on",
            "otworz feedback": "feedback_on", "otworz centrum feedback": "feedback_on",
            "pokaz feedback": "feedback_on", "otworz diagnostyke": "feedback_on",
            "pokaz diagnostyke": "feedback_on",
            "pokaz diagnostyka": "feedback_on", "pokaz diagnostike": "feedback_on",
            "polkaz diagnostike": "feedback_on", "polkaz diagnostyke": "feedback_on",
            "pokaz djagnostyka": "feedback_on", "pokaz djagnostyke": "feedback_on",
            "pokaz djagnostike": "feedback_on",
            "okaze diagnostyka": "feedback_on", "okaz diagnostyka": "feedback_on",
            "o kasz diagnostyke": "feedback_on", "o kasz diagnostike": "feedback_on",
            "pokasz logi": "feedback_on",
            "open diagnostic": "feedback_on", "show diagnostic": "feedback_on",
            "or almost diagnostica": "feedback_on", "all cash diagnostics": "feedback_on",
            "centrum diagnostyczne": "feedback_on",
            "otworz centrum diagnostyczne": "feedback_on",
            "pokaz centrum diagnostyczne": "feedback_on",
            "status systemu": "feedback_on", "pokaz status systemu": "feedback_on",
            "sprawdz zdrowie systemu": "feedback_on", "pokaz zdrowie systemu": "feedback_on",
            "otworz panel diagnostyczny": "feedback_on", "pokaz runtime": "feedback_on",
            "pokaz logi": "feedback_on", "pokaz benchmarki": "feedback_on",
            "pokaz diagnostyke audio": "feedback_on", "pokaz status llm": "feedback_on",
            "pokaz pamiec": "feedback_on", "pokaz status kamery": "feedback_on",
            "pokaz baterie": "feedback_on", "pokaz zasilanie": "feedback_on",
            "tryb feedback": "feedback_on", "feedback mode on": "feedback_on",
            "feedback mode": "feedback_on",
            "feed back on": "feedback_on", "feed the back on": "feedback_on",
            "feedback own": "feedback_on", "feed back own": "feedback_on",
            "oruham feedback": "feedback_on", "oruham feed back": "feedback_on",
            "oruham fitbit": "feedback_on", "urucham feedback": "feedback_on",
            "feedback off": "feedback_off", "feedback stop": "feedback_off",
            "feedback zamknij": "feedback_off", "feedback zamknik": "feedback_off",
            "feedback wylacz": "feedback_off", "feedback wyłącz": "feedback_off",
            "zamknij feedback": "feedback_off", "wylacz feedback": "feedback_off",
            "wyłącz feedback": "feedback_off", "feedback mode off": "feedback_off",
            "feedback of": "feedback_off", "feed back off": "feedback_off",
            "feed back of": "feedback_off", "feed the back off": "feedback_off",
            "feed the back of": "feedback_off", "sheet back off": "feedback_off",
            "sheets back off": "feedback_off", "fit back off": "feedback_off",
            "fit back of": "feedback_off", "feet back off": "feedback_off",
            # diagnostics close aliases — EN
            "close feedback": "feedback_off", "hide feedback": "feedback_off",
            "close feedback center": "feedback_off", "hide feedback center": "feedback_off",
            "close diagnostics": "feedback_off", "hide diagnostics": "feedback_off",
            "close diagnostic center": "feedback_off", "hide diagnostic center": "feedback_off",
            "close diagnostics center": "feedback_off", "hide diagnostics center": "feedback_off",
            "close system status": "feedback_off", "hide system status": "feedback_off",
            "close status panel": "feedback_off", "hide status panel": "feedback_off",
            "close health panel": "feedback_off", "hide health panel": "feedback_off",
            "close logs": "feedback_off", "hide logs": "feedback_off",
            "close dashboard": "feedback_off", "hide dashboard": "feedback_off",
            "close the window": "feedback_off", "hide the window": "feedback_off",
            "close this window": "feedback_off", "hide this window": "feedback_off",
            "close panel": "feedback_off", "hide panel": "feedback_off",
            "exit diagnostics": "feedback_off", "leave diagnostics": "feedback_off",
            # diagnostics close aliases — PL
            "ukryj feedback": "feedback_off",
            "zamknij centrum feedback": "feedback_off", "ukryj centrum feedback": "feedback_off",
            "zamknij diagnostyke": "feedback_off", "ukryj diagnostyke": "feedback_off",
            "zamknij diagnostykę": "feedback_off", "ukryj diagnostykę": "feedback_off",
            "zamknij centrum diagnostyczne": "feedback_off", "ukryj centrum diagnostyczne": "feedback_off",
            "zamknij panel diagnostyczny": "feedback_off", "ukryj panel diagnostyczny": "feedback_off",
            "zamknij status systemu": "feedback_off", "ukryj status systemu": "feedback_off",
            "zamknij panel statusu": "feedback_off", "ukryj panel statusu": "feedback_off",
            "zamknij logi": "feedback_off", "ukryj logi": "feedback_off",
            "zamknij dashboard": "feedback_off", "ukryj dashboard": "feedback_off",
            "zamknij okno": "feedback_off", "ukryj okno": "feedback_off",
            "zamknij to okno": "feedback_off", "ukryj to okno": "feedback_off",
            "zamknij panel": "feedback_off", "ukryj panel": "feedback_off",
            "wyjdź z diagnostyki": "feedback_off", "wyjdz z diagnostyki": "feedback_off",
            "zamknij diagnostyka": "feedback_off",
            "close window": "feedback_off",
            "close diagnostic": "feedback_off", "hide diagnostic": "feedback_off",
            "klaus system status": "feedback_off", "claus system status": "feedback_off",
            "close systems": "feedback_off",
            "zamien okno": "feedback_off", "zamień okno": "feedback_off",
            "help": "help",
            "show help": "help",
            "so help": "help",
            "show commands": "help",
            "show command list": "help",
            "command list": "help",
            "commands list": "help",
            "help screen": "help",
            "open help": "help",
            "open commands": "help",
            "pokaż pomoc": "help",
            "pokaz pomoc": "help",
            "pokaż komendy": "help",
            "pokaz komendy": "help",
            "lista komend": "help",
            "ekran pomocy": "help",
            "otwórz pomoc": "help",
            "otworz pomoc": "help",
            "pomoc": "help",
            "jak możesz mi pomóc": "help",
            "jak mozesz mi pomoc": "help",
            "w czym możesz mi pomóc": "help",
            "w czym mozesz mi pomoc": "help",
            "co potrafisz": "help",
            "co możesz zrobić": "help",
            "co mozesz zrobic": "help",
            "how can you help me": "help",
            "how can you help": "help",
            "what can you do": "help",
            "what can you help me with": "help",
            "what are your commands": "help",
            "commands": "help",
            "status": "status",
            "stan": "status",
            "time": "ask_time",
            "what time": "ask_time",
            "what time is it": "ask_time",
            "tell me the time": "ask_time",
            "current time": "ask_time",
            "godzina": "ask_time",
            "ktora godzina": "ask_time",
            "która godzina": "ask_time",
            "ktora jest godzina": "ask_time",
            "która jest godzina": "ask_time",
            "czas": "ask_time",
            "date": "ask_date",
            "today date": "ask_date",
            "data": "ask_date",
            "jaka data": "ask_date",
            "day": "ask_day",
            "what day": "ask_day",
            "jaki dzis dzien": "ask_day",
            "jaki dziś dzień": "ask_day",
            "dzien": "ask_day",
            "dzień": "ask_day",
            "month": "ask_month",
            "jaki miesiac": "ask_month",
            "jaki miesiąc": "ask_month",
            "miesiac": "ask_month",
            "miesiąc": "ask_month",
            "year": "ask_year",
            "jaki rok": "ask_year",
            "rok": "ask_year",
            "who are you": "introduce_self",
            "what is your name": "introduce_self",
            "tell me your name": "introduce_self",
            "kim jestes": "introduce_self",
            "kim jesteś": "introduce_self",
            "kim ty jesteś": "introduce_self",
            "kim ty jestes": "introduce_self",
            "czym jesteś": "introduce_self",
            "czym jestes": "introduce_self",
            "powiedz kim jesteś": "introduce_self",
            "powiedz kim jestes": "introduce_self",
            "what are you": "introduce_self",
            "tell me who you are": "introduce_self",
            "tell me about yourself": "introduce_self",
            "introduce yourself": "introduce_self",
            "jak sie nazywasz": "introduce_self",
            "jak się nazywasz": "introduce_self",
            "przedstaw sie": "introduce_self",
            "przedstaw się": "introduce_self",
        }

        return direct_map.get(normalized, "")

    def _interrupt_pending_context(self, *, assistant: Any, action: str) -> None:
        if action in {"confirm_yes", "confirm_no"}:
            return

        clear_context = getattr(assistant, "_clear_interaction_context", None)
        if callable(clear_context):
            try:
                clear_context(close_active_window=False)
                return
            except TypeError:
                clear_context()
                return
            except Exception as error:
                LOGGER.warning("Failed to clear interaction context in fast lane: %s", error)

        assistant.pending_confirmation = None
        assistant.pending_follow_up = None

    def _build_route_decision(self, decision: FastCommandDecision) -> RouteDecision:
        tool_name = self._tool_name_for_action(decision.action)

        intents: list[IntentMatch] = [
            IntentMatch(
                name=decision.action,
                confidence=decision.confidence or 1.0,
                entities=[
                    EntityValue(name=str(key), value=value)
                    for key, value in decision.payload.items()
                ],
                requires_clarification=False,
                metadata={"lane": "fast_command"},
            )
        ]

        tools: list[ToolInvocation] = []
        if tool_name:
            tools.append(
                ToolInvocation(
                    tool_name=tool_name,
                    payload=dict(decision.payload),
                    reason="deterministic_fast_path",
                    confidence=max(decision.confidence, 0.90),
                    execute_immediately=True,
                )
            )

        return RouteDecision(
            turn_id=create_turn_id("fast"),
            raw_text=decision.raw_text,
            normalized_text=decision.normalized_text,
            language=decision.language,
            kind=RouteKind.ACTION,
            confidence=max(decision.confidence, 0.90),
            primary_intent=decision.action,
            intents=intents,
            conversation_topics=[],
            tool_invocations=tools,
            notes=["deterministic_fast_path"],
            metadata={
                "lane": "fast_command",
                "interrupts_pending": decision.interrupts_pending,
                "action": decision.action,
                "payload": dict(decision.payload),
                "source": decision.source,
                "llm_prevented": True,
            },
        )

    @staticmethod
    def _extract_action(parser_result: Any) -> str:
        if parser_result is None:
            return ""

        if isinstance(parser_result, dict):
            for key in ("action", "primary_intent", "intent", "name"):
                value = parser_result.get(key)
                if value:
                    return str(value).strip().lower()
            return ""

        for attr in ("action", "primary_intent", "intent", "name"):
            value = getattr(parser_result, attr, None)
            if value:
                return str(value).strip().lower()

        return ""

    @staticmethod
    def _extract_confidence(parser_result: Any) -> float:
        if parser_result is None:
            return 0.0

        if isinstance(parser_result, dict):
            for key in ("confidence", "score"):
                value = parser_result.get(key)
                if value is not None:
                    try:
                        return float(value)
                    except Exception:
                        return 0.0
            return 0.0

        for attr in ("confidence", "score"):
            value = getattr(parser_result, attr, None)
            if value is not None:
                try:
                    return float(value)
                except Exception:
                    return 0.0

        return 0.0

    def _extract_payload(self, parser_result: Any) -> dict[str, Any]:
        if parser_result is None:
            return {}

        if isinstance(parser_result, dict):
            if isinstance(parser_result.get("payload"), dict):
                return dict(parser_result["payload"])
            if isinstance(parser_result.get("data"), dict):
                return dict(parser_result["data"])
            if isinstance(parser_result.get("entities"), dict):
                return dict(parser_result["entities"])
            if isinstance(parser_result.get("slots"), dict):
                return dict(parser_result["slots"])
            return self._dict_payload_from_known_keys(parser_result)

        for attr in ("payload", "data", "entities", "slots"):
            value = getattr(parser_result, attr, None)
            if isinstance(value, dict):
                return dict(value)

        extracted: dict[str, Any] = {}
        for key in (
            "key",
            "value",
            "message",
            "minutes",
            "seconds",
            "hours",
            "query",
            "item",
            "subject",
            "name",
            "id",
            "reminder_id",
            "direction",
        ):
            value = getattr(parser_result, key, None)
            if value not in (None, ""):
                extracted[key] = value
        return extracted

    @staticmethod
    def _dict_payload_from_known_keys(data: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key in (
            "key",
            "value",
            "message",
            "minutes",
            "seconds",
            "hours",
            "query",
            "item",
            "subject",
            "name",
            "id",
            "reminder_id",
            "direction",
        ):
            value = data.get(key)
            if value not in (None, ""):
                payload[key] = value
        return payload

    @staticmethod
    def _tool_name_for_action(action: str) -> str:
        mapping = {
            "help": "system.help",
            "feedback_on": "feedback.on",
            "feedback_off": "feedback.off",
            "show help": "system.help",
            "so help": "system.help",
            "show commands": "system.help",
            "show command list": "system.help",
            "command list": "system.help",
            "commands list": "system.help",
            "help screen": "system.help",
            "open help": "system.help",
            "open commands": "system.help",
            "pokaż pomoc": "system.help",
            "pokaz pomoc": "system.help",
            "pokaż komendy": "system.help",
            "pokaz komendy": "system.help",
            "lista komend": "system.help",
            "ekran pomocy": "system.help",
            "otwórz pomoc": "system.help",
            "otworz pomoc": "system.help",
            "status": "system.status",
            "calculate": "system.calculate",
            "introduce_self": "assistant.introduce",
            "ask_time": "clock.time",
            "show_time": "clock.time",
            "ask_date": "clock.date",
            "show_date": "clock.date",
            "ask_day": "clock.day",
            "show_day": "clock.day",
            "ask_month": "clock.month",
            "show_month": "clock.month",
            "ask_year": "clock.year",
            "show_year": "clock.year",
            "memory_list": "memory.list",
            "memory_clear": "memory.clear",
            "memory_store": "memory.store",
            "memory_recall": "memory.recall",
            "memory_forget": "memory.forget",
            "reminders_list": "reminders.list",
            "reminders_clear": "reminders.clear",
            "reminder_create": "reminders.create",
            "reminder_delete": "reminders.delete",
            "timer_start": "timer.start",
            "timer_stop": "timer.stop",
            "focus_start": "focus.start",
            "break_start": "break.start",
            "exit": "system.exit",
            "shutdown": "system.shutdown",
            "confirm_yes": "",
            "confirm_no": "",
            "look_direction": "pan_tilt.look",
        }
        return mapping.get(str(action).strip().lower(), "")


    _ARITHMETIC_RE = re.compile(
        r"\d+(?:[.,]\d+)?\s*"
        r"(?:[+\-*/xX×·÷:]|plus|minus|razy|dodać|dodac|odjąć|odjac|"
        r"pomnożyć|pomnozyc|podzielić|podzielic|przez|times|divided|over)"
        r"\s*\d+(?:[.,]\d+)?",
        flags=re.IGNORECASE,
    )

    @classmethod
    def _looks_like_arithmetic(cls, text: str) -> bool:
        cleaned = str(text or "").strip()
        if not cleaned:
            return False
        return bool(cls._ARITHMETIC_RE.search(cleaned))

__all__ = ["FastCommandDecision", "FastCommandLane"]
