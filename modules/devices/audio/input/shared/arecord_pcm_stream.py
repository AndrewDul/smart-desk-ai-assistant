from __future__ import annotations

import queue
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np


_ALSA_DEVICE_PREFIX = "alsa:"


@dataclass(slots=True)
class ArecordInputCandidate:
    """ALSA capture device selected from arecord output."""

    device: str
    name: str
    default_sample_rate: int
    summary: str


def is_arecord_device(device: object) -> bool:
    """Return True when a runtime device is an ALSA arecord-backed device."""

    return isinstance(device, str) and device.startswith(_ALSA_DEVICE_PREFIX)


def unwrap_arecord_device(device: str) -> str:
    """Strip the internal ALSA marker from a device name."""

    return device[len(_ALSA_DEVICE_PREFIX) :] if device.startswith(_ALSA_DEVICE_PREFIX) else device


def detect_preferred_arecord_input(
    preferred_name: str | None = None,
) -> ArecordInputCandidate | None:
    """Detect a capture device using arecord when PortAudio reports no inputs.

    This fallback is intentionally narrow: it only uses ALSA capture devices
    listed by arecord and prefers names matching the configured microphone.
    """

    if shutil.which("arecord") is None:
        return None

    try:
        result = subprocess.run(
            ["arecord", "-l"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3.0,
        )
    except Exception:
        return None

    output = (result.stdout or "") + "\n" + (result.stderr or "")
    candidates = _parse_arecord_capture_devices(output)
    if not candidates:
        return None

    wanted = str(preferred_name or "").strip().lower()
    if wanted:
        for candidate in candidates:
            if wanted in candidate.name.lower():
                return candidate

    preferred_keywords = ("xvf3800", "respeaker", "mic", "microphone", "array", "usb")
    for keyword in preferred_keywords:
        for candidate in candidates:
            if keyword in candidate.name.lower():
                return candidate

    return candidates[0]


def _parse_arecord_capture_devices(output: str) -> list[ArecordInputCandidate]:
    candidates: list[ArecordInputCandidate] = []
    summary_parts: list[str] = []
    pattern = re.compile(
        r"^card\s+(?P<card_index>\d+):\s+(?P<card_id>[^\s]+)\s+\[(?P<card_name>[^\]]+)\],\s+"
        r"device\s+(?P<device_index>\d+):\s+(?P<device_name>[^\[]+)(?:\[(?P<device_label>[^\]]+)\])?",
        re.IGNORECASE,
    )

    for raw_line in output.splitlines():
        line = raw_line.strip()
        match = pattern.match(line)
        if match is None:
            continue

        card_id = match.group("card_id").strip()
        card_name = match.group("card_name").strip()
        device_index = match.group("device_index").strip()
        device_name = match.group("device_name").strip().rstrip(",")
        alsa_pcm = f"plughw:CARD={card_id},DEV={device_index}"
        display_name = f"{card_name}, {device_name}".strip().strip(",")
        device = f"{_ALSA_DEVICE_PREFIX}{alsa_pcm}"
        summary_parts.append(f"{display_name} ({alsa_pcm})")
        candidates.append(
            ArecordInputCandidate(
                device=device,
                name=display_name,
                default_sample_rate=16000,
                summary="; ".join(summary_parts),
            )
        )

    final_summary = "; ".join(summary_parts) if summary_parts else "none"
    return [
        ArecordInputCandidate(
            device=candidate.device,
            name=candidate.name,
            default_sample_rate=candidate.default_sample_rate,
            summary=final_summary,
        )
        for candidate in candidates
    ]


class ArecordInputStream:
    """Small InputStream-compatible wrapper around arecord raw PCM capture."""

    def __init__(
        self,
        *,
        samplerate: int,
        blocksize: int,
        device: str,
        channels: int,
        dtype: str,
        callback: Callable[[np.ndarray, int, dict[str, float], str], None],
    ) -> None:
        if dtype != "int16":
            raise ValueError("ArecordInputStream currently supports dtype='int16' only.")
        self.samplerate = max(1, int(samplerate))
        self.blocksize = max(1, int(blocksize))
        self.device = unwrap_arecord_device(str(device))
        self.channels = max(1, int(channels))
        self.dtype = dtype
        self.callback = callback
        self._process: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._errors: queue.Queue[str] = queue.Queue(maxsize=4)

    def start(self) -> None:
        if self._process is not None:
            return
        command = [
            "arecord",
            "-q",
            "-D",
            self.device,
            "-f",
            "S16_LE",
            "-r",
            str(self.samplerate),
            "-c",
            str(self.channels),
            "-t",
            "raw",
            "-",
        ]
        self._stop_event.clear()
        self._process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._thread = threading.Thread(
            target=self._reader_loop,
            name="nexa-arecord-input-stream",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        process = self._process
        self._process = None
        if process is not None:
            try:
                process.terminate()
                process.wait(timeout=1.0)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

    def close(self) -> None:
        self.stop()

    def _reader_loop(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return

        bytes_per_frame = 2 * self.channels
        chunk_size = self.blocksize * bytes_per_frame

        while not self._stop_event.is_set():
            try:
                chunk = process.stdout.read(chunk_size)
            except Exception as error:
                self._record_error(f"read_failed:{type(error).__name__}:{error}")
                break

            if not chunk:
                if process.poll() is not None:
                    stderr = b""
                    if process.stderr is not None:
                        try:
                            stderr = process.stderr.read() or b""
                        except Exception:
                            stderr = b""
                    message = stderr.decode("utf-8", errors="replace").strip()
                    self._record_error(message or f"arecord exited with {process.returncode}")
                    break
                continue

            usable = len(chunk) - (len(chunk) % bytes_per_frame)
            if usable <= 0:
                continue

            array = np.frombuffer(chunk[:usable], dtype=np.int16)
            frames = int(array.size // self.channels)
            if frames <= 0:
                continue
            array = array.reshape(frames, self.channels)
            try:
                self.callback(array.copy(), frames, {}, "")
            except Exception as error:
                self._record_error(f"callback_failed:{type(error).__name__}:{error}")

    def _record_error(self, message: str) -> None:
        if not message:
            return
        try:
            self._errors.put_nowait(message)
        except queue.Full:
            pass


def open_input_stream(
    *,
    samplerate: int,
    blocksize: int,
    device: int | str | None,
    channels: int,
    dtype: str,
    callback: Callable[[np.ndarray, int, Any, Any], None],
) -> Any:
    """Open either a PortAudio stream or the ALSA arecord fallback stream."""

    if is_arecord_device(device):
        return ArecordInputStream(
            samplerate=samplerate,
            blocksize=blocksize,
            device=str(device),
            channels=channels,
            dtype=dtype,
            callback=callback,
        )

    import sounddevice as sd

    return sd.InputStream(
        samplerate=samplerate,
        blocksize=blocksize,
        device=device,
        channels=channels,
        dtype=dtype,
        callback=callback,
    )


__all__ = [
    "ArecordInputCandidate",
    "ArecordInputStream",
    "detect_preferred_arecord_input",
    "is_arecord_device",
    "open_input_stream",
    "unwrap_arecord_device",
]
