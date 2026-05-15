from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from modules.core.flows.action_flow.executors.memory_executor import MemorySkillExecutor
from modules.core.flows.action_flow.memory_actions_mixin import ActionMemoryActionsMixin
from modules.core.flows.pending_flow.follow_up_mixin import PendingFlowFollowUpMixin
from modules.features.memory.service import MemoryService
from modules.features.memory_v2.store import SQLiteMemoryStore
from modules.shared.persistence.repositories import MemoryRepository


class _Assistant:
    def __init__(self, memory: MemoryService) -> None:
        self.memory = memory
        self.pending_follow_up = None
        self.responses: list[dict] = []
        self.committed_language = ""
        self.vision = None

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




class _FramePacket:
    backend_label = "unit_rgb"

    def __init__(self) -> None:
        self.pixels = np.zeros((24, 32, 3), dtype=np.uint8)


class _FakeVisionBackend:
    def __init__(self) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True

    def latest_tracking_observation(self, *, force_refresh: bool = True):
        del force_refresh
        return SimpleNamespace(
            metadata={
                "perception": {
                    "faces": [{"confidence": 0.82}],
                    "face_count": 1,
                }
            }
        )

    def latest_frame(self):
        return _FramePacket()


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

def test_polish_guided_memory_retries_observed_english_false_positive() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        assistant = _Assistant(_memory_service(Path(temp_dir) / "memory.json"))
        assistant.pending_follow_up = {"type": "memory_message", "language": "pl"}
        flow = _PendingFlow(assistant)

        decision = flow.handle_pending_follow_up("Clue chest on the corner.", "pl")

        assert decision.handled is True
        assert decision.consumed_by == "follow_up:memory_message"
        assert assistant.pending_follow_up == {"type": "memory_message", "language": "pl"}
        assert assistant.responses[-1]["source"] == "pending_memory_message_suspicious_retry"
        assert assistant.memory.list_records(language="pl") == []


def test_polish_guided_memory_repairs_glued_keys_phrase_before_saving() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        assistant = _Assistant(_memory_service(Path(temp_dir) / "memory.json"))
        assistant.pending_follow_up = {"type": "memory_message", "language": "pl"}
        flow = _PendingFlow(assistant)

        decision = flow.handle_pending_follow_up("Klułczesą w kuchni.", "pl")

        assert decision.handled is True
        assert assistant.pending_follow_up is None
        assert assistant.responses[-1]["source"] == "pending_memory_message_saved"
        assert assistant.responses[-1]["metadata"]["stored_text"] == "klucze są w kuchni"
        assert assistant.memory.recall("gdzie są moje klucze", language="pl") == "klucze są w kuchni"


def test_guided_person_memory_starts_name_follow_up() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        assistant = _Assistant(_memory_service(Path(temp_dir) / "memory.json"))
        flow = _MemoryActionFlow(assistant)

        handled = flow._handle_memory_store(
            route=SimpleNamespace(),
            language="pl",
            payload={"guided": True, "person_enrollment": True},
            resolved=SimpleNamespace(source="unit_test"),
        )

        assert handled is True
        assert assistant.pending_follow_up == {
            "type": "memory_person_name",
            "language": "pl",
        }
        assert assistant.responses[-1]["source"] == "action_memory_person_name_prompt"
        assert assistant.responses[-1]["text"] == "Dobrze. Jak mam Cię nazywać?"




def test_guided_object_memory_starts_object_name_follow_up() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        assistant = _Assistant(_memory_service(Path(temp_dir) / "memory.json"))
        flow = _MemoryActionFlow(assistant)

        handled = flow._handle_memory_store(
            route=SimpleNamespace(),
            language="pl",
            payload={"guided": True, "object_enrollment": True, "object_hint": "telefon"},
            resolved=SimpleNamespace(source="unit_test"),
        )

        assert handled is True
        assert assistant.pending_follow_up == {
            "type": "memory_object_name",
            "language": "pl",
            "object_hint": "telefon",
        }
        assert assistant.responses[-1]["source"] == "action_memory_object_name_prompt"
        assert assistant.responses[-1]["text"] == "Dobrze. Jak mam nazwać ten obiekt?"


