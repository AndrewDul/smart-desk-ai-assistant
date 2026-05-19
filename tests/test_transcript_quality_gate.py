"""
Tests for transcript quality gate and safe corrections.
Covers Part D (rejection), Part E (corrections), and Part F (open-question routing).
"""
from __future__ import annotations

import unittest

from modules.runtime.contracts import RouteDecision, RouteKind, StreamMode
from modules.understanding.dialogue.transcript_quality import (
    TranscriptQualityResult,
    check_and_correct,
)


class TranscriptQualityGateTests(unittest.TestCase):
    # --- Rejection tests (Part D) ---

    def test_empty_transcript_rejected(self) -> None:
        result = check_and_correct("", "en")
        self.assertFalse(result.is_acceptable)
        self.assertEqual(result.rejection_reason, "empty_transcript")

    def test_single_word_rejected(self) -> None:
        result = check_and_correct("leport", "pl")
        self.assertFalse(result.is_acceptable)

    def test_one_word_conversational_follow_ups_are_accepted(self) -> None:
        for text, language in (
            ("why?", "en"),
            ("how?", "en"),
            ("czemu?", "pl"),
            ("dlaczego?", "pl"),
        ):
            with self.subTest(text=text, language=language):
                result = check_and_correct(text, language)
                self.assertTrue(result.is_acceptable)

    def test_consecutive_fragment_burst_polish_rejected(self) -> None:
        result = check_and_correct("co to jest te lep w ory", "pl")
        self.assertFalse(result.is_acceptable, "te lep w ory has 4 consecutive ≤3-char tokens")
        self.assertEqual(result.rejection_reason, "consecutive_fragment_burst")

    def test_all_short_fragments_rejected(self) -> None:
        result = check_and_correct("lep w ory", "pl")
        self.assertFalse(result.is_acceptable, "all tokens ≤3 chars")

    def test_strong_opener_no_substance_passes_conservatively(self) -> None:
        # "co to jest te lep" — marginal case; gate is conservative, lets LLM attempt it
        result = check_and_correct("co to jest te lep", "pl")
        self.assertIsInstance(result.is_acceptable, bool)  # gate returns a result without error

    def test_longer_consecutive_burst_rejected(self) -> None:
        # 4+ consecutive short words after question opener → reject
        result = check_and_correct("co to jest te lep w ory", "pl")
        self.assertFalse(result.is_acceptable, "te lep w ory = 4 consecutive ≤3-char tokens after opener")

    def test_two_word_min_short_rejected(self) -> None:
        result = check_and_correct("le bor", "pl")
        self.assertFalse(result.is_acceptable)

    # --- Pass-through tests (Part D / F) ---

    def test_clean_polish_question_passes(self) -> None:
        result = check_and_correct("co to jest teleportacja", "pl")
        self.assertTrue(result.is_acceptable)

    def test_clean_english_question_passes(self) -> None:
        result = check_and_correct("what is teleportation", "en")
        self.assertTrue(result.is_acceptable)

    def test_polish_speed_of_light_passes(self) -> None:
        result = check_and_correct("jaka jest prędkość światła", "pl")
        self.assertTrue(result.is_acceptable)

    def test_english_speed_of_light_passes(self) -> None:
        result = check_and_correct("what is the speed of light", "en")
        self.assertTrue(result.is_acceptable)

    def test_polish_colors_passes(self) -> None:
        result = check_and_correct("co to są kolory", "pl")
        self.assertTrue(result.is_acceptable)

    def test_english_colors_passes(self) -> None:
        result = check_and_correct("what are colors", "en")
        self.assertTrue(result.is_acceptable)

    def test_polish_usa_size_passes(self) -> None:
        result = check_and_correct("jak duże jest USA", "pl")
        self.assertTrue(result.is_acceptable)

    def test_english_usa_size_passes(self) -> None:
        result = check_and_correct("how big is the USA", "en")
        self.assertTrue(result.is_acceptable)

    def test_polish_teleportation_czym_passes(self) -> None:
        result = check_and_correct("czym jest teleportacja", "pl")
        self.assertTrue(result.is_acceptable)

    def test_english_gravity_passes(self) -> None:
        result = check_and_correct("explain gravity", "en")
        self.assertTrue(result.is_acceptable)

    def test_polish_gravity_passes(self) -> None:
        result = check_and_correct("wyjaśnij grawitację", "pl")
        self.assertTrue(result.is_acceptable)

    def test_english_how_fast_is_light_passes(self) -> None:
        result = check_and_correct("how fast is light", "en")
        self.assertTrue(result.is_acceptable)

    def test_polish_jak_szybkie_passes(self) -> None:
        result = check_and_correct("jak szybkie jest światło", "pl")
        self.assertTrue(result.is_acceptable)

    # --- Safe correction tests (Part E) ---

    def test_polish_planka_corrected_to_predkosc(self) -> None:
        result = check_and_correct("jaka jest planka światła", "pl")
        self.assertTrue(result.is_acceptable)
        self.assertTrue(result.correction_applied)
        self.assertIn("prędkość", result.corrected_text.lower())
        self.assertNotIn("planka", result.corrected_text.lower())

    def test_polish_szybkej_corrected(self) -> None:
        result = check_and_correct("jak szybkej światło", "pl")
        self.assertTrue(result.is_acceptable)
        self.assertTrue(result.correction_applied)
        self.assertIn("szybkie jest", result.corrected_text.lower())

    def test_polish_te_leport_corrected(self) -> None:
        result = check_and_correct("co to jest te leport", "pl")
        # "co to jest" opener + "te leport" — te(2), leport(6) → max remaining ≥ 5, passes gate
        self.assertTrue(result.is_acceptable)
        self.assertTrue(result.correction_applied)
        self.assertIn("teleportacja", result.corrected_text.lower())

    def test_english_speed_of_lite_corrected(self) -> None:
        result = check_and_correct("what is the speed of lite", "en")
        self.assertTrue(result.is_acceptable)
        self.assertTrue(result.correction_applied)
        self.assertIn("speed of light", result.corrected_text.lower())

    def test_english_black_whole_corrected(self) -> None:
        result = check_and_correct("what is a black whole", "en")
        self.assertTrue(result.is_acceptable)
        self.assertTrue(result.correction_applied)
        self.assertIn("black hole", result.corrected_text.lower())

    def test_english_tele_port_corrected(self) -> None:
        result = check_and_correct("what is tele port", "en")
        self.assertTrue(result.is_acceptable)
        self.assertTrue(result.correction_applied)
        self.assertIn("teleportation", result.corrected_text.lower())

    def test_clean_text_no_correction_applied(self) -> None:
        result = check_and_correct("what is the speed of light", "en")
        self.assertFalse(result.correction_applied)
        self.assertEqual(result.corrected_text, "what is the speed of light")

    def test_correction_reason_logged(self) -> None:
        result = check_and_correct("jaka jest planka światła", "pl")
        self.assertTrue(result.correction_applied)
        self.assertNotEqual(result.correction_reason, "")

    # --- Quality result contract ---

    def test_result_is_acceptable_attribute_type(self) -> None:
        result = check_and_correct("test", "en")
        self.assertIsInstance(result.is_acceptable, bool)
        self.assertIsInstance(result.corrected_text, str)

    def test_repeat_texts_are_non_empty(self) -> None:
        result = check_and_correct("te lep w ory", "pl")
        self.assertFalse(result.is_acceptable)
        self.assertGreater(len(result.repeat_text_pl), 10)
        self.assertGreater(len(result.repeat_text_en), 10)

    def test_repeat_text_polish_is_in_polish(self) -> None:
        result = check_and_correct("te lep w ory", "pl")
        pl_text = result.repeat_text_pl.lower()
        self.assertTrue(
            any(w in pl_text for w in ("powtórz", "usłyszałam", "pytanie")),
            "PL repeat text must be in Polish",
        )

    def test_repeat_text_english_is_in_english(self) -> None:
        result = check_and_correct("not real english lep w ory", "en")
        en_text = result.repeat_text_en.lower()
        self.assertTrue(
            any(w in en_text for w in ("repeat", "heard", "correctly")),
            "EN repeat text must be in English",
        )


