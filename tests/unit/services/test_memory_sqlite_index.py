from __future__ import annotations

import sqlite3
import tempfile
from types import SimpleNamespace
from pathlib import Path

import numpy as np

from modules.features.memory.service import MemoryService
from modules.features.memory_v2.store import SQLiteMemoryStore
from modules.shared.persistence.repositories import MemoryRepository


def test_sqlite_memory_store_creates_database_schema_and_asset_dirs() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "nexa_memory"
        store = SQLiteMemoryStore(root=root)

        store.ensure_ready()

        assert store.path.exists()
        assert store.faces_dir.exists()
        assert store.objects_dir.exists()
        assert store.audio_dir.exists()
        assert store.video_dir.exists()

        with sqlite3.connect(store.path) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }

        assert "memory_records" in tables
        assert "memory_tokens" in tables
        assert "memory_entities" in tables
        assert "memory_facts" in tables
        assert "memory_relationships" in tables
        assert "memory_assets" in tables


def test_memory_service_mirrors_records_into_sqlite_fast_index() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        index_store = SQLiteMemoryStore(root=root / "nexa_memory")
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=index_store,
        )

        memory.remember_text("klucze są w kuchni", language="pl", source="unit_test")
        memory.remember_text("my phone is on the desk", language="en", source="unit_test")

        assert index_store.record_count() == 2
        assert memory.recall("gdzie są moje klucze", language="pl") == "klucze są w kuchni"
        assert memory.recall("where is my phone", language="en") == "my phone is on the desk"


def test_sqlite_fast_index_is_rebuilt_from_json_on_service_start() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory_file = root / "memory.json"
        sqlite_root = root / "nexa_memory"

        first = MemoryService(
            store=MemoryRepository(path=str(memory_file)),
            index_store=SQLiteMemoryStore(root=sqlite_root),
        )
        first.remember_text("telefon jest na biurku", language="pl", source="unit_test")

        rebuilt_index = SQLiteMemoryStore(root=sqlite_root)
        rebuilt_index.clear_records()
        assert rebuilt_index.record_count() == 0

        second = MemoryService(
            store=MemoryRepository(path=str(memory_file)),
            index_store=rebuilt_index,
        )

        assert rebuilt_index.record_count() == 1
        assert second.recall("gdzie jest telefon", language="pl") == "telefon jest na biurku"


def test_memory_service_falls_back_to_json_when_sqlite_index_has_no_candidate() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=SQLiteMemoryStore(root=root / "nexa_memory"),
        )

        memory.remember_text("radio jest w kuchni", language="pl", source="unit_test")

        # This query is intentionally matched by text similarity rather than a
        # direct token hit from the SQLite token index. JSON fallback keeps the
        # old compatibility behavior alive if the fast index cannot help.
        assert memory.recall("radio kuchnia", language="pl") == "radio jest w kuchni"


def test_memory_service_extracts_location_facts_into_sqlite_index() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        index_store = SQLiteMemoryStore(root=root / "nexa_memory")
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=index_store,
        )

        memory.remember_text("klucze są w kuchni", language="pl", source="unit_test")
        memory.remember_text("my phone is on the desk", language="en", source="unit_test")

        assert index_store.fact_count() == 2
        polish_facts = index_store.find_location_facts(subject_tokens=["klucze"], language="pl")
        english_facts = index_store.find_location_facts(subject_tokens=["phone"], language="en")
        assert polish_facts[0]["source_original_text"] == "klucze są w kuchni"
        assert english_facts[0]["source_original_text"] == "my phone is on the desk"


def test_memory_recall_prefers_structured_location_fact() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=SQLiteMemoryStore(root=root / "nexa_memory"),
        )

        memory.remember_text("klucze są w kuchni", language="pl", source="unit_test")

        assert memory.recall("klucze", language="pl") == "klucze są w kuchni"
        assert memory.recall("gdzie są moje klucze", language="pl") == "klucze są w kuchni"


def test_memory_recall_structured_location_fact_survives_service_restart() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory_file = root / "memory.json"
        sqlite_root = root / "nexa_memory"

        first = MemoryService(
            store=MemoryRepository(path=str(memory_file)),
            index_store=SQLiteMemoryStore(root=sqlite_root),
        )
        first.remember_text("telefon jest na biurku", language="pl", source="unit_test")

        second = MemoryService(
            store=MemoryRepository(path=str(memory_file)),
            index_store=SQLiteMemoryStore(root=sqlite_root),
        )

        assert second.index_store is not None
        assert second.index_store.fact_count() == 1
        assert second.recall("gdzie jest telefon", language="pl") == "telefon jest na biurku"


def test_memory_service_extracts_identity_preference_and_ownership_facts() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        index_store = SQLiteMemoryStore(root=root / "nexa_memory")
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=index_store,
        )

        memory.remember_text("mam na imię Andrzej", language="pl", source="unit_test")
        memory.remember_text("lubię programować", language="pl", source="unit_test")
        memory.remember_text("to jest mój telefon", language="pl", source="unit_test")

        assert index_store.fact_count() == 3
        assert memory.recall("jak mam na imię", language="pl") == "mam na imię Andrzej"
        assert memory.recall("co lubię", language="pl") == "lubię programować"
        assert memory.recall("czyj to telefon", language="pl") == "to jest mój telefon"


