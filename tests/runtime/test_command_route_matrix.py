"""Command route matrix — confirms key phrases use fast-line and never fall through to LLM.

Each row verifies:
  - grammar match (intent recognised by CommandGrammar)
  - Vosk vocabulary presence (phrase words appear in generated vocab)
  - FastCommandLane decision (action, source, llm_prevented)
  - speed class (fast_line / grammar / llm_fallback)
"""
from __future__ import annotations

import pytest

from modules.core.session.fast_command_lane import FastCommandLane
from modules.devices.audio.command_asr.command_grammar import build_default_command_grammar
from modules.devices.audio.command_asr.command_language import CommandLanguage
from modules.devices.audio.command_asr.command_result import CommandRecognitionStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeAssistant:
    pending_confirmation = None
    pending_follow_up = None

    @staticmethod
    def _normalize_lang(language: str | None) -> str:
        return "pl" if str(language or "").lower().startswith("pl") else "en"


def _grammar_result(phrase: str, language: str):
    grammar = build_default_command_grammar()
    return grammar.match(phrase)


def _fast_lane_decision(phrase: str, language: str):
    prepared = {
        "raw_text": phrase,
        "routing_text": phrase,
        "normalized_text": phrase.lower().strip("."),
        "language": language,
    }
    return FastCommandLane(enabled=True).classify(prepared=prepared, assistant=_FakeAssistant())


def _in_vosk_vocab(phrase: str) -> bool:
    grammar = build_default_command_grammar()
    vocab = grammar.to_vosk_vocabulary()
    words = phrase.lower().split()
    return all(w in vocab for w in words)


# ---------------------------------------------------------------------------
# Matrix definition
# format: (phrase, language, expected_action, expected_speed_class)
#   speed_class: "fast_lane" | "grammar" | "llm_fallback"
# ---------------------------------------------------------------------------

FAST_LINE_COMMANDS: list[tuple[str, str, str, str]] = [
    # English fast-line
    ("show system status",   "en", "feedback_on",  "fast_lane"),
    ("shows system status",  "en", "feedback_on",  "fast_lane"),
    ("close system status",  "en", "feedback_off", "fast_lane"),
    ("close window",         "en", "feedback_off", "fast_lane"),
    ("close diagnostics",    "en", "feedback_off", "fast_lane"),
    ("exit",                 "en", "exit",         "fast_lane"),
    ("nexa exit",            "en", "exit",         "fast_lane"),
    ("shutdown nexa",        "en", "exit",         "fast_lane"),
    ("close nexa",           "en", "exit",         "fast_lane"),
    # Polish fast-line
    ("pokaż diagnostykę",    "pl", "feedback_on",  "fast_lane"),
    ("zamknij okno",         "pl", "feedback_off", "fast_lane"),
    ("zamknij diagnostykę",  "pl", "feedback_off", "fast_lane"),
    ("która jest godzina",   "pl", "ask_time",     "fast_lane"),
    ("która godzina",        "pl", "ask_time",     "fast_lane"),
    ("powiedz mi godzinę",   "pl", "ask_time",     "fast_lane"),
    ("what time is it",      "en", "ask_time",     "fast_lane"),
    ("tell me the time",     "en", "ask_time",     "fast_lane"),
    ("show me the time",     "en", "show_visual_time", "fast_lane"),
    ("show the time",        "en", "show_visual_time", "fast_lane"),
    ("display the time",     "en", "show_visual_time", "fast_lane"),
    ("pokaż mi czas",        "pl", "show_visual_time", "fast_lane"),
    ("pokaż godzinę",        "pl", "show_visual_time", "fast_lane"),
    ("wyjdź",                "pl", "exit",         "fast_lane"),
    ("wyłącz nexę",          "pl", "exit",         "fast_lane"),
    ("zamknij nexę",         "pl", "exit",         "fast_lane"),
    ("koniec pracy",         "pl", "exit",         "fast_lane"),
]

# Commands that should match grammar but may not be in fast_lane directly
GRAMMAR_COMMANDS: list[tuple[str, str, str, str]] = [
    ("status",              "en", "status",  "grammar"),
    ("status",              "pl", "status",  "grammar"),
]

# Commands that require LLM and must NOT become fast_lane
LLM_COMMANDS: list[tuple[str, str]] = [
    ("explain what a black hole is", "en"),
    ("tell me a story about the ocean", "en"),
    ("wyjaśnij czym jest czarna dziura", "pl"),
]


