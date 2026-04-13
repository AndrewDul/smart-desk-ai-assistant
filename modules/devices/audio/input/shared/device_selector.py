from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

try:
    import sounddevice as sd
except Exception:  # pragma: no cover - runtime dependency available on target device
    sd = None


def _require_sounddevice() -> None:
    if sd is None:
        raise RuntimeError(
            "sounddevice is not available. Install the audio runtime dependency before using input device selection."
        )


@dataclass(slots=True)
class InputDeviceSelection:
    device: int | str | None
    name: str
    default_sample_rate: int
    reason: str
    available_inputs_summary: str


_PREFERRED_INPUT_KEYWORDS = (
    "xvf3800",
    "respeaker",
    "mic array",
    "microphone",
    "usb pnp",
    "seeed",
    "usb",
)


def resolve_input_device_selection(
    *,
    device_index: int | None,
    device_name_contains: str | None,
    discovery_timeout_seconds: float = 0.0,
    discovery_poll_seconds: float = 0.35,
) -> InputDeviceSelection:
    _require_sounddevice()

    timeout_seconds = max(0.0, float(discovery_timeout_seconds or 0.0))
    poll_seconds = max(0.05, float(discovery_poll_seconds or 0.35))
    deadline = time.monotonic() + timeout_seconds

    last_summary = "none"
    last_missing_reason = "No input audio devices are available."
    last_input_candidates: list[dict[str, Any]] = []
    preferred_missing = False

    while True:
        devices = list(sd.query_devices())
        input_candidates = [
            _candidate_from_raw(index, raw_device)
            for index, raw_device in enumerate(devices)
            if _has_input_channels(raw_device)
        ]

        last_input_candidates = input_candidates
        summary = _summarize_candidates(input_candidates)
        last_summary = summary

        if input_candidates:
            if device_name_contains:
                wanted = str(device_name_contains).strip().lower()
                for candidate in input_candidates:
                    if wanted in candidate["normalized_name"]:
                        return _selection_from_candidate(
                            candidate,
                            reason=f"matched device_name_contains='{device_name_contains}'",
                            summary=summary,
                        )

                preferred_missing = True
                last_missing_reason = (
                    f"Input device containing '{device_name_contains}' was not found. "
                    f"Available input devices: {summary}"
                )
            else:
                if device_index is not None:
                    validated = _validate_explicit_index(device_index, devices)
                    if validated is not None:
                        return _selection_from_candidate(
                            validated,
                            reason=f"validated explicit device_index={int(device_index)}",
                            summary=summary,
                        )

                default_candidate = _resolve_default_input_candidate(input_candidates)
                if default_candidate is not None:
                    return _selection_from_candidate(
                        default_candidate,
                        reason="using current default input device",
                        summary=summary,
                    )

                heuristic_candidate = _resolve_heuristic_candidate(input_candidates)
                if heuristic_candidate is not None:
                    return _selection_from_candidate(
                        heuristic_candidate,
                        reason="selected preferred input device by heuristic",
                        summary=summary,
                    )

                return _selection_from_candidate(
                    input_candidates[0],
                    reason="falling back to the first available input device",
                    summary=summary,
                )
        else:
            last_missing_reason = "No input audio devices are available."

        if time.monotonic() >= deadline:
            break

        time.sleep(min(poll_seconds, max(0.0, deadline - time.monotonic())))

    if last_input_candidates:
        if device_index is not None:
            validated = _validate_explicit_index(device_index, list(sd.query_devices()))
            if validated is not None:
                return _selection_from_candidate(
                    validated,
                    reason=(
                        f"preferred name '{device_name_contains}' was unavailable after "
                        f"{timeout_seconds:.1f}s; using validated explicit device_index={int(device_index)}"
                    ),
                    summary=last_summary,
                )

        default_candidate = _resolve_default_input_candidate(last_input_candidates)
        if default_candidate is not None:
            return _selection_from_candidate(
                default_candidate,
                reason=(
                    f"preferred name '{device_name_contains}' was unavailable after "
                    f"{timeout_seconds:.1f}s; using current default input device"
                    if preferred_missing and device_name_contains
                    else "using current default input device"
                ),
                summary=last_summary,
            )

        heuristic_candidate = _resolve_heuristic_candidate(last_input_candidates)
        if heuristic_candidate is not None:
            return _selection_from_candidate(
                heuristic_candidate,
                reason=(
                    f"preferred name '{device_name_contains}' was unavailable after "
                    f"{timeout_seconds:.1f}s; selected preferred input device by heuristic"
                    if preferred_missing and device_name_contains
                    else "selected preferred input device by heuristic"
                ),
                summary=last_summary,
            )

        return _selection_from_candidate(
            last_input_candidates[0],
            reason=(
                f"preferred name '{device_name_contains}' was unavailable after "
                f"{timeout_seconds:.1f}s; falling back to the first available input device"
                if preferred_missing and device_name_contains
                else "falling back to the first available input device"
            ),
            summary=last_summary,
        )

    if timeout_seconds > 0.0:
        raise RuntimeError(
            f"{last_missing_reason} Waited {timeout_seconds:.1f}s for audio input discovery. "
            f"Last visible inputs: {last_summary}"
        )

    raise RuntimeError(last_missing_reason)


