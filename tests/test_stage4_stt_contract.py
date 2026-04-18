from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

from modules.runtime.contracts import InputSource, TranscriptRequest, TranscriptResult
from modules.runtime.stt.service import SpeechRecognitionService

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

_note_turn_benchmark_speech_finalized = _module._note_turn_benchmark_speech_finalized


class _RichBackend:
    def transcribe(self, request: TranscriptRequest) -> TranscriptResult | None:
        return TranscriptResult(
            text="hello benchmark contract",
            language="en",
            confidence=0.73,
            is_final=True,
            source=request.source,
            metadata={
                "backend_label": "faster_whisper",
                "mode": request.mode,
                "adapter": "service_rich_contract",
                "engine": "faster_whisper",
            },
        )


class _BenchmarkProbe:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def note_speech_finalized(self, **kwargs) -> None:
        self.calls.append(dict(kwargs))


class _AssistantProbe:
    def __init__(self) -> None:
        self.turn_benchmark_service = _BenchmarkProbe()


class Stage4STTContractTests(unittest.TestCase):
    def test_service_result_feeds_benchmark_speech_note_contract(self) -> None:
        service = SpeechRecognitionService(
            backend=_RichBackend(),
            backend_label="faster_whisper",
        )
        assistant = _AssistantProbe()

        transcript = service.transcribe_conversation(
            timeout_seconds=6.0,
            debug=False,
            source=InputSource.VOICE,
            metadata={"test_case": "stage4_contract"},
        )

        self.assertIsNotNone(transcript)
        assert transcript is not None
        self.assertEqual(transcript.text, "hello benchmark contract")
        self.assertEqual(transcript.metadata["backend_label"], "faster_whisper")
        self.assertEqual(transcript.metadata["mode"], "conversation")

        _note_turn_benchmark_speech_finalized(
            assistant,
            text=transcript.text,
            phase="conversation",
            transcript=transcript,
        )

        self.assertEqual(len(assistant.turn_benchmark_service.calls), 1)
        call = assistant.turn_benchmark_service.calls[0]
        self.assertEqual(call["text"], "hello benchmark contract")
        self.assertEqual(call["phase"], "conversation")
        self.assertEqual(call["language"], "en")
        self.assertEqual(call["input_source"], "voice")
        self.assertEqual(call["backend_label"], "faster_whisper")
        self.assertEqual(call["mode"], "conversation")
        self.assertAlmostEqual(call["confidence"], 0.73)
        self.assertGreaterEqual(float(call["latency_ms"]), 0.0)
        self.assertGreaterEqual(float(call["audio_duration_ms"]), 0.0)


if __name__ == "__main__":
    unittest.main()