from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RouteDecision

from .models import ResolvedAction, SkillRequest


class ActionMemoryActionsMixin:
    def _handle_memory_store(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route
        key, value = self._resolve_memory_store_fields(payload)
        outcome = self._get_memory_skill_executor().store(key=key, value=value)

        if outcome.status == "missing_fields":
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
                extra_metadata={
                    **dict(outcome.metadata or {}),
                    "resolved_source": resolved.source,
                    "phase": "missing_fields",
                },
            )

        if outcome.status == "unavailable":
            return self._deliver_feature_unavailable(language=language, action="memory_store")

        stored_key = str(outcome.data.get("key", key or "")).strip()
        stored_value = str(outcome.data.get("value", value or "")).strip()
        spoken = self._localized(
            language,
            f"Dobrze. Zapamiętałam: {stored_key}.",
            f"Okay. I remembered: {stored_key}.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action=request.action if request is not None else "memory_store",
            spoken_text=spoken,
            display_title="MEMORY SAVED",
            display_lines=self._display_lines(stored_value),
            extra_metadata={
                **dict(outcome.metadata or {}),
                "resolved_source": resolved.source,
                "key": stored_key,
            },
        )

    def _handle_memory_recall(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route
        key = self._first_present(payload, "key", "subject", "item", "name", "query")
        outcome = self._get_memory_skill_executor().recall(key=key)

        if outcome.status == "missing_key":
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
                extra_metadata={
                    **dict(outcome.metadata or {}),
                    "resolved_source": resolved.source,
                    "phase": "missing_key",
                },
            )

        if outcome.status == "unavailable":
            return self._deliver_feature_unavailable(language=language, action="memory_recall")

        if outcome.status == "not_found":
            missing_key = str(outcome.data.get("key", key or "")).strip()
            return self._deliver_simple_action_response(
                language=language,
                action="memory_recall",
                spoken_text=self._localized(
                    language,
                    f"Nie znalazłam niczego dla: {missing_key}.",
                    f"I could not find anything for: {missing_key}.",
                ),
                display_title="MEMORY",
                display_lines=self._localized_lines(
                    language,
                    ["brak wyniku"],
                    ["not found"],
                ),
                extra_metadata={
                    **dict(outcome.metadata or {}),
                    "resolved_source": resolved.source,
                    "key": missing_key,
                    "phase": "not_found",
                },
            )

        found_key = str(outcome.data.get("key", key or "")).strip()
        found_value = str(outcome.data.get("value", "")).strip()
        spoken = self._localized(
            language,
            f"Dla {found_key} mam zapisane: {found_value}.",
            f"For {found_key}, I have: {found_value}.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action=request.action if request is not None else "memory_recall",
            spoken_text=spoken,
            display_title="MEMORY",
            display_lines=self._display_lines(found_value),
            extra_metadata={
                **dict(outcome.metadata or {}),
                "resolved_source": resolved.source,
                "key": found_key,
            },
        )

    def _handle_memory_forget(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route
        key = self._first_present(payload, "key", "subject", "item", "name", "query")
        outcome = self._get_memory_skill_executor().forget(key=key)

        if outcome.status == "missing_key":
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
                extra_metadata={
                    **dict(outcome.metadata or {}),
                    "resolved_source": resolved.source,
                    "phase": "missing_key",
                },
            )

        if outcome.status == "unavailable":
            return self._deliver_feature_unavailable(language=language, action="memory_forget")

        if outcome.status == "not_found":
            missing_key = str(outcome.data.get("key", key or "")).strip()
            return self._deliver_simple_action_response(
                language=language,
                action="memory_forget",
                spoken_text=self._localized(
                    language,
                    f"Nie znalazłam wpisu do usunięcia dla: {missing_key}.",
                    f"I could not find an entry to remove for: {missing_key}.",
                ),
                display_title="MEMORY",
                display_lines=self._localized_lines(
                    language,
                    ["nic do usuniecia"],
                    ["nothing to remove"],
                ),
                extra_metadata={
                    **dict(outcome.metadata or {}),
                    "resolved_source": resolved.source,
                    "key": missing_key,
                    "phase": "not_found",
                },
            )

        removed_key = str(outcome.data.get("key", key or "")).strip()
        spoken = self._localized(
            language,
            f"Usunęłam z pamięci: {removed_key}.",
            f"I removed {removed_key} from memory.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action=request.action if request is not None else "memory_forget",
            spoken_text=spoken,
            display_title="MEMORY REMOVED",
            display_lines=self._display_lines(removed_key),
            extra_metadata={
                **dict(outcome.metadata or {}),
                "resolved_source": resolved.source,
                "key": removed_key,
            },
        )

    def _handle_memory_list(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route, payload
        outcome = self._get_memory_skill_executor().list_items()
        if outcome.status == "unavailable":
            return self._deliver_feature_unavailable(language=language, action="memory_list")

        items = dict(outcome.data.get("items", {}) or {})
        count = int(outcome.data.get("count", len(items)) or 0)
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
                extra_metadata={
                    **dict(outcome.metadata or {}),
                    "resolved_source": resolved.source,
                    "count": 0,
                },
            )

        keys = list(items.keys())[:4]
        spoken = self._localized(
            language,
            f"Mam zapisane {count} wpisy w pamięci.",
            f"I have {count} items saved in memory.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action=request.action if request is not None else "memory_list",
            spoken_text=spoken,
            display_title="MEMORY",
            display_lines=keys,
            extra_metadata={
                **dict(outcome.metadata or {}),
                "resolved_source": resolved.source,
                "count": count,
            },
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