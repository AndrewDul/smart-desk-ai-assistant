from __future__ import annotations

import importlib.util
import time
import unittest
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "modules"
    / "core"
    / "assistant_impl"
    / "interaction_mixin.py"
)
spec = importlib.util.spec_from_file_location("interaction_mixin_under_test", _MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("Failed to load interaction_mixin module for tests.")
_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_module)
CoreAssistantInteractionMixin = _module.CoreAssistantInteractionMixin


class _FakeBenchmarkService:
    def __init__(self) -> None:
        self.finish_calls: list[dict[str, object]] = []

    def finish_turn(self, *, telemetry, llm_snapshot, response_report):
        self.finish_calls.append(
            {
                "telemetry": dict(telemetry),
                "llm_snapshot": dict(llm_snapshot or {}),
                "response_report": response_report,
            }
        )
        return {
            "wake_to_listen_ms": 10.0,
            "listen_to_speech_ms": 20.0,
            "speech_to_route_ms": 30.0,
            "route_to_first_audio_ms": 40.0,
        }


class _InteractionProbe(CoreAssistantInteractionMixin):
    def __init__(
        self,
        *,
        llm_snapshot: dict[str, object] | None = None,
        response_delivery: dict[str, object] | None = None,
        dialogue_snapshot: dict[str, object] | None = None,
    ) -> None:
        self.turn_benchmark_service = _FakeBenchmarkService()
        self._last_response_stream_report = None
        self._last_response_delivery_snapshot = None
        self.overlay_refresh_reasons: list[str] = []
        self._probe_llm_snapshot = dict(llm_snapshot or {})
        self._probe_response_delivery = dict(response_delivery or {})
        self._probe_dialogue_snapshot = dict(dialogue_snapshot or {})

    def _collect_llm_snapshot(self) -> dict[str, object]:
        return dict(self._probe_llm_snapshot)

    def _collect_response_stream_report(self):
        return None

    def _collect_response_delivery_snapshot(self) -> dict[str, object]:
        return dict(self._probe_response_delivery)

    def _collect_dialogue_result_snapshot(self) -> dict[str, object]:
        return dict(self._probe_dialogue_snapshot)

    def _refresh_developer_overlay(self, *, reason: str) -> None:
        self.overlay_refresh_reasons.append(str(reason))


class TurnDeveloperOverlayRefreshTests(unittest.TestCase):
    def test_finish_turn_telemetry_refreshes_developer_overlay(self) -> None:
        probe = _InteractionProbe()

        probe._finish_turn_telemetry(
            {
                "started_at": time.perf_counter() - 0.05,
                "result": "action_route",
                "handled": True,
                "input_source": "voice",
                "language": "en",
                "stt_backend": "faster_whisper",
                "stt_mode": "command",
                "stt_phase": "command",
                "route_kind": "action",
                "route_confidence": 0.99,
                "primary_intent": "status",
                "topics": ["status"],
            }
        )

        self.assertEqual(probe.overlay_refresh_reasons, ["turn_finished"])
        self.assertEqual(len(probe.turn_benchmark_service.finish_calls), 1)
        self.assertIsNone(probe._last_response_stream_report)
        self.assertEqual(probe._last_response_delivery_snapshot, None)
        
        
    def test_finish_turn_telemetry_drops_stale_llm_snapshot_for_pending_flow(self) -> None:
        probe = _InteractionProbe(
            llm_snapshot={
                "ok": True,
                "latency_ms": 1200.0,
                "first_chunk_latency_ms": 640.0,
                "source": "hailo-ollama",
                "error": "",
            },
            response_delivery={},
            dialogue_snapshot={},
        )

        probe._finish_turn_telemetry(
            {
                "started_at": time.perf_counter() - 0.05,
                "result": "pending_flow",
                "handled": True,
                "input_source": "voice",
                "language": "en",
                "stt_backend": "faster_whisper",
                "stt_mode": "follow_up",
                "stt_phase": "follow_up",
                "route_kind": "",
                "route_confidence": 0.0,
                "primary_intent": "",
                "topics": [],
            }
        )

        self.assertEqual(len(probe.turn_benchmark_service.finish_calls), 1)
        self.assertEqual(
            probe.turn_benchmark_service.finish_calls[0]["llm_snapshot"],
            {},
        )

if __name__ == "__main__":
    unittest.main()