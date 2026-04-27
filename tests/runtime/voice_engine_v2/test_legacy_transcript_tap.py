from __future__ import annotations

import json
from types import SimpleNamespace

from modules.core.assistant_impl.interaction_mixin import CoreAssistantInteractionMixin
from modules.runtime.contracts import RouteDecision, RouteKind
from modules.runtime.voice_engine_v2 import build_voice_engine_v2_runtime


class _FakeInterruptController:
    def clear(self) -> None:
        return None


class _FakeVoiceSession:
    def __init__(self) -> None:
        self.routing_details: list[str] = []

    def transition_to_routing(self, *, detail: str = "") -> None:
        self.routing_details.append(str(detail or ""))


class _FakeBenchmarkService:
    def __init__(self) -> None:
        self.route_events: list[dict[str, object]] = []

    def begin_turn(self, *, user_text: str, language: str, input_source: str = "voice") -> str:
        return "benchmark-shadow-turn"

    def note_route_resolved(self, *, route_kind: str, primary_intent: str, confidence: float) -> None:
        self.route_events.append(
            {
                "route_kind": route_kind,
                "primary_intent": primary_intent,
                "confidence": confidence,
            }
        )


class _RaisingShadowHook:
    def __init__(self) -> None:
        self.calls = 0

    def observe_legacy_turn(self, **kwargs):
        self.calls += 1
        raise RuntimeError("shadow hook failed intentionally")


class _CountingShadowHook:
    def __init__(self) -> None:
        self.calls = 0

    def observe_legacy_turn(self, **kwargs):
        self.calls += 1
        return None


class _LegacyTranscriptTapAssistant(CoreAssistantInteractionMixin):
    def __init__(
        self,
        *,
        shadow_log_path: str,
        shadow_mode_enabled: bool,
        route: RouteDecision | None = None,
        fast_lane_result: bool | None = None,
        shadow_hook: object | None = None,
        transcript: str = "show desktop",
    ) -> None:
        bundle = build_voice_engine_v2_runtime(
            {
                "voice_engine": {
                    "enabled": True,
                    "version": "v2",
                    "mode": "v2",
                    "realtime_audio_bus_enabled": True,
                    "vad_endpointing_enabled": True,
                    "command_first_enabled": True,
                    "fallback_to_legacy_enabled": True,
                    "metrics_enabled": True,
                    "shadow_mode_enabled": shadow_mode_enabled,
                    "shadow_log_path": shadow_log_path,
                    "legacy_removal_stage": "after_acceptance",
                }
            }
        )
        runtime_hook = shadow_hook if shadow_hook is not None else bundle.shadow_runtime_hook
        self.settings = {
            "voice_engine": {
                "shadow_mode_enabled": shadow_mode_enabled,
            }
        }
        self.runtime = SimpleNamespace(
            metadata={
                "voice_engine_v2_shadow_runtime_hook": runtime_hook,
                "voice_engine_v2_metadata": bundle.to_metadata(),
            }
        )
        self.voice_engine_v2_shadow_runtime_hook = runtime_hook
        self.interrupt_controller = _FakeInterruptController()
        self.voice_session = _FakeVoiceSession()
        self.turn_benchmark_service = _FakeBenchmarkService()
        self.command_flow = SimpleNamespace(log_route_decision=lambda route: None)
        self.route = route or _visual_shell_route(transcript)
        self.fast_lane_result = fast_lane_result
        self.last_language = "en"
        self.pending_confirmation = None
        self.pending_follow_up = None
        self.route_calls = 0
        self.dispatched: list[tuple[str, str]] = []
        self.finished_telemetry: dict[str, object] = {}
        self._last_fast_lane_route_snapshot: dict[str, object] = {}
        self._last_input_capture = {
            "input_source": "voice",
            "language": "en",
            "backend_label": "faster-whisper",
            "mode": "command",
            "phase": "command",
            "metadata": {
                "capture_origin": "unit_test",
                "capture_finished_at_monotonic": 22.0,
            },
        }

    def _tick_ai_broker(self) -> None:
        return None

    def _prepare_command(self, text: str, **kwargs):
        return {
            "ignore": False,
            "language": "en",
            "source": SimpleNamespace(value="voice"),
            "capture_phase": "command",
            "capture_mode": "command",
            "capture_backend": "faster-whisper",
            "routing_text": text,
            "normalized_text": text.lower(),
            "already_remembered": True,
            "cancel_requested": False,
        }

    def _commit_language(self, language: str) -> str:
        self.last_language = str(language or "en")
        return self.last_language

    def _handle_pending_state(self, prepared):
        return None

    def _handle_fast_lane(self, prepared):
        if self.fast_lane_result is None:
            return None

        self._last_fast_lane_route_snapshot = {
            "route_kind": "action",
            "route_confidence": 0.98,
            "primary_intent": "visual_shell.show_desktop",
            "topics": ["visual_shell"],
            "route_notes": ["deterministic_visual_shell_command"],
            "route_metadata": {"lane": "visual_shell_command"},
        }
        return self.fast_lane_result

    def _route_command(self, text: str, **kwargs):
        self.route_calls += 1
        return self.route

    def _coerce_route_decision(self, routed, **kwargs):
        return routed

    def _execute_action_route(self, route, language: str) -> bool:
        self.dispatched.append((str(route.primary_intent), language))
        return True

    def _handle_mixed_route(self, route, language: str) -> bool:
        self.dispatched.append(("mixed", language))
        return True

    def _handle_conversation_route(self, route, language: str) -> bool:
        self.dispatched.append(("conversation", language))
        return True

    def _handle_unclear_route(self, route, language: str) -> bool:
        self.dispatched.append(("unclear", language))
        return True

    def _finish_turn_telemetry(self, telemetry):
        self.finished_telemetry = dict(telemetry)


