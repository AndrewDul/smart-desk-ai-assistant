from __future__ import annotations

import unittest

from modules.understanding.parsing.parser.core import IntentParser


class TestMemoryStoreTriggers(unittest.TestCase):
    """
    Memory store should enter guided mode whenever the user spoke only a
    trigger phrase ("remember", "zapamiętaj", "remember it", "zapamiętaj to")
    instead of trying to literally save the pronoun as memory content.
    """

    def setUp(self) -> None:
        self.parser = IntentParser()

    # -- bare triggers --------------------------------------------------

    def test_bare_remember_enters_guided_mode(self) -> None:
        result = self.parser.parse("remember")

        self.assertEqual(result.action, "memory_store")
        self.assertEqual(result.data, {"guided": True})

    def test_bare_zapamietaj_enters_guided_mode(self) -> None:
        result = self.parser.parse("zapamiętaj")

        self.assertEqual(result.action, "memory_store")
        self.assertEqual(result.data, {"guided": True})

    def test_bare_zapamietaj_no_diacritics_enters_guided_mode(self) -> None:
        result = self.parser.parse("zapamietaj")

        self.assertEqual(result.action, "memory_store")
        self.assertEqual(result.data, {"guided": True})

    def test_bare_pamietaj_enters_guided_mode(self) -> None:
        result = self.parser.parse("pamiętaj")

        self.assertEqual(result.action, "memory_store")
        self.assertEqual(result.data, {"guided": True})

    # -- trigger + pronoun residue (was the actual bug) -----------------

    def test_remember_it_enters_guided_mode(self) -> None:
        # Previously this would try to literally save the word "it".
        result = self.parser.parse("remember it")

        self.assertEqual(result.action, "memory_store")
        self.assertEqual(result.data, {"guided": True})

    def test_remember_this_enters_guided_mode(self) -> None:
        result = self.parser.parse("remember this")

        self.assertEqual(result.action, "memory_store")
        self.assertEqual(result.data, {"guided": True})

    def test_remember_that_enters_guided_mode(self) -> None:
        result = self.parser.parse("remember that")

        self.assertEqual(result.action, "memory_store")
        self.assertEqual(result.data, {"guided": True})

    def test_zapamietaj_to_enters_guided_mode(self) -> None:
        # Previously this would try to literally save the word "to".
        result = self.parser.parse("zapamiętaj to")

        self.assertEqual(result.action, "memory_store")
        self.assertEqual(result.data, {"guided": True})

    def test_zapamietaj_to_no_diacritics_enters_guided_mode(self) -> None:
        result = self.parser.parse("zapamietaj to")

        self.assertEqual(result.action, "memory_store")
        self.assertEqual(result.data, {"guided": True})

    def test_zapamietaj_cos_enters_guided_mode(self) -> None:
        result = self.parser.parse("zapamiętaj coś")

        self.assertEqual(result.action, "memory_store")
        self.assertEqual(result.data, {"guided": True})

    def test_remember_something_enters_guided_mode(self) -> None:
        result = self.parser.parse("remember something")

        self.assertEqual(result.action, "memory_store")
        self.assertEqual(result.data, {"guided": True})

    # -- real content still parses normally -----------------------------

    def test_remember_with_content_still_extracts_subject_and_value(self) -> None:
        result = self.parser.parse("remember the phone is on the desk")

        self.assertEqual(result.action, "memory_store")
        self.assertIn("memory_text", result.data)
        self.assertNotIn("guided", result.data)

    def test_zapamietaj_ze_with_content_still_extracts_polish_phrase(self) -> None:
        result = self.parser.parse("zapamietaj ze telefon jest na biurku")

        self.assertEqual(result.action, "memory_store")
        self.assertEqual(result.data.get("memory_text"), "telefon jest na biurku")
        self.assertNotIn("guided", result.data)


if __name__ == "__main__":
    unittest.main()
