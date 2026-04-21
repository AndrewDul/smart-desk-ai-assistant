from __future__ import annotations

import unittest

from modules.presentation.wake_ack import WakeAcknowledgementService
from tests.support.fakes import FakeVoiceOutput


class WakeAcknowledgementServiceTests(unittest.TestCase):
    def test_prefetch_boot_inventory_warms_all_languages(self) -> None:
        voice_output = FakeVoiceOutput()
        service = WakeAcknowledgementService(
            voice_output=voice_output,
            phrase_builder=lambda: "I'm listening.",
            phrase_inventory=("Yes?", "I'm listening."),
            prefetch_on_boot=True,
        )

        prefetched = service.prefetch_boot_inventory(languages=("en", "pl"))

        self.assertEqual(
            voice_output.prepare_calls,
            [
                ("Yes?", "en"),
                ("I'm listening.", "en"),
                ("Yes?", "pl"),
                ("I'm listening.", "pl"),
            ],
        )
        self.assertEqual(
            prefetched,
            (
                "en:Yes?",
                "en:I'm listening.",
                "pl:Yes?",
                "pl:I'm listening.",
            ),
        )

    def test_speak_uses_phrase_builder_and_language(self) -> None:
        voice_output = FakeVoiceOutput()
        service = WakeAcknowledgementService(
            voice_output=voice_output,
            phrase_builder=lambda: "I'm here.",
            phrase_inventory=("Yes?", "I'm listening.", "I'm here."),
        )

        result = service.speak(language="en")

        self.assertTrue(result.spoken)
        self.assertEqual(result.text, "I'm here.")
        self.assertEqual(result.language, "en")
        self.assertEqual(result.strategy, "fast")
        self.assertAlmostEqual(result.output_hold_seconds or 0.0, 0.04)
        self.assertEqual(result.word_count, 2)
        self.assertEqual(
            voice_output.speak_calls,
            [
                {
                    "text": "I'm here.",
                    "language": "en",
                    "prepare_next": None,
                    "output_hold_seconds": 0.04,
                    "latency_profile": None,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()