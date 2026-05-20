from __future__ import annotations

import unittest

from modules.core.assistant_impl.response_mixin import CoreAssistantResponseMixin
from modules.presentation.response_streamer.models import StreamExecutionReport
from modules.presentation.response_streamer.streamer import ResponseStreamer
from modules.runtime.contracts import AssistantChunk, ChunkKind, ResponsePlan, RouteKind, StreamMode
from tests.support.fakes import FakeDisplay, FakeVoiceOutput


class FakeVoiceSession:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def transition_to_speaking(self, *, detail: str) -> None:
        self.events.append(("speaking", str(detail)))

    def transition_to_shutdown(self, *, detail: str) -> None:
        self.events.append(("shutdown", str(detail)))

    def mark_response_finished(self, *, detail: str) -> None:
        self.events.append(("finished", str(detail)))


class EmptyReportStreamer:
    def execute(self, plan: ResponsePlan) -> StreamExecutionReport:
        del plan
        return StreamExecutionReport(
            chunks_spoken=0,
            full_text="",
            display_title="CHAT",
            display_lines=[],
        )


class FailingVoiceOutput(FakeVoiceOutput):
    def speak(self, text: str, **kwargs) -> bool:
        self.speak_calls.append({"text": str(text), **kwargs})
        self._last_speak_report = {
            "text": str(text),
            "success": False,
            "engine": "fake",
            "playback_backend": "fake",
            "playback_command": "fake-play",
            "playback_exit_code": 1,
            "playback_stderr": "simulated playback failure",
            "playback_process_started": True,
            "audio_file_exists": True,
            "audio_file_size_bytes": 128,
        }
        return False


class DummyAssistant(CoreAssistantResponseMixin):
    ASSISTANT_NAME = "NeXa"

    def __init__(self, response_streamer) -> None:
        self.voice_out = FakeVoiceOutput(supports_prepare_next=True)
        self.display = FakeDisplay()
        self.voice_session = FakeVoiceSession()
        self.response_streamer = response_streamer
        self.default_overlay_seconds = 4.0
        self.settings = {
            "streaming": {
                "prefetch_text_responses": True,
                "prefetch_text_response_max_chars": 220,
            }
        }
        self.shutdown_requested = False
        self.stream_mode = StreamMode.SENTENCE
        self._last_response_stream_report = None
        self._last_response_delivery_snapshot = None
        self.remembered_turns: list[dict[str, object]] = []
        self.thinking_ack_stops = 0

    def _thinking_ack_stop(self) -> None:
        self.thinking_ack_stops += 1

    def _display_lines(self, text: str) -> list[str]:
        return [str(text).strip()]

    def _remember_assistant_turn(self, text: str, *, language: str, metadata: dict[str, object]) -> None:
        self.remembered_turns.append(
            {
                "text": str(text),
                "language": str(language),
                "metadata": dict(metadata),
            }
        )

    def _localized(self, language: str, polish: str, english: str) -> str:
        return polish if str(language).strip().lower() == "pl" else english


