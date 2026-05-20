from __future__ import annotations

from tests.runtime.diagnostics import time_command_latency_probe


def test_time_command_probe_reports_deterministic_fast_route_for_core_phrases() -> None:
    report = time_command_latency_probe.build_report()

    by_phrase = {item["input_phrase"]: item for item in report["phrases"]}
    for phrase in (
        "która jest godzina",
        "która godzina",
        "what time is it",
        "tell me the time",
    ):
        item = by_phrase[phrase]
        assert item["matched_intent"] == "system.current_time"
        assert item["route_used"] == "fast_command_lane"
        assert item["fast_lane_action"] == "ask_time"
        assert item["llm_prevented"] is True
        assert item["deterministic_action_used"] is True
