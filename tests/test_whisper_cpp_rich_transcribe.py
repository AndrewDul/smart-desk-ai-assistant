from __future__ import annotations

import unittest

import numpy as np

from modules.devices.audio.input.whisper_cpp.backend import WhisperCppInputBackend
from modules.runtime.contracts import InputSource, TranscriptRequest, TranscriptResult


class WhisperCppRichTranscribeTests(unittest.TestCase):
    def test_transcribe_uses_candidate_language_confidence_and_path_metadata(self) -> None:
        backend = object.__new__(WhisperCppInputBackend)
        backend.sample_rate = 16000
        backend.language = "auto"

        class _Logger:
            def warning(self, *args, **kwargs) -> None:
                return None

        backend.LOGGER = _Logger()
        backend._record_until_silence = lambda timeout=8.0, debug=False: np.ones(16000, dtype=np.float32)
        backend._transcribe_audio_candidate = lambda audio, debug=False: {
            "text": "cześć z whisper cpp",
            "language": "pl",
            "language_probability": 0.0,
            "elapsed": 0.39,
            "forced_language": "pl",
            "path": "rescue",
            "engine": "whisper_cpp",
        }

        result = WhisperCppInputBackend.transcribe(
            backend,
            TranscriptRequest(
                timeout_seconds=4.0,
                debug=False,
                source=InputSource.VOICE,
                mode="conversation",
                metadata={"test_case": "whisper_cpp_rich"},
            ),
        )

        self.assertIsInstance(result, TranscriptResult)
        assert result is not None
        self.assertEqual(result.text, "cześć z whisper cpp")
        self.assertEqual(result.language, "pl")
        self.assertAlmostEqual(result.confidence, 1.0)
        self.assertEqual(result.source, InputSource.VOICE)
        self.assertEqual(result.metadata["mode"], "conversation")
        self.assertEqual(result.metadata["backend_label"], "whisper_cpp")
        self.assertEqual(result.metadata["detected_language"], "pl")
        self.assertAlmostEqual(result.metadata["language_probability"], 0.0)
        self.assertAlmostEqual(result.metadata["transcription_elapsed_seconds"], 0.39)
        self.assertEqual(result.metadata["forced_language"], "pl")
        self.assertEqual(result.metadata["transcription_path"], "rescue")
        self.assertTrue(result.metadata["rescue_used"])
        self.assertFalse(result.metadata["retry_used"])
        self.assertEqual(result.metadata["engine"], "whisper_cpp")
        self.assertGreater(result.metadata["audio_duration_seconds"], 0.0)

    def test_transcribe_returns_none_when_candidate_is_missing(self) -> None:
        backend = object.__new__(WhisperCppInputBackend)
        backend.sample_rate = 16000
        backend.language = "auto"

        class _Logger:
            def warning(self, *args, **kwargs) -> None:
                return None

        backend.LOGGER = _Logger()
        backend._record_until_silence = lambda timeout=8.0, debug=False: np.ones(16000, dtype=np.float32)
        backend._transcribe_audio_candidate = lambda audio, debug=False: None

        result = WhisperCppInputBackend.transcribe(
            backend,
            TranscriptRequest(
                timeout_seconds=4.0,
                debug=False,
                source=InputSource.VOICE,
                mode="command",
                metadata={"test_case": "whisper_cpp_missing_candidate"},
            ),
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()