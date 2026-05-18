from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from modules.presentation.visual_shell.feedback.feedback_center_snapshot import (
    build_feedback_center_snapshot,
)
from modules.presentation.visual_shell.service import BatteryReading, TemperatureReading


@dataclass(slots=True)
class FakeRuntimeProduct:
    def snapshot(self) -> dict[str, Any]:
        return {
            "lifecycle_state": "ready",
            "ready": True,
            "llm_enabled": True,
            "llm_runner": "llama-server",
            "llm_state": "ready",
            "llm_available": True,
            "warnings": [],
        }


@dataclass(slots=True)
class FakeLocalLLM:
    def describe_backend(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "runner": "llama-server",
            "server_url": "http://127.0.0.1:8000",
            "server_model_name": "Qwen2.5-1.5B-Instruct-Q4_K_M",
            "last_generation_source": "server_stream",
            "health": {"state": "ready", "available": True},
        }


@dataclass(slots=True)
class FakeDialogue:
    local_llm: FakeLocalLLM = field(default_factory=FakeLocalLLM)


class FakeMemory:
    def list_people(self, *, language=None) -> list[dict[str, Any]]:
        return [{"display_name": "Tomek"}, {"display_name": "Dominika"}]

    def list_objects(self, *, language=None) -> list[dict[str, Any]]:
        return [{"display_name": "Vape"}]


@dataclass(slots=True)
class FakeMetricsProvider:
    def read_battery(self) -> BatteryReading | None:
        return BatteryReading(percent=81, source="unit-test")

    def read_temperature(self) -> TemperatureReading | None:
        return TemperatureReading(value_c=52, raw_value_c=51.7, source="unit-test")


@dataclass(slots=True)
class FakeAssistant:
    runtime_product: FakeRuntimeProduct = field(default_factory=FakeRuntimeProduct)
    dialogue: FakeDialogue = field(default_factory=FakeDialogue)
    memory: FakeMemory = field(default_factory=FakeMemory)
    settings: dict[str, Any] = None
    last_language: str = "en"
    backend_statuses: dict[str, Any] = None
    _last_input_capture: dict[str, Any] = None
    _last_command_window_policy_snapshot: dict[str, Any] = None
    _last_response_delivery_snapshot: dict[str, Any] = None
    _last_fast_lane_route_snapshot: dict[str, Any] = None
    _diagnostics_events: list[dict[str, Any]] = None

    def __post_init__(self) -> None:
        self.settings = {"voice_input": {"engine": "faster_whisper", "device_name_contains": "reSpeaker"}}
        self.backend_statuses = {}
        self._last_input_capture = {
            "text": "Tell me about black holes",
            "language": "en",
            "mode": "wake_command",
            "capture_profile": "wake_command",
            "overflow_delta": 0,
        }
        self._last_command_window_policy_snapshot = {"action": "open_initial"}
        self._last_response_delivery_snapshot = {
            "source": "dialogue",
            "route_kind": "conversation",
            "first_token_latency_ms": 120.0,
            "first_speakable_chunk_latency_ms": 260.0,
            "first_audio_ms": 540.0,
            "route_to_first_audio_ms": 540.0,
        }
        self._last_fast_lane_route_snapshot = {"route_kind": "conversation"}
        self._diagnostics_events = [
            {"ts_ms": 1, "type": "standby", "message": "Waiting for wake word", "severity": "ok"},
            {"ts_ms": 2, "type": "heard", "message": "Heard: Tell me about black holes", "severity": "info"},
        ]


def _section(snapshot: dict[str, Any], section_id: str) -> dict[str, Any]:
    for section in snapshot["sections"]:
        if section["id"] == section_id:
            return section
    raise AssertionError(f"Missing section: {section_id}")


def test_feedback_center_snapshot_builds_required_sections(tmp_path: Path) -> None:
    snapshot = build_feedback_center_snapshot(
        assistant=FakeAssistant(),
        repo_root=tmp_path,
        metrics_provider=FakeMetricsProvider(),
    )

    assert [section["id"] for section in snapshot["sections"]] == [
        "overview",
        "activity",
        "runtime",
        "llm",
        "audio",
        "tests",
        "logs",
        "memory",
        "vision",
        "power",
    ]
    assert snapshot["current_activity"]["activity_state"] == "Running LLM dialogue"
    assert snapshot["current_activity"]["used_llm"] is True
    assert snapshot["recent_activity_events"][-1]["message"] == "Heard: Tell me about black holes"
    overview_values = {item["label"]: item["value"] for item in _section(snapshot, "overview")["items"]}
    assert overview_values["Activity state"] == "Running LLM dialogue"
    assert overview_values["Last transcript"] == "Tell me about black holes"
    assert overview_values["Last backend used"] == "LLM"
    llm_values = {item["label"]: item["value"] for item in _section(snapshot, "llm")["items"]}
    assert llm_values["Readiness state"] == "ready"
    assert llm_values["first_token_latency_ms"] == "120.0 ms"
    memory_values = {item["label"]: item["value"] for item in _section(snapshot, "memory")["items"]}
    assert memory_values["Known people count"] == "2"
    assert memory_values["Known objects count"] == "1"
    power_values = {item["label"]: item["value"] for item in _section(snapshot, "power")["items"]}
    assert power_values["Battery level"] == "81%"
    activity_values = {item["label"]: item["value"] for item in _section(snapshot, "activity")["items"]}
    assert activity_values["Heard"] == "Heard: Tell me about black holes"


def test_feedback_center_snapshot_handles_missing_sources(tmp_path: Path) -> None:
    snapshot = build_feedback_center_snapshot(
        assistant=object(),
        repo_root=tmp_path,
        metrics_provider=None,
    )

    memory_values = {item["label"]: item["value"] for item in _section(snapshot, "memory")["items"]}
    assert memory_values["Known people count"] == "not available yet"
    assert memory_values["Known objects count"] == "not available yet"
    # On hardware the live metrics provider can read a real battery; accept any non-empty value.
    battery_value = _section(snapshot, "power")["items"][0]["value"]
    assert isinstance(battery_value, str) and battery_value


def test_feedback_center_snapshot_marks_ready_idle_activity(tmp_path: Path) -> None:
    assistant = FakeAssistant()
    assistant._last_response_delivery_snapshot = {}
    assistant._last_fast_lane_route_snapshot = {}
    snapshot = build_feedback_center_snapshot(
        assistant=assistant,
        repo_root=tmp_path,
        metrics_provider=FakeMetricsProvider(),
    )

    overview_values = {item["label"]: item["value"] for item in _section(snapshot, "overview")["items"]}
    assert overview_values["Activity state"] == "Waiting for wake word"


def test_feedback_center_snapshot_caps_recent_activity_events(tmp_path: Path) -> None:
    assistant = FakeAssistant()
    assistant._diagnostics_events = [
        {"ts_ms": index, "type": "event", "message": f"event {index}", "severity": "info"}
        for index in range(40)
    ]

    snapshot = build_feedback_center_snapshot(
        assistant=assistant,
        repo_root=tmp_path,
        metrics_provider=FakeMetricsProvider(),
    )

    assert len(snapshot["recent_activity_events"]) == 30
    assert snapshot["recent_activity_events"][0]["message"] == "event 10"