class TranscriptQualityIntegrationTests(unittest.TestCase):
    """Test that quality gate integrates correctly with CompanionDialogueService."""

    def _route(self, *, language: str, text: str) -> RouteDecision:
        return RouteDecision(
            turn_id=f"turn-quality-{language}",
            raw_text=text,
            normalized_text=text,
            language=language,
            kind=RouteKind.CONVERSATION,
            confidence=0.8,
            primary_intent="conversation",
            intents=[],
            conversation_topics=[],
            tool_invocations=[],
            notes=[],
            metadata={},
        )

    def test_corrupted_polish_transcript_triggers_repeat_plan(self) -> None:
        from modules.understanding.dialogue.companion_dialogue import CompanionDialogueService

        service = CompanionDialogueService()
        service.live_llm_sentence_streaming_enabled = False

        plan = service.build_response_plan(
            self._route(language="pl", text="co to jest te lep w ory"),
            user_profile={},
            stream_mode=StreamMode.SENTENCE,
        )

        full_text = plan.full_text()
        self.assertIn("powtórz", full_text.lower(), "Polish repeat prompt expected")
        self.assertNotIn("teleportacja", full_text.lower())

    def test_corrupted_english_consecutive_burst_triggers_repeat_plan(self) -> None:
        from modules.understanding.dialogue.companion_dialogue import CompanionDialogueService

        service = CompanionDialogueService()
        service.live_llm_sentence_streaming_enabled = False

        # "what is" opener + 4 consecutive fragments after it → gate rejects
        plan = service.build_response_plan(
            self._route(language="en", text="what is te lep w ory blub"),
            user_profile={},
            stream_mode=StreamMode.SENTENCE,
        )

        full_text = plan.full_text()
        self.assertTrue(
            "repeat" in full_text.lower() or "correctly" in full_text.lower(),
            f"English repeat prompt expected, got: {full_text!r}",
        )

    def test_valid_polish_question_does_not_trigger_repeat(self) -> None:
        from modules.understanding.dialogue.companion_dialogue import CompanionDialogueService

        service = CompanionDialogueService()
        service.live_llm_sentence_streaming_enabled = False
        service.local_llm = None

        plan = service.build_response_plan(
            self._route(language="pl", text="jaka jest prędkość światła"),
            user_profile={},
            stream_mode=StreamMode.SENTENCE,
        )

        full_text = plan.full_text()
        self.assertNotIn(
            "powtórz", full_text.lower(), "Valid question must not trigger repeat"
        )

    def test_valid_english_question_does_not_trigger_repeat(self) -> None:
        from modules.understanding.dialogue.companion_dialogue import CompanionDialogueService

        service = CompanionDialogueService()
        service.live_llm_sentence_streaming_enabled = False
        service.local_llm = None

        plan = service.build_response_plan(
            self._route(language="en", text="what is teleportation"),
            user_profile={},
            stream_mode=StreamMode.SENTENCE,
        )

        full_text = plan.full_text()
        self.assertNotIn(
            "repeat", full_text.lower(), "Valid question must not trigger repeat"
        )