def test_memory_service_extracts_english_preference_and_ownership_facts() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        index_store = SQLiteMemoryStore(root=root / "nexa_memory")
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=index_store,
        )

        memory.remember_text("my name is Andrew", language="en", source="unit_test")
        memory.remember_text("I like programming", language="en", source="unit_test")
        memory.remember_text("this is my phone", language="en", source="unit_test")

        assert index_store.fact_count() == 3
        assert memory.recall("what is my name", language="en") == "my name is Andrew"
        assert memory.recall("what do I like", language="en") == "I like programming"
        assert memory.recall("whose phone is this", language="en") == "this is my phone"


def test_memory_service_can_answer_broad_user_knowledge_query_from_structured_facts() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=SQLiteMemoryStore(root=root / "nexa_memory"),
        )

        memory.remember_text("lubię programować", language="pl", source="unit_test")

        assert memory.recall("co wiesz o mnie", language="pl") == "lubię programować"


def test_sqlite_memory_store_persists_person_entities() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "nexa_memory"
        store = SQLiteMemoryStore(root=root)

        store.upsert_entity(
            {
                "id": "person_andrzej",
                "entity_type": "person",
                "display_name": "Andrzej Dul",
                "aliases": ["andrzej", "andrzej dul"],
                "language": "pl",
                "metadata": {"source": "unit_test"},
            }
        )

        assert store.entity_count() == 1
        people = store.list_entities(entity_type="person", language="pl")
        assert people[0]["display_name"] == "Andrzej Dul"
        assert "andrzej" in people[0]["aliases"]

        matches = store.find_entities(
            entity_type="person",
            query_tokens=["andrzej"],
            language="pl",
        )
        assert matches[0]["display_name"] == "Andrzej Dul"


def test_memory_service_creates_user_person_entity_from_name_fact() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        index_store = SQLiteMemoryStore(root=root / "nexa_memory")
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=index_store,
        )

        memory.remember_text("mam na imię Andrzej", language="pl", source="unit_test")

        people = memory.list_people(language="pl")
        assert len(people) == 1
        assert people[0]["display_name"] == "Andrzej"
        assert memory.recall("kogo znasz", language="pl") == "Znam: Andrzej."


def test_memory_service_remember_person_survives_restart() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory_file = root / "memory.json"
        sqlite_root = root / "nexa_memory"

        first = MemoryService(
            store=MemoryRepository(path=str(memory_file)),
            index_store=SQLiteMemoryStore(root=sqlite_root),
        )
        first.remember_person("Andrew Dul", aliases=["Andrew"], language="en")

        second = MemoryService(
            store=MemoryRepository(path=str(memory_file)),
            index_store=SQLiteMemoryStore(root=sqlite_root),
        )

        people = second.list_people(language="en")
        assert len(people) == 1
        assert people[0]["display_name"] == "Andrew Dul"
        assert "andrew" in people[0]["aliases"]
        assert second.recall("who do you know", language="en") == "I know: Andrew Dul."

def test_people_recall_is_cross_language(tmp_path: Path) -> None:
    memory = MemoryService(
        store=MemoryRepository(path=str(tmp_path / "memory.json")),
        index_store=SQLiteMemoryStore(root=tmp_path / "nexa_memory"),
    )

    memory.remember_text("mam na imię Andrzej", language="pl", source="unit_test")
    memory.remember_person("Dominika", aliases=["dominika"], language="pl")

    assert memory.recall("kogo znasz", language="pl") == "Znam: Dominika, Andrzej."
    assert memory.recall("who do you know", language="en") == "I know: Dominika, Andrzej."


def test_sqlite_memory_store_persists_person_face_assets() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "nexa_memory"
        store = SQLiteMemoryStore(root=root)
        store.upsert_entity(
            {
                "id": "person_andrzej",
                "entity_type": "person",
                "display_name": "Andrzej",
                "aliases": ["andrzej"],
                "language": "pl",
                "metadata": {"source": "unit_test"},
            }
        )
        face_dir = store.person_faces_dir("person_andrzej")
        store.upsert_asset(
            {
                "id": "asset_face_1",
                "entity_id": "person_andrzej",
                "asset_type": "face_photo",
                "path": str(face_dir / "face_001.jpg"),
                "caption": "Andrzej",
                "metadata": {"source": "unit_test"},
            }
        )

        assert face_dir.exists()
        assert store.asset_count() == 1
        assets = store.list_assets(entity_id="person_andrzej", asset_type="face_photo")
        assert assets[0]["path"].endswith("face_001.jpg")
        assert assets[0]["caption"] == "Andrzej"


