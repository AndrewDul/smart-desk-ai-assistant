from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modules.features.memory.service import MemoryService
from modules.shared.persistence.repositories import MemoryRepository


class TestMemoryRecords(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory_file = Path(self.temp_dir.name) / "memory.json"
        self.memory = MemoryService(store=MemoryRepository(path=str(self.memory_file)))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_remember_text_stores_full_polish_phrase_with_tokens(self) -> None:
        memory_id = self.memory.remember_text(
            "klucze są w kuchni",
            language="pl",
            source="unit_test",
        )

        records = self.memory.list_records(language="pl")

        self.assertIsNotNone(memory_id)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["language"], "pl")
        self.assertEqual(records[0]["original_text"], "klucze są w kuchni")
        self.assertIn("klucze", records[0]["tokens"])
        self.assertIn("kuchni", records[0]["tokens"])

    def test_recall_polish_memory_by_object_token(self) -> None:
        self.memory.remember_text("klucze są w kuchni", language="pl")

        recalled = self.memory.recall("przypomnij mi gdzie są klucze", language="pl")

        self.assertEqual(recalled, "klucze są w kuchni")

    def test_recall_polish_memory_by_location_token(self) -> None:
        self.memory.remember_text("mam telefon na biurku", language="pl")

        recalled = self.memory.recall("co mam na biurku", language="pl")

        self.assertEqual(recalled, "mam telefon na biurku")

    def test_recall_english_memory_by_object_token(self) -> None:
        self.memory.remember_text("my phone is on the desk", language="en")

        recalled = self.memory.recall("where is my phone", language="en")

        self.assertEqual(recalled, "my phone is on the desk")

    def test_recall_english_memory_by_location_token(self) -> None:
        self.memory.remember_text("my phone is on the desk", language="en")

        recalled = self.memory.recall("what is on my desk", language="en")

        self.assertEqual(recalled, "my phone is on the desk")

    def test_language_filter_keeps_polish_and_english_memory_separate(self) -> None:
        self.memory.remember_text("radio jest w kuchni", language="pl")
        self.memory.remember_text("radio is in the garage", language="en")

        polish_recall = self.memory.recall("gdzie jest radio", language="pl")
        english_recall = self.memory.recall("where is radio", language="en")

        self.assertEqual(polish_recall, "radio jest w kuchni")
        self.assertEqual(english_recall, "radio is in the garage")

    def test_legacy_key_value_memory_is_migrated_to_records(self) -> None:
        self.memory.remember("keys", "in the kitchen", language="en")

        records = self.memory.list_records(language="en")
        recalled = self.memory.recall("keys", language="en")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["original_text"], "keys in the kitchen")
        self.assertEqual(recalled, "keys in the kitchen")

    def test_old_dict_file_is_read_as_legacy_memory(self) -> None:
        self.memory_file.write_text(json.dumps({"keys": "in the drawer"}))
        memory = MemoryService(store=MemoryRepository(path=str(self.memory_file)))

        recalled = memory.recall("where are my keys")

        self.assertEqual(recalled, "keys in the drawer")

    def test_get_all_returns_compatibility_mapping_for_action_lists(self) -> None:
        self.memory.remember_text("klucze są w kuchni", language="pl")
        self.memory.remember_text("my phone is on the desk", language="en")

        items = self.memory.get_all()

        self.assertIn("klucze są w kuchni", items)
        self.assertIn("my phone is on the desk", items)
        self.assertEqual(items["klucze są w kuchni"], "klucze są w kuchni")

    def test_duplicate_same_language_phrase_replaces_existing_record(self) -> None:
        self.memory.remember_text("my phone is on the desk", language="en")
        self.memory.remember_text("my phone is on the desk", language="en")

        records = self.memory.list_records(language="en")

        self.assertEqual(len(records), 1)

    def test_empty_memory_text_is_ignored(self) -> None:
        memory_id = self.memory.remember_text("   ", language="en")

        self.assertIsNone(memory_id)
        self.assertEqual(self.memory.list_records(), [])

    def test_forget_removes_best_matching_record(self) -> None:
        self.memory.remember_text("my phone is on the desk", language="en")

        removed_key, removed_value = self.memory.forget("phone", language="en")

        self.assertEqual(removed_key, "my phone is on the desk")
        self.assertEqual(removed_value, "my phone is on the desk")
        self.assertIsNone(self.memory.recall("phone", language="en"))

    def test_clear_removes_all_records(self) -> None:
        self.memory.remember_text("my phone is on the desk", language="en")
        self.memory.remember_text("klucze są w kuchni", language="pl")

        removed = self.memory.clear()

        self.assertEqual(removed, 2)
        self.assertEqual(self.memory.list_records(), [])


if __name__ == "__main__":
    unittest.main()
