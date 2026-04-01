from __future__ import annotations

import unittest

from modules.intent_parser import IntentParser


class TestIntentParser(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = IntentParser()

    def test_help_in_english(self) -> None:
        result = self.parser.parse("How can you help me")
        self.assertEqual(result.action, "help")

    def test_help_in_polish(self) -> None:
        result = self.parser.parse("Jak możesz mi pomóc")
        self.assertEqual(result.action, "help")

    def test_introduce_yourself(self) -> None:
        result = self.parser.parse("Introduce yourself")
        self.assertEqual(result.action, "introduce_self")

    def test_ask_time(self) -> None:
        result = self.parser.parse("What time is it")
        self.assertEqual(result.action, "ask_time")

    def test_show_time(self) -> None:
        result = self.parser.parse("Pokaż godzinę")
        self.assertEqual(result.action, "show_time")

    def test_ask_date(self) -> None:
        result = self.parser.parse("Jaka jest data")
        self.assertEqual(result.action, "ask_date")

    def test_ask_day(self) -> None:
        result = self.parser.parse("What day is today")
        self.assertEqual(result.action, "ask_day")

    def test_ask_year(self) -> None:
        result = self.parser.parse("Jaki jest rok")
        self.assertEqual(result.action, "ask_year")

    def test_store_memory_polish_relation(self) -> None:
        result = self.parser.parse("Zapamiętaj że klucze są w kuchni")
        self.assertEqual(result.action, "memory_store")
        self.assertEqual(result.data["key"], "klucze")
        self.assertEqual(result.data["value"], "w kuchni")

    def test_store_memory_english_relation(self) -> None:
        result = self.parser.parse("Remember that my phone number is 123456")
        self.assertEqual(result.action, "memory_store")
        self.assertEqual(result.data["key"], "phone number")
        self.assertEqual(result.data["value"], "123456")

    def test_store_memory_generic_sentence(self) -> None:
        result = self.parser.parse("Remember that I parked on level 3")
        self.assertEqual(result.action, "memory_store")
        self.assertIn("memory_text", result.data)
        self.assertTrue(result.data["memory_text"])

    def test_recall_memory_where_are_keys(self) -> None:
        result = self.parser.parse("Where are my keys")
        self.assertEqual(result.action, "memory_recall")
        self.assertEqual(result.data["key"], "keys")

    def test_recall_memory_polish_where(self) -> None:
        result = self.parser.parse("Gdzie są moje klucze")
        self.assertEqual(result.action, "memory_recall")
        self.assertEqual(result.data["key"], "klucze")

    def test_reminder_in_polish(self) -> None:
        result = self.parser.parse("Przypomnij mi o zakupach za 2 minuty")
        self.assertEqual(result.action, "reminder_create")
        self.assertEqual(result.data["seconds"], 120)
        self.assertEqual(result.data["message"], "zakupach")

    def test_reminder_in_english(self) -> None:
        result = self.parser.parse("Remind me in 30 seconds to drink water")
        self.assertEqual(result.action, "reminder_create")
        self.assertEqual(result.data["seconds"], 30)
        self.assertEqual(result.data["message"], "drink water")

    def test_timer_start_with_minutes(self) -> None:
        result = self.parser.parse("Set timer for 10 minutes")
        self.assertEqual(result.action, "timer_start")
        self.assertEqual(result.data["minutes"], 10)

    def test_timer_start_with_seconds(self) -> None:
        result = self.parser.parse("Ustaw timer na 30 sekund")
        self.assertEqual(result.action, "timer_start")
        self.assertAlmostEqual(result.data["minutes"], 0.5)

    def test_focus_start_without_duration(self) -> None:
        result = self.parser.parse("Focus mode")
        self.assertEqual(result.action, "focus_start")
        self.assertEqual(result.data, {})

    def test_focus_start_with_duration(self) -> None:
        result = self.parser.parse("Focus 25 minutes")
        self.assertEqual(result.action, "focus_start")
        self.assertEqual(result.data["minutes"], 25)

    def test_break_start_with_duration(self) -> None:
        result = self.parser.parse("Przerwa 5 minut")
        self.assertEqual(result.action, "break_start")
        self.assertEqual(result.data["minutes"], 5)

    def test_focus_stop_variants(self) -> None:
        examples = [
            "focus off",
            "wyłącz focus",
            "koniec pracy",
            "nie uczę się teraz",
        ]

        for text in examples:
            with self.subTest(text=text):
                result = self.parser.parse(text)
                self.assertEqual(result.action, "timer_stop")

    def test_yes_confirmation(self) -> None:
        result = self.parser.parse("tak")
        self.assertEqual(result.action, "confirm_yes")

    def test_no_confirmation(self) -> None:
        result = self.parser.parse("no")
        self.assertEqual(result.action, "confirm_no")

    def test_fuzzy_match_returns_unclear(self) -> None:
        result = self.parser.parse("statu")
        self.assertEqual(result.action, "unclear")
        self.assertTrue(result.needs_confirmation)
        self.assertTrue(len(result.suggestions) >= 1)

    def test_blank_text_returns_unknown(self) -> None:
        result = self.parser.parse("   ")
        self.assertEqual(result.action, "unknown")
        self.assertEqual(result.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()