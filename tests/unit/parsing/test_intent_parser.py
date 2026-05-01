from __future__ import annotations

import unittest

from modules.understanding.parsing.parser import IntentParser

class TestIntentParser(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = IntentParser(default_focus_minutes=25, default_break_minutes=5)

    def test_help_in_english(self) -> None:
        result = self.parser.parse("How can you help me")
        self.assertEqual(result.action, "help")

    def test_help_in_polish(self) -> None:
        result = self.parser.parse("Jak możesz mi pomóc")
        self.assertEqual(result.action, "help")

    def test_introduce_self_whats_your_name(self) -> None:
        result = self.parser.parse("What's your name")
        self.assertEqual(result.action, "introduce_self")

    def test_introduce_self_who_are_you(self) -> None:
        result = self.parser.parse("Who are you")
        self.assertEqual(result.action, "introduce_self")

    def test_introduce_self_polish(self) -> None:
        result = self.parser.parse("Jak się nazywasz")
        self.assertEqual(result.action, "introduce_self")

    def test_ask_time(self) -> None:
        result = self.parser.parse("What time is it")
        self.assertEqual(result.action, "ask_time")

    def test_show_time_polish(self) -> None:
        result = self.parser.parse("Pokaż godzinę")
        self.assertEqual(result.action, "show_time")

    def test_ask_date_polish(self) -> None:
        result = self.parser.parse("Jaka jest data")
        self.assertEqual(result.action, "ask_date")

    def test_show_day_english(self) -> None:
        result = self.parser.parse("Show day")
        self.assertEqual(result.action, "show_day")

    def test_ask_year_polish(self) -> None:
        result = self.parser.parse("Który mamy rok")
        self.assertEqual(result.action, "ask_year")

    def test_timer_with_digits_in_english(self) -> None:
        result = self.parser.parse("Set timer for 10 minutes")
        self.assertEqual(result.action, "timer_start")
        self.assertEqual(result.data["minutes"], 10.0)

    def test_timer_with_spoken_number_in_english(self) -> None:
        result = self.parser.parse("Set timer for ten minutes")
        self.assertEqual(result.action, "timer_start")
        self.assertEqual(result.data["minutes"], 10.0)

    def test_timer_with_spoken_number_in_polish(self) -> None:
        result = self.parser.parse("Ustaw timer na dziesięć minut")
        self.assertEqual(result.action, "timer_start")
        self.assertEqual(result.data["minutes"], 10.0)

    def test_timer_with_seconds(self) -> None:
        result = self.parser.parse("Set timer for 30 seconds")
        self.assertEqual(result.action, "timer_start")
        self.assertEqual(result.data["minutes"], 0.5)

    def test_focus_without_duration(self) -> None:
        result = self.parser.parse("Focus mode")
        self.assertEqual(result.action, "focus_start")
        self.assertEqual(result.data, {})

    def test_focus_with_spoken_duration(self) -> None:
        result = self.parser.parse("Focus mode twenty five minutes")
        self.assertEqual(result.action, "focus_start")
        self.assertEqual(result.data["minutes"], 25.0)

    def test_break_with_spoken_duration_polish(self) -> None:
        result = self.parser.parse("Przerwa dziesięć minut")
        self.assertEqual(result.action, "break_start")
        self.assertEqual(result.data["minutes"], 10.0)

    def test_focus_offer_from_study_phrase_polish(self) -> None:
        result = self.parser.parse("Chcę się pouczyć")
        self.assertEqual(result.action, "focus_offer")

    def test_break_natural_rest_phrase_polish(self) -> None:
        result = self.parser.parse("Czas na przerwę")
        self.assertEqual(result.action, "break_start")
        self.assertEqual(result.data, {})

    def test_reminder_english_message_then_time(self) -> None:
        result = self.parser.parse("Remind me to drink water in 5 minutes")
        self.assertEqual(result.action, "reminder_create")
        self.assertEqual(result.data["seconds"], 300)
        self.assertEqual(result.data["message"], "drink water")

    def test_reminder_english_time_then_message(self) -> None:
        result = self.parser.parse("Remind me in 30 seconds to stand up")
        self.assertEqual(result.action, "reminder_create")
        self.assertEqual(result.data["seconds"], 30)
        self.assertEqual(result.data["message"], "stand up")

    def test_reminder_polish_message_then_time(self) -> None:
        result = self.parser.parse("Przypomnij mi o zakupach za 2 minuty")
        self.assertEqual(result.action, "reminder_create")
        self.assertEqual(result.data["seconds"], 120)
        self.assertEqual(result.data["message"], "zakupach")

    def test_reminder_polish_time_then_message(self) -> None:
        result = self.parser.parse("Przypomnij mi za 10 sekund rozciąganie")
        self.assertEqual(result.action, "reminder_create")
        self.assertEqual(result.data["seconds"], 10)
        self.assertEqual(result.data["message"], "rozciaganie")

    def test_delete_reminder_by_message_english(self) -> None:
        result = self.parser.parse("Delete reminder drink water")
        self.assertEqual(result.action, "reminder_delete")
        self.assertEqual(result.data["message"], "drink water")

    def test_delete_reminder_by_message_polish(self) -> None:
        result = self.parser.parse("Usuń przypomnienie o zakupach")
        self.assertEqual(result.action, "reminder_delete")
        self.assertEqual(result.data["message"], "zakupach")

    def test_delete_reminder_by_id(self) -> None:
        result = self.parser.parse("Delete reminder id ab12cd34")
        self.assertEqual(result.action, "reminder_delete")
        self.assertEqual(result.data["id"], "ab12cd34")

    def test_clear_reminders_english(self) -> None:
        result = self.parser.parse("Clear reminders")
        self.assertEqual(result.action, "reminders_clear")

    def test_clear_reminders_polish(self) -> None:
        result = self.parser.parse("Wyczyść przypomnienia")
        self.assertEqual(result.action, "reminders_clear")

    def test_memory_store_english(self) -> None:
        result = self.parser.parse("Remember that keys are in the drawer")
        self.assertEqual(result.action, "memory_store")
        self.assertEqual(result.data["key"], "keys")
        self.assertEqual(result.data["value"], "in the drawer")

    def test_memory_store_polish(self) -> None:
        result = self.parser.parse("Zapamiętaj że klucze są w szufladzie")
        self.assertEqual(result.action, "memory_store")
        self.assertEqual(result.data["key"], "klucze")
        self.assertEqual(result.data["value"], "w szufladzie")

    def test_memory_recall_english(self) -> None:
        result = self.parser.parse("Where are my keys")
        self.assertEqual(result.action, "memory_recall")
        self.assertEqual(result.data["key"], "keys")

    def test_memory_recall_polish(self) -> None:
        result = self.parser.parse("Gdzie są moje klucze")
        self.assertEqual(result.action, "memory_recall")
        self.assertEqual(result.data["key"], "klucze")

    def test_memory_forget_english(self) -> None:
        result = self.parser.parse("Forget keys")
        self.assertEqual(result.action, "memory_forget")
        self.assertEqual(result.data["key"], "keys")

    def test_memory_forget_polish(self) -> None:
        result = self.parser.parse("Zapomnij o kluczach")
        self.assertEqual(result.action, "memory_forget")
        self.assertEqual(result.data["key"], "kluczach")

    def test_memory_clear_english(self) -> None:
        result = self.parser.parse("Clear memory")
        self.assertEqual(result.action, "memory_clear")

    def test_memory_clear_polish(self) -> None:
        result = self.parser.parse("Wyczyść pamięć")
        self.assertEqual(result.action, "memory_clear")

    def test_confirm_yes_english(self) -> None:
        result = self.parser.parse("yes")
        self.assertEqual(result.action, "confirm_yes")

    def test_confirm_yes_polish(self) -> None:
        result = self.parser.parse("tak")
        self.assertEqual(result.action, "confirm_yes")

    def test_confirm_no_english(self) -> None:
        result = self.parser.parse("no")
        self.assertEqual(result.action, "confirm_no")

    def test_confirm_no_polish(self) -> None:
        result = self.parser.parse("nie")
        self.assertEqual(result.action, "confirm_no")

    def test_exit_goodbye(self) -> None:
        result = self.parser.parse("goodbye")
        self.assertEqual(result.action, "exit")

    def test_exit_go_to_sleep(self) -> None:
        result = self.parser.parse("go to sleep")
        self.assertEqual(result.action, "exit")

    def test_exit_turn_off_assistant(self) -> None:
        result = self.parser.parse("turn off assistant")
        self.assertEqual(result.action, "exit")

    def test_exit_polish(self) -> None:
        result = self.parser.parse("wyłącz asystenta")
        self.assertEqual(result.action, "exit")

    def test_exit_polish_idz_spac(self) -> None:
        result = self.parser.parse("idź spać")
        self.assertEqual(result.action, "exit")

    def test_exit_polish_odpocznij(self) -> None:
        result = self.parser.parse("odpocznij")
        self.assertEqual(result.action, "exit")

    def test_shutdown_english(self) -> None:
        result = self.parser.parse("shutdown")
        self.assertEqual(result.action, "shutdown")

    def test_shutdown_polish(self) -> None:
        result = self.parser.parse("Wyłącz system")
        self.assertEqual(result.action, "shutdown")

    def test_unclear_with_suggestion(self) -> None:
        result = self.parser.parse("statu")
        self.assertEqual(result.action, "unclear")
        self.assertTrue(result.needs_confirmation)
        self.assertTrue(result.suggestions)
        self.assertEqual(result.suggestions[0]["action"], "status")

    def test_find_action_in_text_with_allowed_actions(self) -> None:
        action = self.parser.find_action_in_text("statu", allowed_actions=["status", "help"])
        self.assertEqual(action, "status")

    def test_find_action_in_text_returns_none_when_not_allowed(self) -> None:
        action = self.parser.find_action_in_text("statu", allowed_actions=["help"])
        self.assertIsNone(action)

    def test_unknown_phrase(self) -> None:
        result = self.parser.parse("purple banana spaceship")
        self.assertIn(result.action, {"unknown", "unclear"})

    def test_normalized_text_is_present(self) -> None:
        result = self.parser.parse("   What   time is it?   ")
        self.assertEqual(result.normalized_text, "what time is it")


if __name__ == "__main__":
    unittest.main()