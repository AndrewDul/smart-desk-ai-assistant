from __future__ import annotations

import unittest

from modules.runtime.contracts import InputSource, TranscriptRequest, TranscriptResult
from modules.runtime.stt.service import SpeechRecognitionService


class _RichBackend:
    def __init__(self) -> None:
        self.requests: list[TranscriptRequest] = []

    def transcribe(self, request: TranscriptRequest) -> TranscriptResult | None:
        self.requests.append(request)
        return TranscriptResult(
            text="hello from rich backend",
            language="en",
            confidence=0.91,
            is_final=True,
            source=request.source,
            metadata={"engine": "fake_rich"},
        )


class _CompatibilityBackend:
    def __init__(self) -> None:
        self.calls: list[tuple[str, float, bool]] = []

    def listen(self, timeout: float = 8.0, debug: bool = False) -> str | None:
        self.calls.append(("listen", timeout, debug))
        return "hello from listen"

    def listen_once(self, timeout: float = 8.0, debug: bool = False) -> str | None:
        self.calls.append(("listen_once", timeout, debug))
        return "hello from listen once"

    def listen_for_command(self, timeout: float = 8.0, debug: bool = False) -> str | None:
        self.calls.append(("listen_for_command", timeout, debug))
        return "hello from command"


class _BlankBackend:
    def transcribe(self, request: TranscriptRequest) -> TranscriptResult | None:
        return TranscriptResult(
            text="   ",
            language="en",
            confidence=0.2,
            is_final=True,
            source=request.source,
            metadata={},
        )


class SpeechRecognitionServiceTests(unittest.TestCase):
    def test_transcribe_prefers_rich_contract(self) -> None:
        backend = _RichBackend()
        service = SpeechRecognitionService(backend=backend, backend_label="fake_rich")

        result = service.transcribe(
            TranscriptRequest(
                timeout_seconds=4.0,
                debug=False,
                source=InputSource.VOICE,
                mode="conversation",
                metadata={"test_case": "rich_contract"},
            )
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.text, "hello from rich backend")
        self.assertEqual(result.language, "en")
        self.assertAlmostEqual(result.confidence, 0.91)
        self.assertEqual(result.source, InputSource.VOICE)
        self.assertEqual(result.metadata["mode"], "conversation")
        self.assertEqual(result.metadata["backend_label"], "fake_rich")
        self.assertEqual(result.metadata["adapter"], "service_rich_contract")
        self.assertEqual(backend.requests[0].mode, "conversation")

    def test_transcribe_command_prefers_listen_for_command_in_compatibility_mode(self) -> None:
        backend = _CompatibilityBackend()
        service = SpeechRecognitionService(backend=backend, backend_label="compat_backend")

        result = service.transcribe_command(
            timeout_seconds=5.0,
            debug=True,
            source=InputSource.VOICE,
            metadata={"test_case": "command_policy"},
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.text, "hello from command")
        self.assertEqual(result.source, InputSource.VOICE)
        self.assertEqual(result.metadata["mode"], "command")
        self.assertEqual(result.metadata["backend_label"], "compat_backend")
        self.assertEqual(result.metadata["adapter"], "service_compatibility")
        self.assertEqual(backend.calls[0], ("listen_for_command", 5.0, True))

    def test_transcribe_conversation_prefers_listen_in_compatibility_mode(self) -> None:
        backend = _CompatibilityBackend()
        service = SpeechRecognitionService(backend=backend, backend_label="compat_backend")

        result = service.transcribe_conversation(
            timeout_seconds=9.0,
            debug=False,
            source=InputSource.VOICE,
            metadata={"test_case": "conversation_policy"},
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.text, "hello from listen")
        self.assertEqual(result.metadata["mode"], "conversation")
        self.assertEqual(backend.calls[0], ("listen", 9.0, False))

    def test_transcribe_returns_none_for_blank_result(self) -> None:
        service = SpeechRecognitionService(
            backend=_BlankBackend(),
            backend_label="blank_backend",
        )

        result = service.transcribe(
            TranscriptRequest(
                timeout_seconds=3.0,
                debug=False,
                source=InputSource.VOICE,
                mode="command",
                metadata={},
            )
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()