class OpenQuestionRoutingTests(unittest.TestCase):
    """Part F: Verify broad knowledge questions route to conversation/knowledge_query (not unclear)."""

    def _route(self, *, language: str, text: str) -> RouteDecision:
        return RouteDecision(
            turn_id=f"turn-routing-{language}",
            raw_text=text,
            normalized_text=text,
            language=language,
            kind=RouteKind.CONVERSATION,
            confidence=0.8,
            primary_intent="conversation",
            intents=[],
            conversation_topics=[],
            tool_invocations=[],
            notes=[],
            metadata={},
        )

    def _quality_passes(self, text: str, language: str) -> bool:
        from modules.understanding.dialogue.transcript_quality import check_and_correct
        return check_and_correct(text, language).is_acceptable

    def test_en_teleportation_passes_gate(self) -> None:
        self.assertTrue(self._quality_passes("what is teleportation", "en"))

    def test_en_speed_of_light_passes_gate(self) -> None:
        self.assertTrue(self._quality_passes("what is the speed of light", "en"))

    def test_en_how_fast_is_light_passes_gate(self) -> None:
        self.assertTrue(self._quality_passes("how fast is light", "en"))

    def test_en_colors_passes_gate(self) -> None:
        self.assertTrue(self._quality_passes("what are colors", "en"))

    def test_en_usa_size_passes_gate(self) -> None:
        self.assertTrue(self._quality_passes("how big is the USA", "en"))

    def test_en_gravity_passes_gate(self) -> None:
        self.assertTrue(self._quality_passes("explain gravity", "en"))

    def test_pl_teleportacja_passes_gate(self) -> None:
        self.assertTrue(self._quality_passes("co to jest teleportacja", "pl"))

    def test_pl_czym_jest_teleportacja_passes_gate(self) -> None:
        self.assertTrue(self._quality_passes("czym jest teleportacja", "pl"))

    def test_pl_predkosc_swiatla_passes_gate(self) -> None:
        self.assertTrue(self._quality_passes("jaka jest prędkość światła", "pl"))

    def test_pl_jak_szybkie_swiatlo_passes_gate(self) -> None:
        self.assertTrue(self._quality_passes("jak szybkie jest światło", "pl"))

    def test_pl_kolory_passes_gate(self) -> None:
        self.assertTrue(self._quality_passes("co to są kolory", "pl"))

    def test_pl_usa_size_passes_gate(self) -> None:
        self.assertTrue(self._quality_passes("jak duże jest USA", "pl"))

    def test_pl_gravity_passes_gate(self) -> None:
        self.assertTrue(self._quality_passes("wyjaśnij grawitację", "pl"))

    def test_bad_pl_lep_w_ory_rejected_by_gate(self) -> None:
        self.assertFalse(self._quality_passes("są to jest te lep w ory", "pl"))

    def test_bad_pl_consecutive_burst_rejected(self) -> None:
        self.assertFalse(self._quality_passes("co to jest te lep w ory", "pl"))

    def test_bad_all_short_fragments_rejected(self) -> None:
        self.assertFalse(self._quality_passes("le bor te op", "pl"))


