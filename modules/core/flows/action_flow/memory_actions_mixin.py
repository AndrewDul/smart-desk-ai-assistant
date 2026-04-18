from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RouteDecision

from .models import ResolvedAction


class ActionMemoryActionsMixin:
    def _handle_memory_store(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route
        key, value = self._resolve_memory_store_fields(payload)

        if not key or not value:
            return self._deliver_simple_action_response(
                language=language,
                action="memory_store",
                spoken_text=self._localized(
                    language,
                    "Brakuje mi tego, co mam zapamiętać albo pod jaką nazwą mam to zapisać.",
                    "I am missing either what I should remember or what key I should save it under.",
                ),
                display_title="MEMORY",
                display_lines=self._localized_lines(
                    language,
                    ["brak danych", "do zapisu"],
                    ["missing data", "for memory"],
                ),
                extra_metadata={"resolved_source": resolved.source, "phase": "missing_fields"},
            )

        remember_method = self._first_callable(self.assistant.memory, "remember", "store", "save", "add")
        if remember_method is None:
            return self._deliver_feature_unavailable(language=language, action="memory_store")

        remember_method(str(key), str(value))

        spoken = self._localized(
            language,
            f"Dobrze. Zapamiętałam: {key}.",
            f"Okay. I remembered: {key}.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="memory_store",
            spoken_text=spoken,
            display_title="MEMORY SAVED",
            display_lines=self._display_lines(str(value)),
            extra_metadata={"resolved_source": resolved.source, "key": str(key)},
        )

    def _handle_memory_recall(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route
        key = self._first_present(payload, "key", "subject", "item", "name", "query")
        if not key:
            return self._deliver_simple_action_response(
                language=language,
                action="memory_recall",
                spoken_text=self._localized(
                    language,
                    "Powiedz proszę, czego mam szukać w pamięci.",
                    "Please tell me what I should look up in memory.",
                ),
                display_title="MEMORY",
                display_lines=self._localized_lines(
                    language,
                    ["podaj klucz", "lub temat"],
                    ["say the key", "or topic"],
                ),
                extra_metadata={"resolved_source": resolved.source, "phase": "missing_key"},
            )

        recall_method = self._first_callable(self.assistant.memory, "recall", "get", "find", "lookup")
        if recall_method is None:
            return self._deliver_feature_unavailable(language=language, action="memory_recall")

        value = recall_method(str(key))
        if not value:
            return self._deliver_simple_action_response(
                language=language,
                action="memory_recall",
                spoken_text=self._localized(
                    language,
                    f"Nie znalazłam niczego dla: {key}.",
                    f"I could not find anything for: {key}.",
                ),
                display_title="MEMORY",
                display_lines=self._localized_lines(
                    language,
                    ["brak wyniku"],
                    ["not found"],
                ),
                extra_metadata={"resolved_source": resolved.source, "key": str(key), "phase": "not_found"},
            )

        spoken = self._localized(
            language,
            f"Dla {key} mam zapisane: {value}.",
            f"For {key}, I have: {value}.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="memory_recall",
            spoken_text=spoken,
            display_title="MEMORY",
            display_lines=self._display_lines(str(value)),
            extra_metadata={"resolved_source": resolved.source, "key": str(key)},
        )

    def _handle_memory_forget(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route
        key = self._first_present(payload, "key", "subject", "item", "name", "query")
        if not key:
            return self._deliver_simple_action_response(
                language=language,
                action="memory_forget",
                spoken_text=self._localized(
                    language,
                    "Powiedz proszę, który wpis mam usunąć z pamięci.",
                    "Please tell me which memory entry I should remove.",
                ),
                display_title="MEMORY",
                display_lines=self._localized_lines(
                    language,
                    ["podaj wpis", "do usuniecia"],
                    ["say entry", "to remove"],
                ),
                extra_metadata={"resolved_source": resolved.source, "phase": "missing_key"},
            )

        forget_method = self._first_callable(self.assistant.memory, "forget", "delete", "remove")
        if forget_method is None:
            return self._deliver_feature_unavailable(language=language, action="memory_forget")

        result = forget_method(str(key))
        removed_key = None
        if isinstance(result, tuple):
            removed_key = result[0]
        elif isinstance(result, str):
            removed_key = result
        elif result:
            removed_key = str(key)

        if not removed_key:
            return self._deliver_simple_action_response(
                language=language,
                action="memory_forget",
                spoken_text=self._localized(
                    language,
                    f"Nie znalazłam wpisu do usunięcia dla: {key}.",
                    f"I could not find an entry to remove for: {key}.",
                ),
                display_title="MEMORY",
                display_lines=self._localized_lines(
                    language,
                    ["nic do usuniecia"],
                    ["nothing to remove"],
                ),
                extra_metadata={"resolved_source": resolved.source, "key": str(key), "phase": "not_found"},
            )

        spoken = self._localized(
            language,
            f"Usunęłam z pamięci: {removed_key}.",
            f"I removed {removed_key} from memory.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="memory_forget",
            spoken_text=spoken,
            display_title="MEMORY REMOVED",
            display_lines=self._display_lines(str(removed_key)),
            extra_metadata={"resolved_source": resolved.source, "key": str(removed_key)},
        )

    def _handle_memory_list(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        items = self._memory_items()
        if not items:
            return self._deliver_simple_action_response(
                language=language,
                action="memory_list",
                spoken_text=self._localized(
                    language,
                    "Nie mam jeszcze zapisanych informacji w pamięci.",
                    "I do not have any saved memory items yet.",
                ),
                display_title="MEMORY",
                display_lines=self._localized_lines(language, ["pamiec pusta"], ["memory empty"]),
                extra_metadata={"resolved_source": resolved.source, "count": 0},
            )

        keys = list(items.keys())[:4]
        spoken = self._localized(
            language,
            f"Mam zapisane {len(items)} wpisy w pamięci.",
            f"I have {len(items)} items saved in memory.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="memory_list",
            spoken_text=spoken,
            display_title="MEMORY",
            display_lines=keys,
            extra_metadata={"resolved_source": resolved.source, "count": len(items)},
        )

    def _handle_memory_clear(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route, payload
        self.assistant.pending_follow_up = {
            "type": "confirm_memory_clear",
            "language": language,
        }
        spoken = self._localized(
            language,
            "Czy na pewno chcesz wyczyścić całą pamięć?",
            "Are you sure you want to clear all memory?",
        )
        return self._deliver_action_follow_up_prompt(
            language=language,
            action=request.action if request is not None else "memory_clear",
            spoken_text=spoken,
            source="action_memory_clear_confirmation",
            follow_up_type="confirm_memory_clear",
            extra_metadata={"resolved_source": resolved.source},
        )

    @staticmethod
    def _route_kind_conversation():
        from modules.runtime.contracts import RouteKind

        return RouteKind.CONVERSATION