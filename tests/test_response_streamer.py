from __future__ import annotations

import time
import unittest

from modules.presentation.response_streamer.streamer import ResponseStreamer
from modules.runtime.contracts import AssistantChunk, ChunkKind, ResponsePlan, RouteKind, StreamMode
from tests.support.fakes import FakeDisplay, FakeVoiceOutput


class _TelemetryVoiceOutput(FakeVoiceOutput):
    def __init__(self, *, audio_delay_seconds: float = 0.05) -> None:
        super().__init__(supports_prepare_next=True)
        self.audio_delay_seconds = float(audio_delay_seconds)

    def speak(
        self,
        text: str,
        language: str | None = None,
        prepare_next: tuple[str, str] | None = None,
        output_hold_seconds: float | None = None,
        latency_profile: str | None = None,
    ) -> bool:
        started_at = time.monotonic()
        time.sleep(self.audio_delay_seconds)
        result = super().speak(
            text,
            language=language,
            prepare_next=prepare_next,
            output_hold_seconds=output_hold_seconds,
            latency_profile=latency_profile,
        )
        self._last_speak_report["first_audio_started_at_monotonic"] = (
            started_at + self.audio_delay_seconds
        )
        self._last_speak_report["first_audio_latency_ms"] = (
            self.audio_delay_seconds * 1000.0
        )
        return result


class _OrderedVoiceOutput(FakeVoiceOutput):
    def __init__(self, events: list[str]) -> None:
        super().__init__(supports_prepare_next=True)
        self.events = events

    def speak(
        self,
        text: str,
        language: str | None = None,
        prepare_next: tuple[str, str] | None = None,
        output_hold_seconds: float | None = None,
        latency_profile: str | None = None,
    ) -> bool:
        self.events.append("speak")
        return super().speak(
            text,
            language=language,
            prepare_next=prepare_next,
            output_hold_seconds=output_hold_seconds,
            latency_profile=latency_profile,
        )


class _OrderedDisplay(FakeDisplay):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self.events = events

    def show_block(self, title: str, lines: list[str], duration: float | None = None) -> None:
        self.events.append("display")
        super().show_block(title, lines, duration=duration)


