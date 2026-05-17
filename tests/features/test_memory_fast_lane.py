from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from modules.core.flows.action_flow.memory_actions_mixin import ActionMemoryActionsMixin
from modules.core.flows.action_flow.executors.memory_executor import MemorySkillExecutor
from modules.devices.audio.command_asr.command_grammar import (
    build_default_command_grammar,
)
from modules.devices.audio.command_asr.command_language import CommandLanguage
from modules.features.memory.service import MemoryService
from modules.runtime.voice_engine_v2.runtime_candidate_executor import (
    RuntimeCandidateExecutionPlanBuilder,
)
from modules.shared.persistence.repositories import MemoryRepository


class TestVoskGrammarPolishFix(unittest.TestCase):
    """
    The Polish phrase 'co zapamietalas'/'co zapamiętałaś' contains words that
    are not in the small Vosk Polish vocabulary, which produced runtime
    grammar warnings every time the recognizer reloaded. Those phrases must
    still match against full-STT transcripts (whisper) but must NOT be
    forwarded to Vosk's limited grammar.
    """

    def setUp(self) -> None:
        self.grammar = build_default_command_grammar()

    def test_polish_zapamietalas_phrase_not_exported_to_vosk(self) -> None:
        polish_vocab = self.grammar.to_vosk_vocabulary(
            language=CommandLanguage.POLISH,
        )
        for phrase in polish_vocab:
            self.assertNotIn("zapamietalas", phrase)
            self.assertNotIn("zapamiętałaś", phrase)

    def test_polish_zapamietalas_phrase_still_matches_whisper_transcript(self) -> None:
        # The phrase must still match for slow-path (whisper) transcripts so
        # the user can say "co zapamietalas" and get the memory list back.
        result = self.grammar.match("co zapamietalas")

        self.assertEqual(result.intent_key, "memory.list")

    def test_polish_recall_prefixes_are_in_vosk_vocab(self) -> None:
        polish_vocab = self.grammar.to_vosk_vocabulary(
            language=CommandLanguage.POLISH,
        )
        # These short phrases must reach Vosk so the fast lane sees them.
        self.assertIn("gdzie jest", polish_vocab)

    def test_english_recall_prefixes_are_in_vosk_vocab(self) -> None:
        english_vocab = self.grammar.to_vosk_vocabulary(
            language=CommandLanguage.ENGLISH,
        )
        self.assertIn("where is", english_vocab)
        self.assertIn("where did i put", english_vocab)

    def test_polish_memory_recall_supports_common_spoken_prefixes(self) -> None:
        polish_vocab = self.grammar.to_vosk_vocabulary(
            language=CommandLanguage.POLISH,
        )
        self.assertIn("przypomnij mi gdzie", polish_vocab)
        self.assertIn("gdzie jest", polish_vocab)
        self.assertNotIn("gdzie polozylem", polish_vocab)


