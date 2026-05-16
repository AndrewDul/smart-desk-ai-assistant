from __future__ import annotations

from modules.presentation.thinking_ack import ThinkingAckService


class _FakeAudioCoordinator:
    def __init__(self, *, active: bool = False) -> None:
        self.active = active

    def assistant_output_active(self) -> bool:
        return self.active


class _FakeVoiceOutput:
    def __init__(self, *, active_output: bool = False) -> None:
        self.audio_coordinator = _FakeAudioCoordinator(active=active_output)
        self.speak_calls: list[tuple[str, str]] = []

    def speak(self, text: str, *, language: str = "en") -> bool:
        self.speak_calls.append((str(text), str(language)))
        return True


class _FakeVoiceSession:
    def __init__(self) -> None:
        self.thinking_events: list[str] = []

    def transition_to_thinking(self, *, detail: str = "thinking") -> None:
        self.thinking_events.append(str(detail))

    def build_thinking_acknowledgement(self, language: str) -> str:
        return "Daj mi chwilę." if language == "pl" else "Give me a moment."


def test_thinking_ack_does_not_speak_before_delay() -> None:
    voice_output = _FakeVoiceOutput()
    service = ThinkingAckService(
        voice_output=voice_output,
        voice_session=_FakeVoiceSession(),
        delay_seconds=0.2,
    )

    handle = service.arm(language="en", detail="unit_test")

    assert handle.wait_until_finished(0.02) is False
    assert voice_output.speak_calls == []
    handle.cancel()


def test_thinking_ack_speaks_once_after_delay() -> None:
    voice_output = _FakeVoiceOutput()
    service = ThinkingAckService(
        voice_output=voice_output,
        voice_session=_FakeVoiceSession(),
        delay_seconds=0.01,
    )

    handle = service.arm(language="en", detail="unit_test")

    assert handle.wait_until_finished(0.5) is True
    assert voice_output.speak_calls == [("Give me a moment.", "en")]


def test_thinking_ack_cancel_before_delay_prevents_filler() -> None:
    voice_output = _FakeVoiceOutput()
    service = ThinkingAckService(
        voice_output=voice_output,
        voice_session=_FakeVoiceSession(),
        delay_seconds=0.2,
    )

    service.arm(language="en", detail="unit_test")
    service.cancel_active()

    assert voice_output.speak_calls == []


def test_thinking_ack_skips_when_assistant_output_is_active() -> None:
    voice_output = _FakeVoiceOutput(active_output=True)
    service = ThinkingAckService(
        voice_output=voice_output,
        voice_session=_FakeVoiceSession(),
        delay_seconds=0.01,
    )

    handle = service.arm(language="en", detail="unit_test")

    assert handle.wait_until_finished(0.5) is True
    assert voice_output.speak_calls == []


def test_thinking_ack_uses_polish_phrase_for_polish_turn() -> None:
    voice_output = _FakeVoiceOutput()
    service = ThinkingAckService(
        voice_output=voice_output,
        voice_session=_FakeVoiceSession(),
        delay_seconds=0.01,
    )

    handle = service.arm(language="pl", detail="unit_test")

    assert handle.wait_until_finished(0.5) is True
    assert voice_output.speak_calls == [("Daj mi chwilę.", "pl")]


def test_thinking_ack_uses_english_phrase_for_english_turn() -> None:
    voice_output = _FakeVoiceOutput()
    service = ThinkingAckService(
        voice_output=voice_output,
        voice_session=_FakeVoiceSession(),
        delay_seconds=0.01,
    )

    handle = service.arm(language="en", detail="unit_test")

    assert handle.wait_until_finished(0.5) is True
    assert voice_output.speak_calls == [("Give me a moment.", "en")]


def test_thinking_ack_sends_thinking_transition_and_start_callback() -> None:
    voice_output = _FakeVoiceOutput()
    voice_session = _FakeVoiceSession()
    started: list[str] = []
    service = ThinkingAckService(
        voice_output=voice_output,
        voice_session=voice_session,
        delay_seconds=0.01,
        on_started=started.append,
    )

    handle = service.arm(language="en", detail="dialogue_plan")

    assert handle.wait_until_finished(0.5) is True
    assert voice_session.thinking_events == ["dialogue_plan"]
    assert started == ["dialogue_plan"]
