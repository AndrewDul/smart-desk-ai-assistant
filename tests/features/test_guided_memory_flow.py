from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from modules.core.flows.action_flow.executors.memory_executor import MemorySkillExecutor
from modules.core.flows.action_flow.memory_actions_mixin import ActionMemoryActionsMixin
from modules.core.flows.pending_flow.follow_up_mixin import PendingFlowFollowUpMixin
from modules.features.memory.service import MemoryService
from modules.shared.persistence.repositories import MemoryRepository


class _Assistant:
    def __init__(self, memory: MemoryService) -> None:
        self.memory = memory
        self.pending_follow_up = None
        self.responses: list[dict] = []
        self.committed_language = ""

    def _localized(self, language: str, polish_text: str, english_text: str) -> str:
        return polish_text if str(language).lower().startswith("pl") else english_text

    def _commit_language(self, language: str) -> None:
        self.committed_language = language

    def deliver_text_response(
        self,
        text: str,
        *,
        language: str,
        route_kind,
        source: str,
        metadata: dict | None = None,
    ) -> bool:
        self.responses.append(
            {
                "text": text,
                "language": language,
                "route_kind": route_kind,
                "source": source,
                "metadata": dict(metadata or {}),
            }
        )
        return True


class _PendingFlow(PendingFlowFollowUpMixin):
    def __init__(self, assistant: _Assistant) -> None:
        self.assistant = assistant

    def _follow_up_language(self, command_lang: str) -> str:
        follow_up = self.assistant.pending_follow_up or {}
        return str(follow_up.get("language", "") or command_lang or "en")

    def _is_no(self, text: str) -> bool:
        return str(text or "").strip().lower() in {"no", "nie"}


class _MemoryActionFlow(ActionMemoryActionsMixin):
    def __init__(self, assistant: _Assistant) -> None:
        self.assistant = assistant

    @staticmethod
    def _first_present(payload: dict, *names: str):
        for name in names:
            value = payload.get(name)
            if str(value or "").strip():
                return value
        return None

    @staticmethod
    def _resolve_memory_store_fields(payload: dict):
        return payload.get("key"), payload.get("value")

    def _get_memory_skill_executor(self) -> MemorySkillExecutor:
        return MemorySkillExecutor(assistant=self.assistant)

    def _deliver_feature_unavailable(self, *, language: str, action: str) -> bool:
        del language, action
        return False


def _memory_service(path: Path) -> MemoryService:
    return MemoryService(store=MemoryRepository(path=str(path)))


def test_guided_memory_store_starts_polish_message_follow_up() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        assistant = _Assistant(_memory_service(Path(temp_dir) / "memory.json"))
        flow = _MemoryActionFlow(assistant)

        handled = flow._handle_memory_store(
            route=SimpleNamespace(),
            language="pl",
            payload={"guided": True},
            resolved=SimpleNamespace(source="unit_test"),
        )

        assert handled is True
        assert assistant.pending_follow_up == {
            "type": "memory_message",
            "language": "pl",
        }
        assert assistant.responses[-1]["source"] == "action_memory_guided_message_prompt"
        assert assistant.responses[-1]["text"] == "Jasne. Co mam zapamiętać?"


def test_polish_guided_memory_message_saves_full_phrase_and_recall_finds_it() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        assistant = _Assistant(_memory_service(Path(temp_dir) / "memory.json"))
        assistant.pending_follow_up = {"type": "memory_message", "language": "pl"}
        flow = _PendingFlow(assistant)

        decision = flow.handle_pending_follow_up("klucze są w kuchni", "pl")

        assert decision.handled is True
        assert decision.consumed_by == "follow_up:memory_message"
        assert assistant.pending_follow_up is None
        assert assistant.responses[-1]["source"] == "pending_memory_message_saved"
        assert assistant.memory.recall("przypomnij mi gdzie są klucze", language="pl") == "klucze są w kuchni"


def test_english_guided_memory_message_saves_full_phrase_and_recall_finds_it() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        assistant = _Assistant(_memory_service(Path(temp_dir) / "memory.json"))
        assistant.pending_follow_up = {"type": "memory_message", "language": "en"}
        flow = _PendingFlow(assistant)

        decision = flow.handle_pending_follow_up("my phone is on the desk", "en")

        assert decision.handled is True
        assert decision.consumed_by == "follow_up:memory_message"
        assert assistant.pending_follow_up is None
        assert assistant.responses[-1]["source"] == "pending_memory_message_saved"
        assert assistant.memory.recall("where is my phone", language="en") == "my phone is on the desk"


def test_guided_memory_keeps_polish_and_english_records_separate() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        memory = _memory_service(Path(temp_dir) / "memory.json")
        assistant = _Assistant(memory)
        flow = _PendingFlow(assistant)

        assistant.pending_follow_up = {"type": "memory_message", "language": "pl"}
        flow.handle_pending_follow_up("radio jest w kuchni", "pl")

        assistant.pending_follow_up = {"type": "memory_message", "language": "en"}
        flow.handle_pending_follow_up("radio is in the garage", "en")

        assert memory.recall("gdzie jest radio", language="pl") == "radio jest w kuchni"
        assert memory.recall("where is radio", language="en") == "radio is in the garage"
