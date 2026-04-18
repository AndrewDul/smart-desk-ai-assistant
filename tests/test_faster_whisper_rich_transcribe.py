from __future__ import annotations

import unittest

import numpy as np

from modules.devices.audio.input.faster_whisper.backend import FasterWhisperInputBackend
from modules.runtime.contracts import InputSource, TranscriptRequest, TranscriptResult


class FasterWhisperRichTranscribeTests(unittest.TestCase):
    def test_transcribe_uses_candidate_language_confidence_and_path_metadata(self) -> None:
        backend = object.__new__(FasterWhisperInputBackend)
        backend.sample_rate = 16000
        backend.language = "auto"

        class _Logger:
            def warning(self, *args, **kwargs) -> None:
                return None

        backend.LOGGER = _Logger()
        backend._record_until_silence = lambda timeout=8.0, debug=False: np.ones(16000, dtype=np.float32)
        backend._transcribe_audio_candidate = lambda audio, debug=False: {
            "text": "cześć nexa",
            "language": "pl",
            "language_probability": 0.87,
            "elapsed": 0.42,
            "forced_language": "pl",
            "path": "rescue",
            "engine": "faster_whisper",
        }

        result = FasterWhisperInputBackend.transcribe(
            backend,
            TranscriptRequest(
                timeout_seconds=4.0,
                debug=False,
                source=InputSource.VOICE,
                mode="conversation",
                metadata={"test_case": "faster_whisper_rich"},
            ),
        )

        self.assertIsInstance(result, TranscriptResult)
        assert result is not None
        self.assertEqual(result.text, "cześć nexa")
        self.assertEqual(result.language, "pl")
        self.assertAlmostEqual(result.confidence, 0.87)
        self.assertEqual(result.source, InputSource.VOICE)
        self.assertEqual(result.metadata["mode"], "conversation")
        self.assertEqual(result.metadata["backend_label"], "faster_whisper")
        self.assertEqual(result.metadata["detected_language"], "pl")
        self.assertAlmostEqual(result.metadata["language_probability"], 0.87)
        self.assertAlmostEqual(result.metadata["transcription_elapsed_seconds"], 0.42)
        self.assertEqual(result.metadata["forced_language"], "pl")
        self.assertEqual(result.metadata["transcription_path"], "rescue")
        self.assertTrue(result.metadata["rescue_used"])
        self.assertFalse(result.metadata["retry_used"])
        self.assertEqual(result.metadata["engine"], "faster_whisper")
        self.assertGreater(result.metadata["audio_duration_seconds"], 0.0)

    def test_transcribe_returns_none_when_candidate_is_missing(self) -> None:
        backend = object.__new__(FasterWhisperInputBackend)
        backend.sample_rate = 16000
        backend.language = "auto"

        class _Logger:
            def warning(self, *args, **kwargs) -> None:
                return None

        backend.LOGGER = _Logger()
        backend._record_until_silence = lambda timeout=8.0, debug=False: np.ones(16000, dtype=np.float32)
        backend._transcribe_audio_candidate = lambda audio, debug=False: None

        result = FasterWhisperInputBackend.transcribe(
            backend,
            TranscriptRequest(
                timeout_seconds=4.0,
                debug=False,
                source=InputSource.VOICE,
                mode="command",
                metadata={"test_case": "faster_whisper_missing_candidate"},
            ),
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()