from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
import importlib
import time
from pathlib import Path
from typing import Any


VOSK_MODEL_PROBE_STAGE = "vosk_model_loading_probe"
VOSK_MODEL_PROBE_VERSION = "stage_24y_v1"

DEFAULT_VOSK_MODEL_PATHS: tuple[Path, ...] = (
    Path("models/vosk/vosk-model-small-en-us-0.15"),
    Path("models/vosk/vosk-model-small-pl-0.22"),
    Path("models/vosk/en"),
    Path("models/vosk/pl"),
    Path("var/models/vosk/vosk-model-small-en-us-0.15"),
    Path("var/models/vosk/vosk-model-small-pl-0.22"),
    Path("var/models/vosk/en"),
    Path("var/models/vosk/pl"),
)

REQUIRED_MODEL_MARKERS: tuple[str, ...] = (
    "am/final.mdl",
    "conf/model.conf",
)

ModelLoader = Callable[[Path], object]


@dataclass(frozen=True, slots=True)
class VoskModelProbeResult:
    model_path: str
    exists: bool
    is_directory: bool
    marker_status: dict[str, bool]
    structure_ready: bool
    load_requested: bool
    load_attempted: bool
    load_success: bool
    load_elapsed_ms: float | None = None
    load_error: str = ""
    reason: str = ""
    action_executed: bool = False
    full_stt_prevented: bool = False
    runtime_takeover: bool = False
    microphone_stream_started: bool = False
    command_recognition_attempted: bool = False
    raw_pcm_included: bool = False

    def __post_init__(self) -> None:
        if self.action_executed:
            raise ValueError("Vosk model probe must never execute actions")
        if self.full_stt_prevented:
            raise ValueError("Vosk model probe must never prevent full STT")
        if self.runtime_takeover:
            raise ValueError("Vosk model probe must never take over runtime")
        if self.microphone_stream_started:
            raise ValueError("Vosk model probe must never start a microphone stream")
        if self.command_recognition_attempted:
            raise ValueError("Vosk model probe must never attempt command recognition")
        if self.raw_pcm_included:
            raise ValueError("Vosk model probe telemetry must not include raw PCM")
        if self.load_success and not self.load_attempted:
            raise ValueError("Vosk model cannot load successfully without load attempt")
        object.__setattr__(self, "marker_status", dict(self.marker_status))

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "exists": self.exists,
            "is_directory": self.is_directory,
            "marker_status": dict(self.marker_status),
            "structure_ready": self.structure_ready,
            "load_requested": self.load_requested,
            "load_attempted": self.load_attempted,
            "load_success": self.load_success,
            "load_elapsed_ms": self.load_elapsed_ms,
            "load_error": self.load_error,
            "reason": self.reason,
            "action_executed": self.action_executed,
            "full_stt_prevented": self.full_stt_prevented,
            "runtime_takeover": self.runtime_takeover,
            "microphone_stream_started": self.microphone_stream_started,
            "command_recognition_attempted": self.command_recognition_attempted,
            "raw_pcm_included": self.raw_pcm_included,
        }


def probe_vosk_model(
    *,
    model_path: Path,
    load_model: bool = False,
    model_loader: ModelLoader | None = None,
) -> VoskModelProbeResult:
    resolved_model_path = Path(model_path)
    exists = resolved_model_path.exists()
    is_directory = resolved_model_path.is_dir()
    marker_status = {
        marker: (resolved_model_path / marker).exists()
        for marker in REQUIRED_MODEL_MARKERS
    }
    structure_ready = bool(
        exists
        and is_directory
        and all(marker_status.values())
    )

    if not exists:
        return VoskModelProbeResult(
            model_path=str(resolved_model_path),
            exists=False,
            is_directory=False,
            marker_status=marker_status,
            structure_ready=False,
            load_requested=load_model,
            load_attempted=False,
            load_success=False,
            reason="model_path_missing",
        )

    if not is_directory:
        return VoskModelProbeResult(
            model_path=str(resolved_model_path),
            exists=True,
            is_directory=False,
            marker_status=marker_status,
            structure_ready=False,
            load_requested=load_model,
            load_attempted=False,
            load_success=False,
            reason="model_path_not_directory",
        )

    if not structure_ready:
        return VoskModelProbeResult(
            model_path=str(resolved_model_path),
            exists=True,
            is_directory=True,
            marker_status=marker_status,
            structure_ready=False,
            load_requested=load_model,
            load_attempted=False,
            load_success=False,
            reason="model_structure_incomplete",
        )

    if not load_model:
        return VoskModelProbeResult(
            model_path=str(resolved_model_path),
            exists=True,
            is_directory=True,
            marker_status=marker_status,
            structure_ready=True,
            load_requested=False,
            load_attempted=False,
            load_success=False,
            reason="model_structure_ready_load_not_requested",
        )

    loader = model_loader or _load_vosk_model
    started = time.perf_counter()

    try:
        loader(resolved_model_path)
    except Exception as error:  # pragma: no cover - exact Vosk errors are platform-specific.
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return VoskModelProbeResult(
            model_path=str(resolved_model_path),
            exists=True,
            is_directory=True,
            marker_status=marker_status,
            structure_ready=True,
            load_requested=True,
            load_attempted=True,
            load_success=False,
            load_elapsed_ms=round(elapsed_ms, 3),
            load_error=f"{type(error).__name__}:{error}",
            reason="model_load_failed",
        )

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return VoskModelProbeResult(
        model_path=str(resolved_model_path),
        exists=True,
        is_directory=True,
        marker_status=marker_status,
        structure_ready=True,
        load_requested=True,
        load_attempted=True,
        load_success=True,
        load_elapsed_ms=round(elapsed_ms, 3),
        reason="model_loaded",
    )


