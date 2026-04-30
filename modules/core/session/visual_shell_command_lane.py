from __future__ import annotations

from types import SimpleNamespace
import time
from dataclasses import dataclass, field
from typing import Any

from modules.core.session.visual_shell_responses import choose_visual_shell_response
from modules.presentation.visual_shell.controller import VisualShellController
from modules.presentation.visual_shell.controller.voice_command_router import (
    VisualShellVoiceCommandRouter,
    VisualVoiceCommandMatch,
    VisualVoiceAction,
)
from modules.presentation.visual_shell.transport import TcpVisualShellTransport
from modules.runtime.contracts import RouteKind
from modules.shared.logging.logger import get_logger

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class VisualShellCommandTrace:
    """Structured diagnostics for one Visual Shell command lane attempt."""

    heard_text: str = ""
    normalized_text: str = ""
    router_match: bool = False
    matched_rule: str = ""
    visual_action: str = ""
    transport_result: str = "not_attempted"
    llm_prevented: bool = False
    response_emitted: bool = False
    elapsed_ms: float = 0.0
    router_match_ms: float = 0.0
    controller_ms: float = 0.0
    response_ms: float = 0.0
    non_response_ms: float = 0.0
    language: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "heard_text": self.heard_text,
            "normalized_text": self.normalized_text,
            "router_match": self.router_match,
            "matched_rule": self.matched_rule,
            "visual_action": self.visual_action,
            "transport_result": self.transport_result,
            "llm_prevented": self.llm_prevented,
            "response_emitted": self.response_emitted,
            "elapsed_ms": round(float(self.elapsed_ms), 3),
            "router_match_ms": round(float(self.router_match_ms), 3),
            "controller_ms": round(float(self.controller_ms), 3),
            "response_ms": round(float(self.response_ms), 3),
            "non_response_ms": round(float(self.non_response_ms), 3),
            "language": self.language,
            "reason": self.reason,
        }

    def log_summary(self) -> str:
        return (
            f"heard_text={self.heard_text!r} | "
            f"normalized_text={self.normalized_text!r} | "
            f"router_match={self.router_match} | "
            f"matched_rule={self.matched_rule or '-'} | "
            f"visual_action={self.visual_action or '-'} | "
            f"transport_result={self.transport_result} | "
            f"llm_prevented={self.llm_prevented} | "
            f"response_emitted={self.response_emitted} | "
            f"language={self.language or '-'} | "
            f"reason={self.reason or '-'} | "
            f"elapsed_ms={self.elapsed_ms:.1f} | "
            f"router_match_ms={self.router_match_ms:.1f} | "
            f"controller_ms={self.controller_ms:.1f} | "
            f"response_ms={self.response_ms:.1f} | "
            f"non_response_ms={self.non_response_ms:.1f}"
        )