class TestVoskFastLaneMemoryRecall(unittest.TestCase):
    """
    Memory recall must run through the Voice Engine v2 runtime candidate
    fast lane instead of full whisper STT. The lane should:
    - detect 'where is X' / 'gdzie jest X' transcripts
    - resolve them to memory.recall with the subject extracted
    - hand the legacy ActionFlow a route with a populated payload
    """

    def setUp(self) -> None:
        self.builder = RuntimeCandidateExecutionPlanBuilder()
        self.tmp = tempfile.TemporaryDirectory()
        self.memory = MemoryService(
            store=MemoryRepository(path=str(Path(self.tmp.name) / "memory.json")),
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_known_memory_recall_queries_resolve_gallery_kind(self) -> None:
        cases = {
            "kogo znasz": "people",
            "kogo z nasz": "people",
            "kogo z nas": "people",
            "kogo znas": "people",
            "jakie obiekty znasz": "objects",
            "jakie obiektyznaz": "objects",
            "jakie obiekty z nasz": "objects",
            "what objects do you know": "objects",
            "what object now": "objects",
        }

        for query, expected_kind in cases.items():
            with self.subTest(query=query):
                self.assertEqual(
                    ActionMemoryActionsMixin._memory_gallery_kind_from_query(query),
                    expected_kind,
                )

    # -- intent resolution ---------------------------------------------

    def test_polish_where_is_phone_resolves_to_memory_recall(self) -> None:
        intent = self.builder._resolve_runtime_intent_key(
            intent_key="",
            transcript="gdzie jest mój telefon",
        )

        self.assertEqual(intent, "memory.recall")

    def test_polish_where_is_phone_extracts_telefon_as_key(self) -> None:
        key = self.builder._extract_recall_key("gdzie jest mój telefon")

        self.assertEqual(key, "telefon")

    def test_polish_where_are_keys_extracts_klucze_as_key(self) -> None:
        key = self.builder._extract_recall_key("gdzie są moje klucze")

        self.assertEqual(key, "klucze")

    def test_english_where_is_phone_resolves_to_memory_recall(self) -> None:
        intent = self.builder._resolve_runtime_intent_key(
            intent_key="",
            transcript="where is my phone",
        )

        self.assertEqual(intent, "memory.recall")

    def test_english_where_is_phone_extracts_phone_as_key(self) -> None:
        key = self.builder._extract_recall_key("where is my phone")

        self.assertEqual(key, "phone")

    def test_english_where_did_i_put_extracts_key(self) -> None:
        key = self.builder._extract_recall_key("where did i put my wallet")

        self.assertEqual(key, "wallet")

    def test_polish_przypomnij_where_extracts_key(self) -> None:
        key = self.builder._extract_recall_key("przypomnij mi gdzie jest mój telefon")

        self.assertEqual(key, "telefon")

    def test_bare_where_does_not_trigger_recall(self) -> None:
        # No subject after the prefix → fast lane must not fire.
        intent = self.builder._resolve_runtime_intent_key(
            intent_key="",
            transcript="gdzie",
        )

        self.assertEqual(intent, "")

    def test_remember_alone_resolves_to_guided_start(self) -> None:
        intent = self.builder._resolve_runtime_intent_key(
            intent_key="",
            transcript="remember",
        )

        self.assertEqual(intent, "memory.guided_start")

    def test_zapamietaj_alone_resolves_to_guided_start(self) -> None:
        intent = self.builder._resolve_runtime_intent_key(
            intent_key="",
            transcript="zapamiętaj",
        )

        self.assertEqual(intent, "memory.guided_start")

    # -- plan building -------------------------------------------------

    def test_polish_recall_plan_has_subject_in_tool_payload(self) -> None:
        plan = self.builder.build_plan_from_intent(
            turn_id="t1",
            intent_key="memory.recall",
            transcript="gdzie jest mój telefon",
            language="pl",
        )

        self.assertIsNotNone(plan)
        self.assertEqual(plan.route_decision.primary_intent, "memory_recall")
        tool_payload = plan.route_decision.tool_invocations[0].payload
        self.assertEqual(tool_payload.get("key"), "telefon")
        self.assertEqual(tool_payload.get("query"), "telefon")

    def test_polish_recall_plan_payload_reaches_intent_entities(self) -> None:
        # The action-flow resolver may pull from intent.entities instead of
        # tool.payload depending on the legacy route shape, so the key must
        # also be present there.
        plan = self.builder.build_plan_from_intent(
            turn_id="t1",
            intent_key="memory.recall",
            transcript="gdzie jest mój telefon",
            language="pl",
        )

        entities = plan.route_decision.intents[0].entities
        keyed = {e.name: e.value for e in entities}
        self.assertEqual(keyed.get("key"), "telefon")

    def test_guided_start_plan_marks_guided_payload(self) -> None:
        plan = self.builder.build_plan_from_intent(
            turn_id="t2",
            intent_key="memory.guided_start",
            transcript="zapamiętaj coś",
            language="pl",
        )

        self.assertIsNotNone(plan)
        self.assertEqual(plan.route_decision.primary_intent, "memory_store")
        self.assertEqual(plan.route_decision.tool_invocations[0].payload, {"guided": True})

    def test_object_guided_start_plan_marks_object_payload(self) -> None:
        plan = self.builder.build_plan_from_intent(
            turn_id="t3",
            intent_key="memory.guided_start",
            transcript="zapamiętaj ten telefon",
            language="pl",
        )

        self.assertIsNotNone(plan)
        self.assertEqual(plan.route_decision.primary_intent, "memory_store")
        self.assertEqual(
            plan.route_decision.tool_invocations[0].payload,
            {"guided": True, "object_enrollment": True, "object_hint": "telefon"},
        )

    # -- end-to-end fast lane recall -----------------------------------

    def test_polish_fast_lane_recall_returns_saved_phrase(self) -> None:
        self.memory.remember_text(
            "telefon jest na biurku",
            language="pl",
            source="unit_test",
        )

        plan = self.builder.build_plan_from_intent(
            turn_id="t1",
            intent_key="memory.recall",
            transcript="gdzie jest mój telefon",
            language="pl",
        )
        payload = plan.route_decision.tool_invocations[0].payload

        executor = MemorySkillExecutor(assistant=SimpleNamespace(memory=self.memory))
        outcome = executor.recall(key=payload["key"], language="pl")

        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.status, "found")
        self.assertEqual(outcome.data["value"], "telefon jest na biurku")

    def test_english_fast_lane_recall_returns_saved_phrase(self) -> None:
        self.memory.remember_text(
            "my phone is on the desk",
            language="en",
            source="unit_test",
        )

        plan = self.builder.build_plan_from_intent(
            turn_id="t1",
            intent_key="memory.recall",
            transcript="where is my phone",
            language="en",
        )
        payload = plan.route_decision.tool_invocations[0].payload

        executor = MemorySkillExecutor(assistant=SimpleNamespace(memory=self.memory))
        outcome = executor.recall(key=payload["key"], language="en")

        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.data["value"], "my phone is on the desk")

    def test_polish_fast_lane_forget_person_hides_from_people_recall(self) -> None:
        self.memory.remember_person("Tomek", language="pl", source="unit_test")

        plan = self.builder.build_plan_from_intent(
            turn_id="t-forget",
            intent_key="memory.forget",
            transcript="zapomnij Tomka",
            language="pl",
        )
        payload = plan.route_decision.tool_invocations[0].payload

        executor = MemorySkillExecutor(assistant=SimpleNamespace(memory=self.memory))
        outcome = executor.forget(
            key=payload["key"],
            language="pl",
            entity_type=payload.get("entity_type"),
        )

        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.status, "removed")
        self.assertEqual(self.memory.recall("kogo znasz", language="pl"), "Nie znam jeszcze żadnych osób.")

    def test_english_fast_lane_forget_object_hides_from_object_recall(self) -> None:
        self.memory.remember_object("Vape", aliases=["phone"], language="en", source="unit_test")

        plan = self.builder.build_plan_from_intent(
            turn_id="t-forget-object",
            intent_key="memory.forget",
            transcript="forget object Vape",
            language="en",
        )
        payload = plan.route_decision.tool_invocations[0].payload

        executor = MemorySkillExecutor(assistant=SimpleNamespace(memory=self.memory))
        outcome = executor.forget(
            key=payload["key"],
            language="en",
            entity_type=payload.get("entity_type"),
        )

        self.assertTrue(outcome.ok)
        self.assertEqual(outcome.status, "removed")
        self.assertEqual(
            self.memory.recall("what objects do you know", language="en"),
            "I do not know any objects yet.",
        )


if __name__ == "__main__":
    unittest.main()