def test_memory_service_registers_person_face_asset_and_preserves_link_after_resync() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory_file = root / "memory.json"
        sqlite_root = root / "nexa_memory"
        memory = MemoryService(
            store=MemoryRepository(path=str(memory_file)),
            index_store=SQLiteMemoryStore(root=sqlite_root),
        )

        asset_id = memory.remember_person_face_asset(
            "Andrzej",
            sqlite_root / "assets" / "faces" / "andrzej" / "face_001.jpg",
            aliases=["andrzej"],
            language="pl",
            caption="Andrzej face reference",
        )

        assert asset_id is not None
        assert memory.index_store is not None
        assert memory.index_store.asset_count() == 1
        assets = memory.list_person_face_assets(display_name="Andrzej", language="pl")
        assert len(assets) == 1
        assert assets[0]["caption"] == "Andrzej face reference"

        # Saving another memory rebuilds the SQLite record/entity/fact index.
        # Face asset links must survive that rebuild because future camera
        # capture will attach photos to person entities independently from
        # general text memories.
        memory.remember_text("lubię programować", language="pl", source="unit_test")
        assets_after_resync = memory.list_person_face_assets(display_name="Andrzej", language="pl")
        assert len(assets_after_resync) == 1
        assert assets_after_resync[0]["entity_id"] == assets[0]["entity_id"]


def test_memory_service_prepares_person_face_capture_slot() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=SQLiteMemoryStore(root=root / "nexa_memory"),
        )

        slot = memory.prepare_person_face_capture_slot(
            "Andrzej",
            aliases=["andrzej"],
            language="pl",
            source="unit_test",
        )

        assert slot is not None
        assert slot["face_capture_ready"] is True
        assert slot["display_name"] == "Andrzej"
        assert slot["person_entity_id"]
        assert Path(slot["person_faces_dir"]).exists()
        assert slot["next_face_asset_path"].endswith("face_001.jpg")
        assert memory.recall("kogo znasz", language="pl") == "Znam: Andrzej."

        asset_id = memory.remember_person_face_asset(
            "Andrzej",
            slot["next_face_asset_path"],
            aliases=["andrzej"],
            language="pl",
            caption="Andrzej face reference",
        )
        assert asset_id is not None

        next_slot = memory.prepare_person_face_capture_slot(
            "Andrzej",
            aliases=["andrzej"],
            language="pl",
            source="unit_test",
        )
        assert next_slot is not None
        assert next_slot["existing_face_asset_count"] == 1
        assert next_slot["next_face_asset_path"].endswith("face_002.jpg")


class _FramePacket:
    backend_label = "unit_rgb"

    def __init__(self) -> None:
        self.pixels = np.zeros((20, 30, 3), dtype=np.uint8)


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
                    "faces": [{"confidence": 0.86}],
                    "face_count": 1,
                }
            }
        )

    def latest_frame(self):
        return _FramePacket()


class _FakeVisionBackendWithoutFace(_FakeVisionBackend):
    def latest_tracking_observation(self, *, force_refresh: bool = True):
        del force_refresh
        return SimpleNamespace(
            metadata={
                "perception": {
                    "faces": [],
                    "face_count": 0,
                }
            }
        )


def test_memory_service_captures_person_face_reference_from_existing_vision_backend() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=SQLiteMemoryStore(root=root / "nexa_memory"),
        )

        result = memory.capture_person_face_reference(
            display_name="Andrzej",
            aliases=["andrzej"],
            language="pl",
            vision_backend=_FakeVisionBackend(),
        )

        assert result["ok"] is True
        assert result["asset_id"].startswith("asset_")
        assert result["width"] == 30
        assert result["height"] == 20
        assert result["face_detected"] is True
        assert result["face_count"] == 1
        assert result["face_confidence"] == 0.86
        assert Path(result["path"]).exists()
        assert memory.index_store is not None
        assert memory.index_store.asset_count() == 1
        assets = memory.list_person_face_assets(display_name="Andrzej", language="pl")
        assert assets[0]["path"] == result["path"]
        assert assets[0]["metadata"]["face_detected"] is True
        assert assets[0]["metadata"]["face_count"] == 1


def test_memory_service_face_capture_skips_asset_when_no_face_is_detected() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=SQLiteMemoryStore(root=root / "nexa_memory"),
        )

        result = memory.capture_person_face_reference(
            display_name="Andrzej",
            aliases=["andrzej"],
            language="pl",
            vision_backend=_FakeVisionBackendWithoutFace(),
        )

        assert result["ok"] is False
        assert result["reason"] == "face_not_detected"
        assert result["face_detected"] is False
        assert result["face_count"] == 0
        assert memory.index_store is not None
        assert memory.index_store.asset_count() == 0


def test_memory_service_face_capture_returns_safe_failure_without_vision_backend() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        memory = MemoryService(
            store=MemoryRepository(path=str(root / "memory.json")),
            index_store=SQLiteMemoryStore(root=root / "nexa_memory"),
        )

        result = memory.capture_person_face_reference(
            display_name="Andrzej",
            language="pl",
            vision_backend=None,
        )

        assert result["ok"] is False
        assert result["reason"] == "vision_backend_unavailable"
        assert memory.index_store is not None
        assert memory.index_store.asset_count() == 0
