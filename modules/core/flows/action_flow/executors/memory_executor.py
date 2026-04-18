from __future__ import annotations

from .base import BaseSkillExecutor
from .models import ExecutorOutcome


class MemorySkillExecutor(BaseSkillExecutor):
    def store(self, *, key: str | None, value: str | None) -> ExecutorOutcome:
        normalized_key = str(key or "").strip()
        normalized_value = str(value or "").strip()
        if not normalized_key or not normalized_value:
            return ExecutorOutcome(ok=False, status="missing_fields")

        remember_method = self.first_callable(self.assistant.memory, "remember", "store", "save", "add")
        if remember_method is None:
            return ExecutorOutcome(ok=False, status="unavailable")

        remember_method(normalized_key, normalized_value)
        return ExecutorOutcome(
            ok=True,
            status="stored",
            data={"key": normalized_key, "value": normalized_value},
            metadata={"source": "memory_service.store"},
        )

    def recall(self, *, key: str | None) -> ExecutorOutcome:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            return ExecutorOutcome(ok=False, status="missing_key")

        recall_method = self.first_callable(self.assistant.memory, "recall", "get", "find", "lookup")
        if recall_method is None:
            return ExecutorOutcome(ok=False, status="unavailable")

        value = recall_method(normalized_key)
        if not value:
            return ExecutorOutcome(
                ok=False,
                status="not_found",
                data={"key": normalized_key},
                metadata={"source": "memory_service.recall"},
            )

        return ExecutorOutcome(
            ok=True,
            status="found",
            data={"key": normalized_key, "value": str(value)},
            metadata={"source": "memory_service.recall"},
        )

    def forget(self, *, key: str | None) -> ExecutorOutcome:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            return ExecutorOutcome(ok=False, status="missing_key")

        forget_method = self.first_callable(self.assistant.memory, "forget", "delete", "remove")
        if forget_method is None:
            return ExecutorOutcome(ok=False, status="unavailable")

        result = forget_method(normalized_key)
        removed_key = ""
        if isinstance(result, tuple) and result:
            removed_key = str(result[0] or "").strip()
        elif isinstance(result, str):
            removed_key = str(result).strip()
        elif result:
            removed_key = normalized_key

        if not removed_key:
            return ExecutorOutcome(
                ok=False,
                status="not_found",
                data={"key": normalized_key},
                metadata={"source": "memory_service.forget"},
            )

        return ExecutorOutcome(
            ok=True,
            status="removed",
            data={"key": removed_key},
            metadata={"source": "memory_service.forget"},
        )

    def list_items(self) -> ExecutorOutcome:
        list_method = self.first_callable(self.assistant.memory, "get_all", "list_all", "items", "export")
        if list_method is None:
            return ExecutorOutcome(ok=False, status="unavailable")

        try:
            result = list_method()
        except Exception as error:
            return ExecutorOutcome(ok=False, status="list_failed", message=str(error))

        items = dict(result or {}) if isinstance(result, dict) else {}
        return ExecutorOutcome(
            ok=True,
            status="listed",
            data={"items": items, "count": len(items)},
            metadata={"source": "memory_service.list"},
        )


__all__ = ["MemorySkillExecutor"]