def test_guided_object_memory_name_follow_up_prepares_object_slot_with_index() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=SQLiteMemoryStore(root=root / "nexa_memory"),
        )
        assistant = _Assistant(memory)
        assistant.pending_follow_up = {"type": "memory_object_name", "language": "pl", "object_hint": "telefon"}
        flow = _PendingFlow(assistant)

        decision = flow.handle_pending_follow_up("mój telefon", "pl")

        assert decision.handled is True
        assert decision.consumed_by == "follow_up:memory_object_name"
        assert assistant.pending_follow_up is None
        response = assistant.responses[-1]
        assert response["source"] == "pending_memory_object_name_saved"
        assert response["metadata"]["display_name"] == "Telefon"
        assert response["metadata"]["owner"] == "user"
        assert response["metadata"]["object_capture_ready"] is True
        assert response["metadata"]["object_capture_saved"] is False
        assert response["metadata"]["object_capture_reason"] == "vision_backend_unavailable"
        assert response["metadata"]["object_entity_id"]
        assert Path(response["metadata"]["object_assets_dir"]).exists()
        assert response["metadata"]["next_object_asset_path"].endswith("object_001.jpg")
        assert response["text"] == "Dobrze. Będę pamiętać ten obiekt jako Telefon."
        assert memory.recall("jakie obiekty znasz", language="pl") == "Znam obiekty: Telefon."



def test_guided_object_memory_name_follow_up_corrects_vape_asr_name() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=SQLiteMemoryStore(root=root / "nexa_memory"),
        )
        assistant = _Assistant(memory)
        assistant.pending_follow_up = {"type": "memory_object_name", "language": "en", "object_hint": "vape"}
        flow = _PendingFlow(assistant)

        decision = flow.handle_pending_follow_up("wipe", "en")

        assert decision.handled is True
        assert decision.consumed_by == "follow_up:memory_object_name"
        assert assistant.pending_follow_up is None
        response = assistant.responses[-1]
        assert response["source"] == "pending_memory_object_name_saved"
        assert response["metadata"]["display_name"] == "Vape"
        assert memory.recall("what objects do you know", language="en") == "I know objects: Vape."


def test_guided_object_memory_name_follow_up_rejects_command_like_name() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=SQLiteMemoryStore(root=root / "nexa_memory"),
        )
        assistant = _Assistant(memory)
        assistant.pending_follow_up = {"type": "memory_object_name", "language": "pl", "object_hint": "telefon"}
        flow = _PendingFlow(assistant)

        decision = flow.handle_pending_follow_up("pokaż pulpit", "pl")

        assert decision.handled is True
        assert decision.consumed_by == "follow_up:memory_object_name"
        assert assistant.pending_follow_up == {"type": "memory_object_name", "language": "pl", "object_hint": "telefon"}
        response = assistant.responses[-1]
        assert response["source"] == "pending_memory_object_name_rejected"
        assert response["metadata"]["rejection_reason"] == "command_like_object_name"
        assert memory.recall("jakie obiekty znasz", language="pl") == "Nie znam jeszcze żadnych obiektów."


def test_guided_object_memory_name_follow_up_rejects_low_quality_hint_mismatch() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=SQLiteMemoryStore(root=root / "nexa_memory"),
        )
        assistant = _Assistant(memory)
        assistant.pending_follow_up = {"type": "memory_object_name", "language": "pl", "object_hint": "telefon"}
        flow = _PendingFlow(assistant)

        decision = flow.handle_pending_follow_up("ale w form", "pl")

        assert decision.handled is True
        assert decision.consumed_by == "follow_up:memory_object_name"
        assert assistant.pending_follow_up == {"type": "memory_object_name", "language": "pl", "object_hint": "telefon"}
        response = assistant.responses[-1]
        assert response["source"] == "pending_memory_object_name_rejected"
        assert response["metadata"]["rejection_reason"] == "low_quality_object_name"
        assert memory.recall("jakie obiekty znasz", language="pl") == "Nie znam jeszcze żadnych obiektów."


