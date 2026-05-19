"""
Tests for explicit session language injection into FasterWhisper open-question ASR.

Policy under test:
- Prior confirmed turn (_last_input_capture truthy) with known language → force that language
- Fresh session (_last_input_capture falsy) → no force_language → config language (auto)
- Unsupported language in prior turn → no force_language → auto
- follow_up / memory_message modes → existing path unchanged

Verifies:
- Fresh session with no prior turn does NOT force English
- Polish prior turn forces language="pl"
- English prior turn forces language="en"
- Language switches (EN→PL→EN) handled via _last_input_capture language
- Unsupported prior-turn language does not silently force EN
- [asr-config] log source reflects source correctly
- follow_up / memory_message injection is unchanged
- _resolve_dictation_preferred_language no longer returns "en" for missing language
- Default beam_size is 3
- ASR benchmark sweep/model-size/beam/language options available
"""
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
    _stub = types.ModuleType("modules.core.assistant")
    _stub.CoreAssistant = object
    sys.modules["modules.core.assistant"] = _stub

if "modules.runtime.main_loop" not in sys.modules:
    _pkg = types.ModuleType("modules.runtime.main_loop")
    _pkg.__path__ = [str(_MODULE_PATH.parent)]
    sys.modules["modules.runtime.main_loop"] = _pkg

_spec = importlib.util.spec_from_file_location(
    "modules.runtime.main_loop.active_window",
    _MODULE_PATH,
)
if _spec is None or _spec.loader is None:
    raise RuntimeError("Failed to load active_window module for tests.")
_active_window = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _active_window
_spec.loader.exec_module(_active_window)

_capture_transcript_with_speech_service = _active_window._capture_transcript_with_speech_service


class _SpeechRecognitionCapture:
    def __init__(self, language: str = "en") -> None:
        self.requests: list[TranscriptRequest] = []
        self.language = language

    def transcribe(self, request: TranscriptRequest) -> TranscriptResult:
        self.requests.append(request)
        return TranscriptResult(
            text="test transcript",
            language=self.language,
            confidence=0.9,
            is_final=True,
            source=request.source,
            metadata={"backend_label": "faster_whisper", "mode": request.mode},
        )


def _make_assistant(
    *,
    last_language: str = "en",
    last_input_capture: dict | None = None,
    last_confirmed_language: str = "",
) -> object:
    """Build a minimal assistant stub with configurable prior-turn state."""
    class _Stub:
        def __init__(self) -> None:
            self.last_language = last_language
            # Mirrors core.py init: {} == fresh session, populated dict == confirmed prior turn
            self._last_input_capture: dict = last_input_capture if last_input_capture is not None else {}
            # Persists across _consume_last_input_capture; set by _remember_input_capture
            self._last_confirmed_language: str = last_confirmed_language
            self.speech_recognition = _SpeechRecognitionCapture(language=last_language)
            self.voice_in = object()
            self.voice_debug = False
            self._last_capture_handoff: dict = {}
            self._primed_capture_handoff: dict = {}
            self.settings = {"voice_input": {}}
            self.pending_follow_up: dict | None = None

    return _Stub()


def _run_capture(assistant: object, mode: str) -> TranscriptRequest:
    result = _capture_transcript_with_speech_service(
        assistant, timeout=5.0, debug=False, mode=mode,
    )
    assert result is not None
    return assistant.speech_recognition.requests[0]


class FreshSessionLanguageTests(unittest.TestCase):
    """Fresh session (_last_input_capture empty) must never force English."""

    def test_fresh_session_command_mode_no_force_language(self) -> None:
        assistant = _make_assistant(last_language="en", last_input_capture={})
        req = _run_capture(assistant, "command")
        self.assertNotIn("force_language", req.metadata)
        self.assertNotIn("preferred_language", req.metadata)

    def test_fresh_session_source_is_unknown_initial_turn(self) -> None:
        assistant = _make_assistant(last_language="en", last_input_capture={})
        req = _run_capture(assistant, "command")
        self.assertEqual(req.metadata.get("asr_language_source"), "unknown_initial_turn")

    def test_fresh_session_wake_command_no_force_language(self) -> None:
        assistant = _make_assistant(last_language="en", last_input_capture={})
        req = _run_capture(assistant, "wake_command")
        self.assertNotIn("force_language", req.metadata)
        self.assertEqual(req.metadata.get("asr_language_source"), "unknown_initial_turn")

    def test_fresh_session_conversation_mode_no_force_language(self) -> None:
        assistant = _make_assistant(last_language="en", last_input_capture={})
        req = _run_capture(assistant, "conversation")
        self.assertNotIn("force_language", req.metadata)
        self.assertEqual(req.metadata.get("asr_language_source"), "unknown_initial_turn")

    def test_fresh_session_inline_command_after_wake_no_force_language(self) -> None:
        assistant = _make_assistant(last_language="en", last_input_capture={})
        req = _run_capture(assistant, "inline_command_after_wake")
        self.assertNotIn("force_language", req.metadata)


