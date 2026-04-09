from __future__ import annotations

from typing import Any

from .helpers import LOGGER
from .models import PreparedCommand


class CommandFlowMemory:
    """Memory and logging helpers for command preparation."""

    assistant: Any

    def _remember_user_turn(self, prepared: PreparedCommand) -> None:
        remember_method = getattr(self.assistant, "_remember_user_turn", None)
        if not callable(remember_method):
            return

        metadata = {
            "routing_text": prepared.routing_text,
            "normalized_text": prepared.normalized_routing_text,
            "detected_language": prepared.detected_language,
            "normalizer_language_hint": prepared.normalizer_language_hint,
            "corrections": list(prepared.normalizer_corrections),
            "source": prepared.source.value,
            "wake_phrase_detected": prepared.wake_phrase_detected,
            "cancel_requested": prepared.cancel_requested,
        }

        if prepared.semantic_override_applied:
            metadata.update(
                {
                    "semantic_override_applied": True,
                    "semantic_override_mode": prepared.semantic_override_mode,
                    "semantic_override_source_text": prepared.semantic_override_source_text,
                }
            )

        try:
            remember_method(
                prepared.raw_text,
                language=prepared.command_language,
                metadata=metadata,
            )
        except TypeError:
            remember_method(prepared.raw_text, prepared.command_language)

    def _log_prepared_command(self, prepared: PreparedCommand) -> None:
        LOGGER.info(
            "Prepared command: raw=%s | routing=%s | normalized=%s | detected_lang=%s | "
            "normalizer_hint=%s | command_lang=%s | semantic_override=%s | "
            "semantic_override_mode=%s | corrections=%s | source=%s | wake=%s | cancel=%s | ignore=%s",
            prepared.raw_text,
            prepared.routing_text,
            prepared.normalized_routing_text,
            prepared.detected_language,
            prepared.normalizer_language_hint,
            prepared.command_language,
            prepared.semantic_override_applied,
            prepared.semantic_override_mode or "",
            list(prepared.normalizer_corrections),
            prepared.source.value,
            prepared.wake_phrase_detected,
            prepared.cancel_requested,
            prepared.ignore,
        )

    def log_route_decision(self, route: Any) -> None:
        route_kind = getattr(route, "kind", None)
        confidence = getattr(route, "confidence", 0.0)
        primary_intent = getattr(route, "primary_intent", "")
        topics = getattr(route, "conversation_topics", []) or []
        notes = getattr(route, "notes", []) or []
        LOGGER.info(
            "Route decision: kind=%s, primary_intent=%s, confidence=%.3f, topics=%s, notes=%s",
            getattr(route_kind, "value", route_kind),
            primary_intent,
            float(confidence or 0.0),
            list(topics),
            list(notes),
        )


__all__ = ["CommandFlowMemory"]