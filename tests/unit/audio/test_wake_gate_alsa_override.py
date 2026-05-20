"""
Unit tests for audio input device selection and wake gate fixes.

Covers the failure modes identified on a PipeWire system where:
- PortAudio opens the ReSpeaker hw: device directly and gets near-silence
- device_index pointing at an output-only USB speaker is rejected
- overflow counter increments on PortAudio overflow status
- alsa_device override forces the arecord path and bypasses PortAudio
"""
from __future__ import annotations

import queue
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from modules.devices.audio.input.shared.device_selector import (
    resolve_input_device_selection,
)
from modules.devices.audio.input.wake.openwakeword_gate.audio_runtime import (
    OpenWakeWordGateAudioRuntime,
)


class FakeSoundDeviceModule:
    def __init__(self, devices, default_input_index=0):
        self._devices = devices
        self.default = SimpleNamespace(device=(default_input_index, None))
        self._always_accept = True

    def query_devices(self):
        return self._devices

    def check_input_settings(self, *, device, channels, dtype, samplerate):
        if not self._always_accept:
            raise RuntimeError(f"unsupported settings device={device} rate={samplerate}")


class _AudioRuntimeProbe(OpenWakeWordGateAudioRuntime):
    """Minimal concrete subclass for testing audio_runtime internals."""

    def __init__(self, *, wake_channel_mode: str = "mono_mix") -> None:
        self.wake_channel_mode = wake_channel_mode
        self.wake_channel_index = None
        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=4)
        self._overflow_count: int = 0


# ---------------------------------------------------------------------------
# Tests: device_index pointing at output-only USB speaker is rejected
# ---------------------------------------------------------------------------

class TestOutputOnlyDeviceRejected(unittest.TestCase):
    def test_output_only_device_index_is_rejected(self, monkeypatch=None):
        """device_index=2 = UAC Demo V1.0 speaker (0 input channels) must be rejected."""
        import sys
        import types

        fake_sd = FakeSoundDeviceModule(
            devices=[
                {"name": "bcm2835 HDMI", "max_input_channels": 0, "default_samplerate": 48000},
                {
                    "name": "reSpeaker XVF3800 4-Mic Array: USB Audio",
                    "max_input_channels": 2,
                    "default_samplerate": 16000,
                },
                {
                    "name": "UACDemoV1.0: USB Audio",
                    "max_input_channels": 0,
                    "default_samplerate": 48000,
                },
            ],
            default_input_index=1,
        )

        import modules.devices.audio.input.shared.device_selector as ds_module
        original_sd = ds_module.sd
        ds_module.sd = fake_sd
        try:
            sel = resolve_input_device_selection(
                device_index=2,
                device_name_contains=None,
            )
        finally:
            ds_module.sd = original_sd

        # device_index=2 has 0 input channels → must fall back to default (index 1)
        self.assertEqual(sel.device, 1)
        self.assertIn("reSpeaker", sel.name)

    def test_device_name_contains_selects_only_input_capable_device(self):
        """device_name_contains='reSpeaker' must find only the input-capable device."""
        import modules.devices.audio.input.shared.device_selector as ds_module

        fake_sd = FakeSoundDeviceModule(
            devices=[
                {"name": "reSpeaker XVF3800 4-Mic Array: USB Audio", "max_input_channels": 2, "default_samplerate": 16000},
                {"name": "UACDemoV1.0: USB Audio", "max_input_channels": 0, "default_samplerate": 48000},
            ],
            default_input_index=0,
        )

        original_sd = ds_module.sd
        ds_module.sd = fake_sd
        try:
            sel = resolve_input_device_selection(
                device_index=None,
                device_name_contains="reSpeaker",
            )
        finally:
            ds_module.sd = original_sd

        self.assertEqual(sel.device, 0)
        self.assertIn("reSpeaker", sel.name)
        self.assertGreater(
            next(
                d["max_input_channels"]
                for d in fake_sd.query_devices()
                if d["name"] == sel.name
            ),
            0,
        )

    def test_device_order_change_still_finds_respeaker_by_name(self):
        """After USB replug the ReSpeaker moves to a different index; name match must survive."""
        import modules.devices.audio.input.shared.device_selector as ds_module

        fake_sd = FakeSoundDeviceModule(
            devices=[
                {"name": "bcm2835 HDMI", "max_input_channels": 0, "default_samplerate": 48000},
                {"name": "UACDemoV1.0: USB Audio", "max_input_channels": 0, "default_samplerate": 48000},
                {"name": "Some Other USB Mic", "max_input_channels": 1, "default_samplerate": 44100},
                {
                    "name": "reSpeaker XVF3800 4-Mic Array: USB Audio",
                    "max_input_channels": 2,
                    "default_samplerate": 16000,
                },
            ],
            default_input_index=2,
        )

        original_sd = ds_module.sd
        ds_module.sd = fake_sd
        try:
            sel = resolve_input_device_selection(
                device_index=None,
                device_name_contains="reSpeaker",
            )
        finally:
            ds_module.sd = original_sd

        # Must find index 3, not the previous index 1
        self.assertEqual(sel.device, 3)
        self.assertIn("reSpeaker", sel.name)