class WakeCommandAlwaysAutoTests(unittest.TestCase):
    """command and wake_command are new-turn modes: always auto regardless of prior turn."""

    def test_pl_prior_turn_does_not_force_pl_for_command(self) -> None:
        assistant = _make_assistant(
            last_confirmed_language="pl",
            last_input_capture={"text": "co to jest", "language": "pl"},
        )
        req = _run_capture(assistant, "command")
        self.assertNotIn("force_language", req.metadata)
        self.assertEqual(req.metadata.get("asr_language_source"), "unknown_initial_turn")

    def test_en_prior_turn_does_not_force_en_for_command(self) -> None:
        assistant = _make_assistant(
            last_confirmed_language="en",
            last_input_capture={"text": "what is gravity", "language": "en"},
        )
        req = _run_capture(assistant, "command")
        self.assertNotIn("force_language", req.metadata)
        self.assertEqual(req.metadata.get("asr_language_source"), "unknown_initial_turn")

    def test_pl_prior_turn_does_not_force_pl_for_wake_command(self) -> None:
        assistant = _make_assistant(
            last_confirmed_language="pl",
            last_input_capture={"text": "jaka jest godzina", "language": "pl"},
        )
        req = _run_capture(assistant, "wake_command")
        self.assertNotIn("force_language", req.metadata)
        self.assertEqual(req.metadata.get("asr_language_source"), "unknown_initial_turn")

    def test_en_prior_turn_does_not_force_en_for_wake_command(self) -> None:
        assistant = _make_assistant(
            last_confirmed_language="en",
            last_input_capture={"text": "hello", "language": "en"},
        )
        req = _run_capture(assistant, "wake_command")
        self.assertNotIn("force_language", req.metadata)
        self.assertEqual(req.metadata.get("asr_language_source"), "unknown_initial_turn")

    def test_bilingual_switch_en_to_pl_command_uses_auto(self) -> None:
        """EN→PL switch: command mode must NOT force EN so Polish is recognized correctly."""
        assistant = _make_assistant(
            last_confirmed_language="en",
            last_input_capture={"text": "what is teleportation", "language": "en"},
        )
        req = _run_capture(assistant, "command")
        self.assertNotIn("force_language", req.metadata)

    def test_bilingual_switch_pl_to_en_command_uses_auto(self) -> None:
        """PL→EN switch: command mode must NOT force PL."""
        assistant = _make_assistant(
            last_confirmed_language="pl",
            last_input_capture={"text": "co to jest teleportacja", "language": "pl"},
        )
        req = _run_capture(assistant, "command")
        self.assertNotIn("force_language", req.metadata)

    def test_unsupported_prior_lang_command_uses_auto(self) -> None:
        assistant = _make_assistant(
            last_confirmed_language="pl",
            last_input_capture={"text": "hallo welt", "language": "de"},
        )
        req = _run_capture(assistant, "command")
        self.assertNotIn("force_language", req.metadata)
        self.assertEqual(req.metadata.get("asr_language_source"), "unknown_initial_turn")

    def test_no_prior_turn_wake_command_uses_auto(self) -> None:
        assistant = _make_assistant(last_language="de", last_input_capture={"language": "de"})
        req = _run_capture(assistant, "command")
        self.assertNotIn("force_language", req.metadata)
        self.assertEqual(req.metadata.get("asr_language_source"), "unknown_initial_turn")


class ContinuationModeUsesLastLanguageTests(unittest.TestCase):
    """inline_command_after_wake and conversation force _last_confirmed_language."""

    def test_pl_confirmed_forces_pl_for_conversation(self) -> None:
        assistant = _make_assistant(last_confirmed_language="pl")
        req = _run_capture(assistant, "conversation")
        self.assertEqual(req.metadata.get("force_language"), "pl")
        self.assertEqual(req.metadata.get("asr_language_source"), "session_last_language")

    def test_en_confirmed_forces_en_for_conversation(self) -> None:
        assistant = _make_assistant(last_confirmed_language="en")
        req = _run_capture(assistant, "conversation")
        self.assertEqual(req.metadata.get("force_language"), "en")
        self.assertEqual(req.metadata.get("asr_language_source"), "session_last_language")

    def test_pl_confirmed_forces_pl_for_inline_command_after_wake(self) -> None:
        assistant = _make_assistant(last_confirmed_language="pl")
        req = _run_capture(assistant, "inline_command_after_wake")
        self.assertEqual(req.metadata.get("force_language"), "pl")
        self.assertEqual(req.metadata.get("asr_language_source"), "session_last_language")

    def test_en_confirmed_forces_en_for_inline_command_after_wake(self) -> None:
        assistant = _make_assistant(last_confirmed_language="en")
        req = _run_capture(assistant, "inline_command_after_wake")
        self.assertEqual(req.metadata.get("force_language"), "en")

    def test_no_confirmed_language_conversation_uses_auto(self) -> None:
        assistant = _make_assistant(last_confirmed_language="")
        req = _run_capture(assistant, "conversation")
        self.assertNotIn("force_language", req.metadata)
        self.assertEqual(req.metadata.get("asr_language_source"), "unknown_initial_turn")


