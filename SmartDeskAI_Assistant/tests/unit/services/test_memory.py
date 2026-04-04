from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.services.memory import SimpleMemory


class TestSimpleMemory(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory_file = Path(self.temp_dir.name) / "memory.json"

        self.memory = SimpleMemory()
        self.memory.path = self.memory_file

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_remember_and_recall_exact_key(self) -> None:
        self.memory.remember("keys", "in the kitchen")
        recalled = self.memory.recall("keys")

        self.assertEqual(recalled, "in the kitchen")

    def test_remember_and_recall_polish_exact_key(self) -> None:
        self.memory.remember("klucze", "w kuchni")
        recalled = self.memory.recall("klucze")

        self.assertEqual(recalled, "w kuchni")

    def test_recall_with_my_prefix_removed(self) -> None:
        self.memory.remember("keys", "in the drawer")
        recalled = self.memory.recall("my keys")

        self.assertEqual(recalled, "in the drawer")

    def test_recall_with_polish_possessive_removed(self) -> None:
        self.memory.remember("klucz", "w plecaku")
        recalled = self.memory.recall("moj klucz")

        self.assertEqual(recalled, "w plecaku")

    def test_recall_matches_plural_and_singular_english(self) -> None:
        self.memory.remember("key", "on the desk")
        recalled = self.memory.recall("keys")

        self.assertEqual(recalled, "on the desk")

    def test_recall_matches_plural_and_singular_polish(self) -> None:
        self.memory.remember("klucz", "na biurku")
        recalled = self.memory.recall("klucze")

        self.assertEqual(recalled, "na biurku")

    def test_recall_with_phone_number_phrase(self) -> None:
        self.memory.remember("phone number", "123456789")
        recalled = self.memory.recall("my phone number")

        self.assertEqual(recalled, "123456789")

    def test_fuzzy_recall_with_partial_overlap(self) -> None:
        self.memory.remember("car keys", "on the shelf")
        recalled = self.memory.recall("keys")

        self.assertEqual(recalled, "on the shelf")

    def test_recall_returns_none_for_unknown_key(self) -> None:
        self.memory.remember("wallet", "in the jacket")
        recalled = self.memory.recall("passport")

        self.assertIsNone(recalled)

    def test_get_all_returns_saved_items(self) -> None:
        self.memory.remember("keys", "kitchen")
        self.memory.remember("wallet", "drawer")

        items = self.memory.get_all()

        self.assertIn("keys", items)
        self.assertIn("wallet", items)
        self.assertEqual(items["keys"], "kitchen")
        self.assertEqual(items["wallet"], "drawer")

    def test_remember_overwrites_same_normalized_key(self) -> None:
        self.memory.remember("my keys", "in the kitchen")
        self.memory.remember("keys", "in the backpack")

        items = self.memory.get_all()

        self.assertEqual(len(items), 1)
        only_value = next(iter(items.values()))
        self.assertEqual(only_value, "in the backpack")

    def test_empty_key_or_value_is_ignored(self) -> None:
        self.memory.remember("", "value")
        self.memory.remember("keys", "")
        items = self.memory.get_all()

        self.assertEqual(items, {})

    def test_memory_file_is_created_on_first_save(self) -> None:
        self.assertFalse(self.memory_file.exists())

        self.memory.remember("keys", "kitchen")

        self.assertTrue(self.memory_file.exists())

    def test_cleanup_normalizes_case_and_spacing(self) -> None:
        self.memory.remember("   Keys   ", "   In   The Kitchen   ")
        recalled = self.memory.recall("keys")

        self.assertEqual(recalled, "in the kitchen")


if __name__ == "__main__":
    unittest.main()