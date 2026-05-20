from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

import modules.presentation.visual_shell.feedback.feedback_center_snapshot as feedback_snapshot
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
class FakeTurnBenchmarkService:
    snapshot: dict[str, Any]

    def latest_snapshot(self) -> dict[str, Any]:
        return dict(self.snapshot)


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
    turn_benchmark_service: FakeTurnBenchmarkService | None = None
    vision: Any = None

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
        self.turn_benchmark_service = FakeTurnBenchmarkService(
            {
                "latest_sample": {},
                "summary": {},
                "overlay_lines": [],
            }
        )


def _fake_oak_status() -> dict[str, Any]:
    camera = {
        "id": "camera_module_3_wide",
        "label": "Camera Module 3 Wide / picamera2",
        "type": "runtime_camera",
        "backend": "picamera2",
        "fallback_backend": "opencv",
        "object_detector_backend": "hailo_yolov11",
        "camera_index": 0,
        "configured_enabled": True,
        "active_runtime_backend": True,
        "active_streaming": True,
    }
    oak = {
        "id": "oak_d_lite_fixed_focus",
        "label": "Luxonis OAK-D Lite Fixed Focus / DepthAI",
        "type": "diagnostic_camera",
        "backend": "depthai",
        "usb_detected": True,
        "depthai_available": True,
        "depthai_device_count": 1,
        "device_info": {
            "mxid": "19443010C1A0E47D00",
            "state": "X_LINK_UNBOOTED",
            "protocol": "X_LINK_USB_VSC",
        },
        "usb_matches": ["Bus 003 Device 004: ID 03e7:2485 Intel Movidius MyriadX"],
        "mxid": "19443010C1A0E47D00",
        "state": "X_LINK_UNBOOTED",
        "protocol": "X_LINK_USB_VSC",
        "repo_has_oak_adapter": False,
        "active_streaming": False,
        "recommended_next_step": "Add a non-default OAK runtime adapter after a separate RGB/depth smoke test.",
        "error": "",
    }
    return {
        "camera_sources": [camera, oak],
        "camera_module_3_wide": camera,
        "oak_d_lite": oak,
        "configured_vision_backend": {"backend": "picamera2", "fallback_backend": "opencv"},
    }


@pytest.fixture(autouse=True)
def _stub_oak_probe(monkeypatch) -> None:
    feedback_snapshot._OAK_STATUS_CACHE["timestamp"] = 0.0
    feedback_snapshot._OAK_STATUS_CACHE["status"] = None
    monkeypatch.setattr(
        feedback_snapshot,
        "build_vision_camera_status",
        lambda **kwargs: _fake_oak_status(),
    )


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
        "performance",
        "runtime",
        "llm",
        "audio",
        "tests",
        "logs",
        "memory",
        "vision",
        "vision_camera_module_3",
        "vision_oak_d_lite",
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
    performance_values = {
        item["label"]: item["value"] for item in _section(snapshot, "performance")["items"]
    }
    assert performance_values["Last command"] == "Tell me about black holes"
    assert performance_values["Route / source"] == "conversation"
    assert performance_values["TTS first audio"] == "540.0 ms"
    assert performance_values["first_token_latency_ms"] == "120.0 ms"
    assert performance_values["first_speakable_chunk_latency_ms"] == "260.0 ms"


def test_feedback_center_snapshot_includes_separate_camera_sources(tmp_path: Path) -> None:
    snapshot = build_feedback_center_snapshot(
        assistant=FakeAssistant(),
        repo_root=tmp_path,
        metrics_provider=FakeMetricsProvider(),
    )

    vision_values = {item["label"]: item["value"] for item in _section(snapshot, "vision")["items"]}

    assert "Camera source: Camera Module 3 Wide / picamera2" in vision_values
    assert "Camera source: OAK-D Lite Fixed Focus / DepthAI" in vision_values
    assert "backend=picamera2" in vision_values["Camera source: Camera Module 3 Wide / picamera2"]
    assert "depthai_available=yes" in vision_values["Camera source: OAK-D Lite Fixed Focus / DepthAI"]


def test_feedback_center_snapshot_includes_camera_diagnostic_pages(tmp_path: Path) -> None:
    snapshot = build_feedback_center_snapshot(
        assistant=FakeAssistant(),
        repo_root=tmp_path,
        metrics_provider=FakeMetricsProvider(),
    )

    assert _section(snapshot, "vision_camera_module_3")["title"] == "Vision Camera Module 3"
    assert _section(snapshot, "vision_oak_d_lite")["title"] == "Vision OAK-D Lite"


