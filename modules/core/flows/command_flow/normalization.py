from __future__ import annotations

from typing import Any

from .helpers import LOGGER, CommandFlowHelpers


class CommandFlowNormalization(CommandFlowHelpers):
    """Normalization, parsing, and semantic override helpers."""

    assistant: Any

    def _normalize_utterance(self, text: str) -> Any:
        normalizer = getattr(self.assistant, "utterance_normalizer", None)
        if normalizer is None:
            return self._fallback_normalized_utterance(text)

        method = getattr(normalizer, "normalize", None)
        if not callable(method):
            return self._fallback_normalized_utterance(text)

        try:
            result = method(text)
            return result if result is not None else self._fallback_normalized_utterance(text)
        except Exception as error:
            LOGGER.warning("Utterance normalizer failed: %s", error)
            return self._fallback_normalized_utterance(text)

    def _parse_intent(self, text: str) -> Any | None:
        parser = getattr(self.assistant, "parser", None)
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
                LOGGER.warning("Command flow parser call failed on %s: %s", method_name, error)
                return None

        return None

    def _semantic_override(self, routing_text: str, command_language: str) -> dict[str, Any] | None:
        override_method = getattr(self.assistant, "_semantic_override", None)
        if not callable(override_method):
            return None

        try:
            value = override_method(routing_text, command_language)
            return value if isinstance(value, dict) else None
        except Exception as error:
            LOGGER.warning("Semantic override failed: %s", error)
            return None


__all__ = ["CommandFlowNormalization"]