class ExistingModesUnchangedTests(unittest.TestCase):
    """memory_message / follow_up / conversation_repair injection is unaffected."""

    def test_memory_message_still_uses_pending_follow_up_language(self) -> None:
        assistant = _make_assistant(last_language="pl")
        assistant.pending_follow_up = {"language": "en"}
        req = _run_capture(assistant, "memory_message")
        self.assertEqual(req.metadata.get("preferred_language"), "en")
        self.assertEqual(req.metadata.get("dictation_capture"), True)
        self.assertNotEqual(req.metadata.get("asr_language_source"), "session_last_language")

    def test_follow_up_still_uses_pending_follow_up_language(self) -> None:
        assistant = _make_assistant(last_language="pl")
        assistant.pending_follow_up = {"language": "en"}
        req = _run_capture(assistant, "follow_up")
        self.assertEqual(req.metadata.get("preferred_language"), "en")
        self.assertEqual(req.metadata.get("follow_up_language_preferred"), True)

    def test_grace_mode_not_injected(self) -> None:
        assistant = _make_assistant(
            last_language="pl",
            last_input_capture={"language": "pl"},
        )
        req = _run_capture(assistant, "grace")
        self.assertNotIn("force_language", req.metadata)
        self.assertNotIn("asr_language_source", req.metadata)


class ResolveDictationPreferredLanguageTests(unittest.TestCase):
    """_resolve_dictation_preferred_language must return None when no language in metadata."""

    def _make_stub(self) -> object:
        from modules.devices.audio.input.faster_whisper.backend.runtime_mixin import (
            FasterWhisperRuntimeMixin,
        )
        from modules.devices.audio.input.faster_whisper.backend.core import (
            FasterWhisperInputBackend,
        )

        class _Stub(FasterWhisperRuntimeMixin):
            SUPPORTED_LANGUAGES = {"pl", "en"}

        stub = _Stub.__new__(_Stub)
        stub._resolve_dictation_preferred_language = (
            FasterWhisperInputBackend._resolve_dictation_preferred_language.__get__(stub)
        )
        return stub

    def test_command_mode_pl_returns_pl(self) -> None:
        stub = self._make_stub()
        result = stub._resolve_dictation_preferred_language(
            mode="command",
            metadata={"force_language": "pl", "preferred_language": "pl"},
        )
        self.assertEqual(result, "pl")

    def test_command_mode_en_returns_en(self) -> None:
        stub = self._make_stub()
        result = stub._resolve_dictation_preferred_language(
            mode="command",
            metadata={"force_language": "en"},
        )
        self.assertEqual(result, "en")

    def test_wake_command_mode_pl_returns_pl(self) -> None:
        stub = self._make_stub()
        result = stub._resolve_dictation_preferred_language(
            mode="wake_command",
            metadata={"force_language": "pl"},
        )
        self.assertEqual(result, "pl")

    def test_conversation_mode_returns_language(self) -> None:
        stub = self._make_stub()
        result = stub._resolve_dictation_preferred_language(
            mode="conversation",
            metadata={"force_language": "en"},
        )
        self.assertEqual(result, "en")

    def test_inline_command_after_wake_returns_language(self) -> None:
        stub = self._make_stub()
        result = stub._resolve_dictation_preferred_language(
            mode="inline_command_after_wake",
            metadata={"force_language": "pl"},
        )
        self.assertEqual(result, "pl")

    def test_empty_metadata_returns_none_not_en(self) -> None:
        """Key requirement: missing force_language must NOT silently return 'en'."""
        stub = self._make_stub()
        result = stub._resolve_dictation_preferred_language(
            mode="command",
            metadata={},
        )
        self.assertIsNone(result)

    def test_none_raw_language_returns_none(self) -> None:
        stub = self._make_stub()
        result = stub._resolve_dictation_preferred_language(
            mode="command",
            metadata={"force_language": None},
        )
        self.assertIsNone(result)

    def test_unknown_mode_returns_none(self) -> None:
        stub = self._make_stub()
        result = stub._resolve_dictation_preferred_language(
            mode="grace",
            metadata={"force_language": "pl"},
        )
        self.assertIsNone(result)

    def test_memory_message_mode_still_works(self) -> None:
        stub = self._make_stub()
        result = stub._resolve_dictation_preferred_language(
            mode="memory_message",
            metadata={"force_language": "pl"},
        )
        self.assertEqual(result, "pl")

    def test_follow_up_mode_still_works(self) -> None:
        stub = self._make_stub()
        result = stub._resolve_dictation_preferred_language(
            mode="follow_up",
            metadata={"preferred_language": "en"},
        )
        self.assertEqual(result, "en")