def test_feedback_center_snapshot_camera_module_3_page_has_runtime_fields(tmp_path: Path) -> None:
    snapshot = build_feedback_center_snapshot(
        assistant=FakeAssistant(),
        repo_root=tmp_path,
        metrics_provider=FakeMetricsProvider(),
    )

    camera_values = {
        item["label"]: item["value"]
        for item in _section(snapshot, "vision_camera_module_3")["items"]
    }

    assert camera_values["Label"] == "Camera Module 3 Wide / picamera2"
    assert camera_values["Backend"] == "picamera2"
    assert camera_values["Fallback backend"] == "opencv"
    assert camera_values["Camera index"] == "0"
    assert camera_values["Object detector backend"] == "hailo_yolov11"
    assert camera_values["Configured enabled"] == "yes"
    assert camera_values["Active runtime backend"] == "yes"
    assert camera_values["Active streaming"] == "yes"
    assert "Current camera status" in camera_values
    assert "Current capture worker status" in camera_values
    assert "Current detector status" in camera_values


def test_feedback_center_snapshot_oak_d_lite_page_has_non_streaming_fields(tmp_path: Path) -> None:
    snapshot = build_feedback_center_snapshot(
        assistant=FakeAssistant(),
        repo_root=tmp_path,
        metrics_provider=FakeMetricsProvider(),
    )

    oak_values = {
        item["label"]: item["value"]
        for item in _section(snapshot, "vision_oak_d_lite")["items"]
    }

    assert oak_values["Label"] == "OAK-D Lite Fixed Focus / DepthAI"
    assert oak_values["USB detected"] == "yes"
    assert "Intel Movidius MyriadX" in oak_values["USB matches"]
    assert oak_values["DepthAI available"] == "yes"
    assert oak_values["DepthAI device count"] == "1"
    assert oak_values["MXID"] == "19443010C1A0E47D00"
    assert oak_values["State"] == "X_LINK_UNBOOTED"
    assert oak_values["Protocol"] == "X_LINK_USB_VSC"
    assert oak_values["Active streaming"] == "no"
    assert oak_values["Repo has OAK adapter"] == "no"
    assert "RGB/depth smoke test" in oak_values["Recommended next step"]


def test_feedback_center_snapshot_includes_oak_d_lite_fields(tmp_path: Path) -> None:
    snapshot = build_feedback_center_snapshot(
        assistant=FakeAssistant(),
        repo_root=tmp_path,
        metrics_provider=FakeMetricsProvider(),
    )

    vision_values = {item["label"]: item["value"] for item in _section(snapshot, "vision")["items"]}

    assert vision_values["OAK USB detected"] == "yes"
    assert vision_values["OAK DepthAI available"] == "yes"
    assert vision_values["OAK device count"] == "1"
    assert vision_values["OAK MXID"] == "19443010C1A0E47D00"
    assert vision_values["OAK state"] == "X_LINK_UNBOOTED"
    assert vision_values["OAK protocol"] == "X_LINK_USB_VSC"
    assert vision_values["OAK active streaming"] == "no"
    assert vision_values["OAK repo adapter"] == "no"
    assert "RGB/depth smoke test" in vision_values["OAK recommended next step"]


def test_feedback_center_snapshot_handles_oak_probe_failure(tmp_path: Path, monkeypatch) -> None:
    feedback_snapshot._OAK_STATUS_CACHE["timestamp"] = 0.0
    feedback_snapshot._OAK_STATUS_CACHE["status"] = None

    def _raise_probe(**kwargs):
        del kwargs
        raise RuntimeError("depthai probe failed")

    monkeypatch.setattr(feedback_snapshot, "build_vision_camera_status", _raise_probe)

    snapshot = build_feedback_center_snapshot(
        assistant=FakeAssistant(),
        repo_root=tmp_path,
        metrics_provider=FakeMetricsProvider(),
    )

    vision_values = {item["label"]: item["value"] for item in _section(snapshot, "vision")["items"]}
    oak_values = {item["label"]: item["value"] for item in _section(snapshot, "vision_oak_d_lite")["items"]}

    assert vision_values["Camera sources"] == "status unavailable"
    assert vision_values["OAK-D Lite status error"] == "depthai probe failed"
    assert oak_values["Label"] == "OAK-D Lite Fixed Focus / DepthAI"
    assert oak_values["OAK-D Lite status error"] == "depthai probe failed"


def test_feedback_center_snapshot_keeps_backward_compatible_vision_items(tmp_path: Path) -> None:
    snapshot = build_feedback_center_snapshot(
        assistant=FakeAssistant(),
        repo_root=tmp_path,
        metrics_provider=FakeMetricsProvider(),
    )

    vision_values = {item["label"]: item["value"] for item in _section(snapshot, "vision")["items"]}

    assert "Camera status" in vision_values
    assert "Camera backend" in vision_values
    assert "Capture worker" in vision_values
    assert "Detector status" in vision_values
    assert "Camera source: Camera Module 3 Wide / picamera2" in vision_values


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
    performance_values = {
        item["label"]: item["value"] for item in _section(snapshot, "performance")["items"]
    }
    assert performance_values["Timing data"] == "No timing data yet"
    assert performance_values["Last command"] == "unavailable"


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


