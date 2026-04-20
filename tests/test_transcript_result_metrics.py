from __future__ import annotations

import unittest

from modules.runtime.contracts import InputSource, TranscriptResult


class TranscriptResultMetricsTests(unittest.TestCase):
    def test_duration_seconds_prefers_audio_duration_metadata(self) -> None:
        result = TranscriptResult(
            text="hello world",
            language="en",
            source=InputSource.VOICE,
            started_at=10.0,
            ended_at=16.0,
            metadata={
                "audio_duration_seconds": 2.4,
                "transcription_elapsed_seconds": 0.62,
            },
        )

        self.assertAlmostEqual(result.wall_clock_duration_seconds, 6.0)
        self.assertAlmostEqual(result.audio_duration_seconds, 2.4)
        self.assertAlmostEqual(result.duration_seconds, 2.4)
        self.assertAlmostEqual(result.processing_duration_seconds, 0.62)
        self.assertAlmostEqual(result.latency_ms, 620.0)

    def test_processing_duration_falls_back_to_wall_clock_minus_audio_duration(self) -> None:
        result = TranscriptResult(
            text="hello world",
            language="en",
            source=InputSource.VOICE,
            started_at=5.0,
            ended_at=9.5,
            metadata={
                "audio_duration_seconds": 3.2,
            },
        )

        self.assertAlmostEqual(result.wall_clock_duration_seconds, 4.5)
        self.assertAlmostEqual(result.audio_duration_seconds, 3.2)
        self.assertAlmostEqual(result.processing_duration_seconds, 1.3)
        self.assertAlmostEqual(result.latency_ms, 1300.0)

    def test_duration_and_latency_fall_back_to_wall_clock_when_no_metadata_exists(self) -> None:
        result = TranscriptResult(
            text="fallback",
            language="en",
            source=InputSource.VOICE,
            started_at=1.0,
            ended_at=2.75,
            metadata={},
        )

        self.assertAlmostEqual(result.wall_clock_duration_seconds, 1.75)
        self.assertAlmostEqual(result.audio_duration_seconds, 1.75)
        self.assertAlmostEqual(result.duration_seconds, 1.75)
        self.assertAlmostEqual(result.processing_duration_seconds, 0.0)
        self.assertAlmostEqual(result.latency_ms, 0.0)


if __name__ == "__main__":
    unittest.main()