def test_guided_object_memory_name_follow_up_captures_object_when_vision_frame_available() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=SQLiteMemoryStore(root=root / "nexa_memory"),
        )
        assistant = _Assistant(memory)
        assistant.vision = _FakeVisionBackend()
        assistant.pending_follow_up = {"type": "memory_object_name", "language": "pl", "object_hint": "telefon"}
        flow = _PendingFlow(assistant)

        decision = flow.handle_pending_follow_up("mój telefon", "pl")

        assert decision.handled is True
        response = assistant.responses[-1]
        assert response["metadata"]["object_capture_ready"] is True
        assert response["metadata"]["object_capture_saved"] is True
        assert response["metadata"]["object_asset_id"].startswith("asset_")
        assert Path(response["metadata"]["object_asset_path"]).exists()
        assert response["metadata"]["object_capture_width"] == 32
        assert response["metadata"]["object_capture_height"] == 24
        assert memory.index_store is not None
        assert memory.index_store.asset_count() == 1
        assert response["text"] == "Dobrze. Będę pamiętać ten obiekt jako Telefon."


def test_guided_person_memory_name_follow_up_prepares_face_slot_with_index() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=SQLiteMemoryStore(root=root / "nexa_memory"),
        )
        assistant = _Assistant(memory)
        assistant.pending_follow_up = {"type": "memory_person_name", "language": "pl"}
        flow = _PendingFlow(assistant)

        decision = flow.handle_pending_follow_up("mam na imię Andrzej", "pl")

        assert decision.handled is True
        assert decision.consumed_by == "follow_up:memory_person_name"
        assert assistant.pending_follow_up is None
        response = assistant.responses[-1]
        assert response["source"] == "pending_memory_person_name_saved"
        assert response["metadata"]["display_name"] == "Andrzej"
        assert response["metadata"]["face_capture_ready"] is True
        assert response["metadata"]["face_capture_saved"] is False
        assert response["metadata"]["person_entity_id"]
        assert Path(response["metadata"]["person_faces_dir"]).exists()
        assert response["metadata"]["next_face_asset_path"].endswith("face_001.jpg")
        assert response["text"] == "Dobrze, Andrzej. Będę Cię już pamiętać."


def test_guided_person_memory_name_follow_up_captures_face_when_vision_frame_available() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=SQLiteMemoryStore(root=root / "nexa_memory"),
        )
        assistant = _Assistant(memory)
        assistant.vision = _FakeVisionBackend()
        assistant.pending_follow_up = {"type": "memory_person_name", "language": "pl"}
        flow = _PendingFlow(assistant)

        decision = flow.handle_pending_follow_up("mam na imię Andrzej", "pl")

        assert decision.handled is True
        response = assistant.responses[-1]
        assert response["metadata"]["face_capture_ready"] is True
        assert response["metadata"]["face_capture_saved"] is True
        assert response["metadata"]["face_asset_id"].startswith("asset_")
        assert Path(response["metadata"]["face_asset_path"]).exists()
        assert response["metadata"]["face_capture_width"] == 32
        assert response["metadata"]["face_capture_height"] == 24
        assert response["metadata"]["face_detected"] is True
        assert response["metadata"]["face_count"] == 1
        assert response["metadata"]["face_confidence"] == 0.82
        assert memory.index_store is not None
        assert memory.index_store.asset_count() == 1
        assert response["text"] == "Dobrze, Andrzej. Będę Cię już pamiętać."

def test_guided_person_memory_name_follow_up_remembers_user_person() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        assistant = _Assistant(_memory_service(Path(temp_dir) / "memory.json"))
        assistant.pending_follow_up = {"type": "memory_person_name", "language": "pl"}
        flow = _PendingFlow(assistant)

        decision = flow.handle_pending_follow_up("mam na imię Andrzej", "pl")

        assert decision.handled is True
        assert decision.consumed_by == "follow_up:memory_person_name"
        assert assistant.pending_follow_up is None
        assert assistant.responses[-1]["source"] == "pending_memory_person_name_saved"
        assert assistant.responses[-1]["metadata"]["display_name"] == "Andrzej"
        assert assistant.memory.recall("kogo znasz", language="pl") == "Znam: Andrzej."
