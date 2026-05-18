from __future__ import annotations

from types import SimpleNamespace

from modules.core.flows.command_flow.orchestrator import CommandFlowOrchestrator
from modules.runtime.contracts import InputSource, TranscriptResult
from modules.runtime.main_loop.active_window import (
    _capture_transcript_with_speech_service,
    _handle_incomplete_open_dialogue_capture,
    _looks_like_incomplete_open_dialogue_query,
)
from modules.runtime.main_loop.text_gate import _should_ignore_active_transcript


class _FakeStateFlags:
    def __init__(self) -> None:
        self.reset_calls = 0

    def reset_active_counters(self) -> None:
        self.reset_calls += 1


class _FakeAssistant:
    def __init__(self) -> None:
        self.pending_follow_up = None
        self.pending_confirmation = None
        self.last_language = "en"
        self.settings = {"voice_input": {}}
        self.voice_in = SimpleNamespace()
        self.text_responses: list[dict[str, object]] = []
        self._return_to_wake_standby_after_response = True

    def _localized(self, language: str, polish: str, english: str) -> str:
        return polish if language == "pl" else english

    def deliver_text_response(self, text: str, **kwargs) -> bool:
        self.text_responses.append({"text": str(text), **dict(kwargs)})
        return True


def test_incomplete_open_dialogue_query_detection_is_narrow() -> None:
    assert _looks_like_incomplete_open_dialogue_query("Explain black holes in")
    assert _looks_like_incomplete_open_dialogue_query("Tell me about")
    assert _looks_like_incomplete_open_dialogue_query("Powiedz mi o")
    assert not _looks_like_incomplete_open_dialogue_query("Tell me about black holes")
    assert not _looks_like_incomplete_open_dialogue_query("what time is it")


def test_incomplete_open_dialogue_capture_opens_repair_window_without_llm() -> None:
    assistant = _FakeAssistant()
    state_flags = _FakeStateFlags()

    handled = _handle_incomplete_open_dialogue_capture(
        assistant,
        state_flags,
        "Explain black holes in",
    )

    assert handled is True
    assert assistant.pending_follow_up == {
        "type": "conversation_repair",
        "language": "en",
        "prefix_text": "Explain black holes in",
        "window_seconds": 6.5,
        "source": "incomplete_open_dialogue_capture",
    }
    assert assistant._return_to_wake_standby_after_response is False
    assert state_flags.reset_calls == 1
    assert assistant.text_responses[-1]["text"] == "Please finish the question."
    assert assistant.text_responses[-1]["remember"] is False


def test_incomplete_open_dialogue_capture_uses_polish_prompt_for_polish_markers() -> None:
    assistant = _FakeAssistant()
    state_flags = _FakeStateFlags()

    handled = _handle_incomplete_open_dialogue_capture(
        assistant,
        state_flags,
        "Wyjaśnij czarne dziury w",
    )

    assert handled is True
    assert assistant.pending_follow_up["language"] == "pl"
    assert assistant.text_responses[-1]["text"] == "Dokończ proszę pytanie."


def test_ghost_background_phrases_are_ignored_without_pending_context() -> None:
    assistant = _FakeAssistant()
    gate_log_times: dict[str, float] = {}

    assert _should_ignore_active_transcript(
        assistant,
        "We'll see you in the next video.",
        gate_log_times,
        last_transcript_normalized=None,
        last_transcript_time=None,
    )
    assert _should_ignore_active_transcript(
        assistant,
        "I'm going to the right.",
        gate_log_times,
        last_transcript_normalized=None,
        last_transcript_time=None,
    )
    assert _should_ignore_active_transcript(
        assistant,
        "or yet me or",
        gate_log_times,
        last_transcript_normalized=None,
        last_transcript_time=None,
    )


def test_ghost_background_phrases_do_not_block_pending_follow_up_context() -> None:
    assistant = _FakeAssistant()
    assistant.pending_follow_up = {"type": "conversation_repair", "language": "en"}

    assert not _should_ignore_active_transcript(
        assistant,
        "We'll see you in the next video.",
        {},
        last_transcript_normalized=None,
        last_transcript_time=None,
    )


def test_background_gate_does_not_block_valid_questions() -> None:
    assistant = _FakeAssistant()

    assert not _should_ignore_active_transcript(
        assistant,
        "Tell me about black holes.",
        {},
        last_transcript_normalized=None,
        last_transcript_time=None,
    )


def test_conversation_repair_capture_prefers_pending_follow_up_language() -> None:
    captured_requests = []

    class _SpeechRecognition:
        def transcribe(self, request):
            captured_requests.append(request)
            return TranscriptResult(
                text="czarne dziury",
                language="pl",
                source=InputSource.VOICE,
                metadata={"backend_label": "test"},
            )

    assistant = _FakeAssistant()
    assistant.speech_recognition = _SpeechRecognition()
    assistant.pending_follow_up = {"type": "conversation_repair", "language": "pl"}

    result = _capture_transcript_with_speech_service(
        assistant,
        timeout=6.5,
        debug=False,
        mode="conversation_repair",
    )

    assert result is not None
    assert captured_requests[0].mode == "conversation_repair"
    assert captured_requests[0].metadata["preferred_language"] == "pl"
    assert captured_requests[0].metadata["force_language"] == "pl"
    assert captured_requests[0].metadata["follow_up_language_preferred"] is True


def test_command_language_uses_clear_current_english_turn_over_polish_fallback() -> None:
    assistant = SimpleNamespace(
        parser=None,
        utterance_normalizer=None,
        voice_session=None,
        _remember_user_turn=lambda *args, **kwargs: None,
    )
    flow = CommandFlowOrchestrator(assistant)

    prepared = flow.prepare(
        text="Tell me about black holes.",
        fallback_language="pl",
        source=InputSource.VOICE,
        capture_phase="command",
        capture_mode="wake_command",
    )

    assert prepared.command_language == "en"


def test_command_language_uses_clear_current_polish_turn_over_english_fallback() -> None:
    assistant = SimpleNamespace(
        parser=None,
        utterance_normalizer=None,
        voice_session=None,
        _remember_user_turn=lambda *args, **kwargs: None,
    )
    flow = CommandFlowOrchestrator(assistant)

    prepared = flow.prepare(
        text="Co to są czarne dziury?",
        fallback_language="en",
        source=InputSource.VOICE,
        capture_phase="command",
        capture_mode="wake_command",
    )

    assert prepared.command_language == "pl"
