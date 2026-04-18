from __future__ import annotations

from .base import BaseActionResponseBuilder
from .models import ActionFollowUpPromptSpec, ActionResponseSpec


class MemorySkillResponseBuilder(BaseActionResponseBuilder):
    def build_store_response(
        self,
        *,
        language: str,
        action: str,
        outcome_status: str,
        resolved_source: str,
        key: str,
        value: str,
        metadata: dict | None = None,
    ) -> ActionResponseSpec:
        if outcome_status == "missing_fields":
            return ActionResponseSpec(
                action=action,
                spoken_text=self.localized(
                    language,
                    "Brakuje mi tego, co mam zapamiętać albo pod jaką nazwą mam to zapisać.",
                    "I am missing either what I should remember or what key I should save it under.",
                ),
                display_title="MEMORY",
                display_lines=self.localized_lines(
                    language,
                    ["brak danych", "do zapisu"],
                    ["missing data", "for memory"],
                ),
                extra_metadata={
                    **dict(metadata or {}),
                    "resolved_source": resolved_source,
                    "phase": "missing_fields",
                },
            )

        return ActionResponseSpec(
            action=action,
            spoken_text=self.localized(
                language,
                f"Dobrze. Zapamiętałam: {key}.",
                f"Okay. I remembered: {key}.",
            ),
            display_title="MEMORY SAVED",
            display_lines=self.display_lines(value),
            extra_metadata={
                **dict(metadata or {}),
                "resolved_source": resolved_source,
                "key": key,
            },
        )

    def build_recall_response(
        self,
        *,
        language: str,
        action: str,
        outcome_status: str,
        resolved_source: str,
        key: str,
        value: str,
        metadata: dict | None = None,
    ) -> ActionResponseSpec:
        if outcome_status == "missing_key":
            return ActionResponseSpec(
                action=action,
                spoken_text=self.localized(
                    language,
                    "Powiedz proszę, czego mam szukać w pamięci.",
                    "Please tell me what I should look up in memory.",
                ),
                display_title="MEMORY",
                display_lines=self.localized_lines(
                    language,
                    ["podaj klucz", "lub temat"],
                    ["say the key", "or topic"],
                ),
                extra_metadata={
                    **dict(metadata or {}),
                    "resolved_source": resolved_source,
                    "phase": "missing_key",
                },
            )

        if outcome_status == "not_found":
            return ActionResponseSpec(
                action=action,
                spoken_text=self.localized(
                    language,
                    f"Nie znalazłam niczego dla: {key}.",
                    f"I could not find anything for: {key}.",
                ),
                display_title="MEMORY",
                display_lines=self.localized_lines(
                    language,
                    ["brak wyniku"],
                    ["not found"],
                ),
                extra_metadata={
                    **dict(metadata or {}),
                    "resolved_source": resolved_source,
                    "key": key,
                    "phase": "not_found",
                },
            )

        return ActionResponseSpec(
            action=action,
            spoken_text=self.localized(
                language,
                f"Dla {key} mam zapisane: {value}.",
                f"For {key}, I have: {value}.",
            ),
            display_title="MEMORY",
            display_lines=self.display_lines(value),
            extra_metadata={
                **dict(metadata or {}),
                "resolved_source": resolved_source,
                "key": key,
            },
        )

    def build_forget_response(
        self,
        *,
        language: str,
        action: str,
        outcome_status: str,
        resolved_source: str,
        key: str,
        metadata: dict | None = None,
    ) -> ActionResponseSpec:
        if outcome_status == "missing_key":
            return ActionResponseSpec(
                action=action,
                spoken_text=self.localized(
                    language,
                    "Powiedz proszę, który wpis mam usunąć z pamięci.",
                    "Please tell me which memory entry I should remove.",
                ),
                display_title="MEMORY",
                display_lines=self.localized_lines(
                    language,
                    ["podaj wpis", "do usuniecia"],
                    ["say entry", "to remove"],
                ),
                extra_metadata={
                    **dict(metadata or {}),
                    "resolved_source": resolved_source,
                    "phase": "missing_key",
                },
            )

        if outcome_status == "not_found":
            return ActionResponseSpec(
                action=action,
                spoken_text=self.localized(
                    language,
                    f"Nie znalazłam wpisu do usunięcia dla: {key}.",
                    f"I could not find an entry to remove for: {key}.",
                ),
                display_title="MEMORY",
                display_lines=self.localized_lines(
                    language,
                    ["nic do usuniecia"],
                    ["nothing to remove"],
                ),
                extra_metadata={
                    **dict(metadata or {}),
                    "resolved_source": resolved_source,
                    "key": key,
                    "phase": "not_found",
                },
            )

        return ActionResponseSpec(
            action=action,
            spoken_text=self.localized(
                language,
                f"Usunęłam z pamięci: {key}.",
                f"I removed {key} from memory.",
            ),
            display_title="MEMORY REMOVED",
            display_lines=self.display_lines(key),
            extra_metadata={
                **dict(metadata or {}),
                "resolved_source": resolved_source,
                "key": key,
            },
        )

    def build_list_response(
        self,
        *,
        language: str,
        action: str,
        resolved_source: str,
        items: dict[str, str],
        count: int,
        metadata: dict | None = None,
    ) -> ActionResponseSpec:
        if not items:
            return ActionResponseSpec(
                action=action,
                spoken_text=self.localized(
                    language,
                    "Nie mam jeszcze zapisanych informacji w pamięci.",
                    "I do not have any saved memory items yet.",
                ),
                display_title="MEMORY",
                display_lines=self.localized_lines(language, ["pamiec pusta"], ["memory empty"]),
                extra_metadata={
                    **dict(metadata or {}),
                    "resolved_source": resolved_source,
                    "count": 0,
                },
            )

        return ActionResponseSpec(
            action=action,
            spoken_text=self.localized(
                language,
                f"Mam zapisane {count} wpisy w pamięci.",
                f"I have {count} items saved in memory.",
            ),
            display_title="MEMORY",
            display_lines=list(items.keys())[:4],
            extra_metadata={
                **dict(metadata or {}),
                "resolved_source": resolved_source,
                "count": count,
            },
        )

    def build_clear_confirmation(
        self,
        *,
        language: str,
        action: str,
        resolved_source: str,
        metadata: dict | None = None,
    ) -> ActionFollowUpPromptSpec:
        return ActionFollowUpPromptSpec(
            action=action,
            spoken_text=self.localized(
                language,
                "Czy na pewno chcesz wyczyścić całą pamięć?",
                "Are you sure you want to clear all memory?",
            ),
            source="action_memory_clear_confirmation",
            follow_up_type="confirm_memory_clear",
            extra_metadata={
                **dict(metadata or {}),
                "resolved_source": resolved_source,
            },
        )


__all__ = ["MemorySkillResponseBuilder"]