class ResponseDeliveryTests(unittest.TestCase):
    def test_deliver_response_plan_executes_live_plan_without_static_chunks(self) -> None:
        voice_output = FakeVoiceOutput(supports_prepare_next=True)
        display = FakeDisplay()
        streamer = ResponseStreamer(
            voice_output=voice_output,
            display=display,
            default_display_seconds=4.0,
            inter_chunk_pause_seconds=0.0,
        )
        assistant = DummyAssistant(streamer)
        assistant.voice_out = voice_output
        assistant.display = display

        def live_factory():
            yield AssistantChunk(text="Black holes are collapsed regions of spacetime.", kind=ChunkKind.CONTENT)
            yield AssistantChunk(text="Their gravity is so strong that even light cannot escape.", kind=ChunkKind.CONTENT)

        plan = ResponsePlan(
            turn_id="turn-live-delivery",
            language="en",
            route_kind=RouteKind.CONVERSATION,
            stream_mode=StreamMode.SENTENCE,
            metadata={
                "display_title": "CHAT",
                "display_lines": [],
                "live_chunk_factory": live_factory,
            },
        )

        delivered = assistant.deliver_response_plan(
            plan,
            source="test_dialogue_flow",
            remember=True,
        )

        self.assertTrue(delivered)
        self.assertEqual(len(voice_output.speak_calls), 2)
        self.assertEqual(len(assistant.remembered_turns), 1)
        self.assertIn("Black holes", assistant.remembered_turns[0]["text"])
        self.assertIsNotNone(assistant._last_response_stream_report)
        self.assertTrue(assistant._last_response_stream_report.live_streaming)
        self.assertEqual(assistant._last_response_stream_report.chunks_spoken, 2)
        self.assertIsNotNone(assistant._last_response_delivery_snapshot)
        self.assertEqual(assistant._last_response_delivery_snapshot["source"], "test_dialogue_flow")
        self.assertEqual(assistant._last_response_delivery_snapshot["route_kind"], "conversation")
        self.assertTrue(assistant._last_response_delivery_snapshot["remembered"])

    def test_deliver_text_response_prefetches_short_text_before_delivery(self) -> None:
        assistant = DummyAssistant(EmptyReportStreamer())

        delivered = assistant.deliver_text_response(
            "The timer is already running.",
            language="en",
            route_kind=RouteKind.ACTION,
            source="test_action_status",
        )

        self.assertTrue(delivered)
        self.assertEqual(len(assistant.voice_out.prepare_calls), 1)
        self.assertEqual(
            assistant.voice_out.prepare_calls[0],
            ("The timer is already running.", "en"),
        )
        self.assertEqual(len(assistant.voice_out.speak_calls), 1)
        self.assertEqual(
            assistant.voice_out.speak_calls[0]["text"],
            "The timer is already running.",
        )
        self.assertEqual(assistant.thinking_ack_stops, 1)

    def test_deliver_response_plan_falls_back_when_stream_report_is_empty(self) -> None:
        assistant = DummyAssistant(EmptyReportStreamer())

        plan = ResponsePlan(
            turn_id="turn-fallback",
            language="en",
            route_kind=RouteKind.CONVERSATION,
            stream_mode=StreamMode.SENTENCE,
        )
        plan.add_text("This is the fallback answer.", kind=ChunkKind.CONTENT, mode=StreamMode.SENTENCE)

        delivered = assistant.deliver_response_plan(
            plan,
            source="test_dialogue_flow",
            remember=True,
        )

        self.assertTrue(delivered)
        self.assertEqual(len(assistant.voice_out.speak_calls), 1)
        self.assertEqual(assistant.voice_out.speak_calls[0]["text"], "This is the fallback answer.")
        self.assertEqual(len(assistant.remembered_turns), 1)
        self.assertEqual(assistant.remembered_turns[0]["text"], "This is the fallback answer.")
        self.assertIsNotNone(assistant._last_response_stream_report)
        self.assertEqual(assistant._last_response_stream_report.full_text, "This is the fallback answer.")

    def test_playback_failure_does_not_report_delivered_true(self) -> None:
        assistant = DummyAssistant(EmptyReportStreamer())
        assistant.voice_out = FailingVoiceOutput()

        delivered = assistant.deliver_text_response(
            "The time is ten thirty.",
            language="en",
            route_kind=RouteKind.ACTION,
            source="action_flow:ask_time",
        )

        self.assertFalse(delivered)
        self.assertIsNotNone(assistant._last_response_delivery_snapshot)
        self.assertFalse(assistant._last_response_delivery_snapshot["delivered"])
        self.assertFalse(assistant._last_response_delivery_snapshot["tts_delivered"])
        self.assertEqual(assistant._last_response_delivery_snapshot["playback_backend"], "fake")
        self.assertEqual(assistant._last_response_delivery_snapshot["playback_exit_code"], 1)
        self.assertEqual(
            assistant._last_response_delivery_snapshot["last_tts_error"],
            "simulated playback failure",
        )

    def test_time_response_does_not_block_next_tts_response(self) -> None:
        assistant = DummyAssistant(EmptyReportStreamer())

        first_delivered = assistant.deliver_text_response(
            "19 55",
            language="en",
            route_kind=RouteKind.ACTION,
            source="action_flow:ask_time",
            metadata={"time_action_mode": "spoken_only"},
        )
        second_delivered = assistant.deliver_text_response(
            "Okay.",
            language="en",
            route_kind=RouteKind.ACTION,
            source="action_flow:exit",
        )

        self.assertTrue(first_delivered)
        self.assertTrue(second_delivered)
        self.assertEqual(len(assistant.voice_out.speak_calls), 2)
        self.assertEqual(assistant.voice_out.speak_calls[0]["text"], "19 55")
        self.assertEqual(assistant.voice_out.speak_calls[1]["text"], "Okay.")

    def test_deliver_response_plan_recovers_when_live_stream_returns_nothing(self) -> None:
        assistant = DummyAssistant(EmptyReportStreamer())

        def live_factory():
            if False:
                yield None

        plan = ResponsePlan(
            turn_id="turn-live-empty",
            language="en",
            route_kind=RouteKind.CONVERSATION,
            stream_mode=StreamMode.SENTENCE,
            metadata={
                "display_title": "CHAT",
                "display_lines": [],
                "live_chunk_factory": live_factory,
            },
        )

        delivered = assistant.deliver_response_plan(
            plan,
            source="test_dialogue_flow",
            remember=True,
        )

        self.assertTrue(delivered)
        self.assertEqual(len(assistant.voice_out.speak_calls), 1)
        self.assertIn("could not generate an answer", assistant.voice_out.speak_calls[0]["text"].lower())
        self.assertEqual(len(assistant.remembered_turns), 1)
        self.assertIn("could not generate an answer", assistant.remembered_turns[0]["text"].lower())
        self.assertFalse(assistant.shutdown_requested)
        self.assertIn(("finished", "response_complete"), assistant.voice_session.events)


if __name__ == "__main__":
    unittest.main()