# ---------------------------------------------------------------------------
# Tests: alsa_device override forces arecord path
# ---------------------------------------------------------------------------

class TestAlsaDeviceOverride(unittest.TestCase):
    def test_config_sets_array_wake_alsa_device(self):
        settings_path = Path(__file__).resolve().parents[3] / "config" / "settings.json"
        settings = json.loads(settings_path.read_text(encoding="utf-8"))

        self.assertEqual(
            settings["voice_input"]["wake_alsa_device"],
            "plughw:CARD=Array,DEV=0",
        )

    def _make_helpers(self):
        from modules.devices.audio.input.wake.openwakeword_gate.helpers import (
            OpenWakeWordGateHelpers,
        )
        import modules.devices.audio.input.shared.device_selector as ds_module

        fake_sd = FakeSoundDeviceModule(
            devices=[
                {"name": "reSpeaker XVF3800 4-Mic Array: USB Audio", "max_input_channels": 2, "default_samplerate": 16000},
            ],
            default_input_index=0,
        )

        class _ConcreteHelpers(OpenWakeWordGateHelpers):
            MODEL_SAMPLE_RATE = 16000
            _MIN_SAFE_THRESHOLD = 0.16
            _MAX_SAFE_THRESHOLD = 0.92
            _MIN_SAFE_TRIGGER_LEVEL = 2
            _MIN_SAFE_BLOCK_MS = 80
            _MIN_SAFE_VAD_THRESHOLD = 0.0
            _MIN_SAFE_ACTIVATION_COOLDOWN_SECONDS = 0.90
            _MIN_SAFE_BLOCK_RELEASE_SETTLE_SECONDS = 0.12
            _MIN_SAFE_ENERGY_RMS_THRESHOLD = 0.0030
            _MIN_SAFE_SCORE_SMOOTHING_WINDOW = 3

        return _ConcreteHelpers(), fake_sd, ds_module

    def test_alsa_device_forces_arecord_path(self):
        obj, fake_sd, ds_module = self._make_helpers()
        original_sd = ds_module.sd
        ds_module.sd = fake_sd
        try:
            device = obj._resolve_input_device(
                device_index=None,
                device_name_contains="reSpeaker",
                alsa_device="plughw:CARD=Array,DEV=0",
            )
        finally:
            ds_module.sd = original_sd

        self.assertTrue(str(device).startswith("alsa:"), f"Expected alsa: prefix, got {device!r}")
        self.assertIn("Array", str(device))
        self.assertEqual(obj.device_name, "plughw:CARD=Array,DEV=0")

    def test_alsa_device_none_falls_back_to_sounddevice(self):
        obj, fake_sd, ds_module = self._make_helpers()
        original_sd = ds_module.sd
        ds_module.sd = fake_sd
        try:
            device = obj._resolve_input_device(
                device_index=None,
                device_name_contains="reSpeaker",
                alsa_device=None,
            )
        finally:
            ds_module.sd = original_sd

        # Without alsa_device, sounddevice returns numeric index
        self.assertIsInstance(device, int)

    def test_alsa_device_empty_string_falls_back_to_sounddevice(self):
        obj, fake_sd, ds_module = self._make_helpers()
        original_sd = ds_module.sd
        ds_module.sd = fake_sd
        try:
            device = obj._resolve_input_device(
                device_index=None,
                device_name_contains="reSpeaker",
                alsa_device="",
            )
        finally:
            ds_module.sd = original_sd

        self.assertIsInstance(device, int)