def test_feedback_center_snapshot_includes_cached_benchmark_timings(tmp_path: Path) -> None:
    assistant = FakeAssistant()
    assistant.turn_benchmark_service = FakeTurnBenchmarkService(
        {
            "latest_sample": {
                "created_at_iso": "2026-05-18T10:00:00+00:00",
                "user_text_preview": "open diagnostics",
                "language": "en",
                "stt_backend_label": "faster_whisper",
                "route_kind": "action",
                "primary_intent": "diagnostics_open",
                "canonical_intent": "diagnostics.open",
                "llm_prevented": True,
                "result": "action_route",
                "total_turn_ms": 1816.0,
                "response_first_audio_ms": 145.0,
                "route_to_first_audio_ms": 220.0,
                "skill_to_first_audio_ms": 180.0,
                "response_total_ms": 310.0,
                "wake_to_listen_ms": 40.0,
                "listen_to_speech_ms": 520.0,
                "speech_to_route_ms": 18.0,
                "skill_execution_window_ms": 70.0,
                "skill_status": "accepted",
                "response_source": "action",
            },
            "summary": {"last_total_turn_ms": 1816.0},
            "overlay_lines": [],
        }
    )

    snapshot = build_feedback_center_snapshot(
        assistant=assistant,
        repo_root=tmp_path,
        metrics_provider=FakeMetricsProvider(),
    )

    performance_values = {
        item["label"]: item["value"] for item in _section(snapshot, "performance")["items"]
    }
    assert performance_values["Last command"] == "open diagnostics"
    assert performance_values["Canonical intent"] == "diagnostics.open"
    assert performance_values["LLM prevented"] == "yes"
    assert performance_values["total_action_ms"] == "1816.0 ms"
    assert performance_values["route_to_first_audio"] == "220.0 ms"
    assert performance_values["skill_to_first_audio"] == "180.0 ms"
    assert "duration=520.0 ms" in performance_values["Event: STT / Listen to speech"]
    assert "1816.0 ms" in performance_values["Slow op: Total turn"]
    assert performance_values["Subsystem: STT"] == "not measured yet"


def test_performance_section_shows_vosk_and_faster_whisper_fields(tmp_path: Path) -> None:
    """Vosk candidate accepted and FasterWhisper prevented must appear from benchmark sample."""
    assistant = FakeAssistant()
    assistant.turn_benchmark_service = FakeTurnBenchmarkService(
        {
            "latest_sample": {
                "user_text_preview": "show system status",
                "language": "en",
                "stt_backend_label": "vosk_pre_whisper",
                "route_kind": "action",
                "canonical_intent": "feedback.on",
                "llm_prevented": True,
                "voice_engine_v2_candidate_accepted": True,
                "faster_whisper_prevented": True,
                "result": "ok",
                "total_turn_ms": 1820.0,
                "response_first_audio_ms": 140.0,
                "route_to_first_audio_ms": 210.0,
            },
            "summary": {},
            "overlay_lines": [],
        }
    )

    snapshot = build_feedback_center_snapshot(
        assistant=assistant,
        repo_root=tmp_path,
        metrics_provider=FakeMetricsProvider(),
    )

    performance_values = {
        item["label"]: item["value"] for item in _section(snapshot, "performance")["items"]
    }
    assert performance_values["Vosk candidate accepted"] == "yes"
    assert performance_values["FasterWhisper prevented"] == "yes"
    assert performance_values["LLM prevented"] == "yes"
    assert performance_values["STT backend"] == "vosk_pre_whisper"


def test_performance_section_shows_unavailable_for_missing_vosk_fields(tmp_path: Path) -> None:
    """When benchmark sample lacks Vosk fields, show 'not available yet'."""
    assistant = FakeAssistant()
    assistant.turn_benchmark_service = FakeTurnBenchmarkService(
        {
            "latest_sample": {
                "user_text_preview": "what time is it",
                "language": "en",
                "route_kind": "action",
                "llm_prevented": True,
                "total_turn_ms": 950.0,
            },
            "summary": {},
            "overlay_lines": [],
        }
    )

    snapshot = build_feedback_center_snapshot(
        assistant=assistant,
        repo_root=tmp_path,
        metrics_provider=FakeMetricsProvider(),
    )

    performance_values = {
        item["label"]: item["value"] for item in _section(snapshot, "performance")["items"]
    }
    # Fields not in the sample → _bool_or_unavailable(None) returns "unavailable"
    assert performance_values["Vosk candidate accepted"] == "unavailable"
    assert performance_values["FasterWhisper prevented"] == "unavailable"


def test_feedback_center_snapshot_does_not_start_heavy_services(tmp_path: Path) -> None:
    class HeavyServiceGuard:
        def __init__(self) -> None:
            self.started = False

        def status(self) -> dict[str, Any]:
            return {"backend": "guarded"}

        def start(self) -> None:
            self.started = True
            raise AssertionError("snapshot must not start camera")

        def capture(self) -> None:
            raise AssertionError("snapshot must not capture vision")

        def generate(self) -> None:
            raise AssertionError("snapshot must not call LLM generation")

    assistant = FakeAssistant()
    guard = HeavyServiceGuard()
    assistant.vision = guard

    build_feedback_center_snapshot(
        assistant=assistant,
        repo_root=tmp_path,
        metrics_provider=FakeMetricsProvider(),
    )

    assert guard.started is False
