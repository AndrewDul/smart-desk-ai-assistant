from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.presentation.response_streamer.models import StreamExecutionReport
from modules.runtime.telemetry import TurnBenchmarkService


class TurnBenchmarkServiceTests(unittest.TestCase):
    def test_finish_turn_persists_sample_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "turn_benchmarks.json"
            service = TurnBenchmarkService(
                enabled=True,
                persist_turns=True,
                path=path,
                max_samples=10,
                summary_window=5,
            )

            service.note_wake_detected(
                source="wake_gate",
                input_source="wake_word",
                latency_ms=35.0,
                backend_label="openwakeword",
            )
            turn_id = service.begin_turn(user_text="what time is it", language="en")
            service.note_wake_acknowledged(
                text="Yes?",
                strategy="fast",
                latency_ms=72.0,
                output_hold_seconds=0.04,
            )
            service.note_listening_started(phase="command")
            service.note_speech_finalized(
                text="what time is it",
                phase="command",
                language="en",
                input_source="voice",
                latency_ms=180.0,
                audio_duration_ms=1450.0,
                backend_label="faster-whisper",
                mode="command",
                confidence=0.91,
            )
            service.note_route_resolved(
                route_kind="action",
                primary_intent="time_query",
                confidence=0.95,
            )

            response_report = StreamExecutionReport(
                chunks_spoken=1,
                full_text="It is 10 o'clock.",
                display_title="ACTION",
                display_lines=["It is 10"],
                first_audio_latency_ms=120.0,
                total_elapsed_ms=340.0,
                started_at_monotonic=1.0,
                first_audio_started_at_monotonic=1.12,
                finished_at_monotonic=1.34,
                chunk_kinds=["content"],
                live_streaming=False,
            )

            sample = service.finish_turn(
                telemetry={
                    "benchmark_turn_id": turn_id,
                    "total_ms": 950.0,
                    "result": "action_done",
                    "handled": True,
                    "route_kind": "action",
                    "route_confidence": 0.95,
                    "primary_intent": "time_query",
                    "topics": ["time"],
                    "language": "en",
                    "input_source": "voice",
                    "user_text": "what time is it",
                    "capture_metadata": {
                        "capture_profile": "command",
                        "capture_timeout_seconds": 4.2,
                        "capture_end_silence_seconds": 0.32,
                        "capture_min_speech_seconds": 0.12,
                        "capture_pre_roll_seconds": 0.18,
                    },
                    "capture_handoff": {
                        "target_owner": "voice_input",
                        "applied_owner": "voice_input",
                        "wake_backend_label": "runtime.wake_gate",
                        "wake_backend_released": True,
                        "voice_input_released": False,
                        "blocked_observed": True,
                        "wait_completed": True,
                        "wait_elapsed_ms": 58.0,
                        "settle_seconds": 0.04,
                        "source_phase": "command",
                        "strategy": "wake_prime_reuse",
                        "reused": True,
                        "reuse_age_ms": 34.0,
                    },
                },
                llm_snapshot={
                    "ok": True,
                    "latency_ms": 210.0,
                    "first_chunk_latency_ms": 85.0,
                    "source": "hailo-ollama",
                    "error": "",
                },
                response_report=response_report,
            )

            self.assertEqual(sample["turn_id"], turn_id)
            self.assertEqual(sample["result"], "action_done")
            self.assertEqual(sample["route_kind"], "action")
            self.assertAlmostEqual(sample["total_turn_ms"], 950.0)
            self.assertAlmostEqual(sample["response_first_audio_ms"], 120.0)
            self.assertAlmostEqual(sample["llm_first_chunk_ms"], 85.0)
            self.assertEqual(sample["wake_input_source"], "wake_word")
            self.assertAlmostEqual(sample["wake_latency_ms"], 35.0)
            self.assertEqual(sample["wake_backend_label"], "openwakeword")
            self.assertAlmostEqual(sample["wake_ack_latency_ms"], 72.0)
            self.assertEqual(sample["wake_ack_text"], "Yes?")
            self.assertEqual(sample["wake_ack_strategy"], "fast")
            self.assertAlmostEqual(sample["wake_ack_output_hold_seconds"], 0.04)
            self.assertEqual(sample["stt_backend_label"], "faster-whisper")
            self.assertEqual(sample["stt_mode"], "command")
            self.assertAlmostEqual(sample["stt_confidence"], 0.91)
            self.assertEqual(sample["capture_profile"], "command")
            self.assertAlmostEqual(sample["capture_timeout_seconds"], 4.2)
            self.assertAlmostEqual(sample["capture_end_silence_seconds"], 0.32)
            self.assertAlmostEqual(sample["capture_min_speech_seconds"], 0.12)
            self.assertAlmostEqual(sample["capture_pre_roll_seconds"], 0.18)
            self.assertEqual(sample["capture_handoff_target_owner"], "voice_input")
            self.assertEqual(sample["capture_handoff_applied_owner"], "voice_input")
            self.assertEqual(sample["capture_handoff_wake_backend_label"], "runtime.wake_gate")
            self.assertEqual(sample["capture_handoff_strategy"], "wake_prime_reuse")
            self.assertEqual(sample["capture_handoff_source_phase"], "command")
            self.assertTrue(sample["capture_handoff_reused"])
            self.assertTrue(sample["capture_handoff_wait_completed"])
            self.assertTrue(sample["capture_handoff_blocked_observed"])
            self.assertTrue(sample["capture_handoff_wake_backend_released"])
            self.assertAlmostEqual(sample["capture_handoff_wait_elapsed_ms"], 58.0)
            self.assertAlmostEqual(sample["capture_handoff_settle_seconds"], 0.04)
            self.assertAlmostEqual(sample["capture_handoff_reuse_age_ms"], 34.0)
            self.assertTrue(sample["voice_benchmark_ready"])

            latest_sample = service.latest_sample()
            latest_summary = service.latest_summary()
            latest_snapshot = service.latest_snapshot()

            self.assertEqual(latest_sample["turn_id"], turn_id)
            self.assertEqual(latest_summary["sample_count"], 1)
            self.assertEqual(latest_summary["last_turn_id"], turn_id)
            self.assertEqual(latest_snapshot["latest_sample"]["turn_id"], turn_id)
            self.assertTrue(latest_snapshot["overlay_lines"])

            payload = service._store.read()
            self.assertEqual(len(payload["samples"]), 1)
            self.assertEqual(payload["summary"]["sample_count"], 1)
            self.assertEqual(payload["summary"]["last_turn_id"], turn_id)


    def test_finish_turn_persists_skill_timing_markers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "turn_benchmarks_skill_markers.json"
            service = TurnBenchmarkService(
                enabled=True,
                persist_turns=True,
                path=path,
                max_samples=10,
                summary_window=5,
            )

            service.note_wake_detected(source="wake_gate")
            turn_id = service.begin_turn(user_text="start a timer", language="en")
            service.note_listening_started(phase="command")
            service.note_speech_finalized(text="start a timer", phase="command")
            service.note_route_resolved(
                route_kind="action",
                primary_intent="timer_start",
                confidence=0.94,
            )
            service.note_skill_started(action="timer_start", source="timer_start")
            service.note_skill_finished(
                action="timer_start",
                status="accepted",
                source="timer_service.start",
            )

            response_started_at = service._active_trace.skill_started_at_monotonic + 0.020
            first_audio_started_at = response_started_at + 0.100
            report = StreamExecutionReport(
                chunks_spoken=1,
                full_text="Focus timer started.",
                display_title="ACTION",
                display_lines=["focus timer started"],
                first_audio_latency_ms=100.0,
                total_elapsed_ms=220.0,
                started_at_monotonic=response_started_at,
                first_audio_started_at_monotonic=first_audio_started_at,
                finished_at_monotonic=response_started_at + 0.220,
                chunk_kinds=["content"],
                live_streaming=False,
            )

            sample = service.finish_turn(
                telemetry={
                    "benchmark_turn_id": turn_id,
                    "total_ms": 450.0,
                    "result": "action_route",
                    "handled": True,
                    "route_kind": "action",
                    "primary_intent": "timer_start",
                    "route_confidence": 0.94,
                },
                llm_snapshot={},
                response_report=report,
            )

            self.assertEqual(sample["skill_action"], "timer_start")
            self.assertEqual(sample["skill_status"], "accepted")
            self.assertEqual(sample["skill_source"], "timer_service.start")
            self.assertIsNotNone(sample["route_to_skill_start_ms"])
            self.assertIsNotNone(sample["skill_execution_window_ms"])
            self.assertIsNotNone(sample["skill_to_response_start_ms"])
            self.assertIsNotNone(sample["skill_to_first_audio_ms"])



    def test_annotate_last_completed_turn_updates_latest_sample_and_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "annotated_benchmarks.json"
            service = TurnBenchmarkService(
                enabled=True,
                persist_turns=True,
                path=path,
                max_samples=10,
                summary_window=5,
            )

            service.note_wake_detected(source="wake_gate")
            turn_id = service.begin_turn(user_text="hello", language="en")
            service.note_listening_started(phase="command")
            service.note_speech_finalized(text="hello", phase="command")
            service.note_route_resolved(
                route_kind="conversation",
                primary_intent="smalltalk",
                confidence=0.8,
            )
            service.finish_turn(
                telemetry={
                    "benchmark_turn_id": turn_id,
                    "total_ms": 700.0,
                    "result": "conversation_route",
                    "handled": True,
                },
                llm_snapshot=None,
                response_report=None,
            )

            updated = service.annotate_last_completed_turn(
                resume_policy={"action": "grace", "reason": "response_delivered"},
                command_window_policy={"action": "retry", "phase": "grace"},
            )

            self.assertTrue(updated)
            latest_sample = service.latest_sample()
            self.assertEqual(latest_sample["resume_policy"]["action"], "grace")
            self.assertEqual(latest_sample["command_window_policy"]["phase"], "grace")

            payload = service._store.read()
            self.assertEqual(payload["samples"][-1]["resume_policy"]["action"], "grace")
            self.assertEqual(payload["samples"][-1]["command_window_policy"]["action"], "retry")

    def test_max_samples_trims_old_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "trimmed_benchmarks.json"
            service = TurnBenchmarkService(
                enabled=True,
                persist_turns=True,
                path=path,
                max_samples=20,
                summary_window=5,
            )

            for index in range(25):
                service.note_wake_detected(source=f"wake:{index}")
                turn_id = service.begin_turn(user_text=f"cmd {index}", language="en")
                service.note_listening_started(phase="command")
                service.note_speech_finalized(text=f"cmd {index}", phase="command")
                service.note_route_resolved(
                    route_kind="action",
                    primary_intent="test",
                    confidence=1.0,
                )
                service.finish_turn(
                    telemetry={
                        "benchmark_turn_id": turn_id,
                        "total_ms": 100.0 + index,
                        "result": "ok",
                        "handled": True,
                    },
                    llm_snapshot=None,
                    response_report=None,
                )

            payload = service._store.read()
            self.assertEqual(len(payload["samples"]), 20)
            self.assertEqual(payload["summary"]["sample_count"], 20)
            self.assertEqual(payload["summary"]["window_size"], 5)

            latest_sample = service.latest_sample()
            latest_summary = service.latest_summary()

            self.assertEqual(latest_summary["sample_count"], 20)
            self.assertEqual(latest_sample["result"], "ok")
            kept_ids = [item["turn_id"] for item in payload["samples"]]
            self.assertEqual(len(set(kept_ids)), 20)


    def test_note_speech_finalized_uses_capture_finished_timestamp_when_provided(self) -> None:
        service = TurnBenchmarkService(
            enabled=True,
            persist_turns=False,
            path="/tmp/turn_benchmarks.json",
            max_samples=20,
            summary_window=5,
        )

        service.note_wake_detected(source="wake_gate")
        service.begin_turn(user_text="hello", language="en")
        service.note_listening_started(phase="command")
        service.note_speech_finalized(
            text="hello",
            phase="command",
            finalized_at_monotonic=12.5,
            latency_ms=180.0,
        )

        self.assertAlmostEqual(service._active_trace.speech_finalized_at_monotonic, 12.5)
        self.assertAlmostEqual(service._active_trace.speech_latency_ms, 180.0)



if __name__ == "__main__":
    unittest.main()