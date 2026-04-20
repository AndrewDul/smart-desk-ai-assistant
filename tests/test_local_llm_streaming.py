from __future__ import annotations

import unittest
from unittest import mock

from modules.understanding.dialogue.llm.local_llm import LocalLLMService


class FakeHTTPStream:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(self._lines)


class LocalLLMStreamingTests(unittest.TestCase):
    def _build_service(self) -> LocalLLMService:
        return LocalLLMService(
            {
                "llm": {
                    "enabled": False,
                    "runner": "hailo-ollama",
                    "stream_sentence_min_chars": 18,
                    "stream_sentence_soft_max_chars": 64,
                }
            }
        )

    def test_split_ready_stream_chunks_respects_sentence_boundaries(self) -> None:
        service = self._build_service()

        ready, tail = service._split_ready_stream_chunks(
            "This is the first complete sentence. This tail is still growing",
            language="en",
            final_flush=False,
        )

        self.assertEqual(ready, ["This is the first complete sentence."])
        self.assertEqual(tail, "This tail is still growing")

    def test_chunk_full_text_reply_emits_ordered_chunks(self) -> None:
        service = self._build_service()

        chunks = list(
            service._chunk_full_text_reply(
                text="This is the first response sentence. This is the second response sentence.",
                language="en",
                source="test",
                first_chunk_latency_ms=42.0,
                max_sentences=2,
                user_prompt="",
            )
        )

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0].sequence, 0)
        self.assertEqual(chunks[0].first_chunk_latency_ms, 42.0)
        self.assertFalse(chunks[0].finished)
        self.assertTrue(chunks[-1].finished)
        self.assertEqual(chunks[-1].sequence, 1)

    def test_iter_streaming_endpoint_chunks_accepts_sse_data_prefix(self) -> None:
        service = self._build_service()

        fake_lines = [
            b'data: {"message": {"content": "Black"}}\n',
            b'data: {"message": {"content": " holes are"}}\n',
            b'data: {"message": {"content": " regions of"}}\n',
            b'data: {"message": {"content": " spacetime."}}\n',
            b'data: {"done": true}\n',
            b'data: [DONE]\n',
        ]

        with mock.patch("urllib.request.urlopen", return_value=FakeHTTPStream(fake_lines)):
            chunks = list(
                service._iter_streaming_endpoint_chunks(
                    url="http://127.0.0.1:8000/api/chat",
                    payload={"stream": True},
                    timeout_seconds=2.0,
                    language="en",
                    source="hailo-ollama",
                )
            )

        self.assertGreaterEqual(len(chunks), 1)
        self.assertEqual(chunks[0].text, "Black holes are regions of spacetime.")

    def test_extract_text_from_json_payload_preserves_stream_token_spacing(self) -> None:
        service = self._build_service()

        payload = {
            "message": {
                "content": " black hole"
            }
        }

        extracted = service._extract_text_from_json_payload(
            payload,
            preserve_token_spacing=True,
        )

        self.assertEqual(extracted, " black hole")

    def test_server_request_candidates_use_only_hailo_chat_for_streaming(self) -> None:
        service = self._build_service()

        candidates = service._server_request_candidates(
            base_url="http://127.0.0.1:8000",
            system_prompt="You are helpful.",
            user_prompt="What is a black hole?",
            profile=service._build_generation_profile(
                language="en",
                context=service._coerce_context({}, user_text="What is a black hole?"),
                user_prompt="What is a black hole?",
            ),
            stream=True,
        )

        urls = [candidate["url"] for candidate in candidates]
        self.assertIn("http://127.0.0.1:8000/api/chat", urls)
        self.assertNotIn("http://127.0.0.1:8000/api/generate", urls)
        self.assertNotIn("http://127.0.0.1:8000/v1/chat/completions", urls)

    def test_payload_for_hailo_chat_compacts_multiline_prompts(self) -> None:
        service = self._build_service()
        profile = service._build_generation_profile(
            language="en",
            context=service._coerce_context({}, user_text="What is a black hole?"),
            user_prompt="What is a black hole?",
        )

        payload = service._payload_for_server_path(
            path="/api/chat",
            system_prompt="You are NeXa.\nReply only in English.\nStay concise.",
            user_prompt="What is a black hole?\nKeep it short.",
            profile=profile,
            stream=True,
        )

        self.assertEqual(
            payload["messages"][0]["content"],
            "You are NeXa. Reply only in English. Stay concise.",
        )
        self.assertEqual(
            payload["messages"][1]["content"],
            "What is a black hole? Keep it short.",
        )
        self.assertNotIn("options", payload)

    def test_payload_for_hailo_generate_removes_raw_newlines(self) -> None:
        service = self._build_service()
        profile = service._build_generation_profile(
            language="en",
            context=service._coerce_context({}, user_text="What is a black hole?"),
            user_prompt="What is a black hole?",
        )

        payload = service._payload_for_server_path(
            path="/api/generate",
            system_prompt="You are NeXa.\nReply only in English.",
            user_prompt="What is a black hole?\nKeep it short.",
            profile=profile,
            stream=False,
        )

        self.assertIn("<|system|>", payload["prompt"])
        self.assertIn("<|user|>", payload["prompt"])
        self.assertNotIn("\n", payload["prompt"])
        self.assertNotIn("\r", payload["prompt"])


    def test_resolved_server_model_name_uses_configured_model_when_available(self) -> None:
        service = self._build_service()
        service.server_model_name = "qwen2:1.5b"

        with mock.patch.object(
            service,
            "_fetch_server_model_names",
            return_value=["qwen2:1.5b", "llama3.2:1b"],
        ):
            resolved = service._resolved_server_model_name()

        self.assertEqual(resolved, "qwen2:1.5b")

    def test_resolved_server_model_name_falls_back_when_configured_model_is_missing(self) -> None:
        service = self._build_service()
        service.server_model_name = "qwen2.5:1.5b"

        with mock.patch.object(
            service,
            "_fetch_server_model_names",
            return_value=["qwen2:1.5b", "llama3.2:1b"],
        ):
            resolved = service._resolved_server_model_name()

        self.assertEqual(resolved, "qwen2:1.5b")


    def test_stream_sanitize_respects_max_sentences(self) -> None:
        service = self._build_service()

        cleaned = service._sanitize_stream_text(
            "Sentence one. Sentence two. Sentence three.",
            language="en",
            max_sentences=2,
            user_prompt="",
            final_chunk=True,
        )

        self.assertEqual(cleaned, "Sentence one. Sentence two.")

    def test_stream_sanitize_does_not_force_period_on_partial_chunk(self) -> None:
        service = self._build_service()

        cleaned = service._sanitize_stream_text(
            "A black hole is a region of",
            language="en",
            max_sentences=2,
            user_prompt="",
            final_chunk=False,
        )

        self.assertEqual(cleaned, "A black hole is a region of")



    def test_split_ready_stream_chunks_emits_fast_first_chunk_without_sentence_boundary(self) -> None:
        service = self._build_service()
        service.stream_first_chunk_min_chars = 20
        service.stream_first_chunk_soft_max_chars = 36

        ready, tail = service._split_ready_stream_chunks(
            "A black hole is a region in space, where gravity is so strong that light cannot escape",
            language="en",
            final_flush=False,
            emitted_count=0,
        )

        self.assertEqual(ready, ["A black hole is a region in space,"])
        self.assertTrue(tail.startswith("where gravity"))



    def test_warmup_backend_if_enabled_primes_server_with_short_non_stream_call(self) -> None:
        service = self._build_service()
        service.enabled = True

        with mock.patch.object(service, "is_available", return_value=True), \
             mock.patch.object(service, "_fetch_server_model_names", return_value=["qwen2:1.5b"]), \
             mock.patch.object(
                 service,
                 "_post_json",
                 return_value='{"message":{"content":"ready"},"done":true}',
             ) as post_json:
            warmed = service.warmup_backend_if_enabled()

        self.assertTrue(warmed)
        self.assertTrue(service._last_warmup_ok)
        post_json.assert_called_once()



    def test_stream_server_chunks_falls_back_to_non_stream_reply(self) -> None:
        service = self._build_service()
        profile = service._build_generation_profile(
            language="en",
            context=service._coerce_context({}, user_text="What is a black hole?"),
            user_prompt="What is a black hole?",
        )

        with mock.patch.object(
            service,
            "_iter_streaming_endpoint_chunks",
            side_effect=RuntimeError("streaming not supported"),
        ), mock.patch.object(
            service,
            "_run_server",
            return_value="A black hole is a region of spacetime with gravity so strong that light cannot escape.",
        ):
            chunks = list(
                service._stream_server_chunks(
                    system_prompt="You are helpful.",
                    user_prompt="What is a black hole?",
                    profile=profile,
                    language="en",
                )
            )

        self.assertGreaterEqual(len(chunks), 1)
        self.assertIn("black hole", chunks[0].text.lower())
        self.assertEqual(service._last_generation_source, "hailo-ollama_non_stream_fallback")
        self.assertTrue(service._last_generation_ok)


if __name__ == "__main__":
    unittest.main()