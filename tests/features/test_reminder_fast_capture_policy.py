from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from modules.runtime.main_loop.active_window import _capture_mode_for_active_phase


def test_reminder_time_follow_up_uses_fast_capture_mode() -> None:
    assistant = SimpleNamespace(
        pending_follow_up={"type": "reminder_time"},
        _last_capture_handoff={},
    )

    assert _capture_mode_for_active_phase(
        assistant,
        active_phase="follow_up",
    ) == "reminder_time"


def test_reminder_message_follow_up_uses_fast_capture_mode() -> None:
    assistant = SimpleNamespace(
        pending_follow_up={"type": "reminder_message"},
        _last_capture_handoff={},
    )

    assert _capture_mode_for_active_phase(
        assistant,
        active_phase="follow_up",
    ) == "reminder_message"


def test_conversation_repair_follow_up_uses_longer_capture_mode() -> None:
    assistant = SimpleNamespace(
        pending_follow_up={"type": "conversation_repair"},
        _last_capture_handoff={},
    )

    assert _capture_mode_for_active_phase(
        assistant,
        active_phase="follow_up",
    ) == "conversation_repair"


def test_incomplete_dialogue_follow_up_uses_conversation_repair_capture_mode() -> None:
    assistant = SimpleNamespace(
        pending_follow_up={
            "type": "clarification_repeat",
            "source": "incomplete_dialogue_query",
        },
        _last_capture_handoff={},
    )

    assert _capture_mode_for_active_phase(
        assistant,
        active_phase="follow_up",
    ) == "conversation_repair"


def test_reminder_capture_profiles_are_shorter_than_generic_follow_up() -> None:
    settings = json.loads(Path("config/settings.json").read_text())
    profiles = settings["voice_input"]["capture_profiles"]

    assert profiles["reminder_time"]["timeout_seconds"] < profiles["follow_up"]["timeout_seconds"]
    assert profiles["reminder_message"]["timeout_seconds"] < profiles["follow_up"]["timeout_seconds"]
    assert profiles["reminder_time"]["end_silence_seconds"] < profiles["follow_up"]["end_silence_seconds"]


def test_example_conversation_repair_profile_is_longer_than_fast_follow_up() -> None:
    settings = json.loads(Path("config/settings.example.json").read_text())
    profiles = settings["voice_input"]["capture_profiles"]

    assert profiles["conversation_repair"]["timeout_seconds"] >= 6.5
    assert profiles["conversation_repair"]["end_silence_seconds"] >= 0.55
    assert profiles["conversation_repair"]["timeout_seconds"] > profiles["reminder_message"]["timeout_seconds"]


def test_example_prefers_respeaker_by_name_without_stale_numeric_index() -> None:
    settings = json.loads(Path("config/settings.example.json").read_text())
    voice_input = settings["voice_input"]

    assert voice_input["device_index"] is None
    assert voice_input["device_name_contains"] == "reSpeaker"
