from __future__ import annotations

from tests.runtime.diagnostics.openwakeword_live_input_probe import evaluate_probe_report


def _base_report() -> dict:
    return {
        "configured_wake_alsa_device": "plughw:CARD=Array,DEV=0",
        "selected_device": "alsa:plughw:CARD=Array,DEV=0",
        "is_arecord_alsa_path": True,
        "rms_int16": 1225.0,
        "frames_above_energy_threshold": 14,
    }


def test_evaluate_probe_accepts_good_arecord_rms() -> None:
    result = evaluate_probe_report(_base_report())

    assert result["ok"] is True
    assert result["failures"] == []


def test_evaluate_probe_rejects_silent_stream() -> None:
    report = _base_report()
    report["rms_int16"] = 12.0
    report["frames_above_energy_threshold"] = 0

    result = evaluate_probe_report(report)

    assert result["ok"] is False
    assert any("rms_int16" in failure for failure in result["failures"])
    assert any("below OpenWakeWord energy threshold" in failure for failure in result["failures"])


def test_evaluate_probe_rejects_wrong_non_alsa_path() -> None:
    report = _base_report()
    report["selected_device"] = "1"
    report["is_arecord_alsa_path"] = False

    result = evaluate_probe_report(report)

    assert result["ok"] is False
    assert any("selected path is" in failure for failure in result["failures"])
    assert any("not the arecord/ALSA path" in failure for failure in result["failures"])
