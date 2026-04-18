from __future__ import annotations

import inspect
import time
from typing import Any

from modules.runtime.contracts import InputSource, TranscriptRequest, TranscriptResult


class SpeechRecognitionService:
    """
    Stable STT orchestration layer for NeXa 2.0.

    Responsibilities:
    - expose one consistent transcript API over multiple backend styles
    - prefer the rich TranscriptRequest -> TranscriptResult contract when available
    - normalize compatibility backends returning plain strings
    - provide explicit command and conversation transcription policies

    This service does not own microphone lifecycle. It only orchestrates calls
    against the currently selected input backend.
    """

    def __init__(
        self,
        *,
        backend: Any,
        backend_label: str | None = None,
    ) -> None:
        self.backend = backend
        self.backend_label = str(backend_label or "").strip()

    def transcribe(self, request: TranscriptRequest) -> TranscriptResult | None:
        if self.backend is None:
            return None

        source = request.source if isinstance(request.source, InputSource) else self._default_input_source()
        started_at = time.monotonic()
        backend_label = self._backend_label()

        transcribe_method = getattr(self.backend, "transcribe", None)
        if callable(transcribe_method):
            result = transcribe_method(request)
            return self._normalize_result(
                result,
                source=source,
                started_at=started_at,
                mode=str(request.mode or "command").strip() or "command",
                backend_label=backend_label,
                adapter_label="service_rich_contract",
            )

        for method_name in self._compatibility_method_order(str(request.mode or "command")):
            method = getattr(self.backend, method_name, None)
            if not callable(method):
                continue

            result = self._call_with_supported_kwargs(
                method,
                timeout=float(request.timeout_seconds),
                debug=bool(request.debug),
            )
            return self._normalize_result(
                result,
                source=source,
                started_at=started_at,
                mode=str(request.mode or "command").strip() or "command",
                backend_label=backend_label,
                adapter_label="service_compatibility",
            )

        return None

    def transcribe_command(
        self,
        *,
        timeout_seconds: float = 8.0,
        debug: bool = False,
        source: InputSource | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptResult | None:
        return self.transcribe(
            TranscriptRequest(
                timeout_seconds=float(timeout_seconds),
                debug=bool(debug),
                source=source if isinstance(source, InputSource) else self._default_input_source(),
                mode="command",
                metadata=dict(metadata or {}),
            )
        )

    def transcribe_conversation(
        self,
        *,
        timeout_seconds: float = 12.0,
        debug: bool = False,
        source: InputSource | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TranscriptResult | None:
        return self.transcribe(
            TranscriptRequest(
                timeout_seconds=float(timeout_seconds),
                debug=bool(debug),
                source=source if isinstance(source, InputSource) else self._default_input_source(),
                mode="conversation",
                metadata=dict(metadata or {}),
            )
        )

    def supports_rich_contract(self) -> bool:
        return callable(getattr(self.backend, "transcribe", None))

    def _backend_label(self) -> str:
        if self.backend_label:
            return self.backend_label
        if self.backend is None:
            return "unknown"
        return self.backend.__class__.__name__

    def _default_input_source(self) -> InputSource:
        class_name = self._backend_label().lower()
        if "textinput" in class_name:
            return InputSource.TEXT
        return InputSource.VOICE

    @staticmethod
    def _compatibility_method_order(mode: str) -> tuple[str, ...]:
        normalized = str(mode or "command").strip().lower()
        if normalized == "command":
            return ("listen_for_command", "listen_once", "listen")
        return ("listen", "listen_once", "listen_for_command")

    @staticmethod
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

    @staticmethod
    def _normalize_result(
        result: Any,
        *,
        source: InputSource,
        started_at: float,
        mode: str,
        backend_label: str,
        adapter_label: str,
    ) -> TranscriptResult | None:
        ended_at = time.monotonic()

        if isinstance(result, TranscriptResult):
            text = str(result.text or "").strip()
            if not text:
                return None

            metadata = dict(result.metadata or {})
            metadata.setdefault("mode", mode)
            metadata.setdefault("backend_label", backend_label)
            metadata.setdefault("adapter", adapter_label)

            return TranscriptResult(
                text=text,
                language=str(result.language or "auto").strip() or "auto",
                confidence=float(result.confidence or 0.0),
                is_final=bool(result.is_final),
                source=result.source if isinstance(result.source, InputSource) else source,
                started_at=float(result.started_at or started_at),
                ended_at=float(result.ended_at or ended_at),
                metadata=metadata,
            )

        text = str(result or "").strip()
        if not text:
            return None

        return TranscriptResult(
            text=text,
            language="auto",
            confidence=0.0,
            is_final=True,
            source=source,
            started_at=started_at,
            ended_at=ended_at,
            metadata={
                "mode": mode,
                "backend_label": backend_label,
                "adapter": adapter_label,
            },
        )


__all__ = ["SpeechRecognitionService"]