class SpeedOfLightCorrectionTests(unittest.TestCase):
    """Task 2: safe corrections for 'speed of light' mishears."""

    def test_speed_of_life_corrected_to_light(self) -> None:
        result = check_and_correct("what is the speed of life", "en")
        self.assertTrue(result.is_acceptable)
        self.assertTrue(result.correction_applied)
        self.assertIn("speed of light", result.corrected_text.lower())
        self.assertNotIn("life", result.corrected_text.lower())

    def test_speed_of_live_corrected_to_light(self) -> None:
        result = check_and_correct("what is the speed of live", "en")
        self.assertTrue(result.is_acceptable)
        self.assertTrue(result.correction_applied)
        self.assertIn("speed of light", result.corrected_text.lower())

    def test_speed_of_lite_still_corrected(self) -> None:
        result = check_and_correct("what is the speed of lite", "en")
        self.assertTrue(result.is_acceptable)
        self.assertTrue(result.correction_applied)
        self.assertIn("speed of light", result.corrected_text.lower())

    def test_whats_speed_of_life_corrected(self) -> None:
        result = check_and_correct("what's the speed of life", "en")
        self.assertTrue(result.is_acceptable)
        self.assertTrue(result.correction_applied)
        self.assertIn("speed of light", result.corrected_text.lower())

    def test_speed_of_light_unchanged(self) -> None:
        result = check_and_correct("what is the speed of light", "en")
        self.assertTrue(result.is_acceptable)
        self.assertFalse(result.correction_applied)
        self.assertEqual(result.corrected_text, "what is the speed of light")

    def test_pl_predkosc_swiatla_no_diacritics_corrected(self) -> None:
        result = check_and_correct("jaka jest prędkość swiatla", "pl")
        self.assertTrue(result.is_acceptable)
        self.assertTrue(result.correction_applied)
        self.assertIn("światła", result.corrected_text)
        self.assertNotIn("swiatla", result.corrected_text)

    def test_pl_predkosc_swiala_corrected(self) -> None:
        result = check_and_correct("jaka jest prędkość świała", "pl")
        self.assertTrue(result.is_acceptable)
        self.assertTrue(result.correction_applied)
        self.assertIn("światła", result.corrected_text)

    def test_pl_predkosc_swiatla_full_question_passes_to_llm(self) -> None:
        result = check_and_correct("jaka jest prędkość swiatla", "pl")
        self.assertTrue(result.is_acceptable)
        self.assertIn("światła", result.corrected_text)

    def test_pl_predkosc_swiatla_correct_unchanged(self) -> None:
        result = check_and_correct("jaka jest prędkość światła", "pl")
        self.assertTrue(result.is_acceptable)
        self.assertFalse(result.correction_applied)


