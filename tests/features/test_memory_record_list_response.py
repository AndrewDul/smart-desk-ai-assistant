from __future__ import annotations

from modules.core.flows.action_flow.builders.memory_builder import MemorySkillResponseBuilder
from modules.core.flows.action_flow.executors.memory_executor import MemorySkillExecutor


class _RecordMemory:
    def list_records(self, *, language: str | None = None):
        del language
        return [
            {
                "id": "mem_keys",
                "language": "pl",
                "original_text": "klucze są w kuchni",
                "normalized_text": "klucze sa w kuchni",
                "tokens": ["klucze", "kuchni"],
            },
            {
                "id": "mem_phone",
                "language": "pl",
                "original_text": "telefon jest na biurku",
                "normalized_text": "telefon jest na biurku",
                "tokens": ["telefon", "biurku"],
            },
        ]


class _LegacyMemory:
    def get_all(self):
        return {
            "keys": "keys in the kitchen",
            "phone": "phone on the desk",
        }


class _Assistant:
    def __init__(self, memory) -> None:
        self.memory = memory


def _builder() -> MemorySkillResponseBuilder:
    def localize_text(language: str, polish_text: str, english_text: str) -> str:
        return polish_text if str(language).lower().startswith("pl") else english_text

    def localize_lines(language: str, polish_lines: list[str], english_lines: list[str]) -> list[str]:
        return polish_lines if str(language).lower().startswith("pl") else english_lines

    def display_lines(value) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        text = str(value or "").strip()
        return [text] if text else []

    def trim_text(value: str, *, max_chars: int = 160) -> str:
        text = str(value or "").strip()
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 1].rstrip() + "…"

    def duration_text(seconds: int | float, *, language: str = "en") -> str:
        seconds_int = int(seconds)
        if str(language).lower().startswith("pl"):
            return f"{seconds_int} sekund"
        return f"{seconds_int} seconds"

    return MemorySkillResponseBuilder(
        localize_text=localize_text,
        localize_lines=localize_lines,
        display_lines=display_lines,
        trim_text=trim_text,
        duration_text=duration_text,
    )


def test_memory_executor_lists_record_memory_as_full_phrases() -> None:
    executor = MemorySkillExecutor(assistant=_Assistant(_RecordMemory()))

    outcome = executor.list_items(language="pl")

    assert outcome.ok is True
    assert outcome.status == "listed"
    assert outcome.data["count"] == 2
    assert outcome.data["items"]["klucze są w kuchni"] == "klucze są w kuchni"
    assert outcome.data["items"]["telefon jest na biurku"] == "telefon jest na biurku"
    assert outcome.metadata["source"] == "memory_service.list_records"


def test_memory_executor_keeps_legacy_get_all_fallback() -> None:
    executor = MemorySkillExecutor(assistant=_Assistant(_LegacyMemory()))

    outcome = executor.list_items()

    assert outcome.ok is True
    assert outcome.status == "listed"
    assert outcome.data["count"] == 2
    assert outcome.data["items"]["keys"] == "keys in the kitchen"


def test_memory_list_response_speaks_saved_phrases_in_polish() -> None:
    builder = _builder()

    spec = builder.build_list_response(
        language="pl",
        action="memory_list",
        resolved_source="unit_test",
        items={
            "klucze są w kuchni": "klucze są w kuchni",
            "telefon jest na biurku": "telefon jest na biurku",
        },
        count=2,
        metadata={"source": "unit_test"},
    )

    assert "Zapamiętałam 2 rzeczy" in spec.spoken_text
    assert "klucze są w kuchni" in spec.spoken_text
    assert "telefon jest na biurku" in spec.spoken_text
    assert spec.display_lines == ["klucze są w kuchni", "telefon jest na biurku"]


def test_memory_list_response_speaks_saved_phrases_in_english() -> None:
    builder = _builder()

    spec = builder.build_list_response(
        language="en",
        action="memory_list",
        resolved_source="unit_test",
        items={
            "my phone is on the desk": "my phone is on the desk",
        },
        count=1,
        metadata={"source": "unit_test"},
    )

    assert spec.spoken_text == "I remember: my phone is on the desk."
    assert spec.display_lines == ["my phone is on the desk"]
