from __future__ import annotations

import unittest

from modules.runtime.contracts import ChunkKind, RouteDecision, RouteKind, StreamMode
from modules.understanding.dialogue.companion_dialogue import CompanionDialogueService
from modules.understanding.dialogue.companion_dialogue.local_llm_mixin import (
    CompanionDialogueLocalLLMMixin,
)

_ALL_EN_ACK = (
    CompanionDialogueLocalLLMMixin._ACK_GENERAL_EN
    + CompanionDialogueLocalLLMMixin._ACK_EXPLAIN_EN
    + CompanionDialogueLocalLLMMixin._ACK_PLAN_EN
)
_ALL_PL_ACK = (
    CompanionDialogueLocalLLMMixin._ACK_GENERAL_PL
    + CompanionDialogueLocalLLMMixin._ACK_EXPLAIN_PL
    + CompanionDialogueLocalLLMMixin._ACK_PLAN_PL
)


class _UnavailableLocalLLM:
    def __init__(self, *, enabled: bool = True, state: str = "failed") -> None:
        self.enabled = enabled
        self.state = state
        self.calls = 0

    def cached_backend_readiness(self, *, refresh_if_stale: bool = False, auto_recover: bool = False):
        self.calls += 1
        del refresh_if_stale, auto_recover
        return {
            "enabled": self.enabled,
            "state": self.state,
            "available": False,
            "healthy": False,
            "warmup_required": True,
            "warmup_ready": False,
            "health_reason": "local llm backend unavailable",
        }

    def stream_companion_reply(self, *args, **kwargs):
        raise AssertionError("unavailable llm should not be streamed")

    def generate_companion_reply(self, *args, **kwargs):
        raise AssertionError("unavailable llm should not be generated")


class _ReadyLocalLLM:
    enabled = True
    state = "ready"
    runner = "test-llm"

    def __init__(self) -> None:
        self.calls = 0
        self.stream_calls = 0
        self.generate_calls = 0

    def cached_backend_readiness(self, *, refresh_if_stale: bool = False, auto_recover: bool = False):
        self.calls += 1
        del refresh_if_stale, auto_recover
        return {
            "enabled": True,
            "state": "ready",
            "available": True,
            "healthy": True,
            "warmup_required": False,
            "warmup_ready": True,
        }

    def stream_companion_reply(self, *args, **kwargs):
        self.stream_calls += 1
        yield type(
            "Chunk",
            (),
            {
                "text": "Streamed answer.",
                "language": "en",
                "metadata": {},
                "first_chunk_latency_ms": 1.0,
            },
        )()

    def generate_companion_reply(self, *args, **kwargs):
        self.generate_calls += 1
        return type(
            "Reply",
            (),
            {
                "ok": True,
                "text": "Generated answer.",
                "source": "test-llm",
                "first_chunk_latency_ms": 1.0,
            },
        )()


