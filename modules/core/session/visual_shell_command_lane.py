from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import dataclass, field
from typing import Any

from modules.presentation.visual_shell.controller import VisualShellController
from modules.presentation.visual_shell.controller.voice_command_router import (
    VisualShellVoiceCommandRouter,
    VisualVoiceCommandMatch,
)
from modules.presentation.visual_shell.transport import TcpVisualShellTransport
from modules.core.session.visual_shell_responses import choose_visual_shell_response
from modules.runtime.contracts import RouteKind
from modules.shared.logging.logger import get_logger

LOGGER = get_logger(__name__)


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
        if not self.enabled or not self.voice_commands_enabled:
            return None

        text = self._routing_text(prepared)
        if not text:
            return None

        match = self.router.match(text)
        if match is None:
            return None

        language = self._language(prepared, assistant)
        self._clear_pending_context(assistant)
        self._mark_routing(assistant, match)
        self._commit_language(assistant, language)
        self._store_route_snapshot(assistant, match)

        handled = self._controller().handle_voice_action(
            match.action,
            source="nexa-voice-builtins",
        )

        if handled:
            self._deliver_success_response(
                assistant=assistant,
                language=language,
                match=match,
            )
            return True

        LOGGER.warning(
            "Visual Shell command matched but renderer command failed: action=%s rule=%s",
            match.action.value,
            match.matched_rule,
        )
        self._deliver_unavailable_response(
            assistant=assistant,
            language=language,
            match=match,
        )
        return True

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

    @staticmethod
    def _language(prepared: dict[str, Any], assistant: Any) -> str:
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
            },
        }

    def _deliver_success_response(
        self,
        *,
        assistant: Any,
        language: str,
        match: VisualVoiceCommandMatch,
    ) -> None:
        if not self.speak_acknowledgements_enabled:
            return

        deliver = getattr(assistant, "deliver_text_response", None)
        if not callable(deliver):
            return

        text = choose_visual_shell_response(match.action, language=language)

        try:
            deliver(text, language=language)
            return
        except TypeError:
            pass
        except Exception as error:
            LOGGER.debug("Visual Shell acknowledgement delivery failed: %s", error)
            return

        try:
            deliver(text)
        except Exception as error:
            LOGGER.debug("Visual Shell acknowledgement fallback failed: %s", error)


    @staticmethod
    def _deliver_unavailable_response(
        *,
        assistant: Any,
        language: str,
        match: VisualVoiceCommandMatch,
    ) -> None:
        deliver = getattr(assistant, "deliver_text_response", None)
        if not callable(deliver):
            return

        text = (
            "Nie mogę teraz sterować ekranem NEXA, bo Visual Shell nie odpowiada."
            if str(language).lower().startswith("pl")
            else "I cannot control the NEXA screen right now because Visual Shell is not responding."
        )

        try:
            deliver(
                text,
                language=language,
                route_kind=RouteKind.ACTION,
                source="visual_shell_command_lane",
                metadata={
                    "action": match.action.value,
                    "matched_rule": match.matched_rule,
                    "response_kind": "visual_shell_unavailable",
                },
            )
        except TypeError:
            try:
                deliver(text, language=language)
            except Exception:
                pass
        except Exception as error:
            LOGGER.debug("Visual Shell unavailable response delivery failed: %s", error)


__all__ = ["VisualShellCommandLane"]