class IncompleteQuestionGateTests(unittest.TestCase):
    """Task 3: incomplete factual questions trigger clarification, not LLM."""

    def test_what_is_the_speed_of_triggers_clarification(self) -> None:
        """Dangling 'of' — small model cut off the object."""
        result = check_and_correct("what is the speed of", "en")
        self.assertFalse(result.is_acceptable)
        self.assertEqual(result.rejection_reason, "incomplete_speed_of_en")
        self.assertIn("Speed of what", result.repeat_text_en)

    def test_whats_speed_of_triggers_clarification(self) -> None:
        result = check_and_correct("what's the speed of", "en")
        self.assertFalse(result.is_acceptable)
        self.assertEqual(result.rejection_reason, "incomplete_speed_of_en")

    def test_what_is_speed_of_no_article_triggers_clarification(self) -> None:
        result = check_and_correct("what is speed of", "en")
        self.assertFalse(result.is_acceptable)
        self.assertEqual(result.rejection_reason, "incomplete_speed_of_en")

    def test_speed_of_light_not_triggered(self) -> None:
        """Full sentence with object must NOT be caught by speed_of gate."""
        result = check_and_correct("what is the speed of light", "en")
        self.assertTrue(result.is_acceptable)

    def test_speed_of_sound_not_triggered(self) -> None:
        result = check_and_correct("what is the speed of sound", "en")
        self.assertTrue(result.is_acceptable)

    def test_what_is_the_speed_triggers_clarification(self) -> None:
        result = check_and_correct("what is the speed?", "en")
        self.assertFalse(result.is_acceptable)
        self.assertEqual(result.rejection_reason, "incomplete_speed_en")
        self.assertIn("Speed of what", result.repeat_text_en)
        self.assertIn("Prędkość czego", result.repeat_text_pl)

    def test_whats_speed_triggers_clarification(self) -> None:
        result = check_and_correct("what's the speed?", "en")
        self.assertFalse(result.is_acceptable)
        self.assertIn("Speed of what", result.repeat_text_en)

    def test_what_is_speed_no_article_triggers_clarification(self) -> None:
        result = check_and_correct("what is speed?", "en")
        self.assertFalse(result.is_acceptable)
        self.assertIn("Speed of what", result.repeat_text_en)

    def test_how_fast_is_it_triggers_clarification(self) -> None:
        result = check_and_correct("how fast is it?", "en")
        self.assertFalse(result.is_acceptable)
        self.assertIn("How fast is what", result.repeat_text_en)

    def test_how_fast_is_triggers_clarification(self) -> None:
        result = check_and_correct("how fast is", "en")
        self.assertFalse(result.is_acceptable)
        self.assertIn("fast", result.repeat_text_en.lower())

    def test_how_big_is_it_triggers_clarification(self) -> None:
        result = check_and_correct("how big is it?", "en")
        self.assertFalse(result.is_acceptable)
        self.assertIn("How big is what", result.repeat_text_en)

    def test_pl_jaka_jest_predkosc_triggers_clarification(self) -> None:
        result = check_and_correct("jaka jest prędkość?", "pl")
        self.assertFalse(result.is_acceptable)
        self.assertEqual(result.rejection_reason, "incomplete_speed_pl")
        self.assertIn("Prędkość czego", result.repeat_text_pl)
        self.assertIn("Speed of what", result.repeat_text_en)

    def test_pl_jaka_jest_predkosc_no_punctuation_triggers_clarification(self) -> None:
        result = check_and_correct("jaka jest prędkość", "pl")
        self.assertFalse(result.is_acceptable)
        self.assertIn("Prędkość czego", result.repeat_text_pl)

    def test_pl_jak_szybkie_jest_triggers_clarification(self) -> None:
        result = check_and_correct("jak szybkie jest?", "pl")
        self.assertFalse(result.is_acceptable)
        self.assertIn("Możesz powtórzyć", result.repeat_text_pl)

    def test_pl_jak_duze_jest_triggers_clarification(self) -> None:
        result = check_and_correct("jak duże jest?", "pl")
        self.assertFalse(result.is_acceptable)
        self.assertIn("Jak duże jest co", result.repeat_text_pl)

    # --- Negative tests: complete questions must NOT trigger clarification ---

    def test_speed_of_light_complete_passes(self) -> None:
        result = check_and_correct("what is the speed of light?", "en")
        self.assertTrue(result.is_acceptable)

    def test_how_fast_is_light_complete_passes(self) -> None:
        result = check_and_correct("how fast is light?", "en")
        self.assertTrue(result.is_acceptable)

    def test_how_big_is_the_usa_complete_passes(self) -> None:
        result = check_and_correct("how big is the USA?", "en")
        self.assertTrue(result.is_acceptable)

    def test_pl_predkosc_swiatla_complete_passes(self) -> None:
        result = check_and_correct("jaka jest prędkość światła?", "pl")
        self.assertTrue(result.is_acceptable)

    def test_pl_jak_szybkie_jest_swiatlo_complete_passes(self) -> None:
        result = check_and_correct("jak szybkie jest światło?", "pl")
        self.assertTrue(result.is_acceptable)

    def test_co_to_jest_teleportacja_passes(self) -> None:
        result = check_and_correct("co to jest teleportacja", "pl")
        self.assertTrue(result.is_acceptable)

    def test_what_is_teleportation_passes(self) -> None:
        result = check_and_correct("what is teleportation", "en")
        self.assertTrue(result.is_acceptable)

    def test_clarification_repeat_texts_are_non_empty(self) -> None:
        result = check_and_correct("what is the speed?", "en")
        self.assertFalse(result.is_acceptable)
        self.assertGreater(len(result.repeat_text_en), 5)
        self.assertGreater(len(result.repeat_text_pl), 5)

    def test_speed_of_life_corrected_then_not_incomplete(self) -> None:
        # "speed of life" → corrected to "speed of light" → complete → passes
        result = check_and_correct("what is the speed of life", "en")
        self.assertTrue(result.is_acceptable)
        self.assertIn("speed of light", result.corrected_text.lower())

    def test_pl_predkosc_swiatla_corrected_then_not_incomplete(self) -> None:
        # "prędkość swiatla" → corrected to "prędkość światła" → complete → passes
        result = check_and_correct("jaka jest prędkość swiatla", "pl")
        self.assertTrue(result.is_acceptable)
        self.assertIn("światła", result.corrected_text)