class _UpdatingDisplay(FakeDisplay):
    def __init__(self) -> None:
        super().__init__()
        self.update_calls: list[dict[str, object]] = []

    def update_block(self, title: str, lines: list[str], duration: float | None = None) -> None:
        self.update_calls.append(
            {
                "title": str(title),
                "lines": list(lines),
                "duration": duration,
            }
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
            yield AssistantChunk(
                text="The timer is running.",
                kind=ChunkKind.CONTENT,
                sequence_index=1,
            )

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

    def test_execute_live_plan_passes_next_chunk_as_prepare_next(self) -> None:
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
                text="First sentence.",
                kind=ChunkKind.CONTENT,
                sequence_index=0,
            )
            yield AssistantChunk(
                text="Second sentence.",
                kind=ChunkKind.CONTENT,
                sequence_index=1,
            )

        plan = ResponsePlan(
            turn_id="turn-live-lookahead",
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
        self.assertEqual(len(voice_output.speak_calls), 2)
        self.assertEqual(
            voice_output.speak_calls[0]["prepare_next"],
            ("Second sentence.", "en"),
        )
        self.assertIsNone(voice_output.speak_calls[1]["prepare_next"])

    def test_execute_live_plan_refreshes_display_for_later_chunks(self) -> None:
        voice_output = FakeVoiceOutput(supports_prepare_next=True)
        display = FakeDisplay()
        streamer = ResponseStreamer(
            voice_output=voice_output,
            display=display,
            default_display_seconds=4.0,
            inter_chunk_pause_seconds=0.0,
            max_display_chars_per_line=80,
        )

        def live_factory():
            yield AssistantChunk(
                text="Black holes are very dense regions.",
                kind=ChunkKind.CONTENT,
                sequence_index=0,
            )
            yield AssistantChunk(
                text="Their gravity is so strong that light cannot escape.",
                kind=ChunkKind.CONTENT,
                sequence_index=1,
            )

        plan = ResponsePlan(
            turn_id="turn-live-display-refresh",
            language="en",
            route_kind=RouteKind.CONVERSATION,
            stream_mode=StreamMode.SENTENCE,
            chunks=[],
            metadata={
                "display_title": "REPLY",
                "display_lines": [],
                "live_chunk_factory": live_factory,
            },
        )

        report = streamer.execute(plan)

        self.assertEqual(report.chunks_spoken, 2)
        self.assertGreaterEqual(len(display.blocks), 2)
        self.assertIn("light cannot", " ".join(display.blocks[-1]["lines"]))

    def test_display_shortening_prefers_word_boundary(self) -> None:
        voice_output = FakeVoiceOutput(supports_prepare_next=True)
        display = FakeDisplay()
        streamer = ResponseStreamer(
            voice_output=voice_output,
            display=display,
            default_display_seconds=4.0,
            inter_chunk_pause_seconds=0.0,
            max_display_chars_per_line=20,
        )

        plan = ResponsePlan(
            turn_id="turn-display-word-boundary",
            language="en",
            route_kind=RouteKind.CONVERSATION,
            stream_mode=StreamMode.SENTENCE,
            chunks=[
                AssistantChunk(
                    text="Black holes are real regions in space.",
                    kind=ChunkKind.CONTENT,
                )
            ],
            metadata={"display_title": "REPLY"},
        )

        report = streamer.execute(plan)

        self.assertTrue(report.display_lines)
        self.assertEqual(report.display_lines[0], "Black holes are...")

    def test_execute_live_plan_uses_display_update_when_available(self) -> None:
        voice_output = FakeVoiceOutput(supports_prepare_next=True)
        display = _UpdatingDisplay()
        streamer = ResponseStreamer(
            voice_output=voice_output,
            display=display,
            default_display_seconds=4.0,
            inter_chunk_pause_seconds=0.0,
            max_display_chars_per_line=80,
        )

        def live_factory():
            yield AssistantChunk(text="First useful sentence.", kind=ChunkKind.CONTENT)
            yield AssistantChunk(text="Second useful sentence.", kind=ChunkKind.CONTENT)

        plan = ResponsePlan(
            turn_id="turn-live-display-update",
            language="en",
            route_kind=RouteKind.CONVERSATION,
            stream_mode=StreamMode.SENTENCE,
            chunks=[],
            metadata={
                "display_title": "REPLY",
                "display_lines": [],
                "live_chunk_factory": live_factory,
            },
        )

        report = streamer.execute(plan)

        self.assertEqual(report.chunks_spoken, 2)
        self.assertEqual(len(display.blocks), 1)
        self.assertEqual(len(display.update_calls), 1)
        self.assertIn("Second useful sentence.", " ".join(display.update_calls[-1]["lines"]))

    def test_execute_live_plan_dedupes_identical_display_updates(self) -> None:
        voice_output = FakeVoiceOutput(supports_prepare_next=True)
        display = _UpdatingDisplay()
        streamer = ResponseStreamer(
            voice_output=voice_output,
            display=display,
            default_display_seconds=4.0,
            inter_chunk_pause_seconds=0.0,
            max_display_chars_per_line=80,
        )

        def live_factory():
            yield AssistantChunk(text="Same useful sentence.", kind=ChunkKind.CONTENT)
            yield AssistantChunk(text="Same useful sentence.", kind=ChunkKind.CONTENT)

        plan = ResponsePlan(
            turn_id="turn-live-display-dedupe",
            language="en",
            route_kind=RouteKind.CONVERSATION,
            stream_mode=StreamMode.SENTENCE,
            chunks=[],
            metadata={
                "display_title": "REPLY",
                "display_lines": [],
                "live_chunk_factory": live_factory,
            },
        )

        report = streamer.execute(plan)

        self.assertEqual(report.chunks_spoken, 2)
        self.assertEqual(len(display.blocks), 1)
        self.assertEqual(len(display.update_calls), 0)

    def test_execute_live_plan_limits_show_block_fallback_updates(self) -> None:
        voice_output = FakeVoiceOutput(supports_prepare_next=True)
        display = FakeDisplay()
        streamer = ResponseStreamer(
            voice_output=voice_output,
            display=display,
            default_display_seconds=4.0,
            inter_chunk_pause_seconds=0.0,
            max_display_chars_per_line=80,
        )

        def live_factory():
            yield AssistantChunk(text="Black holes are real regions in space.", kind=ChunkKind.CONTENT)
            yield AssistantChunk(text="Their gravity is extremely strong.", kind=ChunkKind.CONTENT)
            yield AssistantChunk(text="Even light cannot escape them.", kind=ChunkKind.CONTENT)
            yield AssistantChunk(text="They can form after massive stars collapse.", kind=ChunkKind.CONTENT)

        plan = ResponsePlan(
            turn_id="turn-live-display-fallback-limited",
            language="en",
            route_kind=RouteKind.CONVERSATION,
            stream_mode=StreamMode.SENTENCE,
            chunks=[],
            metadata={
                "display_title": "REPLY",
                "display_lines": [],
                "live_chunk_factory": live_factory,
            },
        )

        report = streamer.execute(plan)

        self.assertEqual(report.chunks_spoken, 4)
        self.assertEqual(len(display.blocks), 2)
        self.assertIn("massive stars", " ".join(display.blocks[-1]["lines"]))

    def test_execute_live_plan_calls_first_chunk_callback_before_speaking(self) -> None:
        voice_output = FakeVoiceOutput(supports_prepare_next=True)
        display = FakeDisplay()
        events: list[str] = []
        streamer = ResponseStreamer(
            voice_output=voice_output,
            display=display,
            default_display_seconds=4.0,
            inter_chunk_pause_seconds=0.0,
        )

        def live_factory():
            yield AssistantChunk(text="First useful sentence.", kind=ChunkKind.CONTENT)

        plan = ResponsePlan(
            turn_id="turn-live-first-callback",
            language="en",
            route_kind=RouteKind.CONVERSATION,
            stream_mode=StreamMode.SENTENCE,
            chunks=[],
            metadata={
                "display_title": "REPLY",
                "display_lines": [],
                "live_chunk_factory": live_factory,
                "on_first_live_chunk": lambda: events.append("first_chunk"),
            },
        )

        report = streamer.execute(plan)

        self.assertEqual(report.chunks_spoken, 1)
        self.assertEqual(events, ["first_chunk"])

    def test_execute_live_plan_stops_future_chunks_after_interrupt(self) -> None:
        voice_output = FakeVoiceOutput(supports_prepare_next=True)
        display = FakeDisplay()
        calls = {"count": 0}

        def interrupted() -> bool:
            calls["count"] += 1
            return calls["count"] >= 2

        streamer = ResponseStreamer(
            voice_output=voice_output,
            display=display,
            default_display_seconds=4.0,
            inter_chunk_pause_seconds=0.0,
            interrupt_requested=interrupted,
        )

        def live_factory():
            yield AssistantChunk(text="First sentence.", kind=ChunkKind.CONTENT)
            yield AssistantChunk(text="Second sentence.", kind=ChunkKind.CONTENT)
            yield AssistantChunk(text="Third sentence.", kind=ChunkKind.CONTENT)

        plan = ResponsePlan(
            turn_id="turn-live-interrupt",
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

        self.assertEqual(report.chunks_spoken, 1)
        self.assertEqual(len(voice_output.speak_calls), 1)
        self.assertIn("First sentence.", report.full_text)
        self.assertNotIn("Second sentence.", report.full_text)

    def test_execute_live_plan_reports_token_and_speakable_latency(self) -> None:
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
                text="Black holes bend spacetime.",
                kind=ChunkKind.CONTENT,
                sequence_index=0,
                metadata={
                    "first_token_latency_ms": 12.0,
                    "first_speakable_chunk_latency_ms": 34.0,
                    "first_chunk_latency_ms": 34.0,
                },
            )

        plan = ResponsePlan(
            turn_id="turn-live-telemetry",
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

        self.assertEqual(report.first_token_latency_ms, 12.0)
        self.assertEqual(report.first_speakable_chunk_latency_ms, 34.0)
        self.assertEqual(report.first_chunk_latency_ms, 34.0)

    def test_execute_live_plan_measures_first_audio_from_voice_output_report(self) -> None:
        voice_output = _TelemetryVoiceOutput(audio_delay_seconds=0.05)
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
        self.assertGreaterEqual(report.first_audio_latency_ms, 50.0)
        self.assertGreaterEqual(report.first_audio_ms, 50.0)
        self.assertGreaterEqual(report.total_elapsed_ms, 50.0)

    def test_execute_standard_plan_prefers_voice_output_first_audio_report_when_available(self) -> None:
        voice_output = _TelemetryVoiceOutput(audio_delay_seconds=0.05)
        display = FakeDisplay()
        streamer = ResponseStreamer(
            voice_output=voice_output,
            display=display,
            default_display_seconds=4.0,
            inter_chunk_pause_seconds=0.0,
        )

        plan = ResponsePlan(
            turn_id="turn-standard-telemetry",
            language="en",
            route_kind=RouteKind.CONVERSATION,
            stream_mode=StreamMode.SENTENCE,
            chunks=[
                AssistantChunk(text="Let me think.", kind=ChunkKind.ACK, sequence_index=0),
                AssistantChunk(text="The focus timer is active.", kind=ChunkKind.CONTENT, sequence_index=1),
            ],
            metadata={"display_title": "CHAT", "display_lines": ["Let me think."]},
        )

        report = streamer.execute(plan)

        self.assertGreaterEqual(report.first_audio_latency_ms, 45.0)
        self.assertGreaterEqual(report.first_sentence_latency_ms, 45.0)
        self.assertGreaterEqual(report.total_elapsed_ms, 50.0)

    def test_execute_action_single_chunk_defers_display_until_after_first_audio(self) -> None:
        events: list[str] = []
        voice_output = _OrderedVoiceOutput(events)
        display = _OrderedDisplay(events)
        streamer = ResponseStreamer(
            voice_output=voice_output,
            display=display,
            default_display_seconds=4.0,
            inter_chunk_pause_seconds=0.0,
        )

        plan = ResponsePlan(
            turn_id="turn-action-single-chunk",
            language="en",
            route_kind=RouteKind.ACTION,
            stream_mode=StreamMode.SENTENCE,
            chunks=[
                AssistantChunk(
                    text="The timer is already running.",
                    kind=ChunkKind.CONTENT,
                    sequence_index=0,
                ),
            ],
            metadata={
                "display_title": "ACTION",
                "display_lines": ["timer already running"],
            },
        )

        report = streamer.execute(plan)

        self.assertEqual(report.chunks_spoken, 1)
        self.assertEqual(events[:2], ["speak", "display"])
        self.assertEqual(len(voice_output.speak_calls), 1)
        self.assertEqual(voice_output.speak_calls[0]["latency_profile"], "action_fast")
        self.assertEqual(len(display.blocks), 1)


if __name__ == "__main__":
    unittest.main()
