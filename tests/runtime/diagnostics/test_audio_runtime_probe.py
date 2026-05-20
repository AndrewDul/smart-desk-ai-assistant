from __future__ import annotations

from tests.runtime.diagnostics import audio_runtime_probe


def test_sounddevice_silence_warning_recommends_array_alsa_card(monkeypatch) -> None:
    class _FakeNumpy:
        int16 = "int16"
        float32 = "float32"

        @staticmethod
        def concatenate(chunks, axis=0):
            del axis
            return chunks[0]

        @staticmethod
        def sqrt(value):
            return value

        @staticmethod
        def mean(value):
            return value

        @staticmethod
        def square(value):
            return value

    class _FakeAudio:
        shape = (16000, 1)

        def copy(self):
            return self

        def astype(self, dtype):
            del dtype
            return self

        def __truediv__(self, other):
            del other
            return 0.0

    class _FakeInputStream:
        def __init__(self, **kwargs):
            self.callback = kwargs["callback"]

        def start(self):
            self.callback(_FakeAudio(), 16000, None, None)

        def stop(self):
            return None

        def close(self):
            return None

    class _FakeSoundDevice:
        InputStream = _FakeInputStream

    monkeypatch.setitem(__import__("sys").modules, "numpy", _FakeNumpy)
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", _FakeSoundDevice)

    result = audio_runtime_probe._probe_sounddevice_input(
        device_index=1,
        device_name="reSpeaker XVF3800 4-Mic Array",
        sample_rate=16000,
        channels=1,
        blocksize=1024,
        capture_seconds=0.01,
    )

    assert "plughw:CARD=Array,DEV=0" in result["warning"]
    assert "XVF3800,DEV=0" not in result["warning"]


def test_diagnosis_recommends_array_alsa_card(monkeypatch) -> None:
    monkeypatch.setattr(audio_runtime_probe, "_load_voice_config", lambda: (
        {
            "device_index": None,
            "device_name_contains": "reSpeaker",
            "wake_alsa_device": "plughw:CARD=Array,DEV=0",
            "sample_rate": 16000,
            "blocksize": 1024,
        },
        {"preferred_playback_backend": "paplay"},
    ))
    monkeypatch.setattr(
        audio_runtime_probe,
        "_probe_sounddevice_devices",
        lambda: {
            "devices": [
                {
                    "index": 1,
                    "name": "reSpeaker XVF3800 4-Mic Array",
                    "max_input_channels": 2,
                }
            ]
        },
    )
    monkeypatch.setattr(audio_runtime_probe, "_probe_pipewire", lambda: {})
    monkeypatch.setattr(audio_runtime_probe, "_probe_arecord_devices", lambda: {})
    monkeypatch.setattr(
        audio_runtime_probe,
        "_probe_sounddevice_input",
        lambda **kwargs: {"rms": 0.0, "overflow_count": 0},
    )
    monkeypatch.setattr(
        audio_runtime_probe,
        "_probe_arecord_input",
        lambda **kwargs: {"rms": 0.01},
    )
    monkeypatch.setattr(audio_runtime_probe, "_probe_playback_backends", lambda: {"paplay": True})
    monkeypatch.setattr(audio_runtime_probe, "_probe_playback_test", lambda preferred_backend: {})

    report = audio_runtime_probe.run_probe(duration=0.01)
    diagnosis = "\n".join(report["diagnosis"])

    assert "plughw:CARD=Array,DEV=0" in diagnosis
    assert "XVF3800,DEV=0" not in diagnosis
