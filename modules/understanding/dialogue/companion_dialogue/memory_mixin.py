from __future__ import annotations

from typing import Any


class CompanionDialogueMemoryMixin:
    """
    Public passthrough helpers for conversation memory.
    """

    def add_user_turn(
        self,
        text: str,
        *,
        language: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.conversation_memory.add_user_turn(
            text,
            language=language,
            metadata=metadata,
        )

    def add_assistant_turn(
        self,
        text: str,
        *,
        language: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.conversation_memory.add_assistant_turn(
            text,
            language=language,
            metadata=metadata,
        )


__all__ = ["CompanionDialogueMemoryMixin"]