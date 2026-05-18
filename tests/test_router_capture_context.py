from __future__ import annotations

import unittest

from modules.runtime.contracts import RouteKind
from modules.understanding.parsing.models import IntentResult
from modules.understanding.routing.companion_router import SemanticCompanionRouter


class _FakeParser:
    def __init__(self, result: IntentResult) -> None:
        self._result = result

    def parse(self, text: str) -> IntentResult:
        return self._result


class RouterCaptureContextTests(unittest.TestCase):
    def test_follow_up_context_biases_unclear_into_conversation(self) -> None:
        router = SemanticCompanionRouter(
            _FakeParser(
                IntentResult.unclear(
                    normalized_text="and tomorrow",
                    confidence=0.22,
                )
            )
        )

        route = router.route(
            "and tomorrow",
            preferred_language="en",
            context={
                "input_source": "voice",
                "capture_phase": "follow_up",
                "capture_mode": "follow_up",
                "capture_backend": "faster_whisper",
            },
        )

        self.assertEqual(route.kind, RouteKind.CONVERSATION)
        self.assertEqual(route.primary_intent, "follow_up_conversation")
        self.assertIn("follow_up_context_bias", route.notes)
        self.assertEqual(route.metadata["capture_phase"], "follow_up")
        self.assertEqual(route.metadata["capture_backend"], "faster_whisper")

    def test_inline_command_after_wake_preserves_context_for_explicit_action(self) -> None:
        router = SemanticCompanionRouter(
            _FakeParser(
                IntentResult.from_action(
                    action="time_query",
                    normalized_text="what time is it",
                    confidence=0.91,
                )
            )
        )

        route = router.route(
            "what time is it",
            preferred_language="en",
            context={
                "input_source": "voice",
                "capture_phase": "inline_command_after_wake",
                "capture_mode": "inline_command_after_wake",
                "capture_backend": "wake_inline_command",
            },
        )

        self.assertEqual(route.kind, RouteKind.ACTION)
        self.assertGreaterEqual(route.confidence, 0.92)
        self.assertEqual(route.metadata["capture_phase"], "inline_command_after_wake")
        self.assertEqual(route.metadata["capture_backend"], "wake_inline_command")
        self.assertIn("capture_phase:inline_command_after_wake", route.notes)

    def test_polish_black_hole_questions_route_to_dialogue(self) -> None:
        router = SemanticCompanionRouter(
            _FakeParser(
                IntentResult.unclear(
                    normalized_text="",
                    confidence=0.24,
                )
            )
        )

        phrases = [
            "co to są czarne dziury",
            "czym są czarne dziury",
            "powiedz mi czym są czarne dziury",
            "opowiedz krótko czym są czarne dziury",
            "wyjaśnij prostymi słowami czym są czarne dziury",
        ]

        for phrase in phrases:
            with self.subTest(phrase=phrase):
                route = router.route(phrase)

                self.assertEqual(route.kind, RouteKind.CONVERSATION)
                self.assertEqual(route.language, "pl")
                self.assertEqual(route.primary_intent, "knowledge_query")
                self.assertEqual(route.conversation_topics, ["knowledge_query"])

    def test_clear_english_query_overrides_previous_polish_language_hint(self) -> None:
        router = SemanticCompanionRouter(
            _FakeParser(
                IntentResult.unclear(
                    normalized_text="",
                    confidence=0.24,
                )
            )
        )

        phrases = [
            "Tell me about black holes",
            "Explain black holes",
            "What are black holes",
        ]

        for phrase in phrases:
            with self.subTest(phrase=phrase):
                route = router.route(phrase, preferred_language="pl")

                self.assertEqual(route.kind, RouteKind.CONVERSATION)
                self.assertEqual(route.language, "en")
                self.assertEqual(route.primary_intent, "knowledge_query")

    def test_clear_polish_query_overrides_previous_english_language_hint(self) -> None:
        router = SemanticCompanionRouter(
            _FakeParser(
                IntentResult.unclear(
                    normalized_text="",
                    confidence=0.24,
                )
            )
        )

        route = router.route("Co to są czarne dziury", preferred_language="en")

        self.assertEqual(route.kind, RouteKind.CONVERSATION)
        self.assertEqual(route.language, "pl")
        self.assertEqual(route.primary_intent, "knowledge_query")

    def test_incomplete_tell_me_about_routes_to_unclear_clarification(self) -> None:
        router = SemanticCompanionRouter(
            _FakeParser(
                IntentResult.unclear(
                    normalized_text="tell me about...",
                    confidence=0.24,
                )
            )
        )

        route = router.route("Tell me about...")

        self.assertEqual(route.kind, RouteKind.UNCLEAR)
        self.assertEqual(route.primary_intent, "incomplete_dialogue_query")
        self.assertTrue(route.metadata["incomplete_dialogue_query"])
        self.assertIn("incomplete_dialogue_query", route.notes)

    def test_polish_artificial_intelligence_asr_variants_normalize_to_dialogue(self) -> None:
        router = SemanticCompanionRouter(
            _FakeParser(
                IntentResult.unclear(
                    normalized_text="",
                    confidence=0.24,
                )
            )
        )

        phrases = [
            "Powiedz mi coś o stucznej",
            "Powiedz mi coś oczcznej",
            "Opowiedz mi coś o stucznej",
            "Powiedz mi coś o szczucznej",
            "Powiedz mi coś o sztucznej.",
        ]

        for phrase in phrases:
            with self.subTest(phrase=phrase):
                route = router.route(phrase)

                self.assertEqual(route.kind, RouteKind.CONVERSATION)
                self.assertEqual(route.language, "pl")
                self.assertEqual(route.primary_intent, "knowledge_query")
                self.assertIn("coś o sztucznej inteligencji", route.normalized_text)

    def test_polish_black_hole_asr_variants_are_normalized_to_dialogue(self) -> None:
        router = SemanticCompanionRouter(
            _FakeParser(
                IntentResult.unclear(
                    normalized_text="",
                    confidence=0.24,
                )
            )
        )

        cases = {
            "Soto są czarne dziur": "co to są czarne dziury",
            "Co to są czarny dziury": "co to są czarne dziury",
            "Obec mi oczarnych cura": "opowiedz mi o czarnych dziurach",
            "Obec mi o czarnych cura": "opowiedz mi o czarnych dziurach",
            "Opowiedz mi oczarnych cura": "opowiedz mi o czarnych dziurach",
            "Powiedz mi oczarnych cura": "opowiedz mi o czarnych dziurach",
        }

        for phrase, expected_normalized in cases.items():
            with self.subTest(phrase=phrase):
                route = router.route(phrase)

                self.assertEqual(route.kind, RouteKind.CONVERSATION)
                self.assertEqual(route.language, "pl")
                self.assertEqual(route.primary_intent, "knowledge_query")
                self.assertEqual(route.normalized_text, expected_normalized)


if __name__ == "__main__":
    unittest.main()
