from __future__ import annotations

import inspect
import time
from typing import Any

from modules.runtime.contracts import (
    InputSource,
    TranscriptRequest,
    TranscriptResult,
    WakeDetectionResult,
)


def _backend_label(backend: Any) -> str:
    return backend.__class__.__name__


def _default_input_source(backend: Any) -> InputSource:
    class_name = backend.__class__.__name__.lower()
    if "textinput" in class_name:
        return InputSource.TEXT
    return InputSource.VOICE


def _call_with_supported_kwargs(method: Any, **kwargs: Any) -> Any:
    try:
        signature = inspect.signature(method)
        supported = {
            key: value
            for key, value in kwargs.items()
            if key in signature.parameters
        }
        return method(**supported)
    except (TypeError, ValueError):
        fallback_kwargs = {}
        for key in ("timeout", "debug"):
            if key in kwargs:
                fallback_kwargs[key] = kwargs[key]
        return method(**fallback_kwargs)


def _normalize_transcript_result(
    result: Any,
    *,
    source: InputSource,
    started_at: float,
    mode: str,
    backend_label: str,
) -> TranscriptResult | None:
    ended_at = time.monotonic()

    if isinstance(result, TranscriptResult):
        metadata = dict(result.metadata)
        metadata.setdefault("mode", mode)
        metadata.setdefault("backend_label", backend_label)
        metadata.setdefault("adapter", "rich_contract")
        return TranscriptResult(
            text=result.text,
            language=result.language,
            confidence=result.confidence,
            is_final=result.is_final,
            source=result.source,
            started_at=result.started_at,
            ended_at=result.ended_at,
            metadata=metadata,
        )

    text = str(result or "").strip()
    if not text:
        return None

    return TranscriptResult(
        text=text,
        source=source,
        started_at=started_at,
        ended_at=ended_at,
        metadata={
            "mode": mode,
            "backend_label": backend_label,
            "adapter": "compatibility",
        },
    )


def _normalize_wake_result(
    result: Any,
    *,
    source: InputSource,
    started_at: float,
    backend_label: str,
) -> WakeDetectionResult | None:
    ended_at = time.monotonic()

    if isinstance(result, WakeDetectionResult):
        metadata = dict(result.metadata)
        metadata.setdefault("backend_label", backend_label)
        metadata.setdefault("adapter", "rich_contract")
        return WakeDetectionResult(
            phrase=result.phrase,
            accepted=result.accepted,
            confidence=result.confidence,
            source=result.source,
            started_at=result.started_at,
            ended_at=result.ended_at,
            metadata=metadata,
        )

    phrase = str(result or "").strip()
    if not phrase:
        return None

    return WakeDetectionResult(
        phrase=phrase,
        accepted=True,
        source=source,
        started_at=started_at,
        ended_at=ended_at,
        metadata={
            "backend_label": backend_label,
            "adapter": "compatibility",
        },
    )


def capture_transcript(
    voice_input: Any,
    *,
    timeout: float,
    debug: bool,
    mode: str = "command",
) -> TranscriptResult | None:
    if voice_input is None:
        return None

    source = _default_input_source(voice_input)
    started_at = time.monotonic()
    backend_label = _backend_label(voice_input)

    transcribe = getattr(voice_input, "transcribe", None)
    if callable(transcribe):
        request = TranscriptRequest(
            timeout_seconds=timeout,
            debug=debug,
            source=source,
            mode=mode,
            metadata={
                "backend_label": backend_label,
                "adapter": "main_loop",
            },
        )
        result = transcribe(request)
        return _normalize_transcript_result(
            result,
            source=source,
            started_at=started_at,
            mode=mode,
            backend_label=backend_label,
        )

    for method_name in ("listen", "listen_once", "listen_for_command"):
        method = getattr(voice_input, method_name, None)
        if not callable(method):
            continue

        result = _call_with_supported_kwargs(
            method,
            timeout=timeout,
            debug=debug,
        )
        return _normalize_transcript_result(
            result,
            source=source,
            started_at=started_at,
            mode=mode,
            backend_label=backend_label,
        )

    return None


def detect_wake_event(
    wake_backend: Any,
    *,
    timeout_seconds: float,
    debug: bool,
    ignore_audio_block: bool,
) -> WakeDetectionResult | None:
    if wake_backend is None:
        return None

    source = _default_input_source(wake_backend)
    started_at = time.monotonic()
    backend_label = _backend_label(wake_backend)

    detect_wake = getattr(wake_backend, "detect_wake", None)
    if callable(detect_wake):
        result = detect_wake(
            timeout_seconds=timeout_seconds,
            debug=debug,
            ignore_audio_block=ignore_audio_block,
        )
        return _normalize_wake_result(
            result,
            source=source,
            started_at=started_at,
            backend_label=backend_label,
        )

    listen_for_wake_phrase = getattr(wake_backend, "listen_for_wake_phrase", None)
    if callable(listen_for_wake_phrase):
        result = _call_with_supported_kwargs(
            listen_for_wake_phrase,
            timeout=timeout_seconds,
            debug=debug,
            ignore_audio_block=ignore_audio_block,
        )
        return _normalize_wake_result(
            result,
            source=source,
            started_at=started_at,
            backend_label=backend_label,
        )

    return None


__all__ = [
    "capture_transcript",
    "detect_wake_event",
]