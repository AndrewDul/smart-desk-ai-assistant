from __future__ import annotations

from typing import Any


class RuntimeBuilderUnderstandingMixin:
    """
    Build the understanding layer services.
    """

    def _build_parser(self) -> Any:
        parser_class = self._import_symbol(
            "modules.understanding.parsing.parser",
            "IntentParser",
        )
        timers_cfg = self._cfg("timers")

        return parser_class(
            default_focus_minutes=float(timers_cfg.get("default_focus_minutes", 25)),
            default_break_minutes=float(timers_cfg.get("default_break_minutes", 5)),
        )

    def _build_router(self, parser: Any) -> Any:
        router_class = self._import_symbol(
            "modules.understanding.routing.companion_router",
            "SemanticCompanionRouter",
        )
        return router_class(parser)

    def _build_dialogue(self) -> Any:
        dialogue_class = self._import_symbol(
            "modules.understanding.dialogue.companion_dialogue",
            "CompanionDialogueService",
        )
        return dialogue_class()


__all__ = ["RuntimeBuilderUnderstandingMixin"]