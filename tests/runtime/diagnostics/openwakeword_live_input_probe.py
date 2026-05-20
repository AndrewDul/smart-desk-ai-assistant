"""
Live OpenWakeWord input probe.

Usage:
    .venv/bin/python -m tests.runtime.diagnostics.openwakeword_live_input_probe --duration 8
"""
from __future__ import annotations

import argparse
import datetime
import json
import queue
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from modules.devices.audio.input.shared.arecord_pcm_stream import is_arecord_device
from modules.devices.audio.input.wake.openwakeword_gate import OpenWakeWordGate
from modules.shared.config.settings import load_settings, reset_settings_cache


PROJECT_ROOT = Path(__file__).resolve().parents[3]
REPORTS_DIR = PROJECT_ROOT / "var" / "reports"
EXPECTED_ALSA_DEVICE = "plughw:CARD=Array,DEV=0"
MIN_SPEAKING_RMS_INT16 = 300.0


def _positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _positive_float(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0.0 else fallback


def _duration_arg(value: str) -> float:
    return _positive_float(value, 8.0)


def _build_gate(voice_input_cfg: dict[str, Any]) -> OpenWakeWordGate:
    return OpenWakeWordGate(
        model_path=voice_input_cfg.get("wake_model_path", "models/wake/nexa.onnx"),
        device_index=voice_input_cfg.get("device_index"),
        device_name_contains=voice_input_cfg.get("device_name_contains"),
        alsa_device=str(voice_input_cfg.get("wake_alsa_device") or "").strip() or None,
        threshold=float(voice_input_cfg.get("wake_threshold", 0.50)),
        trigger_level=int(voice_input_cfg.get("wake_trigger_level", 2)),
        block_ms=int(voice_input_cfg.get("wake_block_ms", 80)),
        vad_threshold=float(voice_input_cfg.get("wake_vad_threshold", 0.0)),
        enable_speex_noise_suppression=bool(
            voice_input_cfg.get("wake_enable_speex_noise_suppression", False)
        ),
        activation_cooldown_seconds=float(
            voice_input_cfg.get("wake_activation_cooldown_seconds", 1.25)
        ),
        block_release_settle_seconds=float(
            voice_input_cfg.get("wake_block_release_settle_seconds", 0.18)
        ),
        energy_rms_threshold=float(
            voice_input_cfg.get("wake_energy_rms_threshold", 0.0085)
        ),
        score_smoothing_window=int(
            voice_input_cfg.get("wake_score_smoothing_window", 3)
        ),
        wake_channel_mode=str(voice_input_cfg.get("wake_channel_mode", "mono_mix")),
        wake_channel_index=voice_input_cfg.get("wake_channel_index"),
        debug=bool(voice_input_cfg.get("wake_debug", False)),
    )


def _drain_audio_queue(gate: OpenWakeWordGate, *, duration: float) -> list[np.ndarray]:
    chunks: list[np.ndarray] = []
    deadline = time.monotonic() + max(0.1, float(duration))
    gate._ensure_stream_open()
    try:
        while time.monotonic() < deadline:
            try:
                chunk = gate.audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            chunks.append(np.asarray(chunk).astype(np.int16, copy=False).reshape(-1))
    finally:
        gate._close_stream()
    return chunks


def analyze_openwakeword_audio(
    gate: OpenWakeWordGate,
    chunks: list[np.ndarray],
) -> dict[str, Any]:
    if chunks:
        audio = np.concatenate(chunks).astype(np.int16, copy=False)
    else:
        audio = np.array([], dtype=np.int16)

    if audio.size:
        audio_f32 = audio.astype(np.float32)
        rms_int16 = float(np.sqrt(np.mean(np.square(audio_f32), dtype=np.float64)))
        peak_int16 = int(np.max(np.abs(audio.astype(np.int32))))
        normalized_rms = rms_int16 / 32768.0
    else:
        rms_int16 = 0.0
        peak_int16 = 0
        normalized_rms = 0.0

    resampled = gate._resample_to_16k(audio, gate.input_sample_rate)
    frame_size = int(gate.model_frame_samples)
    hop = int(gate.frame_hop_samples)

    frames_above_energy_threshold = 0
    frame_count = 0
    max_raw_score: float | None = None
    max_smooth_score: float | None = None
    score_error = ""

    if frame_size > 0 and hop > 0:
        gate._score_history = []
        for start in range(0, max(0, resampled.size - frame_size + 1), hop):
            frame = resampled[start : start + frame_size]
            if frame.size < frame_size:
                continue
            frame_count += 1
            if gate._frame_has_enough_energy(frame):
                frames_above_energy_threshold += 1
            try:
                raw_score = gate._extract_score(gate.model.predict(frame))
                smooth_score = gate._smoothed_score(raw_score)
            except Exception as error:
                score_error = f"{type(error).__name__}: {error}"
                break
            max_raw_score = raw_score if max_raw_score is None else max(max_raw_score, raw_score)
            max_smooth_score = (
                smooth_score
                if max_smooth_score is None
                else max(max_smooth_score, smooth_score)
            )

    return {
        "chunk_count": len(chunks),
        "sample_count": int(audio.size),
        "frame_count": frame_count,
        "rms_int16": round(rms_int16, 3),
        "peak_int16": peak_int16,
        "normalized_rms": round(normalized_rms, 6),
        "frames_above_energy_threshold": frames_above_energy_threshold,
        "energy_threshold": float(gate.energy_rms_threshold),
        "max_raw_score": None if max_raw_score is None else round(max_raw_score, 6),
        "max_smooth_score": None if max_smooth_score is None else round(max_smooth_score, 6),
        "score_error": score_error,
    }


def evaluate_probe_report(
    report: dict[str, Any],
    *,
    expected_alsa_device: str = EXPECTED_ALSA_DEVICE,
    min_speaking_rms_int16: float = MIN_SPEAKING_RMS_INT16,
) -> dict[str, Any]:
    selected_device = str(report.get("selected_device") or "")
    configured_alsa = str(report.get("configured_wake_alsa_device") or "")
    is_alsa = bool(report.get("is_arecord_alsa_path"))
    rms_int16 = float(report.get("rms_int16") or 0.0)
    frames_above = int(report.get("frames_above_energy_threshold") or 0)

    failures: list[str] = []
    if configured_alsa != expected_alsa_device:
        failures.append(
            f"config wake_alsa_device is {configured_alsa!r}, expected {expected_alsa_device!r}"
        )
    if selected_device != f"alsa:{expected_alsa_device}":
        failures.append(
            f"selected path is {selected_device!r}, expected 'alsa:{expected_alsa_device}'"
        )
    if not is_alsa:
        failures.append("selected path is not the arecord/ALSA path")
    if rms_int16 < float(min_speaking_rms_int16):
        failures.append(
            f"rms_int16={rms_int16:.1f} below speaking threshold {min_speaking_rms_int16:.1f}"
        )
    if frames_above <= 0:
        failures.append("all frames are below OpenWakeWord energy threshold")

    return {"ok": not failures, "failures": failures}


def run_probe(*, duration: float) -> dict[str, Any]:
    reset_settings_cache()
    settings = load_settings(force_reload=True)
    voice_input_cfg = settings.get("voice_input", {})
    if not isinstance(voice_input_cfg, dict):
        voice_input_cfg = {}

    wake_alsa_device = str(voice_input_cfg.get("wake_alsa_device") or "").strip()
    gate = _build_gate(voice_input_cfg)
    try:
        chunks = _drain_audio_queue(gate, duration=duration)
        analysis = analyze_openwakeword_audio(gate, chunks)
        report: dict[str, Any] = {
            "timestamp": datetime.datetime.now().isoformat(),
            "duration_seconds": float(duration),
            "configured_wake_alsa_device": wake_alsa_device,
            "selected_device": str(gate.device),
            "selected_device_name": str(gate.device_name),
            "is_arecord_alsa_path": is_arecord_device(gate.device),
            "sample_rate": int(gate.input_sample_rate),
            "channel_count": int(gate.channels),
            "wake_model_path": str(gate.model_path),
            "wake_model_name": str(gate.model_name),
            "threshold": float(gate.threshold),
            "trigger_level": int(gate.trigger_level),
            **analysis,
        }
        report["evaluation"] = evaluate_probe_report(report)
        return report
    finally:
        gate.close()


def _save_report(report: dict[str, Any]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"openwakeword_live_input_probe_{timestamp}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _print_report(report: dict[str, Any], report_path: Path) -> None:
    print("--- OPENWAKEWORD LIVE INPUT PROBE ---")
    print(f"selected device/path      : {report.get('selected_device')}")
    print(f"selected device name      : {report.get('selected_device_name')}")
    print(f"arecord/alsa path         : {report.get('is_arecord_alsa_path')}")
    print(f"sample rate               : {report.get('sample_rate')}")
    print(f"channel count             : {report.get('channel_count')}")
    print(f"frame count               : {report.get('frame_count')}")
    print(f"rms_int16                 : {report.get('rms_int16')}")
    print(f"peak_int16                : {report.get('peak_int16')}")
    print(f"normalized_rms            : {report.get('normalized_rms')}")
    print(f"frames_above_threshold    : {report.get('frames_above_energy_threshold')}")
    print(f"energy threshold          : {report.get('energy_threshold')}")
    print(f"max raw score             : {report.get('max_raw_score')}")
    print(f"max smooth score          : {report.get('max_smooth_score')}")
    if report.get("score_error"):
        print(f"score error               : {report.get('score_error')}")

    evaluation = report.get("evaluation") or {}
    if evaluation.get("ok"):
        print("evaluation                : PASS")
    else:
        print("evaluation                : FAIL")
        for failure in evaluation.get("failures", []):
            print(f"  - {failure}")
    print(f"report                    : {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe live OpenWakeWord wake input audio.")
    parser.add_argument("--duration", type=_duration_arg, default=8.0)
    args = parser.parse_args()

    try:
        report = run_probe(duration=args.duration)
    except Exception as error:
        report = {
            "timestamp": datetime.datetime.now().isoformat(),
            "duration_seconds": args.duration,
            "error": f"{type(error).__name__}: {error}",
            "evaluation": {
                "ok": False,
                "failures": [f"probe failed before audio analysis: {type(error).__name__}: {error}"],
            },
        }
        report_path = _save_report(report)
        _print_report(report, report_path)
        raise SystemExit(1) from error

    report_path = _save_report(report)
    _print_report(report, report_path)
    if not (report.get("evaluation") or {}).get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
