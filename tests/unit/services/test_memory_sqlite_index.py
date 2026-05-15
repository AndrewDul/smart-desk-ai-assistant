from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

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