def probe_vosk_models(
    *,
    model_paths: Iterable[Path] | None = None,
    load_model: bool = False,
    require_model_present: bool = False,
    require_loadable: bool = False,
    model_loader: ModelLoader | None = None,
) -> dict[str, Any]:
    paths = tuple(model_paths or DEFAULT_VOSK_MODEL_PATHS)
    results = [
        probe_vosk_model(
            model_path=path,
            load_model=load_model,
            model_loader=model_loader,
        )
        for path in paths
    ]

    present_model_records = sum(
        1 for result in results if result.exists and result.is_directory
    )
    structure_ready_records = sum(1 for result in results if result.structure_ready)
    load_attempted_records = sum(1 for result in results if result.load_attempted)
    load_success_records = sum(1 for result in results if result.load_success)

    unsafe_action_records = sum(1 for result in results if result.action_executed)
    unsafe_full_stt_records = sum(
        1 for result in results if result.full_stt_prevented
    )
    unsafe_takeover_records = sum(1 for result in results if result.runtime_takeover)
    microphone_stream_records = sum(
        1 for result in results if result.microphone_stream_started
    )
    command_recognition_records = sum(
        1 for result in results if result.command_recognition_attempted
    )
    raw_pcm_records = sum(1 for result in results if result.raw_pcm_included)

    issues: list[str] = []

    if require_model_present and present_model_records <= 0:
        issues.append("vosk_model_present_records_missing")

    if require_loadable and load_success_records <= 0:
        issues.append("vosk_model_load_success_records_missing")

    if require_loadable and not load_model:
        issues.append("require_loadable_without_load_model")

    if unsafe_action_records > 0:
        issues.append("unsafe_action_records_present")
    if unsafe_full_stt_records > 0:
        issues.append("unsafe_full_stt_records_present")
    if unsafe_takeover_records > 0:
        issues.append("unsafe_takeover_records_present")
    if microphone_stream_records > 0:
        issues.append("microphone_stream_records_present")
    if command_recognition_records > 0:
        issues.append("command_recognition_records_present")
    if raw_pcm_records > 0:
        issues.append("raw_pcm_records_present")

    loadable_paths = [
        result.model_path
        for result in results
        if result.load_success
    ]
    structure_ready_paths = [
        result.model_path
        for result in results
        if result.structure_ready
    ]

    return {
        "accepted": not issues,
        "probe_stage": VOSK_MODEL_PROBE_STAGE,
        "probe_version": VOSK_MODEL_PROBE_VERSION,
        "model_path_count": len(paths),
        "present_model_records": present_model_records,
        "structure_ready_records": structure_ready_records,
        "load_requested": load_model,
        "load_attempted_records": load_attempted_records,
        "load_success_records": load_success_records,
        "require_model_present": require_model_present,
        "require_loadable": require_loadable,
        "structure_ready_paths": structure_ready_paths,
        "loadable_paths": loadable_paths,
        "unsafe_action_records": unsafe_action_records,
        "unsafe_full_stt_records": unsafe_full_stt_records,
        "unsafe_takeover_records": unsafe_takeover_records,
        "microphone_stream_records": microphone_stream_records,
        "command_recognition_records": command_recognition_records,
        "raw_pcm_records": raw_pcm_records,
        "results": [result.to_json_dict() for result in results],
        "issues": issues,
    }


def _load_vosk_model(model_path: Path) -> object:
    try:
        vosk_module = importlib.import_module("vosk")
    except ImportError as error:
        raise RuntimeError("vosk_import_failed") from error

    set_log_level = getattr(vosk_module, "SetLogLevel", None)
    if callable(set_log_level):
        set_log_level(-1)

    model_class = getattr(vosk_module, "Model", None)
    if model_class is None:
        raise RuntimeError("vosk_model_class_missing")

    return model_class(str(model_path))


__all__ = [
    "DEFAULT_VOSK_MODEL_PATHS",
    "REQUIRED_MODEL_MARKERS",
    "VOSK_MODEL_PROBE_STAGE",
    "VOSK_MODEL_PROBE_VERSION",
    "ModelLoader",
    "VoskModelProbeResult",
    "probe_vosk_model",
    "probe_vosk_models",
]