def _visual_shell_route(transcript: str = "show desktop") -> RouteDecision:
    return RouteDecision(
        turn_id="legacy-route-turn",
        raw_text=transcript,
        normalized_text=transcript.lower(),
        language="en",
        kind=RouteKind.ACTION,
        confidence=0.98,
        primary_intent="visual_shell.show_desktop",
        intents=[],
        conversation_topics=["visual_shell"],
        tool_invocations=[],
        notes=["unit_test_legacy_route"],
        metadata={
            "capture_phase": "command",
            "capture_mode": "command",
            "capture_backend": "faster-whisper",
        },
    )


def test_guarded_legacy_transcript_tap_does_nothing_when_shadow_mode_disabled(tmp_path) -> None:
    shadow_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    shadow_hook = _CountingShadowHook()
    assistant = _LegacyTranscriptTapAssistant(
        shadow_log_path=str(shadow_path),
        shadow_mode_enabled=False,
        shadow_hook=shadow_hook,
    )

    handled = assistant.handle_command("show desktop")

    assert handled is True
    assert shadow_hook.calls == 0
    assert assistant.dispatched == [("visual_shell.show_desktop", "en")]
    assert assistant.finished_telemetry["result"] == "action_route"
    assert "voice_engine_v2_shadow_invoked" not in assistant.finished_telemetry
    assert shadow_path.exists() is False


def test_guarded_legacy_transcript_tap_records_shadow_telemetry_without_changing_normal_route(tmp_path) -> None:
    shadow_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    assistant = _LegacyTranscriptTapAssistant(
        shadow_log_path=str(shadow_path),
        shadow_mode_enabled=True,
    )

    handled = assistant.handle_command("show desktop")

    assert handled is True
    assert assistant.dispatched == [("visual_shell.show_desktop", "en")]
    assert assistant.route_calls == 1
    assert assistant.finished_telemetry["route_kind"] == "action"
    assert assistant.finished_telemetry["primary_intent"] == "visual_shell.show_desktop"
    assert assistant.finished_telemetry["voice_engine_v2_shadow_invoked"] is True
    assert assistant.finished_telemetry["voice_engine_v2_shadow_action_executed"] is False

    lines = shadow_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["turn_id"] == "legacy-route-turn"
    assert record["transcript"] == "show desktop"
    assert record["legacy_route"] == "action"
    assert record["legacy_intent_key"] == "visual_shell.show_desktop"
    assert record["voice_engine_intent_key"] == "visual_shell.show_desktop"
    assert record["action_executed"] is False
    assert record["legacy_runtime_primary"] is True
    assert record["metadata"]["source"] == "legacy_runtime_transcript_tap"
    assert record["metadata"]["route_path"] == "normal_route"
    assert record["metadata"]["handled"] is True
    assert record["metadata"]["shadow_runtime_hook"] is True
    assert record["metadata"]["action_safe"] is True


def test_guarded_legacy_transcript_tap_observes_fast_lane_after_live_fast_path(tmp_path) -> None:
    shadow_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    assistant = _LegacyTranscriptTapAssistant(
        shadow_log_path=str(shadow_path),
        shadow_mode_enabled=True,
        fast_lane_result=True,
    )

    handled = assistant.handle_command("show desktop")

    assert handled is True
    assert assistant.route_calls == 0
    assert assistant.dispatched == []
    assert assistant.finished_telemetry["result"] == "fast_lane"
    assert assistant.finished_telemetry["handled"] is True
    assert assistant.finished_telemetry["primary_intent"] == "visual_shell.show_desktop"
    assert assistant.finished_telemetry["voice_engine_v2_shadow_invoked"] is True
    assert assistant.finished_telemetry["voice_engine_v2_shadow_action_executed"] is False

    record = json.loads(shadow_path.read_text(encoding="utf-8").splitlines()[0])
    assert record["turn_id"] == "benchmark-shadow-turn"
    assert record["legacy_route"] == "action"
    assert record["legacy_intent_key"] == "visual_shell.show_desktop"
    assert record["voice_engine_intent_key"] == "visual_shell.show_desktop"
    assert record["action_executed"] is False
    assert record["metadata"]["route_path"] == "fast_lane"
    assert record["metadata"]["handled"] is True


def test_guarded_legacy_transcript_tap_is_fail_open_when_hook_raises(tmp_path) -> None:
    shadow_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    shadow_hook = _RaisingShadowHook()
    assistant = _LegacyTranscriptTapAssistant(
        shadow_log_path=str(shadow_path),
        shadow_mode_enabled=True,
        shadow_hook=shadow_hook,
    )

    handled = assistant.handle_command("show desktop")

    assert handled is True
    assert shadow_hook.calls == 1
    assert assistant.dispatched == [("visual_shell.show_desktop", "en")]
    assert assistant.finished_telemetry["result"] == "action_route"
    assert assistant.finished_telemetry["voice_engine_v2_shadow_error"] == "RuntimeError"
    assert shadow_path.exists() is False


def test_guarded_legacy_transcript_tap_does_not_observe_empty_transcript(tmp_path) -> None:
    shadow_path = tmp_path / "voice_engine_v2_shadow.jsonl"
    shadow_hook = _CountingShadowHook()
    assistant = _LegacyTranscriptTapAssistant(
        shadow_log_path=str(shadow_path),
        shadow_mode_enabled=True,
        shadow_hook=shadow_hook,
    )

    handled = assistant.handle_command("   ")

    assert handled is True
    assert shadow_hook.calls == 0
    assert assistant.dispatched == []
    assert assistant.finished_telemetry == {}
    assert shadow_path.exists() is False