@dataclass(slots=True)
class VisualShellCommandLane:
    """Low-latency runtime lane for deterministic Visual Shell voice commands.

    This lane keeps Visual Shell commands out of the LLM path. It only forwards
    recognized visual commands to the Visual Shell controller. The renderer stays
    optional: if Godot is not available, the command is still treated as handled
    so it does not fall through into generative dialogue.
    """

    enabled: bool = True
    voice_commands_enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8765
    timeout_sec: float = 0.10
    speak_acknowledgements_enabled: bool = True
    controller: VisualShellController | None = None
    router: VisualShellVoiceCommandRouter = field(default_factory=VisualShellVoiceCommandRouter)

    @classmethod
    def from_settings(cls, settings: dict[str, Any] | None) -> "VisualShellCommandLane":
        visual_settings = dict(settings or {})
        transport_settings = dict(visual_settings.get("transport", {}) or {})

        return cls(
            enabled=bool(visual_settings.get("enabled", True)),
            voice_commands_enabled=bool(
                visual_settings.get("voice_commands_enabled", True)
            ),
            host=str(transport_settings.get("host", "127.0.0.1") or "127.0.0.1"),
            port=int(transport_settings.get("port", 8765) or 8765),
            timeout_sec=float(transport_settings.get("timeout_sec", 0.10) or 0.10),
            speak_acknowledgements_enabled=bool(
                visual_settings.get("speak_acknowledgements_enabled", True)
            ),
        )

    def try_handle(self, *, prepared: dict[str, Any], assistant: Any) -> bool | None:
        started_at = time.perf_counter()
        trace = VisualShellCommandTrace()

        if not self.enabled:
            trace.reason = "lane_disabled"
            self._finish_trace(assistant=assistant, trace=trace, started_at=started_at)
            return None

        if not self.voice_commands_enabled:
            trace.reason = "voice_commands_disabled"
            self._finish_trace(assistant=assistant, trace=trace, started_at=started_at)
            return None

        text = self._routing_text(prepared)
        trace.heard_text = text

        if not text:
            trace.reason = "empty_text"
            self._finish_trace(assistant=assistant, trace=trace, started_at=started_at)
            return None

        trace.normalized_text = self.router.normalize(text)

        router_started_at = time.perf_counter()
        match = self.router.match(text)
        trace.router_match_ms = (time.perf_counter() - router_started_at) * 1000.0

        if match is None:
            trace.reason = "no_visual_match"
            self._finish_trace(
                assistant=assistant,
                trace=trace,
                started_at=started_at,
                matched=False,
            )
            return None

        language = self._language(prepared, assistant, text=text, match=match)

        trace.router_match = True
        trace.matched_rule = match.matched_rule
        trace.visual_action = match.action.value
        trace.language = language
        trace.normalized_text = match.normalized_text
        trace.llm_prevented = True

        self._clear_pending_context(assistant)
        self._mark_routing(assistant, match)
        self._commit_language(assistant, language)
        self._store_route_snapshot(assistant, match)

        handled = False
        controller_started_at = time.perf_counter()
        try:
            handled = bool(
                self._controller().handle_voice_action(
                    match.action,
                    source="nexa-voice-builtins",
                )
            )
        except Exception as error:
            trace.transport_result = "failed"
            trace.reason = f"transport_exception:{type(error).__name__}"
            LOGGER.warning(
                "Visual Shell command transport failed safely: action=%s rule=%s error=%s",
                match.action.value,
                match.matched_rule,
                error,
            )
        finally:
            trace.controller_ms = (time.perf_counter() - controller_started_at) * 1000.0

        if handled:
            trace.transport_result = "ok"
            trace.reason = "handled"
            response_started_at = time.perf_counter()
            trace.response_emitted = self._deliver_success_response(
                assistant=assistant,
                language=language,
                match=match,
            )
            trace.response_ms = (time.perf_counter() - response_started_at) * 1000.0
            self._finish_trace(
                assistant=assistant,
                trace=trace,
                started_at=started_at,
                matched=True,
            )
            return True

        if trace.transport_result == "not_attempted":
            trace.transport_result = "failed"
            trace.reason = "renderer_unavailable"

        LOGGER.warning(
            "Visual Shell command matched but renderer command failed: action=%s rule=%s",
            match.action.value,
            match.matched_rule,
        )
        response_started_at = time.perf_counter()
        trace.response_emitted = self._deliver_unavailable_response(
            assistant=assistant,
            language=language,
            match=match,
        )
        trace.response_ms = (time.perf_counter() - response_started_at) * 1000.0
        self._finish_trace(
            assistant=assistant,
            trace=trace,
            started_at=started_at,
            matched=True,
        )
        return True


    def try_handle_action(
        self,
        *,
        action: str,
        language: str,
        prepared: dict[str, Any],
        assistant: Any,
        source: str = "action_flow.visual_shell",
    ) -> bool | None:
        started_at = time.perf_counter()
        trace = VisualShellCommandTrace()

        if not self.enabled:
            trace.reason = "lane_disabled"
            self._finish_trace(assistant=assistant, trace=trace, started_at=started_at)
            return None

        if not self.voice_commands_enabled:
            trace.reason = "voice_commands_disabled"
            self._finish_trace(assistant=assistant, trace=trace, started_at=started_at)
            return None

        visual_action = self._visual_action_for_resolved_action(action)
        if visual_action is None:
            trace.reason = "unsupported_visual_action"
            self._finish_trace(
                assistant=assistant,
                trace=trace,
                started_at=started_at,
                matched=False,
            )
            return None

        text = self._routing_text(prepared) or action
        normalized_text = self.router.normalize(text)

        trace.heard_text = text
        trace.normalized_text = normalized_text
        trace.router_match = True
        trace.matched_rule = action
        trace.visual_action = visual_action.value
        trace.language = language
        trace.llm_prevented = True

        match = SimpleNamespace(
            action=visual_action,
            matched_rule=action,
            normalized_text=normalized_text,
        )

        self._clear_pending_context(assistant)
        self._mark_routing(assistant, match)
        self._commit_language(assistant, language)
        self._store_route_snapshot(assistant, match)

        handled = False
        controller_started_at = time.perf_counter()
        try:
            handled = bool(
                self._controller().handle_voice_action(
                    visual_action,
                    source=source,
                )
            )
        except Exception as error:
            trace.transport_result = "failed"
            trace.reason = f"transport_exception:{type(error).__name__}"
            LOGGER.warning(
                "Visual Shell direct action transport failed safely: action=%s visual_action=%s error=%s",
                action,
                visual_action.value,
                error,
            )
        finally:
            trace.controller_ms = (time.perf_counter() - controller_started_at) * 1000.0

        if handled:
            trace.transport_result = "ok"
            trace.reason = "handled"
            response_started_at = time.perf_counter()
            trace.response_emitted = self._deliver_success_response(
                assistant=assistant,
                language=language,
                match=match,
            )
            trace.response_ms = (time.perf_counter() - response_started_at) * 1000.0
            self._finish_trace(
                assistant=assistant,
                trace=trace,
                started_at=started_at,
                matched=True,
            )
            return True

        if trace.transport_result == "not_attempted":
            trace.transport_result = "failed"
            trace.reason = "renderer_unavailable"

        LOGGER.warning(
            "Visual Shell direct action matched but renderer command failed: action=%s visual_action=%s",
            action,
            visual_action.value,
        )
        response_started_at = time.perf_counter()
        trace.response_emitted = self._deliver_unavailable_response(
            assistant=assistant,
            language=language,
            match=match,
        )
        trace.response_ms = (time.perf_counter() - response_started_at) * 1000.0
        self._finish_trace(
            assistant=assistant,
            trace=trace,
            started_at=started_at,
            matched=True,
        )
        return True

    @staticmethod
    def _visual_action_for_resolved_action(action: str) -> VisualVoiceAction | None:
        normalized = str(action or "").strip().lower()
        mapping = {
            "show_desktop": VisualVoiceAction.SHOW_DESKTOP,
            "show_shell": VisualVoiceAction.HIDE_DESKTOP,
            "show_self": VisualVoiceAction.SHOW_SELF,
            "show_eyes": VisualVoiceAction.SHOW_EYES,
            "show_face_contour": VisualVoiceAction.SHOW_FACE_CONTOUR,
            "look_at_user": VisualVoiceAction.LOOK_AT_USER,
            "start_scanning": VisualVoiceAction.START_SCANNING,
            "return_to_idle": VisualVoiceAction.RETURN_TO_IDLE,
            "show_temperature": VisualVoiceAction.SHOW_TEMPERATURE,
            "show_battery": VisualVoiceAction.SHOW_BATTERY,
            "show_visual_time": VisualVoiceAction.SHOW_TIME,
        }

        show_date = getattr(VisualVoiceAction, "SHOW_DATE", None)
        if show_date is not None:
            mapping["show_visual_date"] = show_date

        return mapping.get(normalized)

    def _controller(self) -> VisualShellController:
        if self.controller is not None:
            return self.controller

        self.controller = VisualShellController(
            transport=TcpVisualShellTransport(
                host=self.host,
                port=self.port,
                timeout_sec=self.timeout_sec,
            )
        )
        return self.controller

    @staticmethod
    def _routing_text(prepared: dict[str, Any]) -> str:
        return str(
            prepared.get("routing_text")
            or prepared.get("raw_text")
            or prepared.get("normalized_text")
            or ""
        ).strip()

    @classmethod
    def _language(
        cls,
        prepared: dict[str, Any],
        assistant: Any,
        *,
        text: str,
        match: VisualVoiceCommandMatch,
    ) -> str:
        inferred = cls._language_from_visual_command(text=text, match=match)
        if inferred:
            return inferred

        raw_language = str(
            prepared.get("language")
            or prepared.get("command_language")
            or getattr(assistant, "last_language", "en")
            or "en"
        ).strip()

        normalize = getattr(assistant, "_normalize_lang", None)
        if callable(normalize):
            try:
                return str(normalize(raw_language) or "en")
            except Exception:
                return raw_language or "en"

        return raw_language or "en"

    @staticmethod
    def _language_from_visual_command(
        *,
        text: str,
        match: VisualVoiceCommandMatch,
    ) -> str:
        normalized = VisualShellVoiceCommandRouter.normalize(text)

        polish_tokens = (
            "pulpit",
            "pokaz",
            "schowaj",
            "ukryj",
            "zamknij",
            "odslon",
            "wroc",
            "spojrz",
            "patrz",
            "temperatura",
            "bateria",
            "oczy",
            "twarz",
        )
        english_tokens = (
            "desktop",
            "show",
            "hide",
            "close",
            "open",
            "switch",
            "return",
            "back",
            "look",
            "watch",
            "temperature",
            "battery",
            "eyes",
            "face",
        )

        if any(token in normalized for token in polish_tokens):
            return "pl"

        if any(token in normalized for token in english_tokens):
            return "en"

        if match.normalized_text in {"show desktop", "hide desktop", "desktop", "hide"}:
            return "en"

        return ""

    @staticmethod
    def _commit_language(assistant: Any, language: str) -> None:
        commit = getattr(assistant, "_commit_language", None)
        if not callable(commit):
            return

        try:
            commit(language)
        except Exception as error:
            LOGGER.debug("Visual Shell lane language commit failed: %s", error)

    @staticmethod
    def _clear_pending_context(assistant: Any) -> None:
        clear_context = getattr(assistant, "_clear_interaction_context", None)
        if callable(clear_context):
            try:
                clear_context(close_active_window=False)
                return
            except TypeError:
                try:
                    clear_context()
                    return
                except Exception:
                    pass
            except Exception as error:
                LOGGER.debug("Visual Shell lane context clear failed: %s", error)

        if hasattr(assistant, "pending_confirmation"):
            assistant.pending_confirmation = None
        if hasattr(assistant, "pending_follow_up"):
            assistant.pending_follow_up = None

    @staticmethod
    def _mark_routing(assistant: Any, match: VisualVoiceCommandMatch) -> None:
        voice_session = getattr(assistant, "voice_session", None)
        if voice_session is None:
            return

        detail = f"visual_shell_lane:{match.matched_rule}"

        set_state = getattr(voice_session, "set_state", None)
        if callable(set_state):
            try:
                set_state("routing", detail=detail)
                return
            except TypeError:
                try:
                    set_state("routing")
                    return
                except Exception:
                    pass
            except Exception:
                pass

        transition = getattr(voice_session, "transition_to_routing", None)
        if callable(transition):
            try:
                transition(detail=detail)
            except Exception:
                pass

    @staticmethod
    def _store_route_snapshot(assistant: Any, match: VisualVoiceCommandMatch) -> None:
        assistant._last_fast_lane_route_snapshot = {
            "route_kind": RouteKind.ACTION.value,
            "route_confidence": 0.98,
            "primary_intent": f"visual_shell.{match.action.value.lower()}",
            "topics": ["visual_shell"],
            "route_notes": ["deterministic_visual_shell_command"],
            "route_metadata": {
                "lane": "visual_shell_command",
                "action": match.action.value,
                "matched_rule": match.matched_rule,
                "normalized_text": match.normalized_text,
                "source": "visual_shell_voice_router",
                "llm_prevented": True,
            },
        }

    def _deliver_success_response(
        self,
        *,
        assistant: Any,
        language: str,
        match: VisualVoiceCommandMatch,
    ) -> bool:
        if not self.speak_acknowledgements_enabled:
            return False

        deliver = getattr(assistant, "deliver_text_response", None)
        if not callable(deliver):
            return False

        text = choose_visual_shell_response(match.action, language=language)
        metadata = {
            "action": match.action.value,
            "matched_rule": match.matched_rule,
            "normalized_text": match.normalized_text,
            "response_kind": "visual_shell_acknowledgement",
            "llm_prevented": True,
        }

        try:
            return bool(
                deliver(
                    text,
                    language=language,
                    route_kind=RouteKind.ACTION,
                    source="visual_shell_command_lane",
                    metadata=metadata,
                )
            )
        except TypeError:
            pass
        except Exception as error:
            LOGGER.debug("Visual Shell acknowledgement delivery failed: %s", error)
            return False

        try:
            return bool(deliver(text, language=language))
        except TypeError:
            pass
        except Exception as error:
            LOGGER.debug("Visual Shell acknowledgement delivery fallback failed: %s", error)
            return False

        try:
            return bool(deliver(text))
        except Exception as error:
            LOGGER.debug("Visual Shell acknowledgement final fallback failed: %s", error)
            return False

    @staticmethod
    def _deliver_unavailable_response(
        *,
        assistant: Any,
        language: str,
        match: VisualVoiceCommandMatch,
    ) -> bool:
        deliver = getattr(assistant, "deliver_text_response", None)
        if not callable(deliver):
            return False

        text = (
            "Nie mogę teraz sterować ekranem NEXA, bo Visual Shell nie odpowiada."
            if str(language).lower().startswith("pl")
            else "I cannot control the NEXA screen right now because Visual Shell is not responding."
        )

        metadata = {
            "action": match.action.value,
            "matched_rule": match.matched_rule,
            "normalized_text": match.normalized_text,
            "response_kind": "visual_shell_unavailable",
            "llm_prevented": True,
        }

        try:
            return bool(
                deliver(
                    text,
                    language=language,
                    route_kind=RouteKind.ACTION,
                    source="visual_shell_command_lane",
                    metadata=metadata,
                )
            )
        except TypeError:
            pass
        except Exception as error:
            LOGGER.debug("Visual Shell unavailable response delivery failed: %s", error)
            return False

        try:
            return bool(deliver(text, language=language))
        except TypeError:
            pass
        except Exception:
            return False

        try:
            return bool(deliver(text))
        except Exception:
            return False

    @staticmethod
    def _finish_trace(
        *,
        assistant: Any,
        trace: VisualShellCommandTrace,
        started_at: float,
        matched: bool = False,
    ) -> None:
        trace.elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        trace.non_response_ms = max(0.0, trace.elapsed_ms - trace.response_ms)
        trace_dict = trace.to_dict()

        try:
            assistant._last_visual_shell_command_trace = trace_dict
        except Exception:
            pass

        if matched:
            LOGGER.info("VisualShellCommandTrace | %s", trace.log_summary())
        else:
            LOGGER.debug("VisualShellCommandTrace | %s", trace.log_summary())


__all__ = ["VisualShellCommandLane", "VisualShellCommandTrace"]