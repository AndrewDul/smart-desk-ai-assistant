from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

from modules.runtime.contracts import InputSource, TranscriptRequest, TranscriptResult

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_MODULE_PATH = _PROJECT_ROOT / "modules" / "runtime" / "main_loop" / "active_window.py"

if "modules.core.assistant" not in sys.modules:
    assistant_stub = types.ModuleType("modules.core.assistant")
    assistant_stub.CoreAssistant = object
    sys.modules["modules.core.assistant"] = assistant_stub

if "modules.runtime.main_loop" not in sys.modules:
    package = types.ModuleType("modules.runtime.main_loop")
    package.__path__ = [str(_MODULE_PATH.parent)]
    sys.modules["modules.runtime.main_loop"] = package

spec = importlib.util.spec_from_file_location(
    "modules.runtime.main_loop.active_window",
    _MODULE_PATH,
)
if spec is None or spec.loader is None:
    raise RuntimeError("Failed to load active_window module for tests.")

_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = _module
spec.loader.exec_module(_module)

_capture_transcript_for_assistant = _module._capture_transcript_for_assistant
_listen_for_active_command = _module._listen_for_active_command


class _SpeechRecognitionProbe:
    def __init__(self, text: str = "hello via service") -> None:
        self.text = text
        self.requests: list[TranscriptRequest] = []

    def transcribe(self, request: TranscriptRequest) -> TranscriptResult | None:
        self.requests.append(request)
        return TranscriptResult(
            text=self.text,
            language="en",
            confidence=0.88,
            is_final=True,
            source=request.source,
            metadata={
                "backend_label": "faster_whisper",
                "mode": request.mode,
                "adapter": "service_rich_contract",
                "engine": "faster_whisper",
            },
        )


class _VoiceSessionProbe:
    def __init__(self) -> None:
        self.listening_calls: list[dict[str, object]] = []
        self.transcribing_calls: list[dict[str, object]] = []

    def transition_to_listening(self, *, detail: str, phase: str, input_owner: str) -> None:
        self.listening_calls.append(
            {
                "detail": detail,
                "phase": phase,
                "input_owner": input_owner,
            }
        )

    def transition_to_transcribing(self, *, detail: str, phase: str) -> None:
        self.transcribing_calls.append(
            {
                "detail": detail,
                "phase": phase,
            }
        )

    def active_window_remaining_seconds(self) -> float:
        return 3.0


class _StateFlags:
    def __init__(self) -> None:
        self.active_phase = "command"

    def consume_prefetched_command(self):
        return None


class _AssistantProbe:
    def __init__(self) -> None:
        self.voice_in = object()
        self.voice_debug = False
        self.speech_recognition = _SpeechRecognitionProbe()
        self.voice_session = _VoiceSessionProbe()
        self._last_input_capture = None


class ActiveWindowSTTServiceIntegrationTests(unittest.TestCase):
    def test_capture_transcript_for_assistant_prefers_speech_recognition_service(self) -> None:
        assistant = _AssistantProbe()

        transcript = _capture_transcript_for_assistant(
            assistant,
            timeout=5.0,
            debug=True,
            mode="conversation",
        )

        self.assertIsNotNone(transcript)
        assert transcript is not None
        self.assertEqual(transcript.text, "hello via service")
        self.assertEqual(transcript.language, "en")
        self.assertEqual(transcript.metadata["backend_label"], "faster_whisper")
        self.assertEqual(assistant.speech_recognition.requests[0].mode, "conversation")
        self.assertEqual(assistant.speech_recognition.requests[0].source, InputSource.VOICE)

    def test_listen_for_active_command_uses_speech_recognition_service_path(self) -> None:
        assistant = _AssistantProbe()
        state_flags = _StateFlags()

        original_prepare = _module._prepare_for_active_capture
        original_note_listening = _module._note_turn_benchmark_listening_started
        original_remember = _module._remember_capture_from_transcript
        original_note_finalized = _module._note_turn_benchmark_speech_finalized

        remembered: list[str] = []
        finalized: list[dict[str, object]] = []

        try:
            _module._prepare_for_active_capture = lambda assistant_obj: None
            _module._note_turn_benchmark_listening_started = lambda assistant_obj, phase: None
            _module._remember_capture_from_transcript = (
                lambda assistant_obj, transcript, phase: remembered.append(transcript.text)
            )
            _module._note_turn_benchmark_speech_finalized = (
                lambda assistant_obj, text, phase, transcript=None: finalized.append(
                    {
                        "text": text,
                        "phase": phase,
                        "backend_label": dict(getattr(transcript, "metadata", {}) or {}).get("backend_label", ""),
                        "mode": dict(getattr(transcript, "metadata", {}) or {}).get("mode", ""),
                        "confidence": float(getattr(transcript, "confidence", 0.0) or 0.0),
                    }
                )
            )

            result = _listen_for_active_command(assistant, state_flags)
        finally:
            _module._prepare_for_active_capture = original_prepare
            _module._note_turn_benchmark_listening_started = original_note_listening
            _module._remember_capture_from_transcript = original_remember
            _module._note_turn_benchmark_speech_finalized = original_note_finalized

        self.assertEqual(result, "hello via service")
        self.assertEqual(remembered, ["hello via service"])
        self.assertEqual(len(finalized), 1)
        self.assertEqual(finalized[0]["text"], "hello via service")
        self.assertEqual(finalized[0]["phase"], "command")
        self.assertEqual(finalized[0]["backend_label"], "faster_whisper")
        self.assertEqual(finalized[0]["mode"], "command")
        self.assertAlmostEqual(finalized[0]["confidence"], 0.88)
        self.assertEqual(
            assistant.speech_recognition.requests[0].mode,
            "command",
        )
        self.assertEqual(
            assistant.voice_session.listening_calls[0]["detail"],
            "active_window:command",
        )
        self.assertEqual(
            assistant.voice_session.transcribing_calls[0]["detail"],
            "speech_captured",
        )


if __name__ == "__main__":
    unittest.main()