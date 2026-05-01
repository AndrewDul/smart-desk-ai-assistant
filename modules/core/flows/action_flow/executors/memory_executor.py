from __future__ import annotations

from .base import BaseSkillExecutor
from .models import ExecutorOutcome


class MemorySkillExecutor(BaseSkillExecutor):
    def store(
        self,
        *,
        key: str | None,
        value: str | None,
        language: str | None = None,
    ) -> ExecutorOutcome:
        normalized_key = str(key or "").strip()
        normalized_value = str(value or "").strip()
        if not normalized_key or not normalized_value:
            return ExecutorOutcome(ok=False, status="missing_fields")

        remember_method = self.first_callable(self.assistant.memory, "remember", "store", "save", "add")
        if remember_method is None:
            return ExecutorOutcome(ok=False, status="unavailable")

        try:
            remember_method(normalized_key, normalized_value, language=language)
        except TypeError:
            remember_method(normalized_key, normalized_value)

        return ExecutorOutcome(
            ok=True,
            status="stored",
            data={"key": normalized_key, "value": normalized_value},
            metadata={
                "source": "memory_service.store",
                "language": str(language or "").strip().lower(),
            },
        )

    def store_text(
        self,
        *,
        text: str | None,
        language: str | None = None,
        source: str = "memory_service.store_text",
    ) -> ExecutorOutcome:
        memory_text = str(text or "").strip()
        if not memory_text:
            return ExecutorOutcome(ok=False, status="missing_fields")

        remember_text_method = self.first_callable(
            self.assistant.memory,
            "remember_text",
            "store_text",
            "save_text",
            "add_text",
        )
        if remember_text_method is not None:
            try:
                memory_id = remember_text_method(
                    memory_text,
                    language=language,
                    source=source,
                )
            except TypeError:
                try:
                    memory_id = remember_text_method(memory_text, language=language)
                except TypeError:
                    memory_id = remember_text_method(memory_text)

            return ExecutorOutcome(
                ok=True,
                status="stored",
                data={
                    "key": memory_text,
                    "value": memory_text,
                    "memory_text": memory_text,
                    "memory_id": str(memory_id or "").strip(),
                },
                metadata={
                    "source": source,
                    "language": str(language or "").strip().lower(),
                    "storage_mode": "record_text",
                },
            )

        remember_method = self.first_callable(self.assistant.memory, "remember", "store", "save", "add")
        if remember_method is None:
            return ExecutorOutcome(ok=False, status="unavailable")

        try:
            remember_method(memory_text, memory_text, language=language)
        except TypeError:
            remember_method(memory_text, memory_text)

        return ExecutorOutcome(
            ok=True,
            status="stored",
            data={
                "key": memory_text,
                "value": memory_text,
                "memory_text": memory_text,
            },
            metadata={
                "source": source,
                "language": str(language or "").strip().lower(),
                "storage_mode": "legacy_text",
            },
        )

    def recall(self, *, key: str | None, language: str | None = None) -> ExecutorOutcome:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            return ExecutorOutcome(ok=False, status="missing_key")

        recall_method = self.first_callable(self.assistant.memory, "recall", "get", "find", "lookup")
        if recall_method is None:
            return ExecutorOutcome(ok=False, status="unavailable")

        try:
            value = recall_method(normalized_key, language=language)
        except TypeError:
            value = recall_method(normalized_key)

        if not value:
            return ExecutorOutcome(
                ok=False,
                status="not_found",
                data={"key": normalized_key},
                metadata={
                    "source": "memory_service.recall",
                    "language": str(language or "").strip().lower(),
                },
            )

        return ExecutorOutcome(
            ok=True,
            status="found",
            data={"key": normalized_key, "value": str(value)},
            metadata={
                "source": "memory_service.recall",
                "language": str(language or "").strip().lower(),
            },
        )

    def forget(self, *, key: str | None, language: str | None = None) -> ExecutorOutcome:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            return ExecutorOutcome(ok=False, status="missing_key")

        forget_method = self.first_callable(self.assistant.memory, "forget", "delete", "remove")
        if forget_method is None:
            return ExecutorOutcome(ok=False, status="unavailable")

        try:
            result = forget_method(normalized_key, language=language)
        except TypeError:
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
                metadata={
                    "source": "memory_service.forget",
                    "language": str(language or "").strip().lower(),
                },
            )

        return ExecutorOutcome(
            ok=True,
            status="removed",
            data={"key": removed_key},
            metadata={
                "source": "memory_service.forget",
                "language": str(language or "").strip().lower(),
            },
        )

    def list_items(self, *, language: str | None = None) -> ExecutorOutcome:
        memory = self.assistant.memory

        records_method = self.first_callable(memory, "list_records", "list_items")
        if records_method is not None:
            try:
                result = records_method(language=language)
            except TypeError:
                result = records_method()
            except Exception as error:
                return ExecutorOutcome(ok=False, status="list_failed", message=str(error))

            records = [dict(item) for item in list(result or []) if isinstance(item, dict)]
            items: dict[str, str] = {}
            for record in records:
                original_text = str(record.get("original_text", "") or "").strip()
                if not original_text:
                    continue
                item_key = original_text
                if item_key in items:
                    item_key = str(record.get("id", item_key) or item_key)
                items[item_key] = original_text

            return ExecutorOutcome(
                ok=True,
                status="listed",
                data={
                    "items": items,
                    "records": records,
                    "count": len(items),
                },
                metadata={"source": "memory_service.list_records"},
            )

        list_method = self.first_callable(memory, "get_all", "list_all", "items", "export")
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