class DefaultBeamSizeTests(unittest.TestCase):
    """Default beam_size should be 3 after upgrade from 1."""

    def test_default_beam_size_is_3(self) -> None:
        from modules.shared.config.settings_core.defaults import DEFAULT_SETTINGS
        voice_input = DEFAULT_SETTINGS.get("voice_input", {})
        self.assertEqual(voice_input.get("beam_size"), 3)


class ASRBenchmarkOptionTests(unittest.TestCase):
    """ASR benchmark module exposes sweep / model-size / beam / language CLI options."""

    def _load_benchmark_module(self):
        spec = importlib.util.spec_from_file_location(
            "asr_benchmark_for_options_test",
            str(_PROJECT_ROOT / "scripts" / "asr_benchmark.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_sweep_configs_defined(self) -> None:
        mod = self._load_benchmark_module()
        self.assertIsInstance(mod.SWEEP_CONFIGS, list)
        self.assertGreater(len(mod.SWEEP_CONFIGS), 2)

    def test_sweep_configs_have_required_keys(self) -> None:
        mod = self._load_benchmark_module()
        for cfg in mod.SWEEP_CONFIGS:
            self.assertIn("model_size", cfg)
            self.assertIn("beam_size", cfg)
            self.assertIn("language_mode", cfg)

    def test_run_sweep_callable(self) -> None:
        mod = self._load_benchmark_module()
        self.assertTrue(callable(getattr(mod, "run_sweep", None)))

    def test_run_single_config_callable(self) -> None:
        mod = self._load_benchmark_module()
        self.assertTrue(callable(getattr(mod, "run_single_config", None)))

    def test_word_error_rough_still_exists(self) -> None:
        mod = self._load_benchmark_module()
        self.assertAlmostEqual(mod._word_error_rough("co to jest", "co to jest"), 0.0)
        self.assertGreater(mod._word_error_rough("co to jest", "garbage xyz abc"), 0.5)


class ConfirmedLanguagePersistenceTests(unittest.TestCase):
    """_last_confirmed_language persists across _consume_last_input_capture for continuation modes."""

    def test_pl_confirmed_survives_consumption_for_conversation(self) -> None:
        """After _last_input_capture consumed ({}), conversation still gets pl via _last_confirmed_language."""
        assistant = _make_assistant(
            last_input_capture={},  # consumed
            last_confirmed_language="pl",
        )
        req = _run_capture(assistant, "conversation")
        self.assertEqual(req.metadata.get("force_language"), "pl")
        self.assertEqual(req.metadata.get("asr_language_source"), "session_last_language")

    def test_en_confirmed_survives_consumption_for_conversation(self) -> None:
        assistant = _make_assistant(
            last_input_capture={},
            last_confirmed_language="en",
        )
        req = _run_capture(assistant, "conversation")
        self.assertEqual(req.metadata.get("force_language"), "en")

    def test_pl_confirmed_survives_consumption_for_inline_command_after_wake(self) -> None:
        assistant = _make_assistant(
            last_input_capture={},
            last_confirmed_language="pl",
        )
        req = _run_capture(assistant, "inline_command_after_wake")
        self.assertEqual(req.metadata.get("force_language"), "pl")

    def test_fresh_session_command_is_auto_regardless_of_last_language(self) -> None:
        """command mode is always auto — _last_confirmed_language is ignored for new wake turns."""
        assistant = _make_assistant(
            last_input_capture={},
            last_confirmed_language="pl",
        )
        req = _run_capture(assistant, "command")
        self.assertNotIn("force_language", req.metadata)
        self.assertEqual(req.metadata.get("asr_language_source"), "unknown_initial_turn")

    def test_fresh_session_wake_command_is_auto_regardless_of_confirmed(self) -> None:
        assistant = _make_assistant(last_confirmed_language="en")
        req = _run_capture(assistant, "wake_command")
        self.assertNotIn("force_language", req.metadata)
        self.assertEqual(req.metadata.get("asr_language_source"), "unknown_initial_turn")

    def test_no_confirmed_conversation_uses_auto(self) -> None:
        assistant = _make_assistant(last_input_capture={}, last_confirmed_language="")
        req = _run_capture(assistant, "conversation")
        self.assertNotIn("force_language", req.metadata)
        self.assertEqual(req.metadata.get("asr_language_source"), "unknown_initial_turn")


if __name__ == "__main__":
    unittest.main()