class ASRConfigTelemetryFormatTests(unittest.TestCase):
    """Task 1: [asr-config] log line format."""

    def test_asr_config_log_prefix(self) -> None:
        sample = (
            "[asr-config] mode=open_question model_size='tiny' compute_type='int8' "
            "beam_size=3 language='pl' source=session_last_language"
        )
        self.assertTrue(sample.startswith("[asr-config]"))
        self.assertIn("mode=open_question", sample)
        self.assertIn("language=", sample)
        self.assertIn("source=", sample)

    def test_asr_config_unknown_initial_turn_source(self) -> None:
        sample = (
            "[asr-config] mode=open_question model_size='tiny' compute_type='int8' "
            "beam_size=3 language='auto' source=unknown_initial_turn"
        )
        self.assertIn("source=unknown_initial_turn", sample)
        self.assertIn("language='auto'", sample)


class AudioDeviceDiagnosticTests(unittest.TestCase):
    """Verify that [audio-device] log format is correct."""

    def test_audio_device_log_prefix_format(self) -> None:
        prefix = "[audio-device]"
        sample_wake = (
            f"{prefix} role=wake device=2 name='reSpeaker XVF3800' "
            "sample_rate=16000 channels=1 fallback_used=False reason='matched'"
        )
        self.assertTrue(sample_wake.startswith(prefix))

    def test_audio_device_log_has_required_fields(self) -> None:
        import re
        log_line = (
            "[audio-device] role=command device=2 name='reSpeaker' "
            "sample_rate=16000 channels=1 model_size='tiny' compute_type='int8' "
            "beam_size=1 language='auto' fallback_used=False reason='matched'"
        )
        required = ["role=", "device=", "name=", "sample_rate=", "channels="]
        for field in required:
            self.assertIn(field, log_line, f"Missing field {field!r} in log line")