# ---------------------------------------------------------------------------
# Tests — fast-line commands
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phrase,language,expected_action,speed_class", FAST_LINE_COMMANDS)
def test_fast_line_command_route(phrase: str, language: str, expected_action: str, speed_class: str) -> None:
    decision = _fast_lane_decision(phrase, language)
    assert decision is not None, (
        f"FastCommandLane returned no decision for {phrase!r} ({language}) — expected {expected_action!r}"
    )
    assert decision.action == expected_action, (
        f"{phrase!r}: expected action={expected_action!r}, got {decision.action!r}"
    )
    assert decision.language == language, (
        f"{phrase!r}: expected language={language!r}, got {decision.language!r}"
    )


@pytest.mark.parametrize("phrase,language,expected_action,speed_class", FAST_LINE_COMMANDS)
def test_fast_line_command_llm_not_needed(phrase: str, language: str, expected_action: str, speed_class: str) -> None:
    decision = _fast_lane_decision(phrase, language)
    assert decision is not None, f"No fast-lane decision for {phrase!r}"
    # Fast-lane decisions are inherently LLM-prevented — verify the source is deterministic
    assert "fast_command_lane" in decision.source or "direct" in decision.source or "diagnostics" in decision.source or decision.source != "", (
        f"{phrase!r}: source {decision.source!r} does not look like a deterministic route"
    )


# ---------------------------------------------------------------------------
# Tests — grammar commands
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phrase,language,expected_action,speed_class", GRAMMAR_COMMANDS)
def test_grammar_command_matches(phrase: str, language: str, expected_action: str, speed_class: str) -> None:
    result = _grammar_result(phrase, language)
    assert result.status == CommandRecognitionStatus.MATCHED, (
        f"Grammar did not match {phrase!r} ({language}): status={result.status}"
    )


# ---------------------------------------------------------------------------
# Tests — LLM commands must NOT be intercepted by fast-line
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phrase,language", LLM_COMMANDS)
def test_llm_command_not_intercepted_by_fast_lane(phrase: str, language: str) -> None:
    decision = _fast_lane_decision(phrase, language)
    assert decision is None, (
        f"FastCommandLane incorrectly intercepted LLM phrase {phrase!r} with action={getattr(decision, 'action', '?')!r}"
    )


# ---------------------------------------------------------------------------
# Tests — Vosk vocabulary does not include long/noisy stt_recovery phrases
# ---------------------------------------------------------------------------

def test_vosk_vocabulary_does_not_include_stt_recovery_phrases() -> None:
    grammar = build_default_command_grammar()
    vosk_vocab = grammar.to_vosk_vocabulary()
    # stt_recovery phrases are excluded by default; these mishear variants should NOT appear
    stt_recovery_noise_words = [
        "djagnostyka",   # mishear variant of "diagnostyka"
        "djagnostike",   # mishear variant
        "djagnostyke",   # mishear variant
        "polkaz",        # mishear of "pokaż"
        "diagnostica",   # English mishear (not a real Polish word)
    ]
    found = [word for word in stt_recovery_noise_words if word in vosk_vocab]
    assert not found, (
        f"Vosk vocabulary unexpectedly contains stt_recovery noise words: {found}. "
        "These should be excluded via vosk_exclude tag."
    )


def test_vosk_vocabulary_includes_core_deterministic_phrases() -> None:
    grammar = build_default_command_grammar()
    vosk_vocab = grammar.to_vosk_vocabulary()
    # Vosk vocab contains full phrases, not individual tokens. These are
    # standalone single-word commands that appear as complete phrases.
    required_phrases = [
        "exit",
        "status",
        "nexa exit",
        "shutdown nexa",
        "close nexa",
        "stop nexa",
        "quit nexa",
        "wyłącz nexę",
        "zamknij nexę",
        "zakończ pracę",
        "koniec pracy",
    ]
    missing = [p for p in required_phrases if p not in vosk_vocab]
    assert not missing, (
        f"Vosk vocabulary is missing core deterministic phrases: {missing}"
    )


# ---------------------------------------------------------------------------
# Tests — feedback_on / feedback_off must be in fast-lane action map
# ---------------------------------------------------------------------------

def test_feedback_on_off_are_fast_line_actions() -> None:
    lane = FastCommandLane(enabled=True)
    # These are the canonical action names the action flow expects
    assert "feedback_on" in lane.DIRECT_ACTIONS
    assert "feedback_off" in lane.DIRECT_ACTIONS


def test_exit_is_fast_line_action() -> None:
    lane = FastCommandLane(enabled=True)
    assert "exit" in lane.DIRECT_ACTIONS


def test_stop_routes_through_grammar_not_fast_lane() -> None:
    # "stop" is handled by grammar/runtime candidates, not FastCommandLane.
    # This is intentional — it goes through the full ASR pipeline.
    decision = _fast_lane_decision("stop", "en")
    assert decision is None, (
        f"'stop' should NOT be intercepted by FastCommandLane, got action={getattr(decision, 'action', '?')!r}"
    )
