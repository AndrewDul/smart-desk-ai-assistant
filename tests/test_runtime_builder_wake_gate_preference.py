from __future__ import annotations

import unittest

from modules.runtime.builder.wake_gate_mixin import RuntimeBuilderWakeGateMixin
from modules.runtime.contracts import RuntimeBackendStatus


class _DummyVoiceInput:
    pass


class _FakeOpenWakeWordGate:
    def __init__(self, **kwargs) -> None:
        self.kwargs = dict(kwargs)


class _BuilderProbe(RuntimeBuilderWakeGateMixin):
    @staticmethod
    def _single_capture_mode_enabled(config: dict[str, object]) -> bool:
        value = config.get("single_capture_mode")
        if value is None:
            return True
        return bool(value)

    @staticmethod
    def _import_symbol(module_name: str, symbol_name: str):
        if module_name == "modules.devices.audio.input.wake.openwakeword_gate" and symbol_name == "OpenWakeWordGate":
            return _FakeOpenWakeWordGate
        raise AssertionError(f"Unexpected import: {module_name}.{symbol_name}")


class RuntimeBuilderWakeGatePreferenceTests(unittest.TestCase):
    def test_prefers_dedicated_openwakeword_when_explicitly_requested(self) -> None:
        builder = _BuilderProbe()
        voice_input = _DummyVoiceInput()
        voice_input_status = RuntimeBackendStatus(
            component="voice_input",
            ok=True,
            selected_backend="faster_whisper",
            requested_backend="faster_whisper",
            runtime_mode="speech_to_text",
        )

        backend, status = builder._build_wake_gate(
            {
                "enabled": True,
                "wake_engine": "openwakeword",
                "single_capture_mode": True,
                "wake_prefer_dedicated_gate": True,
                "wake_channel_mode": "mono_mix",
                "wake_channel_index": 0,
            },
            voice_input=voice_input,
            voice_input_status=voice_input_status,
        )

        self.assertIsInstance(backend, _FakeOpenWakeWordGate)
        self.assertTrue(status.ok)
        self.assertEqual(status.selected_backend, "openwakeword")
        self.assertEqual(status.runtime_mode, "dedicated_wake_gate")
        self.assertEqual(backend.kwargs["wake_channel_mode"], "mono_mix")
        self.assertEqual(backend.kwargs["wake_channel_index"], 0)

    def test_keeps_compatibility_gate_when_dedicated_is_not_preferred(self) -> None:
        builder = _BuilderProbe()
        voice_input = _DummyVoiceInput()
        voice_input_status = RuntimeBackendStatus(
            component="voice_input",
            ok=True,
            selected_backend="faster_whisper",
            requested_backend="faster_whisper",
            runtime_mode="speech_to_text",
        )

        _, status = builder._build_wake_gate(
            {
                "enabled": True,
                "wake_engine": "openwakeword",
                "single_capture_mode": True,
                "wake_prefer_dedicated_gate": False,
            },
            voice_input=voice_input,
            voice_input_status=voice_input_status,
        )

        self.assertTrue(status.ok)
        self.assertEqual(status.selected_backend, "compatibility_voice_input")
        self.assertEqual(status.runtime_mode, "single_capture_compatibility")


if __name__ == "__main__":
    unittest.main()