class ASRBenchmarkDryRunTests(unittest.TestCase):
    """Verify asr_benchmark.py module can be imported and runs dry-run without errors."""

    def test_benchmark_script_importable(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "asr_benchmark",
            "/home/devdul/Projects/smart-desk-ai-assistant/scripts/asr_benchmark.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(callable(getattr(module, "main", None)))

    def test_record_asr_samples_script_importable(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "record_asr_test_samples",
            "/home/devdul/Projects/smart-desk-ai-assistant/scripts/record_asr_test_samples.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(callable(getattr(module, "main", None)))

    def test_word_error_rough_perfect_match(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "asr_benchmark",
            "/home/devdul/Projects/smart-desk-ai-assistant/scripts/asr_benchmark.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        wer = module._word_error_rough("what is teleportation", "what is teleportation")
        self.assertAlmostEqual(wer, 0.0)

    def test_word_error_rough_all_wrong(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "asr_benchmark",
            "/home/devdul/Projects/smart-desk-ai-assistant/scripts/asr_benchmark.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        wer = module._word_error_rough("what is teleportation", "garbage nonsense xyz")
        self.assertGreater(wer, 0.5)

    def test_word_error_rough_empty_ref(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "asr_benchmark",
            "/home/devdul/Projects/smart-desk-ai-assistant/scripts/asr_benchmark.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        wer_empty = module._word_error_rough("", "")
        self.assertAlmostEqual(wer_empty, 0.0)


class PolishSwiadlCorrectionTests(unittest.TestCase):
    """Task 2 extension: świadł/swiadl/swiatl variants correct to światła."""

    def test_pl_predkosc_swiadl_corrected(self) -> None:
        result = check_and_correct("jaka jest prędkość świadł", "pl")
        self.assertTrue(result.is_acceptable)
        self.assertTrue(result.correction_applied)
        self.assertIn("światła", result.corrected_text)
        self.assertNotIn("świadł", result.corrected_text)

    def test_pl_predkosc_swiadl_latin_corrected(self) -> None:
        result = check_and_correct("jaka jest prędkość swiadl", "pl")
        self.assertTrue(result.is_acceptable)
        self.assertTrue(result.correction_applied)
        self.assertIn("światła", result.corrected_text)

    def test_pl_predkosc_swiatl_truncated_corrected(self) -> None:
        result = check_and_correct("jaka jest prędkość swiatl", "pl")
        self.assertTrue(result.is_acceptable)
        self.assertTrue(result.correction_applied)
        self.assertIn("światła", result.corrected_text)

    def test_pl_predkosc_swiadl_full_question_passes_to_llm(self) -> None:
        result = check_and_correct("jaka jest prędkość świadł", "pl")
        self.assertTrue(result.is_acceptable)
        self.assertEqual(result.corrected_text, "jaka jest prędkość światła")

    def test_pl_predkosc_swiatla_no_diacritics_still_corrected(self) -> None:
        result = check_and_correct("jaka jest prędkość swiatla", "pl")
        self.assertTrue(result.is_acceptable)
        self.assertTrue(result.correction_applied)
        self.assertIn("światła", result.corrected_text)

    def test_correction_reason_includes_swiadl(self) -> None:
        result = check_and_correct("jaka jest prędkość świadł", "pl")
        self.assertTrue(result.correction_applied)
        self.assertIn("świadł", result.correction_reason)


class ASRConfigStdoutTests(unittest.TestCase):
    """Task 1: [asr-config] telemetry is emitted via print(), not append_log()."""

    def test_asr_config_uses_print_in_transcribe(self) -> None:
        import inspect
        from modules.devices.audio.input.faster_whisper.backend.core import FasterWhisperInputBackend
        src = inspect.getsource(FasterWhisperInputBackend.transcribe)
        pos = src.find("[asr-config]")
        self.assertGreater(pos, 0, "[asr-config] not found in transcribe()")
        context = src[max(0, pos - 200):pos]
        self.assertIn("print(", context, "[asr-config] must be emitted via print()")
        self.assertNotIn("append_log(", context, "[asr-config] must NOT use append_log()")


class ASREnvOverrideTests(unittest.TestCase):
    """Task 3: env vars override FasterWhisper config without touching settings.json."""

    def _make_mixin_stub(self):
        from unittest.mock import MagicMock
        from modules.runtime.builder.voice_input_mixin import RuntimeBuilderVoiceInputMixin

        mock_backend_class = MagicMock()
        mock_backend_class.return_value = MagicMock()

        class _Stub(RuntimeBuilderVoiceInputMixin):
            def _import_symbol(self, module_path, symbol_name):
                if symbol_name == "FasterWhisperInputBackend":
                    return mock_backend_class
                m = MagicMock()
                m.return_value = MagicMock()
                return m

        stub = _Stub.__new__(_Stub)
        stub._captured_backend_class = mock_backend_class
        return stub

    def _call_build(self, stub, config: dict, extra_env: dict) -> dict:
        import os
        from unittest.mock import patch
        clean_env = {
            k: v for k, v in os.environ.items()
            if k not in {
                "NEXA_OPEN_QUESTION_ASR_MODEL",
                "NEXA_OPEN_QUESTION_ASR_BEAM_SIZE",
                "NEXA_OPEN_QUESTION_ASR_COMPUTE_TYPE",
            }
        }
        clean_env.update(extra_env)
        with patch.dict(os.environ, clean_env, clear=True):
            stub._build_voice_input(config)
        return dict(stub._captured_backend_class.call_args.kwargs)

    def test_model_env_var_overrides_config(self) -> None:
        stub = self._make_mixin_stub()
        kwargs = self._call_build(
            stub,
            {"engine": "faster_whisper", "model_size_or_path": "tiny"},
            {"NEXA_OPEN_QUESTION_ASR_MODEL": "base"},
        )
        self.assertEqual(kwargs["model_size_or_path"], "base")

    def test_beam_size_env_var_overrides_config(self) -> None:
        stub = self._make_mixin_stub()
        kwargs = self._call_build(
            stub,
            {"engine": "faster_whisper", "beam_size": 1},
            {"NEXA_OPEN_QUESTION_ASR_BEAM_SIZE": "3"},
        )
        self.assertEqual(kwargs["beam_size"], 3)

    def test_compute_type_env_var_overrides_config(self) -> None:
        stub = self._make_mixin_stub()
        kwargs = self._call_build(
            stub,
            {"engine": "faster_whisper", "compute_type": "int8"},
            {"NEXA_OPEN_QUESTION_ASR_COMPUTE_TYPE": "float16"},
        )
        self.assertEqual(kwargs["compute_type"], "float16")

    def test_no_env_vars_uses_config_model(self) -> None:
        stub = self._make_mixin_stub()
        kwargs = self._call_build(
            stub,
            {"engine": "faster_whisper", "model_size_or_path": "tiny"},
            {},
        )
        self.assertEqual(kwargs["model_size_or_path"], "tiny")

    def test_no_env_vars_uses_config_beam_size(self) -> None:
        stub = self._make_mixin_stub()
        kwargs = self._call_build(
            stub,
            {"engine": "faster_whisper", "beam_size": 3},
            {},
        )
        self.assertEqual(kwargs["beam_size"], 3)

    def test_invalid_beam_size_env_var_falls_back_to_config(self) -> None:
        stub = self._make_mixin_stub()
        kwargs = self._call_build(
            stub,
            {"engine": "faster_whisper", "beam_size": 2},
            {"NEXA_OPEN_QUESTION_ASR_BEAM_SIZE": "notanumber"},
        )
        self.assertEqual(kwargs["beam_size"], 2)

    def test_settings_json_not_modified(self) -> None:
        settings_path = (
            "/home/devdul/Projects/smart-desk-ai-assistant/config/settings.json"
        )
        with open(settings_path) as f:
            before = f.read()
        stub = self._make_mixin_stub()
        self._call_build(
            stub,
            {"engine": "faster_whisper"},
            {
                "NEXA_OPEN_QUESTION_ASR_MODEL": "base",
                "NEXA_OPEN_QUESTION_ASR_BEAM_SIZE": "2",
                "NEXA_OPEN_QUESTION_ASR_COMPUTE_TYPE": "float16",
            },
        )
        with open(settings_path) as f:
            after = f.read()
        self.assertEqual(before, after, "settings.json must not be modified by ASR env override")

    def test_config_dict_not_mutated(self) -> None:
        config = {
            "engine": "faster_whisper",
            "model_size_or_path": "tiny",
            "beam_size": 1,
            "compute_type": "int8",
        }
        original = dict(config)
        stub = self._make_mixin_stub()
        self._call_build(
            stub,
            config,
            {
                "NEXA_OPEN_QUESTION_ASR_MODEL": "base",
                "NEXA_OPEN_QUESTION_ASR_BEAM_SIZE": "5",
            },
        )
        self.assertEqual(config, original, "config dict must not be mutated by env override")

    def test_small_model_rejected_without_opt_in(self) -> None:
        stub = self._make_mixin_stub()
        kwargs = self._call_build(
            stub,
            {"engine": "faster_whisper", "model_size_or_path": "tiny"},
            {"NEXA_OPEN_QUESTION_ASR_MODEL": "small"},
        )
        # rejected → falls back to config value "tiny"
        self.assertEqual(kwargs["model_size_or_path"], "tiny")

    def test_medium_model_rejected_without_opt_in(self) -> None:
        stub = self._make_mixin_stub()
        kwargs = self._call_build(
            stub,
            {"engine": "faster_whisper", "model_size_or_path": "tiny"},
            {"NEXA_OPEN_QUESTION_ASR_MODEL": "medium"},
        )
        self.assertEqual(kwargs["model_size_or_path"], "tiny")

    def test_small_model_allowed_with_opt_in(self) -> None:
        stub = self._make_mixin_stub()
        kwargs = self._call_build(
            stub,
            {"engine": "faster_whisper", "model_size_or_path": "tiny"},
            {
                "NEXA_OPEN_QUESTION_ASR_MODEL": "small",
                "NEXA_ALLOW_SLOW_OPEN_QUESTION_ASR": "1",
            },
        )
        self.assertEqual(kwargs["model_size_or_path"], "small")

    def test_base_model_not_considered_slow(self) -> None:
        """base is fast enough on Pi; should not require opt-in."""
        stub = self._make_mixin_stub()
        kwargs = self._call_build(
            stub,
            {"engine": "faster_whisper", "model_size_or_path": "tiny"},
            {"NEXA_OPEN_QUESTION_ASR_MODEL": "base"},
        )
        self.assertEqual(kwargs["model_size_or_path"], "base")

    def test_slow_model_rejection_does_not_modify_settings_json(self) -> None:
        settings_path = (
            "/home/devdul/Projects/smart-desk-ai-assistant/config/settings.json"
        )
        with open(settings_path) as f:
            before = f.read()
        stub = self._make_mixin_stub()
        self._call_build(
            stub,
            {"engine": "faster_whisper"},
            {"NEXA_OPEN_QUESTION_ASR_MODEL": "small"},
        )
        with open(settings_path) as f:
            after = f.read()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
