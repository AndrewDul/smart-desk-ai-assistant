from __future__ import annotations

import unittest

import numpy as np

from modules.devices.audio.input.faster_whisper.backend import FasterWhisperInputBackend
from modules.devices.audio.input.text_input import TextInput
from modules.devices.audio.input.whisper_cpp.backend import WhisperCppInputBackend
from modules.runtime.contracts import InputSource, TranscriptRequest, TranscriptResult


class STTContractAlignmentTests(unittest.TestCase):
    def test_text_input_transcribe_returns_transcript_result(self) -> None:
        backend = TextInput()
        backend.listen = lambda timeout=8.0, debug=False: "hello nexa"  # type: ignore[method-assign]

        result = backend.transcribe(
            TranscriptRequest(
                timeout_seconds=3.0,
                debug=False,
                source=InputSource.TEXT,
                mode="command",
                metadata={"test_case": "text_input"},
            )
        )

        self.assertIsInstance(result, TranscriptResult)
        assert result is not None
        self.assertEqual(result.text, "hello nexa")
        self.assertEqual(result.source, InputSource.TEXT)
        self.assertEqual(result.metadata["mode"], "command")
        self.assertEqual(result.metadata["backend_label"], "text_input")

    def test_faster_whisper_transcribe_returns_transcript_result(self) -> None:
        backend = object.__new__(FasterWhisperInputBackend)
        backend.sample_rate = 16000
        backend.language = "auto"

        class _Logger:
            def warning(self, *args, **kwargs) -> None:
                return None

        backend.LOGGER = _Logger()
        backend._record_until_silence = lambda timeout=8.0, debug=False: np.ones(16000, dtype=np.float32)
        backend._transcribe_audio_candidate = lambda audio, debug=False: {
            "text": "hello from faster whisper",
            "language": "en",
            "language_probability": 0.83,
            "elapsed": 0.31,
            "forced_language": "",
            "path": "primary",
            "engine": "faster_whisper",
        }

        result = FasterWhisperInputBackend.transcribe(
            backend,
            TranscriptRequest(
                timeout_seconds=4.0,
                debug=False,
                source=InputSource.VOICE,
                mode="conversation",
                metadata={"test_case": "faster_whisper"},
            ),
        )

        self.assertIsInstance(result, TranscriptResult)
        assert result is not None
        self.assertEqual(result.text, "hello from faster whisper")
        self.assertEqual(result.language, "en")
        self.assertAlmostEqual(result.confidence, 0.83)
        self.assertEqual(result.source, InputSource.VOICE)
        self.assertEqual(result.metadata["mode"], "conversation")
        self.assertEqual(result.metadata["backend_label"], "faster_whisper")
        self.assertEqual(result.metadata["detected_language"], "en")
        self.assertAlmostEqual(result.metadata["language_probability"], 0.83)
        self.assertAlmostEqual(result.metadata["transcription_elapsed_seconds"], 0.31)
        self.assertEqual(result.metadata["transcription_path"], "primary")
        self.assertFalse(result.metadata["rescue_used"])
        self.assertFalse(result.metadata["retry_used"])
        self.assertGreater(result.metadata["audio_duration_seconds"], 0.0)

    def test_whisper_cpp_transcribe_returns_transcript_result(self) -> None:
        backend = object.__new__(WhisperCppInputBackend)
        backend.sample_rate = 16000
        backend.language = "auto"

        class _Logger:
            def warning(self, *args, **kwargs) -> None:
                return None

        backend.LOGGER = _Logger()
        backend._record_until_silence = lambda timeout=8.0, debug=False: np.ones(8000, dtype=np.float32)
        backend._transcribe_audio_candidate = lambda audio, debug=False: {
            "text": "hello from whisper cpp",
            "language": "en",
            "language_probability": 0.0,
            "elapsed": 0.27,
            "forced_language": "",
            "path": "primary",
            "engine": "whisper_cpp",
        }

        result = WhisperCppInputBackend.transcribe(
            backend,
            TranscriptRequest(
                timeout_seconds=4.0,
                debug=False,
                source=InputSource.VOICE,
                mode="command",
                metadata={"test_case": "whisper_cpp"},
            ),
        )

        self.assertIsInstance(result, TranscriptResult)
        assert result is not None
        self.assertEqual(result.text, "hello from whisper cpp")
        self.assertEqual(result.language, "en")
        self.assertAlmostEqual(result.confidence, 0.0)
        self.assertEqual(result.source, InputSource.VOICE)
        self.assertEqual(result.metadata["mode"], "command")
        self.assertEqual(result.metadata["backend_label"], "whisper_cpp")
        self.assertEqual(result.metadata["detected_language"], "en")
        self.assertAlmostEqual(result.metadata["transcription_elapsed_seconds"], 0.27)
        self.assertEqual(result.metadata["transcription_path"], "primary")
        self.assertFalse(result.metadata["rescue_used"])
        self.assertFalse(result.metadata["retry_used"])
        self.assertGreater(result.metadata["audio_duration_seconds"], 0.0)


if __name__ == "__main__":
    unittest.main()