class DialogueLLMFallbackTests(unittest.TestCase):
    def _route(self, *, language: str, text: str | None = None) -> RouteDecision:
        if text is None:
            text = "opowiedz o czarnych dziurach" if language == "pl" else "explain black holes"
        return RouteDecision(
            turn_id=f"turn-llm-fallback-{language}",
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

    def test_unavailable_llm_returns_short_english_fallback_plan(self) -> None:
        service = CompanionDialogueService()
        service.local_llm = _UnavailableLocalLLM(enabled=True)

        plan = service.build_response_plan(
            self._route(language="en"),
            user_profile={},
            stream_mode=StreamMode.SENTENCE,
        )

        self.assertEqual(
            plan.full_text(),
            "I can’t use the language model right now. Try again in a moment.",
        )
        self.assertFalse(callable(plan.metadata.get("live_chunk_factory")))

    def test_live_llm_sentence_streaming_flag_disables_live_factory(self) -> None:
        service = CompanionDialogueService()
        service.local_llm = _ReadyLocalLLM()
        service.live_llm_sentence_streaming_enabled = False

        plan = service.build_response_plan(
            self._route(language="en"),
            user_profile={},
            stream_mode=StreamMode.SENTENCE,
        )

        self.assertFalse(callable(plan.metadata.get("live_chunk_factory")))
        self.assertEqual(plan.full_text(), "Generated answer.")
        self.assertEqual(service.local_llm.stream_calls, 0)
        self.assertEqual(service.local_llm.generate_calls, 1)
        self.assertGreaterEqual(service.local_llm.calls, 1)

    def test_unavailable_llm_returns_short_polish_fallback_plan(self) -> None:
        service = CompanionDialogueService()
        service.local_llm = _UnavailableLocalLLM(enabled=True)

        plan = service.build_response_plan(
            self._route(language="pl"),
            user_profile={},
            stream_mode=StreamMode.SENTENCE,
        )

        self.assertEqual(
            plan.full_text(),
            "Nie mogę teraz użyć modelu językowego. Spróbuj za chwilę.",
        )
        self.assertFalse(callable(plan.metadata.get("live_chunk_factory")))

    def test_live_llm_plan_enables_presence_heartbeat_english(self) -> None:
        service = CompanionDialogueService()
        service.local_llm = _ReadyLocalLLM()

        plan = service.build_response_plan(
            self._route(language="en"),
            user_profile={},
            stream_mode=StreamMode.SENTENCE,
        )

        self.assertTrue(callable(plan.metadata.get("live_chunk_factory")))
        self.assertFalse([c for c in plan.chunks if c.kind == ChunkKind.ACK])
        self.assertTrue(plan.metadata.get("presence_heartbeat_enabled"))
        self.assertAlmostEqual(plan.metadata.get("presence_heartbeat_first_delay_s"), 1.0)

    def test_live_llm_plan_enables_presence_heartbeat_polish(self) -> None:
        service = CompanionDialogueService()
        service.local_llm = _ReadyLocalLLM()

        plan = service.build_response_plan(
            self._route(language="pl"),
            user_profile={},
            stream_mode=StreamMode.SENTENCE,
        )

        self.assertTrue(callable(plan.metadata.get("live_chunk_factory")))
        self.assertFalse([c for c in plan.chunks if c.kind == ChunkKind.ACK])
        self.assertTrue(plan.metadata.get("presence_heartbeat_enabled"))

    def test_live_llm_plan_has_no_ack_when_llm_unavailable(self) -> None:
        service = CompanionDialogueService()
        service.local_llm = _UnavailableLocalLLM(enabled=True)

        plan = service.build_response_plan(
            self._route(language="en"),
            user_profile={},
            stream_mode=StreamMode.SENTENCE,
        )

        ack_chunks = [c for c in plan.chunks if c.kind == ChunkKind.ACK]
        self.assertEqual(len(ack_chunks), 0, "No ACK chunk expected when LLM is unavailable")

    def test_llm_ack_category_explain_english(self) -> None:
        service = CompanionDialogueService()

        ack_text = service._llm_thinking_ack("en", user_text="explain what a black hole is")
        self.assertIn(ack_text, CompanionDialogueLocalLLMMixin._ACK_EXPLAIN_EN,
                      "EN explain query must select explanation ACK phrase")

    def test_llm_ack_category_explain_polish(self) -> None:
        service = CompanionDialogueService()

        ack_text = service._llm_thinking_ack("pl", user_text="wyjaśnij czym jest czarna dziura")
        self.assertIn(ack_text, CompanionDialogueLocalLLMMixin._ACK_EXPLAIN_PL,
                      "PL explain query must select explanation ACK phrase")

    def test_llm_ack_category_plan_english(self) -> None:
        service = CompanionDialogueService()

        ack_text = service._llm_thinking_ack("en", user_text="give me steps to clean my desk")
        self.assertIn(ack_text, CompanionDialogueLocalLLMMixin._ACK_PLAN_EN,
                      "EN plan query must select planning ACK phrase")

    def test_llm_ack_category_plan_polish(self) -> None:
        service = CompanionDialogueService()

        ack_text = service._llm_thinking_ack("pl", user_text="pomóż mi ułożyć kroki do sprzątania")
        self.assertIn(ack_text, CompanionDialogueLocalLLMMixin._ACK_PLAN_PL,
                      "PL plan query must select planning ACK phrase")

    def test_llm_ack_category_speed_of_light_polish_is_explain_not_plan(self) -> None:
        service = CompanionDialogueService()

        ack_text = service._llm_thinking_ack("pl", user_text="jak szybkie jest światło")
        self.assertIn(ack_text, CompanionDialogueLocalLLMMixin._ACK_EXPLAIN_PL,
                      "'jak szybkie' must select explanation ACK, not plan")
        self.assertNotIn(ack_text, CompanionDialogueLocalLLMMixin._ACK_PLAN_PL,
                         "'jak szybkie jest światło' must NOT select plan ACK")

    def test_llm_ack_category_how_fast_is_light_english_is_explain(self) -> None:
        service = CompanionDialogueService()

        ack_text = service._llm_thinking_ack("en", user_text="how fast is light")
        self.assertIn(ack_text, CompanionDialogueLocalLLMMixin._ACK_EXPLAIN_EN,
                      "'how fast' must select explanation ACK")

    def test_llm_ack_category_jak_alone_does_not_trigger_plan(self) -> None:
        service = CompanionDialogueService()

        ack_text = service._llm_thinking_ack("pl", user_text="jak się masz")
        self.assertNotIn(ack_text, CompanionDialogueLocalLLMMixin._ACK_PLAN_PL,
                         "'jak się masz' must NOT select plan ACK")
        self.assertIn(ack_text, _ALL_PL_ACK,
                      "ACK must still be from the PL pool")

    def test_llm_ack_category_what_are_colors_english_is_explain(self) -> None:
        service = CompanionDialogueService()

        ack_text = service._llm_thinking_ack("en", user_text="what are colors")
        self.assertIn(ack_text, CompanionDialogueLocalLLMMixin._ACK_EXPLAIN_EN,
                      "'what are' must select explanation ACK")

    def test_live_llm_plan_has_no_prequeued_ack_duplication(self) -> None:
        service = CompanionDialogueService()
        service.local_llm = _ReadyLocalLLM()

        plan = service.build_response_plan(
            self._route(language="en"),
            user_profile={},
            stream_mode=StreamMode.SENTENCE,
        )

        ack_chunks = [c for c in plan.chunks if c.kind == ChunkKind.ACK]
        self.assertEqual(len(ack_chunks), 0, "live LLM uses heartbeat, not a queued ACK")


if __name__ == "__main__":
    unittest.main()