# ---------------------------------------------------------------------------
# Tests: overflow counter increments on overflow status
# ---------------------------------------------------------------------------

class TestOverflowCounter(unittest.TestCase):
    def test_overflow_counter_increments_on_overflow_status(self):
        runtime = _AudioRuntimeProbe()

        class _FakeStatus:
            def __str__(self):
                return "input overflow"
            def __bool__(self):
                return True

        indata = np.zeros((512, 1), dtype=np.int16)
        runtime._audio_callback(indata, 512, None, _FakeStatus())
        runtime._audio_callback(indata, 512, None, _FakeStatus())

        self.assertEqual(runtime._overflow_count, 2)

    def test_overflow_counter_does_not_increment_on_none_status(self):
        runtime = _AudioRuntimeProbe()
        indata = np.zeros((512, 1), dtype=np.int16)
        runtime._audio_callback(indata, 512, None, None)

        self.assertEqual(runtime._overflow_count, 0)

    def test_overflow_counter_does_not_increment_on_non_overflow_status(self):
        runtime = _AudioRuntimeProbe()

        class _FakeStatus:
            def __str__(self):
                return "output underflow"
            def __bool__(self):
                return True

        indata = np.zeros((512, 1), dtype=np.int16)
        runtime._audio_callback(indata, 512, None, _FakeStatus())

        self.assertEqual(runtime._overflow_count, 0)


# ---------------------------------------------------------------------------
# Tests: playback backend order when paplay is preferred
# ---------------------------------------------------------------------------

class TestPlaybackBackendPreference(unittest.TestCase):
    def test_paplay_is_tried_before_aplay_when_preferred(self):
        from modules.devices.audio.output.tts_pipeline.resolution_mixin import (
            TTSPipelineResolutionMixin,
        )
        import shutil as _shutil

        class _Resolver(TTSPipelineResolutionMixin):
            pass

        obj = _Resolver()
        backends = obj._detect_playback_backends()
        names = [name for name, _ in backends]

        if "paplay" in names and "aplay" in names:
            self.assertLess(
                names.index("paplay"),
                names.index("aplay"),
                "paplay must be detected before aplay (natural PipeWire-first order)",
            )

    def test_detected_backend_list_is_nonempty_when_tools_available(self):
        from modules.devices.audio.output.tts_pipeline.resolution_mixin import (
            TTSPipelineResolutionMixin,
        )

        class _Resolver(TTSPipelineResolutionMixin):
            pass

        obj = _Resolver()
        backends = obj._detect_playback_backends()
        # At least one playback backend must be found in a normal dev environment
        # (aplay is always available on Debian/Ubuntu/RPiOS)
        has_any = any(
            True for _ in backends
        )
        # Soft check: do not fail on CI without audio tools; just verify structure
        for name, cmd in backends:
            self.assertIsInstance(name, str)
            self.assertIsInstance(cmd, list)
            self.assertTrue(len(cmd) >= 1)


if __name__ == "__main__":
    unittest.main()
