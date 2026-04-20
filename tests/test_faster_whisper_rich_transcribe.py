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
        backend.max_record_seconds = 6.5
        backend.capture_profiles = {
            "default": {
                "timeout_seconds": 6.5,
                "end_silence_seconds": 0.6,
                "min_speech_seconds": 0.2,
                "pre_roll_seconds": 0.45,
            },
            "conversation": {
                "timeout_seconds": 6.5,
                "end_silence_seconds": 0.6,
                "min_speech_seconds": 0.2,
                "pre_roll_seconds": 0.45,
            },
        }

        class _Logger:
            def warning(self, *args, **kwargs) -> None:
                return None

        backend.LOGGER = _Logger()
        backend._record_until_silence = lambda timeout=8.0, debug=False, **kwargs: np.ones(16000, dtype=np.float32)
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
        self.assertEqual(result.metadata["capture_profile"], "conversation")
        self.assertAlmostEqual(result.metadata["capture_timeout_seconds"], 4.0)
        self.assertAlmostEqual(result.metadata["capture_end_silence_seconds"], 0.6)
        self.assertAlmostEqual(result.metadata["capture_min_speech_seconds"], 0.2)
        self.assertAlmostEqual(result.metadata["capture_pre_roll_seconds"], 0.45)
        self.assertGreater(result.metadata["audio_duration_seconds"], 0.0)
        self.assertGreater(float(result.metadata["capture_finished_at_monotonic"]), 0.0)
        self.assertGreaterEqual(float(result.metadata["capture_elapsed_seconds"]), 0.0)

    def test_transcribe_returns_none_when_candidate_is_missing(self) -> None:
        backend = object.__new__(FasterWhisperInputBackend)
        backend.sample_rate = 16000
        backend.language = "auto"
        backend.max_record_seconds = 6.5
        backend.capture_profiles = {
            "default": {
                "timeout_seconds": 6.5,
                "end_silence_seconds": 0.6,
                "min_speech_seconds": 0.2,
                "pre_roll_seconds": 0.45,
            },
            "command": {
                "timeout_seconds": 5.2,
                "end_silence_seconds": 0.4,
                "min_speech_seconds": 0.14,
                "pre_roll_seconds": 0.24,
            },
        }

        class _Logger:
            def warning(self, *args, **kwargs) -> None:
                return None

        backend.LOGGER = _Logger()
        backend._record_until_silence = lambda timeout=8.0, debug=False, **kwargs: np.ones(16000, dtype=np.float32)
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

    def test_transcribe_uses_mode_specific_capture_profile_for_follow_up(self) -> None:
        backend = object.__new__(FasterWhisperInputBackend)
        backend.sample_rate = 16000
        backend.language = "auto"
        backend.max_record_seconds = 6.5
        backend.capture_profiles = {
            "default": {
                "timeout_seconds": 6.5,
                "end_silence_seconds": 0.6,
                "min_speech_seconds": 0.2,
                "pre_roll_seconds": 0.45,
            },
            "follow_up": {
                "timeout_seconds": 4.8,
                "end_silence_seconds": 0.34,
                "min_speech_seconds": 0.12,
                "pre_roll_seconds": 0.2,
            },
        }

        class _Logger:
            def warning(self, *args, **kwargs) -> None:
                return None

        backend.LOGGER = _Logger()
        capture_calls: list[dict[str, float | bool]] = []

        def _record_until_silence(timeout=8.0, debug=False, **kwargs):
            capture_calls.append(
                {
                    "timeout": float(timeout),
                    "debug": bool(debug),
                    "end_silence_seconds": float(kwargs["end_silence_seconds"]),
                    "min_speech_seconds": float(kwargs["min_speech_seconds"]),
                    "pre_roll_seconds": float(kwargs["pre_roll_seconds"]),
                }
            )
            return np.ones(12000, dtype=np.float32)

        backend._record_until_silence = _record_until_silence
        backend._transcribe_audio_candidate = lambda audio, debug=False: {
            "text": "yes, delete it",
            "language": "en",
            "language_probability": 0.92,
            "elapsed": 0.25,
            "forced_language": "",
            "path": "primary",
            "engine": "faster_whisper",
        }

        result = FasterWhisperInputBackend.transcribe(
            backend,
            TranscriptRequest(
                timeout_seconds=6.0,
                debug=True,
                source=InputSource.VOICE,
                mode="follow_up",
                metadata={"test_case": "faster_whisper_follow_up_profile"},
            ),
        )

        self.assertEqual(len(capture_calls), 1)
        self.assertAlmostEqual(capture_calls[0]["timeout"], 4.8)
        self.assertAlmostEqual(capture_calls[0]["end_silence_seconds"], 0.34)
        self.assertAlmostEqual(capture_calls[0]["min_speech_seconds"], 0.12)
        self.assertAlmostEqual(capture_calls[0]["pre_roll_seconds"], 0.2)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.metadata["capture_profile"], "follow_up")
        self.assertAlmostEqual(result.metadata["capture_timeout_seconds"], 4.8)
        self.assertAlmostEqual(result.metadata["capture_end_silence_seconds"], 0.34)
        self.assertAlmostEqual(result.metadata["capture_min_speech_seconds"], 0.12)
        self.assertAlmostEqual(result.metadata["capture_pre_roll_seconds"], 0.2)


    def test_transcribe_uses_wake_command_capture_profile(self) -> None:
        backend = object.__new__(FasterWhisperInputBackend)
        backend.sample_rate = 16000
        backend.language = "auto"
        backend.max_record_seconds = 6.5
        backend.capture_profiles = {
            "default": {
                "timeout_seconds": 6.5,
                "end_silence_seconds": 0.6,
                "min_speech_seconds": 0.2,
                "pre_roll_seconds": 0.45,
            },
            "wake_command": {
                "timeout_seconds": 4.4,
                "end_silence_seconds": 0.26,
                "min_speech_seconds": 0.10,
                "pre_roll_seconds": 0.14,
            },
        }

        class _Logger:
            def warning(self, *args, **kwargs) -> None:
                return None

        backend.LOGGER = _Logger()
        capture_calls: list[dict[str, float | bool]] = []

        def _record_until_silence(timeout=8.0, debug=False, **kwargs):
            capture_calls.append(
                {
                    "timeout": float(timeout),
                    "debug": bool(debug),
                    "end_silence_seconds": float(kwargs["end_silence_seconds"]),
                    "min_speech_seconds": float(kwargs["min_speech_seconds"]),
                    "pre_roll_seconds": float(kwargs["pre_roll_seconds"]),
                }
            )
            return np.ones(11000, dtype=np.float32)

        backend._record_until_silence = _record_until_silence
        backend._transcribe_audio_candidate = lambda audio, debug=False: {
            "text": "set a timer for ten minutes",
            "language": "en",
            "language_probability": 0.93,
            "elapsed": 0.24,
            "forced_language": "",
            "path": "primary",
            "engine": "faster_whisper",
        }

        result = FasterWhisperInputBackend.transcribe(
            backend,
            TranscriptRequest(
                timeout_seconds=6.0,
                debug=False,
                source=InputSource.VOICE,
                mode="wake_command",
                metadata={"test_case": "faster_whisper_wake_command_profile"},
            ),
        )

        self.assertEqual(len(capture_calls), 1)
        self.assertAlmostEqual(capture_calls[0]["timeout"], 4.4)
        self.assertAlmostEqual(capture_calls[0]["end_silence_seconds"], 0.26)
        self.assertAlmostEqual(capture_calls[0]["min_speech_seconds"], 0.10)
        self.assertAlmostEqual(capture_calls[0]["pre_roll_seconds"], 0.14)
        assert result is not None
        self.assertEqual(result.metadata["capture_profile"], "wake_command")


if __name__ == "__main__":
    unittest.main()