def resolve_supported_input_sample_rate(
    *,
    device: int | str | None,
    device_name: str,
    channels: int,
    dtype: str,
    preferred_sample_rate: int | None,
    default_sample_rate: int,
    logger: logging.Logger | None = None,
    context_label: str = "audio input",
) -> int:
    _require_sounddevice()
    candidates = _build_rate_candidates(
        preferred_sample_rate=preferred_sample_rate,
        default_sample_rate=default_sample_rate,
    )
    failures: list[str] = []

    for rate in candidates:
        try:
            sd.check_input_settings(
                device=device,
                channels=channels,
                dtype=dtype,
                samplerate=rate,
            )
            if preferred_sample_rate and int(rate) != int(preferred_sample_rate) and logger is not None:
                logger.warning(
                    "%s sample rate fallback: requested=%s, selected=%s, device='%s'",
                    context_label,
                    int(preferred_sample_rate),
                    rate,
                    device_name,
                )
            return int(rate)
        except Exception as error:
            failures.append(f"{rate}Hz -> {error}")

    failure_summary = "; ".join(failures) if failures else "no candidate rates were tested"
    raise RuntimeError(
        f"No supported sample rate found for {context_label} on device '{device_name}'. "
        f"Tried rates: {candidates}. Failures: {failure_summary}"
    )


def _build_rate_candidates(*, preferred_sample_rate: int | None, default_sample_rate: int) -> list[int]:
    candidates: list[int] = []
    if preferred_sample_rate:
        candidates.append(int(preferred_sample_rate))
    candidates.extend([int(default_sample_rate), 16000, 32000, 44100, 48000])

    seen: set[int] = set()
    unique_candidates: list[int] = []
    for rate in candidates:
        if rate <= 0 or rate in seen:
            continue
        unique_candidates.append(rate)
        seen.add(rate)
    return unique_candidates


def _validate_explicit_index(device_index: int, devices: list[Any]) -> dict[str, Any] | None:
    try:
        index = int(device_index)
    except (TypeError, ValueError):
        return None

    if index < 0 or index >= len(devices):
        return None

    raw_device = devices[index]
    if not _has_input_channels(raw_device):
        return None

    return _candidate_from_raw(index, raw_device)


def _resolve_default_input_candidate(input_candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    default_device = getattr(sd, "default", None)
    default_value = getattr(default_device, "device", None)
    default_input_index: int | None = None

    if isinstance(default_value, (list, tuple)) and default_value:
        try:
            default_input_index = int(default_value[0])
        except (TypeError, ValueError):
            default_input_index = None
    elif isinstance(default_value, int):
        default_input_index = default_value

    if default_input_index is None or default_input_index < 0:
        return None

    for candidate in input_candidates:
        if int(candidate["index"]) == default_input_index:
            return candidate
    return None


def _resolve_heuristic_candidate(input_candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    scored: list[tuple[tuple[int, int, str], dict[str, Any]]] = []

    for candidate in input_candidates:
        normalized_name = str(candidate["normalized_name"])
        keyword_score = sum(1 for keyword in _PREFERRED_INPUT_KEYWORDS if keyword in normalized_name)
        channel_score = int(candidate["max_input_channels"])
        scored.append(((keyword_score, channel_score, normalized_name), candidate))

    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return None

    best_score, best_candidate = scored[0]
    if best_score[0] <= 0:
        return None
    return best_candidate


def _selection_from_candidate(
    candidate: dict[str, Any],
    *,
    reason: str,
    summary: str,
) -> InputDeviceSelection:
    return InputDeviceSelection(
        device=int(candidate["index"]),
        name=str(candidate["name"]),
        default_sample_rate=int(candidate["default_sample_rate"]),
        reason=reason,
        available_inputs_summary=summary,
    )


def _candidate_from_raw(index: int, raw_device: Any) -> dict[str, Any]:
    name = str(raw_device.get("name", f"Device {index}"))
    max_input_channels = int(raw_device.get("max_input_channels", 0) or 0)
    default_sample_rate = int(round(float(raw_device.get("default_samplerate", 16000) or 16000)))
    normalized_name = name.strip().lower()

    return {
        "index": int(index),
        "name": name,
        "normalized_name": normalized_name,
        "max_input_channels": max_input_channels,
        "default_sample_rate": default_sample_rate,
    }


def _has_input_channels(raw_device: Any) -> bool:
    try:
        return int(raw_device.get("max_input_channels", 0) or 0) > 0
    except Exception:
        return False


def _summarize_candidates(input_candidates: list[dict[str, Any]]) -> str:
    if not input_candidates:
        return "none"

    parts: list[str] = []
    for candidate in input_candidates:
        parts.append(
            f"{candidate['index']}:{candidate['name']}[{candidate['max_input_channels']}ch@{candidate['default_sample_rate']}Hz]"
        )
    return "; ".join(parts)