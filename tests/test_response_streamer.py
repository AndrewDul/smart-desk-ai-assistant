from __future__ import annotations

import unittest
import time
from modules.presentation.response_streamer.streamer import ResponseStreamer
from modules.runtime.contracts import AssistantChunk, ChunkKind, ResponsePlan, RouteKind, StreamMode
from tests.support.fakes import FakeDisplay, FakeVoiceOutput



class _SlowVoiceOutput(FakeVoiceOutput):
    def __init__(self, *, sleep_seconds: float = 0.06) -> None:
        super().__init__(supports_prepare_next=True)
        self.sleep_seconds = float(sleep_seconds)

    def speak(
        self,
        text: str,
        language: str | None = None,
        prepare_next: tuple[str, str] | None = None,
        output_hold_seconds: float | None = None,
    ) -> bool:
        time.sleep(self.sleep_seconds)
        return super().speak(
            text,
            language=language,
            prepare_next=prepare_next,
            output_hold_seconds=output_hold_seconds,
        )


class ResponseStreamerTests(unittest.TestCase):
    def test_execute_standard_plan_collects_metrics_and_prefetch(self) -> None:
        voice_output = FakeVoiceOutput(supports_prepare_next=True)
        display = FakeDisplay()
        streamer = ResponseStreamer(
            voice_output=voice_output,
            display=display,
            default_display_seconds=4.0,
            inter_chunk_pause_seconds=0.0,
        )

        plan = ResponsePlan(
            turn_id="turn-standard",
            language="en",
            route_kind=RouteKind.CONVERSATION,
            stream_mode=StreamMode.SENTENCE,
            chunks=[
                AssistantChunk(text="Sure.", kind=ChunkKind.ACK, sequence_index=0),
                AssistantChunk(text="I can help with that.", kind=ChunkKind.CONTENT, sequence_index=1),
                AssistantChunk(text="What would you like next?", kind=ChunkKind.FOLLOW_UP, sequence_index=2),
            ],
            metadata={"display_title": "CHAT", "display_lines": ["Sure."]},
        )

        report = streamer.execute(plan)

        self.assertGreaterEqual(report.chunks_spoken, 1)
        self.assertIn("I can help", report.full_text)
        self.assertGreaterEqual(report.total_elapsed_ms, 0.0)
        self.assertGreaterEqual(report.first_audio_latency_ms, 0.0)
        self.assertGreaterEqual(report.first_sentence_latency_ms, 0.0)
        self.assertEqual(report.first_chunk_latency_ms, 0.0)
        self.assertFalse(report.live_streaming)
        self.assertTrue(voice_output.speak_calls)
        self.assertTrue(display.blocks)

    def test_execute_live_plan_uses_live_chunk_factory(self) -> None:
        voice_output = FakeVoiceOutput(supports_prepare_next=True)
        display = FakeDisplay()
        streamer = ResponseStreamer(
            voice_output=voice_output,
            display=display,
            default_display_seconds=4.0,
            inter_chunk_pause_seconds=0.0,
        )

        def live_factory():
            yield AssistantChunk(
                text="Let me check.",
                kind=ChunkKind.ACK,
                sequence_index=0,
                metadata={"first_chunk_latency_ms": 42.0},
            )
            yield AssistantChunk(text="The timer is running.", kind=ChunkKind.CONTENT, sequence_index=1)

        plan = ResponsePlan(
            turn_id="turn-live",
            language="en",
            route_kind=RouteKind.CONVERSATION,
            stream_mode=StreamMode.SENTENCE,
            chunks=[],
            metadata={
                "display_title": "CHAT",
                "display_lines": [],
                "live_chunk_factory": live_factory,
            },
        )

        report = streamer.execute(plan)

        self.assertTrue(report.live_streaming)
        self.assertEqual(report.chunks_spoken, 2)
        self.assertIn("The timer is running.", report.full_text)
        self.assertEqual(report.chunk_kinds, ["ack", "content"])
        self.assertEqual(report.first_chunk_latency_ms, 42.0)
        self.assertGreaterEqual(report.first_sentence_latency_ms, 0.0)
        self.assertEqual(len(voice_output.speak_calls), 2)
        self.assertTrue(display.blocks)



    def test_execute_live_plan_measures_first_audio_from_speak_start_not_completion(self) -> None:
        voice_output = _SlowVoiceOutput(sleep_seconds=0.06)
        display = FakeDisplay()
        streamer = ResponseStreamer(
            voice_output=voice_output,
            display=display,
            default_display_seconds=4.0,
            inter_chunk_pause_seconds=0.0,
        )

        def live_factory():
            yield AssistantChunk(
                text="Black holes bend spacetime in extreme ways",
                kind=ChunkKind.CONTENT,
                sequence_index=0,
                metadata={"first_chunk_latency_ms": 12.0},
            )

        plan = ResponsePlan(
            turn_id="turn-live-first-audio",
            language="en",
            route_kind=RouteKind.CONVERSATION,
            stream_mode=StreamMode.SENTENCE,
            chunks=[],
            metadata={
                "display_title": "CHAT",
                "display_lines": [],
                "live_chunk_factory": live_factory,
            },
        )

        report = streamer.execute(plan)

        self.assertTrue(report.live_streaming)
        self.assertLess(report.first_audio_latency_ms, 40.0)
        self.assertGreaterEqual(report.total_elapsed_ms, 50.0)

if __name__ == "__main__":
    unittest.main()