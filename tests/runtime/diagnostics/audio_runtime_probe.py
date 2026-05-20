"""
Audio runtime probe for NeXa.

Diagnoses the live audio input/output configuration to reproduce the
failure mode where OpenWakeWord reports 'input overflow' and the
microphone delivers near-silence when PipeWire is running.

Usage:
    python -m tests.runtime.diagnostics.audio_runtime_probe --duration 10
    python -m tests.runtime.diagnostics.audio_runtime_probe --duration 10 --no-save

Report saved to: var/reports/audio_runtime_probe_<timestamp>.json
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


_BASE_DIR = Path(__file__).resolve().parents[3]
_REPORTS_DIR = _BASE_DIR / "var" / "reports"


def _run(cmd: list[str], timeout: float = 4.0) -> tuple[str, str, int]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout or "", result.stderr or "", result.returncode
    except FileNotFoundError:
        return "", f"command not found: {cmd[0]}", 127
    except subprocess.TimeoutExpired:
        return "", f"timeout after {timeout}s", -1
    except Exception as exc:
        return "", str(exc), -2


def _probe_sounddevice_devices() -> dict:
    try:
        import sounddevice as sd
    except ImportError:
        return {"error": "sounddevice not installed"}

    try:
        raw = list(sd.query_devices())
    except Exception as exc:
        return {"error": str(exc)}

    devices = []
    for i, dev in enumerate(raw):
        devices.append(
            {
                "index": i,
                "name": str(dev.get("name", "")),
                "max_input_channels": int(dev.get("max_input_channels", 0) or 0),
                "max_output_channels": int(dev.get("max_output_channels", 0) or 0),
                "default_samplerate": int(
                    round(float(dev.get("default_samplerate", 0) or 0))
                ),
            }
        )

    default_input: int | None = None
    default_output: int | None = None
    try:
        dv = getattr(sd.default, "device", None)
        if isinstance(dv, (list, tuple)) and len(dv) >= 2:
            default_input = int(dv[0]) if dv[0] is not None else None
            default_output = int(dv[1]) if dv[1] is not None else None
        elif isinstance(dv, int):
            default_input = dv
    except Exception:
        pass

    return {
        "devices": devices,
        "default_input_index": default_input,
        "default_output_index": default_output,
    }


def _probe_pipewire() -> dict:
    pactl_stdout, pactl_stderr, pactl_rc = _run(["pactl", "info"])
    pw_cli_stdout, _, pw_cli_rc = _run(["pw-cli", "info", "0"])

    default_sink = ""
    default_source = ""
    for line in pactl_stdout.splitlines():
        if "Default Sink:" in line:
            default_sink = line.split(":", 1)[-1].strip()
        if "Default Source:" in line:
            default_source = line.split(":", 1)[-1].strip()

    paplay_path = shutil.which("paplay") or ""
    pw_play_path = shutil.which("pw-play") or ""
    parecord_path = shutil.which("parecord") or ""

    return {
        "pactl_available": shutil.which("pactl") is not None,
        "pactl_rc": pactl_rc,
        "default_sink": default_sink,
        "default_source": default_source,
        "paplay_available": bool(paplay_path),
        "pw_play_available": bool(pw_play_path),
        "parecord_available": bool(parecord_path),
    }


def _probe_arecord_devices() -> dict:
    stdout, stderr, rc = _run(["arecord", "-l"])
    return {
        "arecord_available": shutil.which("arecord") is not None,
        "rc": rc,
        "output": (stdout + stderr).strip()[:800],
    }


def _probe_sounddevice_input(
    device_index: int | None,
    device_name: str,
    sample_rate: int,
    channels: int,
    blocksize: int,
    capture_seconds: float,
) -> dict:
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exc:
        return {"error": str(exc)}

    captured: list[np.ndarray] = []
    overflow_count = 0
    callback_count = 0
    cap_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=200)

    def _cb(indata, frames, time_info, status):
        nonlocal overflow_count, callback_count
        callback_count += 1
        if status and "overflow" in str(status).lower():
            overflow_count += 1
        try:
            cap_queue.put_nowait(indata.copy())
        except queue.Full:
            pass

    try:
        stream = sd.InputStream(
            device=device_index,
            samplerate=sample_rate,
            channels=channels,
            dtype="int16",
            blocksize=blocksize,
            callback=_cb,
        )
        stream.start()
        deadline = time.monotonic() + capture_seconds
        while time.monotonic() < deadline:
            time.sleep(0.05)
        stream.stop()
        stream.close()
    except Exception as exc:
        return {
            "device_index": device_index,
            "device_name": device_name,
            "error": str(exc),
            "overflow_count": overflow_count,
            "callback_count": callback_count,
        }

    while not cap_queue.empty():
        try:
            captured.append(cap_queue.get_nowait())
        except queue.Empty:
            break

    rms = 0.0
    total_samples = 0
    if captured:
        try:
            audio = np.concatenate(captured, axis=0).astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(np.square(audio))))
            total_samples = int(audio.shape[0])
        except Exception:
            rms = 0.0

    return {
        "device_index": device_index,
        "device_name": device_name,
        "sample_rate": sample_rate,
        "channels": channels,
        "blocksize": blocksize,
        "capture_seconds": capture_seconds,
        "callback_count": callback_count,
        "overflow_count": overflow_count,
        "total_samples": total_samples,
        "rms": round(rms, 6),
        "rms_int16_scale": round(rms * 32768, 2),
        "signal_ok": rms > 0.005,
        "warning": (
            "RMS near silence — microphone may be delivering empty audio. "
            "On PipeWire systems the PortAudio hw: device path is owned by PipeWire. "
            "Set voice_input.wake_alsa_device='plughw:CARD=Array,DEV=0' to fix."
            if rms < 0.005 else ""
        ),
    }


def _probe_arecord_input(
    alsa_device: str,
    sample_rate: int,
    channels: int,
    capture_seconds: float,
) -> dict:
    if not shutil.which("arecord"):
        return {"error": "arecord not available"}

    try:
        import numpy as np
    except ImportError:
        return {"error": "numpy not available"}

    cmd = [
        "arecord",
        "-q",
        "-D", alsa_device,
        "-f", "S16_LE",
        "-r", str(sample_rate),
        "-c", str(channels),
        "-t", "raw",
        "-d", str(int(capture_seconds) + 1),
        "-",
    ]

    started_at = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        raw_chunks: list[bytes] = []
        chunk_size = int(sample_rate * channels * 2 * capture_seconds) + 4096

        def _reader():
            assert proc.stdout is not None
            data = proc.stdout.read(chunk_size)
            if data:
                raw_chunks.append(data)

        reader_thread = threading.Thread(target=_reader, daemon=True)
        reader_thread.start()
        reader_thread.join(timeout=capture_seconds + 2.0)
        elapsed = time.monotonic() - started_at
        proc.terminate()
        try:
            proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            proc.kill()

        stderr_text = ""
        if proc.stderr:
            try:
                stderr_text = proc.stderr.read(200).decode("utf-8", errors="replace").strip()
            except Exception:
                pass

        raw = b"".join(raw_chunks)
        if not raw:
            return {
                "alsa_device": alsa_device,
                "error": f"no data captured; stderr={stderr_text!r}",
                "elapsed": round(elapsed, 2),
            }

        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(np.square(audio))))
        return {
            "alsa_device": alsa_device,
            "sample_rate": sample_rate,
            "channels": channels,
            "capture_seconds": capture_seconds,
            "bytes_captured": len(raw),
            "total_samples": len(audio),
            "rms": round(rms, 6),
            "rms_int16_scale": round(rms * 32768, 2),
            "signal_ok": rms > 0.005,
            "elapsed": round(elapsed, 2),
            "stderr": stderr_text,
        }
    except Exception as exc:
        return {"alsa_device": alsa_device, "error": str(exc)}


def _probe_playback_backends() -> dict:
    backends: dict[str, str | bool] = {}
    for name, cmd in [
        ("pw-play", "pw-play"),
        ("paplay", "paplay"),
        ("aplay", "aplay"),
        ("ffplay", "ffplay"),
    ]:
        path = shutil.which(cmd)
        backends[name] = path or False
    return backends


def _probe_playback_test(preferred_backend: str) -> dict:
    import tempfile
    import wave

    try:
        import numpy as np
    except ImportError:
        return {"error": "numpy not available"}

    sample_rate = 22050
    duration_s = 0.3
    freq = 440.0
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    tone = (np.sin(2 * np.pi * freq * t) * 16000).astype(np.int16)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(tone.tobytes())

        results: dict[str, dict] = {}
        for backend_name, cmd_base in [
            ("paplay", ["paplay"]),
            ("pw-play", ["pw-play"]),
            ("aplay", ["aplay"]),
        ]:
            path = shutil.which(cmd_base[0])
            if not path:
                results[backend_name] = {"available": False}
                continue
            stdout, stderr, rc = _run([path, tmp_path], timeout=5.0)
            results[backend_name] = {
                "available": True,
                "rc": rc,
                "success": rc == 0,
                "stderr": stderr.strip()[:200],
            }

        return {
            "preferred_backend": preferred_backend,
            "test_wav": tmp_path,
            "backends_tested": results,
            "recommendation": (
                "paplay routes through PipeWire to default sink (USB speaker). "
                "Set voice_output.preferred_playback_backend='paplay' in config/settings.json."
            ),
        }
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _load_voice_config() -> tuple[dict, dict]:
    cfg_path = _BASE_DIR / "config" / "settings.json"
    try:
        with open(cfg_path) as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    return cfg.get("voice_input", {}), cfg.get("voice_output", {})


def _detect_best_arecord_device(preferred_name_contains: str | None = None) -> str:
    """Return the best plughw: ALSA capture device path found via arecord -l."""
    try:
        from modules.devices.audio.input.shared.arecord_pcm_stream import (
            detect_preferred_arecord_input,
        )
        candidate = detect_preferred_arecord_input(preferred_name_contains)
        if candidate:
            # Strip the alsa: prefix to get the raw ALSA device string
            device = candidate.device
            if device.startswith("alsa:"):
                device = device[len("alsa:"):]
            return device
    except Exception:
        pass
    return "plughw:CARD=Array,DEV=0"


def run_probe(duration: float = 10.0) -> dict:
    print("[audio_runtime_probe] Starting — this may take up to", int(duration + 10), "seconds")

    voice_input_cfg, voice_output_cfg = _load_voice_config()

    device_index = voice_input_cfg.get("device_index")
    device_name_contains = voice_input_cfg.get("device_name_contains") or ""
    wake_alsa_device = voice_input_cfg.get("wake_alsa_device") or ""
    sample_rate = int(voice_input_cfg.get("sample_rate", 16000))
    blocksize = int(voice_input_cfg.get("blocksize", 512))
    preferred_playback_backend = voice_output_cfg.get("preferred_playback_backend", "aplay")

    print("[audio_runtime_probe] Querying sounddevice devices...")
    sd_info = _probe_sounddevice_devices()

    print("[audio_runtime_probe] Querying PipeWire status...")
    pw_info = _probe_pipewire()

    print("[audio_runtime_probe] Querying arecord devices...")
    arecord_info = _probe_arecord_devices()

    # Resolve which device NeXa would actually select
    resolved_device_index: int | None = None
    resolved_device_name: str = "unknown"
    for dev in sd_info.get("devices", []):
        if dev["max_input_channels"] > 0:
            name_lower = dev["name"].lower()
            if device_name_contains and device_name_contains.lower() in name_lower:
                resolved_device_index = dev["index"]
                resolved_device_name = dev["name"]
                break

    if resolved_device_index is None and device_index is not None:
        resolved_device_index = int(device_index)
        for dev in sd_info.get("devices", []):
            if dev["index"] == resolved_device_index:
                resolved_device_name = dev["name"]
                break

    capture_seconds = min(5.0, max(2.0, duration / 2))

    print(
        f"[audio_runtime_probe] Testing sounddevice input: device={resolved_device_index} "
        f"name={resolved_device_name!r} sample_rate={sample_rate}Hz"
    )
    sd_input_result = _probe_sounddevice_input(
        device_index=resolved_device_index,
        device_name=resolved_device_name,
        sample_rate=sample_rate,
        channels=1,
        blocksize=blocksize,
        capture_seconds=capture_seconds,
    )

    # Test the arecord / ALSA path.
    # Auto-detect the correct ALSA card ID via arecord -l when no explicit device is configured.
    # The sounddevice name contains "XVF3800" but the ALSA card short-id is "Array", so
    # plughw:CARD=Array,DEV=0 is the correct path (not plughw:CARD=XVF3800,DEV=0).
    if wake_alsa_device:
        test_alsa_device = wake_alsa_device
    else:
        test_alsa_device = _detect_best_arecord_device(device_name_contains)
    print(f"[audio_runtime_probe] Testing arecord path: {test_alsa_device}")
    arecord_input_result = _probe_arecord_input(
        alsa_device=test_alsa_device,
        sample_rate=sample_rate,
        channels=1,
        capture_seconds=capture_seconds,
    )

    print("[audio_runtime_probe] Probing playback backends...")
    playback_backends = _probe_playback_backends()
    playback_test = _probe_playback_test(preferred_playback_backend)

    # Diagnosis
    diagnosis: list[str] = []
    sd_rms = sd_input_result.get("rms", 0.0)
    arecord_rms = arecord_input_result.get("rms", 0.0)
    sd_overflow = sd_input_result.get("overflow_count", 0)

    if isinstance(sd_rms, float) and sd_rms < 0.005:
        diagnosis.append(
            "INPUT: sounddevice path gives near-silence (RMS={:.4f}). "
            "Root cause: PipeWire owns the USB mic; PortAudio hw: access gets empty audio. "
            "FIX: set voice_input.wake_alsa_device='plughw:CARD=Array,DEV=0'.".format(sd_rms)
        )
    if sd_overflow > 0:
        diagnosis.append(
            f"INPUT: {sd_overflow} PortAudio overflow(s) in {capture_seconds}s. "
            "Root cause: PipeWire quantum/PortAudio blocksize mismatch. "
            "FIX: use arecord path via wake_alsa_device."
        )
    if isinstance(arecord_rms, float) and arecord_rms > 0.005:
        diagnosis.append(
            f"INPUT: arecord path has good signal (RMS={arecord_rms:.4f}). "
            "Confirms wake_alsa_device fix will work."
        )
    elif "error" in arecord_input_result:
        diagnosis.append(
            f"INPUT: arecord path error: {arecord_input_result['error']}"
        )

    if preferred_playback_backend == "aplay":
        diagnosis.append(
            "OUTPUT: preferred_playback_backend='aplay' routes to ALSA default card "
            "which may NOT be the USB speaker (card 3). "
            "FIX: set voice_output.preferred_playback_backend='paplay' to route "
            "through PipeWire to the configured default sink (USB speaker)."
        )
    if not playback_backends.get("paplay"):
        diagnosis.append("OUTPUT: paplay not available — install pulseaudio-utils.")

    report = {
        "timestamp": datetime.datetime.now().isoformat(),
        "duration_seconds": duration,
        "voice_input_config": {
            "device_index": device_index,
            "device_name_contains": device_name_contains,
            "wake_alsa_device": wake_alsa_device,
            "sample_rate": sample_rate,
            "blocksize": blocksize,
        },
        "voice_output_config": {
            "preferred_playback_backend": preferred_playback_backend,
        },
        "sounddevice_devices": sd_info,
        "pipewire_status": pw_info,
        "arecord_devices": arecord_info,
        "resolved_input_device": {
            "index": resolved_device_index,
            "name": resolved_device_name,
        },
        "sounddevice_input_test": sd_input_result,
        "arecord_input_test": arecord_input_result,
        "playback_backends": playback_backends,
        "playback_test": playback_test,
        "diagnosis": diagnosis,
    }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="NeXa audio runtime probe")
    parser.add_argument("--duration", type=float, default=10.0, help="Capture duration in seconds")
    parser.add_argument("--no-save", action="store_true", help="Do not save JSON report")
    args = parser.parse_args()

    # Ensure project root on sys.path
    project_root = str(_BASE_DIR)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    report = run_probe(duration=args.duration)

    print("\n--- DIAGNOSIS ---")
    if report["diagnosis"]:
        for item in report["diagnosis"]:
            print(f"  * {item}")
    else:
        print("  No issues detected.")

    print("\n--- SUMMARY ---")
    sd_test = report["sounddevice_input_test"]
    ar_test = report["arecord_input_test"]
    print(f"  sounddevice RMS : {sd_test.get('rms', 'n/a')}  overflows={sd_test.get('overflow_count', 0)}")
    print(f"  arecord RMS     : {ar_test.get('rms', 'n/a')}")
    print(f"  PipeWire sink   : {report['pipewire_status'].get('default_sink', 'unknown')}")
    print(f"  PipeWire source : {report['pipewire_status'].get('default_source', 'unknown')}")
    print(f"  paplay available: {report['playback_backends'].get('paplay', False)}")
    print(f"  pw-play available: {report['playback_backends'].get('pw-play', False)}")

    if not args.no_save:
        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = _REPORTS_DIR / f"audio_runtime_probe_{ts}.json"
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n  Report saved: {out_path}")


if __name__ == "__main__":
    main()
