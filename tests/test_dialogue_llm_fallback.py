from __future__ import annotations

import unittest

from modules.runtime.contracts import RouteDecision, RouteKind, StreamMode
from modules.understanding.dialogue.companion_dialogue import CompanionDialogueService


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
    def _route(self, *, language: str) -> RouteDecision:
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


if __name__ == "__main__":
    unittest.main()
