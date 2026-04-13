from __future__ import annotations

from types import SimpleNamespace

from modules.devices.audio.input.shared.device_selector import (
    resolve_input_device_selection,
    resolve_supported_input_sample_rate,
)


class FakeSoundDeviceModule:
    def __init__(self, devices, default_input_index=0, supported_rates=None):
        self._devices = devices
        self.default = SimpleNamespace(device=(default_input_index, None))
        self._supported_rates = set(supported_rates or [])

    def query_devices(self):
        return self._devices

    def check_input_settings(self, *, device, channels, dtype, samplerate):
        if samplerate not in self._supported_rates:
            raise RuntimeError(f"unsupported rate {samplerate}")
        return None


def test_resolve_input_device_selection_prefers_name_match(monkeypatch):
    fake_sd = FakeSoundDeviceModule(
        devices=[
            {"name": "Dummy Output", "max_input_channels": 0, "default_samplerate": 48000},
            {"name": "USB Mic", "max_input_channels": 1, "default_samplerate": 44100},
            {"name": "reSpeaker XVF3800 4-Mic Array", "max_input_channels": 2, "default_samplerate": 16000},
        ],
        default_input_index=1,
        supported_rates={16000, 44100},
    )
    monkeypatch.setattr(
        "modules.devices.audio.input.shared.device_selector.sd",
        fake_sd,
    )

    selection = resolve_input_device_selection(
        device_index=None,
        device_name_contains="reSpeaker XVF3800",
    )

    assert selection.device == 2
    assert selection.name == "reSpeaker XVF3800 4-Mic Array"
    assert "reSpeaker XVF3800" in selection.reason


def test_resolve_input_device_selection_falls_back_from_invalid_index_to_default(monkeypatch):
    fake_sd = FakeSoundDeviceModule(
        devices=[
            {"name": "USB Mic", "max_input_channels": 1, "default_samplerate": 44100},
            {"name": "reSpeaker XVF3800 4-Mic Array", "max_input_channels": 2, "default_samplerate": 16000},
        ],
        default_input_index=1,
        supported_rates={16000, 44100},
    )
    monkeypatch.setattr(
        "modules.devices.audio.input.shared.device_selector.sd",
        fake_sd,
    )

    selection = resolve_input_device_selection(
        device_index=99,
        device_name_contains=None,
    )

    assert selection.device == 1
    assert selection.name == "reSpeaker XVF3800 4-Mic Array"
    assert selection.reason == "using current default input device"


def test_resolve_supported_input_sample_rate_uses_fallback_rate(monkeypatch):
    fake_sd = FakeSoundDeviceModule(
        devices=[
            {"name": "reSpeaker XVF3800 4-Mic Array", "max_input_channels": 2, "default_samplerate": 16000},
        ],
        default_input_index=0,
        supported_rates={44100},
    )
    monkeypatch.setattr(
        "modules.devices.audio.input.shared.device_selector.sd",
        fake_sd,
    )

    rate = resolve_supported_input_sample_rate(
        device=0,
        device_name="reSpeaker XVF3800 4-Mic Array",
        channels=1,
        dtype="int16",
        preferred_sample_rate=16000,
        default_sample_rate=16000,
        logger=None,
        context_label="test-backend",
    )

    assert rate == 44100