from __future__ import annotations

import unittest

from modules.runtime.builder.wake_gate_mixin import RuntimeBuilderWakeGateMixin
from modules.runtime.contracts import RuntimeBackendStatus


class _DummyVoiceInput:
    pass


class _FakeOpenWakeWordGate:
    def __init__(self, **kwargs) -> None:
        self.kwargs = dict(kwargs)


class _WakeGateBuilderProbe(RuntimeBuilderWakeGateMixin):
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
        raise AssertionError(f"Unexpected import request: {module_name}.{symbol_name}")


class RuntimeBuilderWakeGateMixinTests(unittest.TestCase):
    def test_prefers_dedicated_openwakeword_gate_when_enabled_in_single_capture_mode(self) -> None:
        builder = _WakeGateBuilderProbe()
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
                "wake_model_path": "models/wake/nexa.onnx",
                "device_index": 1,
                "sample_rate": 16000,
            },
            voice_input=voice_input,
            voice_input_status=voice_input_status,
        )

        self.assertIsInstance(backend, _FakeOpenWakeWordGate)
        self.assertTrue(status.ok)
        self.assertEqual(status.selected_backend, "openwakeword")
        self.assertEqual(status.runtime_mode, "dedicated_wake_gate")
        self.assertFalse(status.fallback_used)

    def test_can_force_compatibility_gate_even_when_voice_input_is_ready(self) -> None:
        builder = _WakeGateBuilderProbe()
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
                "wake_prefer_dedicated_gate": False,
            },
            voice_input=voice_input,
            voice_input_status=voice_input_status,
        )

        self.assertEqual(backend.__class__.__name__, "CompatibilityWakeGate")
        self.assertTrue(status.ok)
        self.assertEqual(status.selected_backend, "compatibility_voice_input")
        self.assertEqual(status.runtime_mode, "single_capture_compatibility")
        self.assertFalse(status.fallback_used)


if __name__ == "__main__":
    unittest.main()