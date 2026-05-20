"""Inspect deterministic routing for time commands without running audio hardware."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from modules.core.session.fast_command_lane import FastCommandLane
from modules.devices.audio.command_asr.command_grammar import (
    build_default_command_grammar,
    normalize_command_text,
)


BASE_DIR = Path(__file__).resolve().parents[3]
BENCHMARK_PATH = BASE_DIR / "var" / "data" / "turn_benchmarks.json"

DEFAULT_PHRASES = (
    ("która jest godzina", "pl"),
    ("która godzina", "pl"),
    ("what time is it", "en"),
    ("tell me the time", "en"),
)


class _FakeAssistant:
    pending_confirmation = None
    pending_follow_up = None

    @staticmethod
    def _normalize_lang(language: str | None) -> str:
        return "pl" if str(language or "").lower().startswith("pl") else "en"


def _fast_lane_decision(phrase: str, language: str) -> Any:
    prepared = {
        "raw_text": phrase,
        "routing_text": phrase,
        "normalized_text": normalize_command_text(phrase),
        "language": language,
    }
    return FastCommandLane(enabled=True).classify(
        prepared=prepared,
        assistant=_FakeAssistant(),
    )


def _load_benchmark_samples(path: Path = BENCHMARK_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        samples = payload.get("samples") or payload.get("turns") or payload.get("history")
        if isinstance(samples, list):
            return [item for item in samples if isinstance(item, dict)]
    return []


def _find_recent_benchmark(phrase: str) -> dict[str, Any]:
    normalized_phrase = normalize_command_text(phrase)
    for sample in reversed(_load_benchmark_samples()):
        preview = str(
            sample.get("user_text_preview")
            or sample.get("user_text")
            or sample.get("transcript")
            or ""
        )
        if normalize_command_text(preview).startswith(normalized_phrase):
            return {
                "total_turn_ms": sample.get("total_turn_ms"),
                "response_first_audio_ms": sample.get("response_first_audio_ms"),
                "llm_first_chunk_ms": sample.get("llm_first_chunk_ms"),
                "stt_ms": sample.get("stt_ms"),
                "route_ms": sample.get("route_ms"),
                "response_source": sample.get("response_source"),
                "primary_intent": sample.get("primary_intent"),
                "canonical_intent": sample.get("canonical_intent"),
            }
    return {}


def inspect_phrase(phrase: str, language: str) -> dict[str, Any]:
    grammar = build_default_command_grammar()
    grammar_result = grammar.match(phrase)
    fast_decision = _fast_lane_decision(phrase, language)
    route_used = "fast_command_lane" if fast_decision is not None else "no_fast_lane_match"

    return {
        "input_phrase": phrase,
        "normalized_phrase": normalize_command_text(phrase),
        "language": language,
        "grammar_status": grammar_result.status.value,
        "matched_intent": grammar_result.intent_key,
        "matched_phrase": grammar_result.matched_phrase,
        "route_used": route_used,
        "fast_lane_action": getattr(fast_decision, "action", None),
        "fast_lane_source": getattr(fast_decision, "source", None),
        "llm_prevented": bool(fast_decision is not None),
        "deterministic_action_used": getattr(fast_decision, "action", None)
        in {"ask_time", "show_time"},
        "estimated_or_recorded_latency": _find_recent_benchmark(phrase),
    }


def build_report(phrases: tuple[tuple[str, str], ...] = DEFAULT_PHRASES) -> dict[str, Any]:
    return {
        "probe": "time_command_latency_probe",
        "benchmark_path": str(BENCHMARK_PATH),
        "phrases": [inspect_phrase(phrase, language) for phrase, language in phrases],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phrase", action="append", default=[])
    args = parser.parse_args()

    phrases = tuple((phrase, "pl" if "godzina" in phrase.lower() else "en") for phrase in args.phrase)
    report = build_report(phrases or DEFAULT_PHRASES)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
